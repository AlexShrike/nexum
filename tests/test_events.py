"""
Tests for the Event System (Observer Pattern)

Tests the new event dispatcher and integration with domain objects.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from core_banking.events import (
    DomainEvent, EventPayload, EventDispatcher, 
    create_transaction_event, create_account_event, create_customer_event,
    get_global_dispatcher, set_global_dispatcher
)
from core_banking.transactions import TransactionProcessor, TransactionType, TransactionChannel
from core_banking.accounts import AccountManager, ProductType, AccountState
from core_banking.customers import CustomerManager, KYCStatus, KYCTier
from core_banking.currency import Money, Currency


class TestEventPayload:
    """Test EventPayload creation and serialization"""
    
    def test_event_payload_creation(self):
        """Test creating event payloads"""
        event = EventPayload(
            event_type=DomainEvent.TRANSACTION_CREATED,
            entity_type="transaction",
            entity_id="test-123",
            data={"amount": "100.00", "currency": "USD"}
        )
        
        assert event.event_type == DomainEvent.TRANSACTION_CREATED
        assert event.entity_type == "transaction"
        assert event.entity_id == "test-123"
        assert event.data["amount"] == "100.00"
        assert isinstance(event.timestamp, datetime)
        assert len(event.event_id) > 0
    
    def test_event_payload_serialization(self):
        """Test event payload to/from dict"""
        original = EventPayload(
            event_type=DomainEvent.ACCOUNT_CREATED,
            entity_type="account", 
            entity_id="acc-456",
            data={"balance": "0.00"}
        )
        
        # Convert to dict
        event_dict = original.to_dict()
        assert event_dict['event_type'] == DomainEvent.ACCOUNT_CREATED.value
        assert event_dict['entity_type'] == "account"
        assert event_dict['entity_id'] == "acc-456"
        
        # Convert back from dict
        restored = EventPayload.from_dict(event_dict)
        assert restored.event_type == original.event_type
        assert restored.entity_type == original.entity_type
        assert restored.entity_id == original.entity_id
        assert restored.data == original.data
        assert restored.event_id == original.event_id


class TestEventDispatcher:
    """Test the event dispatcher"""
    
    def test_subscribe_and_publish_single_event(self):
        """Test subscribing to a single event type and publishing"""
        dispatcher = EventDispatcher()
        handler = Mock()
        
        # Subscribe to transaction events
        dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, handler)
        
        # Create and publish event
        event = EventPayload(
            event_type=DomainEvent.TRANSACTION_CREATED,
            entity_type="transaction",
            entity_id="test-123",
            data={}
        )
        dispatcher.publish(event)
        
        # Verify handler was called
        handler.assert_called_once_with(event)
    
    def test_subscribe_multiple_event_types(self):
        """Test subscribing to multiple event types"""
        dispatcher = EventDispatcher()
        transaction_handler = Mock()
        account_handler = Mock()
        
        # Subscribe to different event types
        dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, transaction_handler)
        dispatcher.subscribe(DomainEvent.ACCOUNT_CREATED, account_handler)
        
        # Publish transaction event
        tx_event = EventPayload(
            event_type=DomainEvent.TRANSACTION_CREATED,
            entity_type="transaction",
            entity_id="tx-123",
            data={}
        )
        dispatcher.publish(tx_event)
        
        # Publish account event
        acc_event = EventPayload(
            event_type=DomainEvent.ACCOUNT_CREATED,
            entity_type="account",
            entity_id="acc-456",
            data={}
        )
        dispatcher.publish(acc_event)
        
        # Verify correct handlers were called
        transaction_handler.assert_called_once_with(tx_event)
        account_handler.assert_called_once_with(acc_event)
    
    def test_global_handler_receives_all_events(self):
        """Test global handlers receive all events"""
        dispatcher = EventDispatcher()
        global_handler = Mock()
        specific_handler = Mock()
        
        # Subscribe to all events and specific event
        dispatcher.subscribe_all(global_handler)
        dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, specific_handler)
        
        # Publish different events
        tx_event = EventPayload(DomainEvent.TRANSACTION_CREATED, "transaction", "tx-123", {})
        acc_event = EventPayload(DomainEvent.ACCOUNT_CREATED, "account", "acc-456", {})
        
        dispatcher.publish(tx_event)
        dispatcher.publish(acc_event)
        
        # Global handler should receive both events
        assert global_handler.call_count == 2
        global_handler.assert_any_call(tx_event)
        global_handler.assert_any_call(acc_event)
        
        # Specific handler should only receive transaction event
        specific_handler.assert_called_once_with(tx_event)
    
    def test_unsubscribe_works(self):
        """Test unsubscribing from events"""
        dispatcher = EventDispatcher()
        handler = Mock()
        
        # Subscribe then unsubscribe
        dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, handler)
        dispatcher.unsubscribe(DomainEvent.TRANSACTION_CREATED, handler)
        
        # Publish event
        event = EventPayload(DomainEvent.TRANSACTION_CREATED, "transaction", "tx-123", {})
        dispatcher.publish(event)
        
        # Handler should not be called
        handler.assert_not_called()
    
    def test_handler_exceptions_dont_break_publisher(self):
        """Test that exceptions in handlers don't break event publishing"""
        dispatcher = EventDispatcher()
        
        # Create handlers - one that throws, one that works
        failing_handler = Mock(side_effect=Exception("Handler error"))
        working_handler = Mock()
        
        dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, failing_handler)
        dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, working_handler)
        
        # Publish event - should not raise exception
        event = EventPayload(DomainEvent.TRANSACTION_CREATED, "transaction", "tx-123", {})
        dispatcher.publish(event)  # Should not raise
        
        # Both handlers should be called
        failing_handler.assert_called_once()
        working_handler.assert_called_once()
    
    def test_handler_counts(self):
        """Test getting handler counts"""
        dispatcher = EventDispatcher()
        
        handler1 = Mock()
        handler2 = Mock()
        global_handler = Mock()
        
        # Initially no handlers
        assert dispatcher.get_handler_count() == 0
        assert dispatcher.get_handler_count(DomainEvent.TRANSACTION_CREATED) == 0
        
        # Add specific handlers
        dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, handler1)
        dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, handler2)
        assert dispatcher.get_handler_count(DomainEvent.TRANSACTION_CREATED) == 2
        
        # Add global handler
        dispatcher.subscribe_all(global_handler)
        assert dispatcher.get_handler_count() == 3  # 2 specific + 1 global
        
        # Test subscribed events
        subscribed_events = dispatcher.get_subscribed_events()
        assert DomainEvent.TRANSACTION_CREATED in subscribed_events
        assert len(subscribed_events) == 1
    
    def test_clear_all_handlers(self):
        """Test clearing all handlers"""
        dispatcher = EventDispatcher()
        
        handler = Mock()
        global_handler = Mock()
        
        dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, handler)
        dispatcher.subscribe_all(global_handler)
        
        assert dispatcher.get_handler_count() == 2
        
        dispatcher.clear()
        
        assert dispatcher.get_handler_count() == 0
        assert len(dispatcher.get_subscribed_events()) == 0


class TestGlobalDispatcher:
    """Test global dispatcher singleton"""
    
    def test_get_global_dispatcher(self):
        """Test getting global dispatcher"""
        dispatcher = get_global_dispatcher()
        assert isinstance(dispatcher, EventDispatcher)
        
        # Should return same instance
        dispatcher2 = get_global_dispatcher()
        assert dispatcher is dispatcher2
    
    def test_set_global_dispatcher(self):
        """Test setting custom global dispatcher"""
        custom_dispatcher = EventDispatcher()
        set_global_dispatcher(custom_dispatcher)
        
        retrieved = get_global_dispatcher()
        assert retrieved is custom_dispatcher
        
        # Reset to clean up
        set_global_dispatcher(EventDispatcher())


class TestEventFactoryFunctions:
    """Test event creation factory functions"""
    
    def test_create_transaction_event(self):
        """Test creating transaction events"""
        # Mock transaction object
        transaction = Mock()
        transaction.id = "tx-123"
        transaction.transaction_type.value = "deposit"
        transaction.amount.amount = Decimal("100.00")
        transaction.currency.code = "USD"
        transaction.from_account_id = None
        transaction.to_account_id = "acc-456"
        transaction.description = "Test deposit"
        transaction.channel.value = "online"
        transaction.state.value = "pending"
        
        event = create_transaction_event(DomainEvent.TRANSACTION_CREATED, transaction)
        
        assert event.event_type == DomainEvent.TRANSACTION_CREATED
        assert event.entity_type == "transaction"
        assert event.entity_id == "tx-123"
        assert event.data["transaction_type"] == "deposit"
        assert event.data["amount"] == "100.00"
        assert event.data["currency"] == "USD"
        assert event.data["from_account_id"] is None
        assert event.data["to_account_id"] == "acc-456"
    
    def test_create_account_event(self):
        """Test creating account events"""
        # Mock account object
        account = Mock()
        account.id = "acc-456"
        account.account_number = "1234567890"
        account.customer_id = "cust-789"
        account.product_type.value = "savings"
        account.status.value = "active"
        account.current_balance.amount = Decimal("500.00")
        account.currency.code = "USD"
        
        event = create_account_event(DomainEvent.ACCOUNT_CREATED, account)
        
        assert event.event_type == DomainEvent.ACCOUNT_CREATED
        assert event.entity_type == "account"
        assert event.entity_id == "acc-456"
        assert event.data["account_number"] == "1234567890"
        assert event.data["customer_id"] == "cust-789"
        assert event.data["product_type"] == "savings"
        assert event.data["status"] == "active"
        assert event.data["balance"] == "500.00"
    
    def test_create_customer_event(self):
        """Test creating customer events"""
        # Mock customer object
        customer = Mock()
        customer.id = "cust-789"
        customer.customer_number = "C001234"
        customer.first_name = "John"
        customer.last_name = "Doe"
        customer.email = "john@example.com"
        customer.status.value = "active"
        customer.kyc_status.value = "verified"
        customer.kyc_tier = "TIER_2"
        
        event = create_customer_event(DomainEvent.CUSTOMER_CREATED, customer)
        
        assert event.event_type == DomainEvent.CUSTOMER_CREATED
        assert event.entity_type == "customer"
        assert event.entity_id == "cust-789"
        assert event.data["customer_number"] == "C001234"
        assert event.data["first_name"] == "John"
        assert event.data["last_name"] == "Doe"
        assert event.data["email"] == "john@example.com"


