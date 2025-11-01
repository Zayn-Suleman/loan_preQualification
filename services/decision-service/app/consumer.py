"""Idempotent Kafka consumer for decision service.

This module implements a reliable Kafka consumer that:
- Ensures exactly-once processing using processed_messages table
- Applies business rules for loan decisions
- Updates application status with optimistic locking
- Handles concurrent update conflicts with retry logic
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from confluent_kafka import Consumer, KafkaError, Message
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from services.shared.encryption import EncryptionService

from .logic import DecisionService
from .repository import ApplicationRepository, OptimisticLockError

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Consumer configuration from environment variables."""

    database_url: str
    encryption_key: str
    service_name: str = "decision-service"
    log_level: str = "INFO"

    kafka_bootstrap_servers: str = "localhost:9092"
    consumer_group_id: str = "decision-service-group"
    input_topic: str = "credit_reports_generated"
    dlq_topic: str = "credit_reports_generated_dlq"

    max_poll_records: int = 10
    session_timeout_ms: int = 30000
    max_retries: int = 3
    max_update_retries: int = 3

    class Config:
        """Pydantic config."""

        env_file = ".env"


class DecisionServiceConsumer:
    """Idempotent Kafka consumer for processing credit reports and making decisions."""

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
        self.engine.dispose()
        logger.info("Consumer stopped")

    def process_message(self, msg: Message):
        """Process a single Kafka message with idempotency.

        Flow:
            1. Generate message_id from application_id:topic:partition:offset
            2. Check if already processed (idempotency)
            3. Deserialize credit report message
            4. Fetch application data from database
            5. Apply business rules for decision
            6. Update application status with optimistic locking
            7. Mark as processed in DB
            8. Commit Kafka offset

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
            credit_report = json.loads(value)
            application_id = credit_report.get("application_id")

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

            # Extract CIBIL score from credit report
            cibil_score = credit_report.get("cibil_score")
            if cibil_score is None:
                logger.error(f"Credit report missing CIBIL score for application {application_id}")
                self.consumer.commit(message=msg)
                return

            # Fetch application from database
            repository = ApplicationRepository(db)
            application = repository.get_application_by_id(application_id)

            if not application:
                logger.error(f"Application {application_id} not found in database")
                self.consumer.commit(message=msg)
                return

            # Prepare application data for decision engine
            # Note: annual_income is stored, but we need monthly for decision
            annual_income = application.get("annual_income", 0)
            monthly_income = annual_income / 12 if annual_income else 0

            application_data = {
                "application_id": application_id,
                "monthly_income_inr": monthly_income,
                "loan_amount_inr": application.get("requested_amount", 0),
            }

            # Make decision using business rules
            logger.info(f"Evaluating application {application_id} with CIBIL score {cibil_score}")
            decision = DecisionService.make_decision(application_data, cibil_score)

            logger.info(
                f"Decision for application {application_id}: {decision['status']} - "
                f"{decision['decision_reason']}"
            )

            # Update application status with optimistic locking and retry
            repository.update_with_retry(
                application_id=application_id,
                status=decision["status"],
                cibil_score=decision["cibil_score"],
                decision_reason=decision["decision_reason"],
                max_approved_amount=decision.get("max_approved_amount"),
                max_retries=self.settings.max_update_retries,
            )

            # Mark message as processed (idempotency table)
            self.mark_as_processed(db, message_id, topic, partition, offset)

            # Commit transaction
            db.commit()

            # Commit Kafka offset (only after successful processing)
            self.consumer.commit(message=msg)

            logger.info(
                f"Successfully processed message: {message_id}, "
                f"application status: {decision['status']}"
            )

        except OptimisticLockError as e:
            logger.error(f"Optimistic lock failure after retries: {e}")
            # Rollback database transaction
            if db:
                db.rollback()
            # Do NOT commit offset - message will be reprocessed

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
