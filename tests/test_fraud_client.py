"""
Tests for fraud detection client integration
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch
import httpx

from core_banking.fraud_client import BastionClient, MockBastionClient, FraudScore
from core_banking.currency import Money, Currency
from core_banking.transactions import TransactionProcessor, TransactionType, TransactionChannel, TransactionState


class TestFraudScore:
    """Test FraudScore data class"""
    
    def test_fraud_score_creation(self):
        """Test FraudScore creation"""
        score = FraudScore(
            score=0.75,
            decision="REVIEW",
            risk_level="HIGH",
            reasons=["large_amount", "unusual_pattern"],
            latency_ms=150.5
        )
        
        assert score.score == 0.75
        assert score.decision == "REVIEW"
        assert score.risk_level == "HIGH"
        assert score.reasons == ["large_amount", "unusual_pattern"]
        assert score.latency_ms == 150.5


class TestMockBastionClient:
    """Test MockBastionClient for development and testing"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_client = MockBastionClient()
    
    def test_mock_client_initialization(self):
        """Test MockBastionClient initialization"""
        assert self.mock_client.enabled is True
        assert self.mock_client.health_check() is True
    
    def test_mock_scoring_by_amount_approve(self):
        """Test mock scoring for small amounts (should approve)"""
        transaction_data = {
            "transaction_id": "test-123",
            "amount": "1000.00",
            "currency": "USD"
        }
        
        result = self.mock_client.score_transaction(transaction_data)
        
        assert result.decision == "APPROVE"
        assert result.risk_level == "LOW"
        assert result.score == 0.1
        assert result.reasons == []
        assert result.latency_ms == 1.0
    
    def test_mock_scoring_by_amount_review_medium(self):
        """Test mock scoring for medium amounts (should review)"""
        transaction_data = {
            "transaction_id": "test-123",
            "amount": "7500.00",  # Between 5K and 10K
            "currency": "USD"
        }
        
        result = self.mock_client.score_transaction(transaction_data)
        
        assert result.decision == "REVIEW"
        assert result.risk_level == "MEDIUM"
        assert result.score == 0.35
        assert result.reasons == ["medium_amount"]
        assert result.latency_ms == 1.0
    
    def test_mock_scoring_by_amount_review_high(self):
        """Test mock scoring for large amounts (should review)"""
        transaction_data = {
            "transaction_id": "test-123",
            "amount": "15000.00",  # Between 10K and 50K
            "currency": "USD"
        }
        
        result = self.mock_client.score_transaction(transaction_data)
        
        assert result.decision == "REVIEW"
        assert result.risk_level == "HIGH"
        assert result.score == 0.55
        assert result.reasons == ["large_amount"]
        assert result.latency_ms == 1.0
    
    def test_mock_scoring_by_amount_block(self):
        """Test mock scoring for very large amounts (should block)"""
        transaction_data = {
            "transaction_id": "test-123",
            "amount": "75000.00",  # Over 50K
            "currency": "USD"
        }
        
        result = self.mock_client.score_transaction(transaction_data)
        
        assert result.decision == "BLOCK"
        assert result.risk_level == "CRITICAL"
        assert result.score == 0.85
        assert result.reasons == ["high_amount"]
        assert result.latency_ms == 1.0


class TestBastionClient:
    """Test BastionClient for real Bastion integration"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.client = BastionClient(
            base_url="http://localhost:8080",
            timeout=2.0,
            api_key="test-key",
            enabled=True,
            fallback_on_error="APPROVE"
        )
    
    def test_bastion_client_initialization(self):
        """Test BastionClient initialization"""
        assert self.client.base_url == "http://localhost:8080"
        assert self.client.timeout == 2.0
        assert self.client.api_key == "test-key"
        assert self.client.enabled is True
        assert self.client.fallback_on_error == "APPROVE"
    
    def test_bastion_client_disabled(self):
        """Test BastionClient when disabled"""
        client = BastionClient(enabled=False)
        
        transaction_data = {"transaction_id": "test-123", "amount": "1000.00"}
        result = client.score_transaction(transaction_data)
        
        assert result.decision == "APPROVE"
        assert result.risk_level == "LOW"
        assert result.score == 0.0
        assert result.reasons == ["fraud_scoring_disabled"]
        assert result.latency_ms == 0.0
    
    def test_risk_level_mapping(self):
        """Test risk level mapping from numeric scores"""
        client = BastionClient()
        
        assert client._map_risk_level(0.85) == "CRITICAL"
        assert client._map_risk_level(0.65) == "HIGH"
        assert client._map_risk_level(0.45) == "MEDIUM"
        assert client._map_risk_level(0.15) == "LOW"
    
    @patch('httpx.Client.post')
    def test_successful_scoring(self, mock_post):
        """Test successful scoring response from Bastion"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "risk_score": 0.35,
            "action": "review",
            "reasons": ["velocity_check", "large_amount"]
        }
        mock_post.return_value = mock_response
        
        transaction_data = {
            "transaction_id": "test-123",
            "customer_id": "cust-456",
            "amount": "5000.00",
            "currency": "USD",
            "channel": "online",
            "transaction_type": "transfer"
        }
        
        result = self.client.score_transaction(transaction_data)
        
        assert result.score == 0.35
        assert result.decision == "REVIEW"
        assert result.risk_level == "MEDIUM"
        assert result.reasons == ["velocity_check", "large_amount"]
        assert result.latency_ms > 0
        
        # Verify the request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check URL (first positional argument)
        assert call_args[0][0] == "http://localhost:8080/score"
        
        # Check headers (keyword argument)
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test-key"
        
        # Check request data mapping (keyword argument)
        request_data = call_args.kwargs["json"]
        assert request_data["transaction_id"] == "test-123"
        assert request_data["cif_id"] == "cust-456"
        assert request_data["amount"] == 5000.0
        assert request_data["currency"] == "USD"
        assert request_data["channel"] == "online"
        assert request_data["metadata"]["transaction_type"] == "transfer"
    
    @patch('httpx.Client.post')
    def test_http_error_fallback(self, mock_post):
        """Test fallback when Bastion returns HTTP error"""
        # Mock HTTP error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        transaction_data = {"transaction_id": "test-123", "amount": "1000.00"}
        result = self.client.score_transaction(transaction_data)
        
        assert result.decision == "APPROVE"  # fallback_on_error
        assert result.risk_level == "UNKNOWN"
        assert result.score == 0.0
        assert result.reasons == ["bastion_unavailable"]
    
    @patch('httpx.Client.post')
    def test_connection_error_fallback(self, mock_post):
        """Test fallback when connection to Bastion fails"""
        # Mock connection error
        mock_post.side_effect = httpx.ConnectError("Connection failed")
        
        transaction_data = {"transaction_id": "test-123", "amount": "1000.00"}
        result = self.client.score_transaction(transaction_data)
        
        assert result.decision == "APPROVE"  # fallback_on_error
        assert result.risk_level == "UNKNOWN"
        assert result.score == 0.0
        assert result.reasons == ["bastion_unavailable"]
        assert result.latency_ms == 0.0
    
    @patch('httpx.Client.post')
    def test_custom_fallback_decision(self, mock_post):
        """Test custom fallback decision"""
        client = BastionClient(fallback_on_error="REVIEW")
        mock_post.side_effect = httpx.ConnectError("Connection failed")
        
        transaction_data = {"transaction_id": "test-123", "amount": "1000.00"}
        result = client.score_transaction(transaction_data)
        
        assert result.decision == "REVIEW"  # Custom fallback
    
    @patch('httpx.Client.get')
    def test_health_check_success(self, mock_get):
        """Test successful health check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        assert self.client.health_check() is True
        mock_get.assert_called_once_with("http://localhost:8080/health")
    
    @patch('httpx.Client.get')
    def test_health_check_failure(self, mock_get):
        """Test failed health check"""
        mock_get.side_effect = httpx.ConnectError("Connection failed")
        
        assert self.client.health_check() is False


class TestTransactionProcessorFraudIntegration:
    """Test fraud client integration with transaction processor"""
    
    def setup_method(self):
        """Set up test fixtures with fraud client"""
        # Create test banking system directly
        from core_banking.storage import InMemoryStorage
        from core_banking.audit import AuditTrail
        from core_banking.ledger import GeneralLedger
        from core_banking.accounts import AccountManager
        from core_banking.customers import CustomerManager
        from core_banking.compliance import ComplianceEngine
        from core_banking.transactions import TransactionProcessor
        
        # Create system with mock fraud client
        self.fraud_client = MockBastionClient()
        
        # Initialize core components
        storage = InMemoryStorage()
        audit_trail = AuditTrail(storage)
        ledger = GeneralLedger(storage, audit_trail)
        account_manager = AccountManager(storage, ledger, audit_trail)
        customer_manager = CustomerManager(storage, audit_trail)
        compliance_engine = ComplianceEngine(storage, customer_manager, audit_trail)
        
        # Create a simple system object
        class TestSystem:
            def __init__(self, fraud_client):
                self.storage = storage
                self.audit_trail = audit_trail
                self.ledger = ledger
                self.account_manager = account_manager
                self.customer_manager = customer_manager
                self.compliance_engine = compliance_engine
                self.transaction_processor = TransactionProcessor(
                    storage, ledger, account_manager, customer_manager,
                    compliance_engine, audit_trail, fraud_client=fraud_client
                )
        
        self.system = TestSystem(self.fraud_client)
        
        # Create a test customer
        from datetime import datetime
        self.customer = self.system.customer_manager.create_customer(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-1234"
        )
        
        # Set customer to verified KYC status to avoid compliance blocks
        from core_banking.customers import KYCStatus, KYCTier
        self.customer.kyc_status = KYCStatus.VERIFIED
        self.customer.kyc_tier = KYCTier.TIER_2
        self.system.customer_manager._save_customer(self.customer)
        
        from core_banking.accounts import ProductType
        from core_banking.currency import Currency
        
        self.account = self.system.account_manager.create_account(
            customer_id=self.customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Test Checking Account"
        )
        
        # Fund the account
        deposit = self.system.transaction_processor.deposit(
            account_id=self.account.id,
            amount=Money(Decimal('10000'), Currency.USD),
            description="Initial deposit",
            channel=TransactionChannel.SYSTEM
        )
        self.system.transaction_processor.process_transaction(deposit.id)
    
    def test_fraud_client_integration_approve(self):
        """Test transaction processing with fraud scoring - approve"""
        # Small amount should be approved
        transaction = self.system.transaction_processor.withdraw(
            account_id=self.account.id,
            amount=Money(Decimal('1000'), Currency.USD),
            description="Small withdrawal",
            channel=TransactionChannel.ONLINE
        )
        
        processed = self.system.transaction_processor.process_transaction(transaction.id)
        
        # Transaction should be completed
        assert processed.state == TransactionState.COMPLETED
        
        # Check fraud metadata
        assert processed.metadata["fraud_score"] == 0.1
        assert processed.metadata["fraud_decision"] == "APPROVE"
        assert processed.metadata["fraud_reasons"] == []
        assert "fraud_latency_ms" in processed.metadata
        assert "needs_review" not in processed.metadata
    
    def test_fraud_client_integration_review(self):
        """Test transaction processing with fraud scoring - review"""
        # Medium amount should be flagged for review but still processed
        transaction = self.system.transaction_processor.withdraw(
            account_id=self.account.id,
            amount=Money(Decimal('7500'), Currency.USD),
            description="Medium withdrawal",
            channel=TransactionChannel.ONLINE
        )
        
        processed = self.system.transaction_processor.process_transaction(transaction.id)
        
        # Transaction should be completed but flagged for review
        assert processed.state == TransactionState.COMPLETED
        
        # Check fraud metadata
        assert processed.metadata["fraud_score"] == 0.35
        assert processed.metadata["fraud_decision"] == "REVIEW"
        assert processed.metadata["fraud_reasons"] == ["medium_amount"]
        assert processed.metadata["needs_review"] is True
        assert "fraud_latency_ms" in processed.metadata
    
    def test_fraud_client_integration_block(self):
        """Test transaction processing with fraud scoring - block"""
        # Large amount should be blocked
        transaction = self.system.transaction_processor.withdraw(
            account_id=self.account.id,
            amount=Money(Decimal('75000'), Currency.USD),
            description="Large withdrawal",
            channel=TransactionChannel.ONLINE
        )
        
        # Processing should fail
        with pytest.raises(ValueError, match="Blocked by fraud detection"):
            self.system.transaction_processor.process_transaction(transaction.id)
        
        # Check transaction state
        blocked_txn = self.system.transaction_processor.get_transaction(transaction.id)
        assert blocked_txn.state == TransactionState.FAILED
        assert blocked_txn.error_message == "Blocked by fraud detection"
        
        # Check fraud metadata
        assert blocked_txn.metadata["fraud_score"] == 0.85
        assert blocked_txn.metadata["fraud_decision"] == "BLOCK"
        assert blocked_txn.metadata["fraud_reasons"] == ["high_amount"]
        assert blocked_txn.metadata["rejection_reason"] == "fraud_detected"
        assert "fraud_latency_ms" in blocked_txn.metadata
    
    def test_no_fraud_client_fallback(self):
        """Test transaction processing without fraud client"""
        # Create processor without fraud client
        processor_no_fraud = TransactionProcessor(
            storage=self.system.storage,
            ledger=self.system.ledger,
            account_manager=self.system.account_manager,
            customer_manager=self.system.customer_manager,
            compliance_engine=self.system.compliance_engine,
            audit_trail=self.system.audit_trail,
            fraud_client=None  # No fraud client
        )
        
        transaction = processor_no_fraud.create_transaction(
            transaction_type=TransactionType.WITHDRAWAL,
            amount=Money(Decimal('1000'), Currency.USD),
            description="Test withdrawal",
            channel=TransactionChannel.ONLINE,
            from_account_id=self.account.id
        )
        
        processed = processor_no_fraud.process_transaction(transaction.id)
        
        # Transaction should be completed without fraud scoring
        assert processed.state == TransactionState.COMPLETED
        assert "fraud_score" not in processed.metadata
        assert "fraud_decision" not in processed.metadata
    
    def test_fraud_scoring_stored_in_metadata(self):
        """Test that fraud scoring results are properly stored"""
        transaction = self.system.transaction_processor.withdraw(
            account_id=self.account.id,
            amount=Money(Decimal('7500'), Currency.USD),  # Should trigger review but not compliance block
            description="Medium withdrawal",
            channel=TransactionChannel.ONLINE
        )
        
        processed = self.system.transaction_processor.process_transaction(transaction.id)
        
        # Verify all fraud metadata is stored
        metadata = processed.metadata
        assert "fraud_score" in metadata
        assert "fraud_decision" in metadata
        assert "fraud_reasons" in metadata
        assert "fraud_latency_ms" in metadata
        assert metadata["needs_review"] is True
        
        # Verify specific values for $7500 (medium amount)
        assert metadata["fraud_score"] == 0.35
        assert metadata["fraud_decision"] == "REVIEW"
        assert metadata["fraud_reasons"] == ["medium_amount"]
        
        # Verify data types
        assert isinstance(metadata["fraud_score"], float)
        assert isinstance(metadata["fraud_decision"], str)
        assert isinstance(metadata["fraud_reasons"], list)
        assert isinstance(metadata["fraud_latency_ms"], float)
        assert isinstance(metadata["needs_review"], bool)
    
    def test_system_transactions_skip_fraud_scoring(self):
        """Test that system transactions skip fraud scoring"""
        # System transactions should skip fraud scoring
        transaction = self.system.transaction_processor.create_transaction(
            transaction_type=TransactionType.FEE,
            amount=Money(Decimal('100000'), Currency.USD),  # Large amount that would normally be blocked
            description="System fee",
            channel=TransactionChannel.SYSTEM,  # System channel
            from_account_id=self.account.id
        )
        
        processed = self.system.transaction_processor.process_transaction(transaction.id)
        
        # Transaction should be completed without fraud scoring
        assert processed.state == TransactionState.COMPLETED
        assert "fraud_score" not in processed.metadata
    
    def test_reversal_transactions_skip_fraud_scoring(self):
        """Test that reversal transactions skip fraud scoring"""
        # First create and process a normal transaction
        original = self.system.transaction_processor.withdraw(
            account_id=self.account.id,
            amount=Money(Decimal('1000'), Currency.USD),
            description="Original withdrawal",
            channel=TransactionChannel.ONLINE
        )
        processed_original = self.system.transaction_processor.process_transaction(original.id)
        
        # Now reverse it (reversal should skip fraud scoring even for large amounts)
        reversal = self.system.transaction_processor.reverse_transaction(
            original_transaction_id=processed_original.id,
            reason="Customer request"
        )
        
        # Reversal should be completed without fraud scoring
        assert reversal.state == TransactionState.COMPLETED
        assert "fraud_score" not in reversal.metadata
    
    def test_fraud_client_connection_failure_fallback(self):
        """Test graceful fallback when fraud client fails"""
        # Create a client that will fail
        failing_client = BastionClient(
            base_url="http://nonexistent:9999",
            timeout=0.1,
            fallback_on_error="APPROVE"
        )
        
        # Replace fraud client with failing one
        self.system.transaction_processor.fraud_client = failing_client
        
        transaction = self.system.transaction_processor.withdraw(
            account_id=self.account.id,
            amount=Money(Decimal('1000'), Currency.USD),
            description="Test withdrawal",
            channel=TransactionChannel.ONLINE
        )
        
        # Transaction should still be processed (fallback to APPROVE)
        processed = self.system.transaction_processor.process_transaction(transaction.id)
        
        assert processed.state == TransactionState.COMPLETED
        assert processed.metadata["fraud_decision"] == "APPROVE"
        assert processed.metadata["fraud_reasons"] == ["bastion_unavailable"]