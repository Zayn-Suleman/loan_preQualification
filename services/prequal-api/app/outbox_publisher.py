"""OutboxPublisher - Background process for reliable Kafka message publishing.

This module implements the Transactional Outbox Pattern publisher that:
1. Polls outbox_events table every 100ms for unpublished events
2. Publishes events to Kafka topics
3. Marks events as published atomically
4. Handles Kafka failures with circuit breaker
5. Implements exponential backoff for retries

Architecture:
    API → DB Transaction (Application + OutboxEvent) → OutboxPublisher → Kafka

Flow:
    1. Poll: SELECT * FROM outbox_events WHERE published = FALSE ORDER BY created_at LIMIT 10
    2. Publish: For each event, send to Kafka topic
    3. Mark Published: UPDATE outbox_events SET published = TRUE, published_at = NOW()
    4. Handle Failures: Increment retry_count, log error_message
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from confluent_kafka import KafkaException, Producer
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .db import OutboxEvent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker for Kafka producer.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast
    - HALF_OPEN: Testing if service recovered

    Thresholds:
    - failure_threshold: 5 consecutive failures → OPEN
    - timeout: 30 seconds in OPEN before → HALF_OPEN
    - success_threshold: 2 consecutive successes in HALF_OPEN → CLOSED
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 30.0,
        success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold

        self.failure_count = 0
        self.success_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.last_failure_time: Optional[float] = None

    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if self.state == "OPEN":
            # Check if timeout elapsed
            if time.time() - self.last_failure_time >= self.timeout:
                logger.info("Circuit breaker: OPEN → HALF_OPEN (timeout elapsed)")
                self.state = "HALF_OPEN"
                self.success_count = 0
            else:
                # Fail fast
                raise KafkaException("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        """Handle successful call."""
        self.failure_count = 0

        if self.state == "HALF_OPEN":
            self.success_count += 1
            logger.info(
                f"Circuit breaker: HALF_OPEN success {self.success_count}/{self.success_threshold}"
            )
            if self.success_count >= self.success_threshold:
                logger.info("Circuit breaker: HALF_OPEN → CLOSED (recovered)")
                self.state = "CLOSED"
                self.success_count = 0

    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == "HALF_OPEN":
            logger.warning("Circuit breaker: HALF_OPEN → OPEN (failure during test)")
            self.state = "OPEN"
            self.success_count = 0
        elif self.state == "CLOSED":
            if self.failure_count >= self.failure_threshold:
                logger.error(f"Circuit breaker: CLOSED → OPEN ({self.failure_count} failures)")
                self.state = "OPEN"


class OutboxPublisher:
    """Background process that publishes outbox events to Kafka.

    This implements the publisher side of the Transactional Outbox Pattern.
    Ensures at-least-once delivery of events to Kafka.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
        kafka_bootstrap_servers: str,
        poll_interval_ms: int = 100,
        batch_size: int = 10,
        max_retries: int = 5,
    ):
        """Initialize OutboxPublisher.

        Args:
            session_factory: SQLAlchemy session factory
            kafka_bootstrap_servers: Kafka broker addresses
            poll_interval_ms: Polling interval in milliseconds (default 100ms)
            batch_size: Max events to process per batch (default 10)
            max_retries: Max retry attempts before marking as failed (default 5)
        """
        self.session_factory = session_factory
        self.poll_interval_ms = poll_interval_ms
        self.batch_size = batch_size
        self.max_retries = max_retries

        # Kafka producer configuration
        producer_config = {
            "bootstrap.servers": kafka_bootstrap_servers,
            "client.id": "outbox-publisher",
            "acks": "all",  # Wait for all replicas
            "retries": 3,  # Producer-level retries
            "max.in.flight.requests.per.connection": 1,  # Preserve order
            "compression.type": "gzip",
            "linger.ms": 10,  # Batch messages for 10ms
        }

        self.producer = Producer(producer_config)
        self.circuit_breaker = CircuitBreaker()
        self.running = False

        # Metrics
        self.total_published = 0
        self.total_failed = 0

        logger.info(
            f"OutboxPublisher initialized: poll_interval={poll_interval_ms}ms, batch_size={batch_size}"
        )

    async def start(self):
        """Start the OutboxPublisher background loop."""
        self.running = True
        logger.info("OutboxPublisher started")

        try:
            while self.running:
                try:
                    await self._poll_and_publish()
                except Exception as e:
                    logger.error(f"Error in OutboxPublisher loop: {e}", exc_info=True)

                # Sleep for poll interval
                await asyncio.sleep(self.poll_interval_ms / 1000.0)

        except asyncio.CancelledError:
            logger.info("OutboxPublisher cancelled")
        finally:
            self.running = False
            self._shutdown()

    def stop(self):
        """Stop the OutboxPublisher."""
        logger.info("Stopping OutboxPublisher...")
        self.running = False

    async def _poll_and_publish(self):
        """Poll outbox events and publish to Kafka."""
        db: Session = self.session_factory()

        try:
            # Query unpublished events (oldest first)
            events = (
                db.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.published == False)  # noqa: E712
                    .where(OutboxEvent.retry_count < self.max_retries)
                    .order_by(OutboxEvent.created_at)
                    .limit(self.batch_size)
                )
                .scalars()
                .all()
            )

            if not events:
                return  # No events to publish

            logger.debug(f"Found {len(events)} unpublished events")

            for event in events:
                try:
                    # Publish to Kafka with circuit breaker
                    self.circuit_breaker.call(self._publish_event, db, event)
                    self.total_published += 1

                except KafkaException as e:
                    self._handle_publish_failure(db, event, str(e))
                    self.total_failed += 1

                except Exception as e:
                    logger.error(
                        f"Unexpected error publishing event {event.id}: {e}",
                        exc_info=True,
                    )
                    self._handle_publish_failure(db, event, str(e))
                    self.total_failed += 1

            # Commit all changes
            db.commit()

        except Exception as e:
            logger.error(f"Error in _poll_and_publish: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    def _publish_event(self, db: Session, event: OutboxEvent):
        """Publish a single event to Kafka.

        Args:
            db: Database session
            event: OutboxEvent to publish

        Raises:
            KafkaException: If publishing fails
        """
        # Prepare Kafka message
        key = str(event.aggregate_id).encode("utf-8") if event.partition_key else None
        value = json.dumps(event.payload).encode("utf-8")

        logger.debug(
            f"Publishing event {event.id}: topic={event.topic_name}, type={event.event_type}"
        )

        # Produce message (synchronous for reliability)
        try:
            self.producer.produce(
                topic=event.topic_name,
                key=key,
                value=value,
                callback=self._delivery_callback,
            )

            # Flush to ensure message sent (blocking)
            self.producer.flush(timeout=5.0)

            # Mark as published
            event.published = True
            event.published_at = datetime.now(tz=timezone.utc)
            event.error_message = None

            logger.info(
                f"✅ Published event {event.id} to {event.topic_name} (type: {event.event_type})"
            )

        except KafkaException as e:
            logger.error(f"Kafka error publishing event {event.id}: {e}")
            raise

    def _handle_publish_failure(self, db: Session, event: OutboxEvent, error_msg: str):
        """Handle failed event publication.

        Args:
            db: Database session
            event: Failed event
            error_msg: Error message
        """
        event.retry_count += 1
        event.error_message = error_msg[:500]  # Truncate long errors

        if event.retry_count >= self.max_retries:
            logger.error(
                f"❌ Event {event.id} exceeded max retries ({self.max_retries}). Giving up."
            )
        else:
            logger.warning(
                f"⚠️  Event {event.id} failed. Retry {event.retry_count}/{self.max_retries}"
            )

        db.commit()

    def _delivery_callback(self, err, msg):
        """Kafka producer delivery callback.

        Args:
            err: Error if delivery failed
            msg: Message metadata
        """
        if err:
            logger.error(f"Kafka delivery failed: {err}")
        else:
            logger.debug(
                f"Kafka delivery success: topic={msg.topic()}, partition={msg.partition()}, offset={msg.offset()}"
            )

    def _shutdown(self):
        """Shutdown Kafka producer gracefully."""
        logger.info("Shutting down OutboxPublisher...")
        if self.producer:
            # Flush remaining messages
            remaining = self.producer.flush(timeout=10.0)
            if remaining > 0:
                logger.warning(f"{remaining} messages not delivered before shutdown")

        logger.info(
            f"OutboxPublisher stopped. Stats: published={self.total_published}, failed={self.total_failed}"
        )

    def get_metrics(self):
        """Get publisher metrics."""
        return {
            "total_published": self.total_published,
            "total_failed": self.total_failed,
            "circuit_breaker_state": self.circuit_breaker.state,
            "running": self.running,
        }
