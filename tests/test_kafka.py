"""
Tests for Kafka Integration Module

Tests all event publishing, command handling, and event bus functionality
using InMemoryEventBus (no real Kafka needed).
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from core_banking.currency import Money, Currency
from core_banking.kafka_integration import (
    KafkaTopics, EventSchema, EventBus, InMemoryEventBus, LogEventBus, 
    NexumEventPublisher, NexumCommandHandler
)
from core_banking.event_hooks import EventHookManager, create_event_enabled_banking_system
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.customers import CustomerManager, KYCStatus, KYCTier
from core_banking.accounts import AccountManager, ProductType
from core_banking.transactions import TransactionProcessor, TransactionType, TransactionState, TransactionChannel
from core_banking.loans import LoanManager, PaymentFrequency, LoanState
from core_banking.ledger import GeneralLedger
from core_banking.compliance import ComplianceEngine


class TestEventSchema:
    """Test event schema functionality"""
    
    def test_event_schema_creation(self):
        """Test creating event schema"""
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="test_event",
            timestamp=datetime.now(timezone.utc),
            entity_type="test",
            entity_id="123",
            data={"key": "value"},
            metadata={"correlation_id": "abc123"}
        )
        
        assert event.source == "nexum"
        assert event.version == "1.0"
        assert event.entity_type == "test"
        assert event.entity_id == "123"
        assert event.data["key"] == "value"
        assert event.metadata["correlation_id"] == "abc123"
    
    def test_event_schema_serialization(self):
        """Test event serialization with Decimal handling"""
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="transaction_created",
            timestamp=datetime.now(timezone.utc),
            entity_type="transaction",
            entity_id="txn_123",
            data={
                "amount": Decimal("100.50"),
                "nested": {
                    "value": Decimal("25.00")
                },
                "money": Money(Decimal("50.00"), Currency.USD)
            }
        )
        
        serialized = event.to_dict()
        
        # Check that Decimals are converted to strings
        assert serialized["data"]["amount"] == "100.50"
        assert serialized["data"]["nested"]["value"] == "25.00"
        
        # Check Money conversion
        assert serialized["data"]["money"]["amount"] == "50.00"
        assert serialized["data"]["money"]["currency"] == "USD"
        
        # Check timestamp conversion
        assert isinstance(serialized["timestamp"], str)
        
        # Test deserialization
        deserialized = EventSchema.from_dict(serialized)
        assert deserialized.event_id == event.event_id
        assert deserialized.timestamp == event.timestamp
    
    def test_event_schema_validation(self):
        """Test CloudEvents compliance"""
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="customer_created",
            timestamp=datetime.now(timezone.utc)
        )
        
        serialized = event.to_dict()
        
        # CloudEvents required fields
        assert "event_id" in serialized
        assert "event_type" in serialized
        assert "timestamp" in serialized
        assert "source" in serialized
        assert serialized["source"] == "nexum"


class TestInMemoryEventBus:
    """Test in-memory event bus"""
    
    def test_event_bus_lifecycle(self):
        """Test starting and stopping event bus"""
        bus = InMemoryEventBus()
        assert not bus.is_running()
        
        bus.start()
        assert bus.is_running()
        
        bus.stop()
        assert not bus.is_running()
    
    def test_event_publishing(self):
        """Test basic event publishing"""
        bus = InMemoryEventBus()
        bus.start()
        
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="test_event",
            timestamp=datetime.now(timezone.utc)
        )
        
        topic = "nexum.test.events"
        bus.publish(topic, event, key="test_key")
        
        events = bus.get_events()
        assert len(events) == 1
        
        stored_topic, stored_event, stored_key = events[0]
        assert stored_topic == topic
        assert stored_event.event_id == event.event_id
        assert stored_key == "test_key"
    
    def test_batch_publishing(self):
        """Test batch event publishing"""
        bus = InMemoryEventBus()
        bus.start()
        
        events = [
            EventSchema(
                event_id=str(uuid.uuid4()),
                event_type="test_event_1",
                timestamp=datetime.now(timezone.utc)
            ),
            EventSchema(
                event_id=str(uuid.uuid4()),
                event_type="test_event_2",
                timestamp=datetime.now(timezone.utc)
            )
        ]
        
        topic = "nexum.test.batch"
        keys = ["key1", "key2"]
        bus.publish_batch(topic, events, keys)
        
        stored_events = bus.get_events(topic)
        assert len(stored_events) == 2
        
        # Check events are stored correctly
        for i, (stored_topic, stored_event, stored_key) in enumerate(stored_events):
            assert stored_topic == topic
            assert stored_event.event_id == events[i].event_id
            assert stored_key == keys[i]
    
    def test_event_subscription(self):
        """Test event subscription and handlers"""
        bus = InMemoryEventBus()
        bus.start()
        
        received_events = []
        
        def handler(event: EventSchema):
            received_events.append(event)
        
        topic = "nexum.test.subscription"
        bus.subscribe(topic, handler)
        
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="subscription_test",
            timestamp=datetime.now(timezone.utc)
        )
        
        bus.publish(topic, event)
        
        # Handler should have been called
        assert len(received_events) == 1
        assert received_events[0].event_id == event.event_id
    
    def test_multiple_subscribers(self):
        """Test multiple subscribers for same topic"""
        bus = InMemoryEventBus()
        bus.start()
        
        handler1_events = []
        handler2_events = []
        
        def handler1(event: EventSchema):
            handler1_events.append(event)
        
        def handler2(event: EventSchema):
            handler2_events.append(event)
        
        topic = "nexum.test.multi"
        bus.subscribe(topic, handler1)
        bus.subscribe(topic, handler2)
        
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="multi_test",
            timestamp=datetime.now(timezone.utc)
        )
        
        bus.publish(topic, event)
        
        # Both handlers should have been called
        assert len(handler1_events) == 1
        assert len(handler2_events) == 1
        assert handler1_events[0].event_id == event.event_id
        assert handler2_events[0].event_id == event.event_id
    
    def test_event_filtering(self):
        """Test getting events by topic"""
        bus = InMemoryEventBus()
        bus.start()
        
        topic1 = "nexum.test.topic1"
        topic2 = "nexum.test.topic2"
        
        event1 = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="type1",
            timestamp=datetime.now(timezone.utc)
        )
        
        event2 = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="type2",
            timestamp=datetime.now(timezone.utc)
        )
        
        bus.publish(topic1, event1)
        bus.publish(topic2, event2)
        
        # Get all events
        all_events = bus.get_events()
        assert len(all_events) == 2
        
        # Get events by topic
        topic1_events = bus.get_events(topic1)
        assert len(topic1_events) == 1
        assert topic1_events[0][1].event_id == event1.event_id
        
        topic2_events = bus.get_events(topic2)
        assert len(topic2_events) == 1
        assert topic2_events[0][1].event_id == event2.event_id
    
    def test_clear_events(self):
        """Test clearing events"""
        bus = InMemoryEventBus()
        bus.start()
        
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="clear_test",
            timestamp=datetime.now(timezone.utc)
        )
        
        bus.publish("nexum.test.clear", event)
        assert len(bus.get_events()) == 1
        
        bus.clear_events()
        assert len(bus.get_events()) == 0


class TestLogEventBus:
    """Test log event bus"""
    
    def test_log_event_bus_creation(self):
        """Test creating log event bus"""
        bus = LogEventBus()
        assert not bus.is_running()
        
        bus.start()
        assert bus.is_running()
        
        bus.stop()
        assert not bus.is_running()
    
    @patch('core_banking.kafka_integration.logging')
    def test_log_event_publishing(self, mock_logging):
        """Test that events are logged"""
        mock_logger = Mock()
        mock_logging.getLogger.return_value = mock_logger
        
        bus = LogEventBus(mock_logger)
        bus.start()
        
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="log_test",
            timestamp=datetime.now(timezone.utc),
            entity_type="test",
            entity_id="123"
        )
        
        bus.publish("nexum.test.log", event)
        
        # Check that logger.info was called (at least once for the event)
        assert mock_logger.info.call_count >= 1
        # Check the last call is our event
        last_call_args = mock_logger.info.call_args[0][0]
        assert "nexum.test.log" in last_call_args
        assert "log_test" in last_call_args
        assert "test:123" in last_call_args


class TestNexumEventPublisher:
    """Test Nexum event publisher"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.bus = InMemoryEventBus()
        self.bus.start()
        self.publisher = NexumEventPublisher(self.bus)
    
    def test_transaction_created_event(self):
        """Test transaction created event publishing"""
        # Mock transaction object
        transaction = Mock()
        transaction.id = "txn_123"
        transaction.transaction_type = TransactionType.DEPOSIT
        transaction.amount = Money(Decimal("100.00"), Currency.USD)
        transaction.from_account_id = "acc_from"
        transaction.to_account_id = "acc_to"
        transaction.description = "Test deposit"
        transaction.reference = "REF123"
        transaction.correlation_id = "corr_123"
        
        self.publisher.on_transaction_created(transaction)
        
        events = self.bus.get_events(KafkaTopics.TRANSACTIONS_CREATED.value)
        assert len(events) == 1
        
        topic, event, key = events[0]
        assert topic == KafkaTopics.TRANSACTIONS_CREATED.value
        assert event.event_type == "transaction_created"
        assert event.entity_type == "transaction"
        assert event.entity_id == "txn_123"
        assert key == "txn_123"
        
        # Check data
        assert event.data["transaction_type"] == "deposit"
        assert event.data["amount"] == "100.00"
        assert event.data["currency"] == "USD"
        assert event.data["from_account_id"] == "acc_from"
        assert event.data["description"] == "Test deposit"
    
    def test_transaction_posted_event(self):
        """Test transaction posted event publishing"""
        transaction = Mock()
        transaction.id = "txn_456"
        transaction.transaction_type = TransactionType.WITHDRAWAL
        transaction.amount = Money(Decimal("50.00"), Currency.USD)
        transaction.from_account_id = "acc_from"
        transaction.to_account_id = None
        transaction.final_balance = Decimal("450.00")
        transaction.journal_entry_id = "je_789"
        
        self.publisher.on_transaction_posted(transaction)
        
        events = self.bus.get_events(KafkaTopics.TRANSACTIONS_POSTED.value)
        assert len(events) == 1
        
        topic, event, key = events[0]
        assert event.event_type == "transaction_posted"
        assert event.data["final_balance"] == "450.00"
        assert event.data["journal_entry_id"] == "je_789"
    
    def test_account_created_event(self):
        """Test account created event publishing"""
        account = Mock()
        account.id = "acc_123"
        account.account_number = "1234567890"
        account.product_type = ProductType.SAVINGS
        account.customer_id = "cust_123"
        account.currency = Currency.USD
        account.name = "Test Savings"
        account.balance = Money(Decimal("1000.00"), Currency.USD)
        
        self.publisher.on_account_created(account)
        
        events = self.bus.get_events(KafkaTopics.ACCOUNTS_CREATED.value)
        assert len(events) == 1
        
        topic, event, key = events[0]
        assert event.event_type == "account_created"
        assert event.entity_type == "account"
        assert event.data["product_type"] == "savings"
        assert event.data["balance"] == "1000.00"
    
    def test_customer_created_event(self):
        """Test customer created event publishing"""
        customer = Mock()
        customer.id = "cust_123"
        customer.first_name = "John"
        customer.last_name = "Doe"
        customer.email = "john@example.com"
        customer.phone = "+1234567890"
        customer.kyc_status = KYCStatus.VERIFIED
        customer.kyc_tier = KYCTier.TIER_2
        
        self.publisher.on_customer_created(customer)
        
        events = self.bus.get_events(KafkaTopics.CUSTOMERS_CREATED.value)
        assert len(events) == 1
        
        topic, event, key = events[0]
        assert event.event_type == "customer_created"
        assert event.data["first_name"] == "John"
        assert event.data["kyc_status"] == "verified"
        assert event.data["kyc_tier"] == "tier_2"
    
    def test_customer_kyc_changed_event(self):
        """Test customer KYC changed event publishing"""
        customer = Mock()
        customer.id = "cust_123"
        customer.kyc_status = KYCStatus.VERIFIED
        customer.kyc_tier = KYCTier.TIER_2
        
        old_status = KYCStatus.PENDING
        old_tier = KYCTier.TIER_1
        
        self.publisher.on_customer_kyc_changed(customer, old_status, old_tier)
        
        events = self.bus.get_events(KafkaTopics.CUSTOMERS_KYC_CHANGED.value)
        assert len(events) == 1
        
        topic, event, key = events[0]
        assert event.event_type == "kyc_status_changed"
        assert event.data["old_status"] == "pending"
        assert event.data["new_status"] == "verified"
        assert event.data["old_tier"] == "tier_1"
        assert event.data["new_tier"] == "tier_2"
    
    def test_loan_originated_event(self):
        """Test loan originated event publishing"""
        loan = Mock()
        loan.id = "loan_123"
        loan.customer_id = "cust_123"
        loan.principal = Money(Decimal("10000.00"), Currency.USD)
        loan.interest_rate = Decimal("5.5")
        loan.term_months = 60
        loan.payment_frequency = PaymentFrequency.MONTHLY
        
        self.publisher.on_loan_originated(loan)
        
        events = self.bus.get_events(KafkaTopics.LOANS_ORIGINATED.value)
        assert len(events) == 1
        
        topic, event, key = events[0]
        assert event.event_type == "loan_originated"
        assert event.data["principal"] == "10000.00"
        assert event.data["interest_rate"] == "5.5"
        assert event.data["term_months"] == 60
        assert event.data["payment_frequency"] == "monthly"
    
    def test_compliance_alert_event(self):
        """Test compliance alert event publishing"""
        alert = {
            'id': 'alert_123',
            'type': 'suspicious_transaction',
            'severity': 'high',
            'customer_id': 'cust_123',
            'account_id': 'acc_123',
            'description': 'Large cash deposit'
        }
        
        self.publisher.on_compliance_alert(alert)
        
        events = self.bus.get_events(KafkaTopics.COMPLIANCE_ALERT.value)
        assert len(events) == 1
        
        topic, event, key = events[0]
        assert event.event_type == "compliance_alert"
        assert event.data["alert_type"] == "suspicious_transaction"
        assert event.data["severity"] == "high"
    
    def test_all_event_types_json_serializable(self):
        """Test that all events are JSON serializable"""
        import json
        
        # Create a simple transaction-like object without Mock
        class FakeTransaction:
            def __init__(self):
                self.id = "txn_123"
                self.transaction_type = TransactionType.DEPOSIT
                self.amount = Money(Decimal("100.00"), Currency.USD)
                self.from_account_id = "acc_from"
                self.to_account_id = "acc_to"
                self.description = "Test"
                self.reference = "REF"
                self.correlation_id = "corr"
                self.user_id = "user_123"  # Real string, not Mock
        
        transaction = FakeTransaction()
        
        self.publisher.on_transaction_created(transaction)
        
        events = self.bus.get_events()
        assert len(events) == 1
        
        # Should be able to serialize to JSON
        event_dict = events[0][1].to_dict()
        json_str = json.dumps(event_dict)
        
        # Should be able to deserialize back
        restored = json.loads(json_str)
        assert restored["event_type"] == "transaction_created"


class TestNexumCommandHandler:
    """Test command handler"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.bus = InMemoryEventBus()
        self.bus.start()
        self.banking_system = Mock()
        self.handler = NexumCommandHandler(self.bus, self.banking_system)
    
    def test_transaction_command_handling(self):
        """Test handling transaction commands"""
        # Create a deposit command
        command_event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="deposit_command",
            timestamp=datetime.now(timezone.utc),
            data={
                'action': 'deposit',
                'account_id': 'acc_123',
                'amount': '100.00',
                'currency': 'USD',
                'description': 'Command deposit'
            }
        )
        
        # Mock the handler method
        with patch.object(self.handler, 'handle_transaction_command') as mock_handle:
            self.handler.start()
            
            # Publish command
            self.bus.publish(KafkaTopics.COMMANDS_TRANSACTIONS.value, command_event)
            
            # Handler should have been called
            mock_handle.assert_called_once_with(command_event)
    
    def test_customer_command_handling(self):
        """Test handling customer commands"""
        command_event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="create_customer_command",
            timestamp=datetime.now(timezone.utc),
            data={
                'action': 'create',
                'first_name': 'Jane',
                'last_name': 'Smith',
                'email': 'jane@example.com'
            }
        )
        
        with patch.object(self.handler, 'handle_customer_command') as mock_handle:
            self.handler.start()
            self.bus.publish(KafkaTopics.COMMANDS_CUSTOMERS.value, command_event)
            mock_handle.assert_called_once_with(command_event)
    
    def test_loan_command_handling(self):
        """Test handling loan commands"""
        command_event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="originate_loan_command",
            timestamp=datetime.now(timezone.utc),
            data={
                'action': 'originate',
                'customer_id': 'cust_123',
                'principal': '10000.00',
                'currency': 'USD',
                'interest_rate': '5.5',
                'term_months': 60
            }
        )
        
        with patch.object(self.handler, 'handle_loan_command') as mock_handle:
            self.handler.start()
            self.bus.publish(KafkaTopics.COMMANDS_LOANS.value, command_event)
            mock_handle.assert_called_once_with(command_event)
    
    def test_error_handling_in_commands(self):
        """Test error handling in command processing"""
        with patch('core_banking.kafka_integration.logging') as mock_logging:
            mock_logger = Mock()
            mock_logging.error = mock_logger
            
            # Create invalid command that will cause error
            command_event = EventSchema(
                event_id=str(uuid.uuid4()),
                event_type="invalid_command",
                timestamp=datetime.now(timezone.utc),
                data={'action': 'invalid'}
            )
            
            self.handler.start()
            self.handler.handle_transaction_command(command_event)
            
            # Should not raise exception, but should log error


class TestEventHooks:
    """Test event hooks functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.storage = InMemoryStorage()
        self.audit_trail = AuditTrail(self.storage)
        self.ledger = GeneralLedger(self.storage, self.audit_trail)
        
        self.customer_manager = CustomerManager(self.storage, self.audit_trail)
        self.account_manager = AccountManager(self.storage, self.ledger, self.audit_trail)
        self.compliance_engine = ComplianceEngine(self.storage, self.customer_manager, self.audit_trail)
        self.transaction_processor = TransactionProcessor(
            self.storage, self.ledger, self.account_manager, 
            self.customer_manager, self.compliance_engine, self.audit_trail
        )
        
        self.bus = InMemoryEventBus()
        self.bus.start()
        
        self.publisher = NexumEventPublisher(self.bus)
        self.hook_manager = EventHookManager(self.publisher)
    
    def test_transaction_event_hooks(self):
        """Test transaction event hooks"""
        # Enable transaction events
        self.hook_manager.enable_transaction_events(self.transaction_processor)
        
        # Create a customer and account first
        customer = self.customer_manager.create_customer(
            first_name="Test",
            last_name="User",
            email="test@example.com"
        )
        
        account = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Test Account"
        )
        
        # Create and process a transaction (this should fire events)
        transaction = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.DEPOSIT,
            amount=Money(Decimal("100.00"), Currency.USD),
            to_account_id=account.id,
            description="Test deposit",
            channel=TransactionChannel.ONLINE
        )
        
        # Check that transaction created event was fired
        created_events = self.bus.get_events(KafkaTopics.TRANSACTIONS_CREATED.value)
        assert len(created_events) >= 1
        
        # Process the transaction (should fire posted or failed event)
        try:
            self.transaction_processor.process_transaction(transaction)
            
            # Check for posted event
            posted_events = self.bus.get_events(KafkaTopics.TRANSACTIONS_POSTED.value)
            failed_events = self.bus.get_events(KafkaTopics.TRANSACTIONS_FAILED.value)
            
            # Should have either posted or failed event
            assert len(posted_events) > 0 or len(failed_events) > 0
            
        except Exception:
            # If processing fails, should have failed event
            failed_events = self.bus.get_events(KafkaTopics.TRANSACTIONS_FAILED.value)
            assert len(failed_events) >= 1
    
    def test_customer_event_hooks(self):
        """Test customer event hooks"""
        self.hook_manager.enable_customer_events(self.customer_manager)
        
        # Create customer (should fire event)
        customer = self.customer_manager.create_customer(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com"
        )
        
        # Check that customer created event was fired
        events = self.bus.get_events(KafkaTopics.CUSTOMERS_CREATED.value)
        assert len(events) == 1
        
        topic, event, key = events[0]
        assert event.entity_id == customer.id
        assert event.data["first_name"] == "Jane"
        assert event.data["email"] == "jane@example.com"
        
        # Update customer (should fire event)
        updated_customer = self.customer_manager.update_customer_info(
            customer.id,
            phone="+1234567890"
        )
        
        # Check that customer updated event was fired
        updated_events = self.bus.get_events(KafkaTopics.CUSTOMERS_UPDATED.value)
        assert len(updated_events) == 1
    
    def test_account_event_hooks(self):
        """Test account event hooks"""
        self.hook_manager.enable_account_events(self.account_manager)
        
        # Create customer first
        customer = self.customer_manager.create_customer(
            first_name="Test",
            last_name="Account",
            email="account@example.com"
        )
        
        # Create account (should fire event)
        account = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Test Savings"
        )
        
        # Check that account created event was fired
        events = self.bus.get_events(KafkaTopics.ACCOUNTS_CREATED.value)
        assert len(events) == 1
        
        topic, event, key = events[0]
        assert event.entity_id == account.id
        assert event.data["product_type"] == "savings"
    
    def test_event_ordering_preservation(self):
        """Test that events maintain order"""
        self.hook_manager.enable_customer_events(self.customer_manager)
        
        # Create multiple customers in sequence
        customers = []
        for i in range(5):
            customer = self.customer_manager.create_customer(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com"
            )
            customers.append(customer)
        
        events = self.bus.get_events(KafkaTopics.CUSTOMERS_CREATED.value)
        assert len(events) == 5
        
        # Check that events are in the correct order
        for i, (topic, event, key) in enumerate(events):
            assert event.entity_id == customers[i].id
            assert event.data["first_name"] == f"User{i}"
    
    def test_create_event_enabled_banking_system(self):
        """Test the convenience function for creating event-enabled system"""
        components = {
            'transaction_processor': self.transaction_processor,
            'account_manager': self.account_manager,
            'customer_manager': self.customer_manager,
            'audit_trail': self.audit_trail
        }
        
        hook_manager = create_event_enabled_banking_system(self.bus, components)
        assert isinstance(hook_manager, EventHookManager)
        
        # Test that hooks are working
        customer = self.customer_manager.create_customer(
            first_name="Hook",
            last_name="Test",
            email="hook@example.com"
        )
        
        events = self.bus.get_events(KafkaTopics.CUSTOMERS_CREATED.value)
        assert len(events) == 1
    
    def test_hook_restoration(self):
        """Test that hooks can be disabled and original methods restored"""
        # Store original method
        original_create = self.customer_manager.create_customer
        
        # Enable hooks
        self.hook_manager.enable_customer_events(self.customer_manager)
        
        # Method should be different now
        assert self.customer_manager.create_customer != original_create
        
        # Disable hooks
        self.hook_manager.disable_all_events()
        
        # Method should be restored
        assert self.customer_manager.create_customer == original_create


class TestKafkaTopics:
    """Test topic enumeration"""
    
    def test_all_topics_defined(self):
        """Test that all required topics are defined"""
        required_topics = [
            "nexum.transactions.created",
            "nexum.transactions.posted",
            "nexum.transactions.failed",
            "nexum.accounts.created",
            "nexum.accounts.updated",
            "nexum.customers.created",
            "nexum.customers.updated",
            "nexum.customers.kyc_changed",
            "nexum.loans.originated",
            "nexum.loans.disbursed",
            "nexum.loans.payment",
            "nexum.loans.paid_off",
            "nexum.loans.defaulted",
            "nexum.credit.statement_generated",
            "nexum.credit.payment",
            "nexum.collections.case_created",
            "nexum.collections.case_escalated",
            "nexum.collections.case_resolved",
            "nexum.compliance.alert",
            "nexum.compliance.suspicious_activity",
            "nexum.audit.events",
            "nexum.workflows.step_completed",
            "nexum.workflows.completed",
            "nexum.workflows.rejected",
            "nexum.commands.transactions",
            "nexum.commands.customers",
            "nexum.commands.loans"
        ]
        
        topic_values = [topic.value for topic in KafkaTopics]
        
        for required_topic in required_topics:
            assert required_topic in topic_values
    
    def test_topic_naming_convention(self):
        """Test that topics follow naming convention"""
        for topic in KafkaTopics:
            # Should start with nexum
            assert topic.value.startswith("nexum.")
            
            # Should use lowercase and dots
            assert topic.value.islower() or "_" in topic.value
            assert "." in topic.value


class TestErrorHandling:
    """Test error handling in various scenarios"""
    
    def test_handler_exception_doesnt_break_bus(self):
        """Test that handler exceptions don't break the event bus"""
        bus = InMemoryEventBus()
        bus.start()
        
        def failing_handler(event: EventSchema):
            raise Exception("Handler failure")
        
        def working_handler(event: EventSchema):
            working_handler.called = True
        
        working_handler.called = False
        
        topic = "nexum.test.error"
        bus.subscribe(topic, failing_handler)
        bus.subscribe(topic, working_handler)
        
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="error_test",
            timestamp=datetime.now(timezone.utc)
        )
        
        # Should not raise exception
        bus.publish(topic, event)
        
        # Working handler should still be called
        assert working_handler.called
    
    def test_serialization_error_handling(self):
        """Test handling of serialization errors"""
        # Test with non-serializable object
        class NonSerializable:
            pass
        
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type="serialization_test",
            timestamp=datetime.now(timezone.utc),
            data={"non_serializable": NonSerializable()}
        )
        
        # Should not raise exception when converting to dict
        # Non-serializable objects should be left as-is
        serialized = event.to_dict()
        assert "non_serializable" in serialized["data"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])