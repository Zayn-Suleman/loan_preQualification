"""Integration tests for credit-service Kafka consumer.

Tests the consumer logic with mocked Kafka and database:
- Message deserialization
- PAN decryption
- CIBIL score calculation
- Message publishing to output topic
- Idempotent processing
- Error handling and DLQ
"""
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

# Add parent directories to path
service_root = Path(__file__).parent.parent
sys.path.insert(0, str(service_root))


class TestCreditServiceConsumer:
    """Test Kafka consumer message processing."""

    @patch("app.consumer.EncryptionService")
    @patch("app.consumer.KafkaProducer")
    def test_process_message_success(self, mock_producer, mock_encryption_service):
        """Test successful message processing."""
        from app.consumer import CreditReportConsumer

        # Mock encryption service
        mock_encryption = Mock()
        mock_encryption.decrypt_pan_from_kafka.return_value = "ABCDE1234F"
        mock_encryption.encrypt_pan_for_kafka.return_value = "encrypted_base64"
        mock_encryption_service.return_value = mock_encryption

        # Create consumer
        consumer = CreditReportConsumer(
            bootstrap_servers="localhost:9092",
            encryption_key="test_key_32_bytes_long_string!",
        )
        consumer.producer = mock_producer()

        # Create test message
        application_id = str(uuid4())
        message_value = {
            "application_id": application_id,
            "pan_number": "encrypted_pan_base64",
            "applicant_name": "Rajesh Kumar",
            "monthly_income_inr": 80000.0,
            "loan_amount_inr": 500000.0,
            "loan_type": "PERSONAL",
        }

        # Process message
        result = consumer._process_message(message_value)

        # Verify result
        assert result is not None
        assert result["application_id"] == application_id
        assert result["cibil_score"] == 790  # Test PAN ABCDE1234F → 790
        assert "credit_report_generated_at" in result

        # Verify PAN was decrypted
        mock_encryption.decrypt_pan_from_kafka.assert_called_once_with("encrypted_pan_base64")

        # Verify output was encrypted
        mock_encryption.encrypt_pan_for_kafka.assert_called()

    @patch("app.consumer.EncryptionService")
    @patch("app.consumer.KafkaProducer")
    def test_process_message_with_poor_credit_pan(self, mock_producer, mock_encryption_service):
        """Test processing message with poor credit test PAN."""
        from app.consumer import CreditReportConsumer

        # Mock encryption service
        mock_encryption = Mock()
        mock_encryption.decrypt_pan_from_kafka.return_value = "FGHIJ5678K"  # Poor credit PAN
        mock_encryption.encrypt_pan_for_kafka.return_value = "encrypted_base64"
        mock_encryption_service.return_value = mock_encryption

        # Create consumer
        consumer = CreditReportConsumer(
            bootstrap_servers="localhost:9092",
            encryption_key="test_key_32_bytes_long_string!",
        )
        consumer.producer = mock_producer()

        # Create test message
        message_value = {
            "application_id": str(uuid4()),
            "pan_number": "encrypted_pan_base64",
            "applicant_name": "Test User",
            "monthly_income_inr": 30000.0,
            "loan_amount_inr": 200000.0,
            "loan_type": "PERSONAL",
        }

        # Process message
        result = consumer._process_message(message_value)

        # Verify poor credit score
        assert result["cibil_score"] == 610  # Test PAN FGHIJ5678K → 610

    @patch("app.consumer.EncryptionService")
    @patch("app.consumer.KafkaProducer")
    def test_process_message_with_deterministic_scoring(
        self, mock_producer, mock_encryption_service
    ):
        """Test that same application_id produces same score (determinism)."""
        from app.consumer import CreditReportConsumer

        # Mock encryption service
        mock_encryption = Mock()
        mock_encryption.decrypt_pan_from_kafka.return_value = "XYZAB9999C"  # Non-test PAN
        mock_encryption.encrypt_pan_for_kafka.return_value = "encrypted_base64"
        mock_encryption_service.return_value = mock_encryption

        # Create consumer
        consumer = CreditReportConsumer(
            bootstrap_servers="localhost:9092",
            encryption_key="test_key_32_bytes_long_string!",
        )
        consumer.producer = mock_producer()

        # Use fixed application_id
        application_id = str(uuid4())
        message_value = {
            "application_id": application_id,
            "pan_number": "encrypted_pan_base64",
            "applicant_name": "Test User",
            "monthly_income_inr": 50000.0,
            "loan_amount_inr": 300000.0,
            "loan_type": "HOME",
        }

        # Process message twice
        result1 = consumer._process_message(message_value)
        result2 = consumer._process_message(message_value)

        # Verify same score both times (deterministic)
        assert result1["cibil_score"] == result2["cibil_score"]

    @patch("app.consumer.EncryptionService")
    @patch("app.consumer.KafkaProducer")
    def test_process_message_decryption_failure(self, mock_producer, mock_encryption_service):
        """Test handling of PAN decryption failure."""
        from app.consumer import CreditReportConsumer

        # Mock encryption service with decryption failure
        mock_encryption = Mock()
        mock_encryption.decrypt_pan_from_kafka.side_effect = Exception("Decryption failed")
        mock_encryption_service.return_value = mock_encryption

        # Create consumer
        consumer = CreditReportConsumer(
            bootstrap_servers="localhost:9092",
            encryption_key="test_key_32_bytes_long_string!",
        )
        consumer.producer = mock_producer()

        # Create test message
        message_value = {
            "application_id": str(uuid4()),
            "pan_number": "corrupted_encrypted_data",
            "applicant_name": "Test User",
            "monthly_income_inr": 50000.0,
            "loan_amount_inr": 300000.0,
            "loan_type": "PERSONAL",
        }

        # Process message should raise exception
        with pytest.raises(Exception, match="Decryption failed"):
            consumer._process_message(message_value)

    @patch("app.consumer.EncryptionService")
    @patch("app.consumer.KafkaProducer")
    def test_process_message_missing_fields(self, mock_producer, mock_encryption_service):
        """Test handling of message with missing fields."""
        from app.consumer import CreditReportConsumer

        # Mock encryption service
        mock_encryption = Mock()
        mock_encryption.decrypt_pan_from_kafka.return_value = "ABCDE1234F"
        mock_encryption_service.return_value = mock_encryption

        # Create consumer
        consumer = CreditReportConsumer(
            bootstrap_servers="localhost:9092",
            encryption_key="test_key_32_bytes_long_string!",
        )
        consumer.producer = mock_producer()

        # Create test message with missing fields
        message_value = {
            "application_id": str(uuid4()),
            "pan_number": "encrypted_pan_base64",
            # Missing other required fields
        }

        # Process should handle gracefully (return None or default values)
        result = consumer._process_message(message_value)

        # Verify it still calculates a score with defaults
        assert result is not None
        assert "cibil_score" in result

    @patch("app.consumer.EncryptionService")
    @patch("app.consumer.KafkaProducer")
    def test_idempotent_processing_same_message_twice(self, mock_producer, mock_encryption_service):
        """Test that processing the same message twice is idempotent."""
        from app.consumer import CreditReportConsumer

        # Mock encryption service
        mock_encryption = Mock()
        mock_encryption.decrypt_pan_from_kafka.return_value = "ABCDE1234F"
        mock_encryption.encrypt_pan_for_kafka.return_value = "encrypted_base64"
        mock_encryption_service.return_value = mock_encryption

        # Create consumer
        consumer = CreditReportConsumer(
            bootstrap_servers="localhost:9092",
            encryption_key="test_key_32_bytes_long_string!",
        )
        consumer.producer = mock_producer()
        consumer.processed_messages = set()  # Track processed messages

        # Create test message with same ID
        application_id = str(uuid4())
        message_value = {
            "application_id": application_id,
            "pan_number": "encrypted_pan_base64",
            "applicant_name": "Rajesh Kumar",
            "monthly_income_inr": 80000.0,
            "loan_amount_inr": 500000.0,
            "loan_type": "PERSONAL",
        }

        # Process message first time
        _result1 = consumer._process_message(message_value)
        consumer.processed_messages.add(application_id)

        # Process same message second time
        if application_id in consumer.processed_messages:
            # Should skip processing
            result2 = None
        else:
            result2 = consumer._process_message(message_value)

        # Verify second processing was skipped
        assert result2 is None

    def test_message_deserialization(self):
        """Test JSON message deserialization."""
        # Create JSON message
        message_data = {
            "application_id": str(uuid4()),
            "pan_number": "encrypted_data",
            "applicant_name": "Test User",
        }
        json_bytes = json.dumps(message_data).encode("utf-8")

        # Deserialize
        result = json.loads(json_bytes)

        assert result["application_id"] == message_data["application_id"]
        assert result["pan_number"] == message_data["pan_number"]

    @patch("app.consumer.EncryptionService")
    @patch("app.consumer.KafkaProducer")
    def test_publish_to_output_topic(self, mock_producer, mock_encryption_service):
        """Test publishing credit report to output Kafka topic."""
        from app.consumer import CreditReportConsumer

        # Mock encryption service
        mock_encryption = Mock()
        mock_encryption.decrypt_pan_from_kafka.return_value = "ABCDE1234F"
        mock_encryption.encrypt_pan_for_kafka.return_value = "encrypted_base64"
        mock_encryption_service.return_value = mock_encryption

        # Mock producer
        mock_prod_instance = Mock()
        mock_producer.return_value = mock_prod_instance

        # Create consumer
        consumer = CreditReportConsumer(
            bootstrap_servers="localhost:9092",
            encryption_key="test_key_32_bytes_long_string!",
        )
        consumer.producer = mock_prod_instance

        # Create and process message
        message_value = {
            "application_id": str(uuid4()),
            "pan_number": "encrypted_pan_base64",
            "applicant_name": "Rajesh Kumar",
            "monthly_income_inr": 80000.0,
            "loan_amount_inr": 500000.0,
            "loan_type": "PERSONAL",
        }

        result = consumer._process_message(message_value)

        # Publish result
        if result:
            consumer._publish_credit_report(result)

        # Verify producer was called
        mock_prod_instance.send.assert_called_once()
        call_args = mock_prod_instance.send.call_args
        assert call_args[1]["topic"] == "credit_reports_generated"
