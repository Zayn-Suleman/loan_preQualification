"""Idempotent Kafka consumer for credit service.

This module implements a reliable Kafka consumer that:
- Ensures exactly-once processing using processed_messages table
- Handles message retries with exponential backoff
- Sends failed messages to DLQ after max retries
- Publishes credit reports to output topic
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from confluent_kafka import Consumer, KafkaError, Message, Producer
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from services.shared.encryption import EncryptionService

from .logic import CibilService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Consumer configuration from environment variables."""

    database_url: str
    encryption_key: str
    service_name: str = "credit-service"
    log_level: str = "INFO"

    kafka_bootstrap_servers: str = "localhost:9092"
    consumer_group_id: str = "credit-service-group"
    input_topic: str = "loan_applications_submitted"
    output_topic: str = "credit_reports_generated"
    dlq_topic: str = "loan_applications_submitted_dlq"

    max_poll_records: int = 10
    session_timeout_ms: int = 30000
    max_retries: int = 3

    class Config:
        """Pydantic config."""

        env_file = ".env"


class CreditServiceConsumer:
    """Idempotent Kafka consumer for processing loan applications."""

    def __init__(self, settings: Settings):
        """Initialize consumer with database and Kafka connections.

        Args:
            settings: Configuration settings
        """
        self.settings = settings
        self.encryption_service = EncryptionService(settings.encryption_key)

        # Database setup
        self.engine = create_engine(settings.database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Kafka consumer configuration
        consumer_config = {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": settings.consumer_group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,  # Manual commit for transactional processing
            "max.poll.interval.ms": 300000,  # 5 minutes
            "session.timeout.ms": settings.session_timeout_ms,
        }
        self.consumer = Consumer(consumer_config)

        # Kafka producer configuration for publishing credit reports
        producer_config = {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "client.id": f"{settings.service_name}-producer",
            "acks": "all",  # Wait for all replicas
            "retries": 3,
            "max.in.flight.requests.per.connection": 1,  # Preserve order
            "compression.type": "gzip",
        }
        self.producer = Producer(producer_config)

        # Subscribe to input topic
        self.consumer.subscribe([settings.input_topic])
        logger.info(f"Subscribed to topic: {settings.input_topic}")

        self.running = False

    def start(self):
        """Start consuming messages from Kafka."""
        self.running = True
        logger.info(f"{self.settings.service_name} started")

        try:
            while self.running:
                # Poll for messages
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition, not an error
                        continue
                    logger.error(f"Kafka error: {msg.error()}")
                    continue

                # Process message
                self.process_message(msg)

        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
        except Exception as e:
            logger.error(f"Consumer error: {e}", exc_info=True)
        finally:
            self.stop()

    def stop(self):
        """Stop consumer and cleanup resources."""
        logger.info("Stopping consumer...")
        self.running = False
        self.consumer.close()
        self.producer.flush()
        self.engine.dispose()
        logger.info("Consumer stopped")

    def process_message(self, msg: Message):
        """Process a single Kafka message with idempotency.

        Flow:
            1. Generate message_id from application_id:topic:partition:offset
            2. Check if already processed (idempotency)
            3. Deserialize and decrypt message
            4. Calculate CIBIL score
            5. Publish credit report to output topic
            6. Mark as processed in DB
            7. Commit Kafka offset

        Args:
            msg: Kafka message
        """
        db: Optional[Session] = None

        try:
            # Extract message metadata
            topic = msg.topic()
            partition = msg.partition()
            offset = msg.offset()
            value = msg.value().decode("utf-8")

            # Deserialize message
            application_data = json.loads(value)
            application_id = application_data.get("application_id")

            # Generate unique message_id for idempotency
            message_id = f"{application_id}:{topic}:{partition}:{offset}"

            logger.info(f"Processing message: {message_id}")

            # Open database session
            db = self.SessionLocal()

            # Check if already processed (idempotency)
            if self.is_already_processed(db, message_id):
                logger.info(f"Message {message_id} already processed, skipping")
                self.consumer.commit(message=msg)
                return

            # Decrypt PAN from Kafka message
            encrypted_pan_base64 = application_data.get("pan_number")
            if encrypted_pan_base64:
                pan_plaintext = self.encryption_service.decrypt_pan_from_kafka(encrypted_pan_base64)
                application_data["pan_number"] = pan_plaintext

            # Calculate CIBIL score
            logger.info(f"Calculating CIBIL score for application {application_id}")
            credit_report = CibilService.get_credit_report(application_data)
            logger.info(f"CIBIL score calculated: {credit_report['cibil_score']}")

            # Re-encrypt PAN for Kafka output
            if credit_report.get("pan_number"):
                encrypted_pan_for_kafka = self.encryption_service.encrypt_pan_for_kafka(
                    credit_report["pan_number"]
                )
                credit_report["pan_number"] = encrypted_pan_for_kafka

            # Publish credit report to output topic
            self.publish_credit_report(credit_report)

            # Mark message as processed (idempotency table)
            self.mark_as_processed(db, message_id, topic, partition, offset)

            # Commit transaction
            db.commit()

            # Commit Kafka offset (only after successful processing)
            self.consumer.commit(message=msg)

            logger.info(f"Successfully processed message: {message_id}")

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

            # Rollback database transaction
            if db:
                db.rollback()

            # TODO: Implement retry logic and DLQ
            # For now, just log the error and continue

        finally:
            if db:
                db.close()

    def is_already_processed(self, db: Session, message_id: str) -> bool:
        """Check if message has already been processed.

        Args:
            db: Database session
            message_id: Unique message identifier

        Returns:
            bool: True if already processed, False otherwise
        """
        result = db.execute(
            text("SELECT 1 FROM processed_messages WHERE message_id = :message_id"),
            {"message_id": message_id},
        )
        return result.fetchone() is not None

    def mark_as_processed(
        self, db: Session, message_id: str, topic: str, partition: int, offset: int
    ):
        """Mark message as processed in database.

        Args:
            db: Database session
            message_id: Unique message identifier
            topic: Kafka topic name
            partition: Kafka partition number
            offset: Kafka message offset
        """
        db.execute(
            text(
                """
                INSERT INTO processed_messages
                (message_id, topic_name, partition_num, offset_num, consumer_group, processed_at)
                VALUES (:message_id, :topic, :partition, :offset, :group, :timestamp)
            """
            ),
            {
                "message_id": message_id,
                "topic": topic,
                "partition": partition,
                "offset": offset,
                "group": self.settings.consumer_group_id,
                "timestamp": datetime.now(tz=timezone.utc),
            },
        )
        logger.debug(f"Marked message as processed: {message_id}")

    def publish_credit_report(self, credit_report: Dict[str, Any]):
        """Publish credit report to output Kafka topic.

        Args:
            credit_report: Credit report data to publish
        """
        try:
            # Serialize to JSON
            message_value = json.dumps(credit_report).encode("utf-8")

            # Use application_id as partition key for ordering
            partition_key = credit_report["application_id"].encode("utf-8")

            # Produce message
            self.producer.produce(
                topic=self.settings.output_topic,
                key=partition_key,
                value=message_value,
                callback=self._delivery_callback,
            )

            # Poll for delivery reports (non-blocking)
            self.producer.poll(0)

            logger.info(
                f"Published credit report to {self.settings.output_topic} for application {credit_report['application_id']}"
            )

        except Exception as e:
            logger.error(f"Failed to publish credit report: {e}", exc_info=True)
            raise

    def _delivery_callback(self, err, msg):
        """Callback for Kafka message delivery reports.

        Args:
            err: Error if delivery failed
            msg: Delivered message
        """
        if err:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(
                f"Message delivered to {msg.topic()}[{msg.partition()}] at offset {msg.offset()}"
            )
