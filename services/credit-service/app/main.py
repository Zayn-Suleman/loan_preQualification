"""Main entry point for credit service.

This service consumes loan applications from Kafka, calculates CIBIL scores,
and publishes credit reports for the decision service.
"""
import logging
import signal
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from .consumer import CreditServiceConsumer, Settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main function to start credit service consumer."""
    logger.info("=" * 60)
    logger.info("Starting Credit Service")
    logger.info("=" * 60)

    # Load settings
    try:
        settings = Settings()
        logger.info(f"Service: {settings.service_name}")
        logger.info(f"Kafka: {settings.kafka_bootstrap_servers}")
        logger.info(f"Consumer Group: {settings.consumer_group_id}")
        logger.info(f"Input Topic: {settings.input_topic}")
        logger.info(f"Output Topic: {settings.output_topic}")
        logger.info(f"Database: {settings.database_url.split('@')[1]}")  # Hide password
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        sys.exit(1)

    # Initialize consumer
    try:
        consumer = CreditServiceConsumer(settings)
    except Exception as e:
        logger.error(f"Failed to initialize consumer: {e}", exc_info=True)
        sys.exit(1)

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        consumer.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start consuming
    logger.info("Credit service is ready to process messages")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    try:
        consumer.start()
    except Exception as e:
        logger.error(f"Consumer failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
