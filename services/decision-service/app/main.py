"""Main entry point for decision service.

This service consumes credit reports from Kafka, applies business rules,
and updates application status in the database.
"""
import logging
import signal
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from .consumer import DecisionServiceConsumer, Settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main function to start decision service consumer."""
    logger.info("=" * 60)
    logger.info("Starting Decision Service")
    logger.info("=" * 60)

    # Load settings
    try:
        settings = Settings()
        logger.info(f"Service: {settings.service_name}")
        logger.info(f"Kafka: {settings.kafka_bootstrap_servers}")
        logger.info(f"Consumer Group: {settings.consumer_group_id}")
        logger.info(f"Input Topic: {settings.input_topic}")
        logger.info(f"Database: {settings.database_url.split('@')[1]}")  # Hide password
        logger.info(f"Max Update Retries: {settings.max_update_retries}")
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        sys.exit(1)

    # Initialize consumer
    try:
        consumer = DecisionServiceConsumer(settings)
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
    logger.info("Decision service is ready to process credit reports")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    try:
        consumer.start()
    except Exception as e:
        logger.error(f"Consumer failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
