"""
Tests for fraud event bridge integration with Bastion
"""

import json
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch, call

from core_banking.fraud_events import (
    FraudEventBridge, 
    TransactionEvent, 
    FraudDecisionEvent,
    FraudAlertEvent,
    NEXUM_TRANSACTION_TOPIC,
    NEXUM_CUSTOMER_TOPIC,
    BASTION_DECISIONS_TOPIC,
    BASTION_ALERTS_TOPIC
)
from core_banking.events import DomainEvent, EventPayload, EventDispatcher
from core_banking.kafka_integration import InMemoryEventBus, EventSchema


class TestEventSchemas:
    """Test event schema definitions"""
    
    def test_transaction_event_schema(self):
        """Test transaction event schema structure"""
        schema = TransactionEvent.schema
        
        assert schema["event_type"] == "transaction.processed"
        assert "transaction_id" in schema
        assert "amount" in schema
        assert "currency" in schema
        assert "customer_id" in schema
        assert "transaction_type" in schema
        assert "channel" in schema
        
    def test_fraud_decision_event_schema(self):
        """Test fraud decision event schema structure"""
        schema = FraudDecisionEvent.schema
        
        assert schema["event_type"] == "fraud.decision"
        assert "transaction_id" in schema
        assert "score" in schema
        assert "decision" in schema
        assert "risk_level" in schema
        assert "reasons" in schema
        
    def test_fraud_alert_event_schema(self):
        """Test fraud alert event schema structure"""
        schema = FraudAlertEvent.schema
        
        assert schema["event_type"] == "fraud.alert"
        assert "alert_id" in schema
        assert "customer_id" in schema
        assert "alert_type" in schema
        assert "severity" in schema
        assert "related_transactions" in schema


class TestFraudEventBridge:
    """Test FraudEventBridge functionality"""
    
    @pytest.fixture
    def event_bus(self):
        """Create in-memory event bus for testing"""
        return InMemoryEventBus()
    
    @pytest.fixture
    def mock_storage(self):
        """Create mock storage interface"""
        storage = Mock()
        storage.get_transaction.return_value = Mock()
        return storage
    
    @pytest.fixture
    def mock_compliance_manager(self):
        """Create mock compliance manager"""
        return Mock()
    
    @pytest.fixture
    def event_dispatcher(self):
        """Create event dispatcher for testing"""
        return EventDispatcher()
    
    @pytest.fixture
    def fraud_bridge(self, event_bus, mock_storage, mock_compliance_manager):
        """Create fraud event bridge"""
        with patch('core_banking.fraud_events.get_global_dispatcher') as mock_dispatcher:
            dispatcher = EventDispatcher()
            mock_dispatcher.return_value = dispatcher
            
            bridge = FraudEventBridge(
                event_bus=event_bus,
                storage=mock_storage,
                compliance_manager=mock_compliance_manager
            )
            bridge.event_dispatcher = dispatcher
            return bridge
    
    def test_bridge_initialization(self, fraud_bridge):
        """Test bridge initialization"""
        assert fraud_bridge.running is False
        assert fraud_bridge.event_bus is not None
        assert fraud_bridge.storage is not None
        assert fraud_bridge.compliance_manager is not None
    
    def test_bridge_start_stop(self, fraud_bridge):
        """Test starting and stopping the bridge"""
        # Start bridge
        fraud_bridge.start()
        assert fraud_bridge.running is True
        assert fraud_bridge.event_bus.is_running() is True
        
        # Stop bridge
        fraud_bridge.stop()
        assert fraud_bridge.running is False
    
    def test_transaction_posted_event_handling(self, fraud_bridge):
        """Test handling of TRANSACTION_POSTED events"""
        fraud_bridge.start()
        
        # Create transaction posted event
        event = EventPayload(
            event_type=DomainEvent.TRANSACTION_POSTED,
            entity_type="transaction",
            entity_id="txn-123",
            data={
                "transaction_type": "TRANSFER",
                "amount": "100.50",
                "currency": "USD",
                "from_account_id": "acc-1",
                "to_account_id": "acc-2",
                "description": "Test transfer",
                "channel": "ONLINE",
                "from_customer_id": "cust-456"
            }
        )
        
        # Publish internal event
        fraud_bridge.event_dispatcher.publish(event)
        
        # Check that Kafka event was published
        kafka_events = fraud_bridge.event_bus.get_events(NEXUM_TRANSACTION_TOPIC)
        assert len(kafka_events) == 1
        
        topic, kafka_event, key = kafka_events[0]
        assert topic == NEXUM_TRANSACTION_TOPIC
        assert key == "txn-123"
        assert kafka_event.event_type == "transaction.processed"
        assert kafka_event.data["transaction_id"] == "txn-123"
        assert kafka_event.data["amount"] == "100.50"
        assert kafka_event.data["currency"] == "USD"
        assert kafka_event.data["customer_id"] == "cust-456"
    
    def test_customer_created_event_handling(self, fraud_bridge):
        """Test handling of CUSTOMER_CREATED events"""
        fraud_bridge.start()
        
        # Create customer created event
        event = EventPayload(
            event_type=DomainEvent.CUSTOMER_CREATED,
            entity_type="customer",
            entity_id="cust-789",
            data={
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "phone": "+1234567890",
                "kyc_status": "VERIFIED",
                "kyc_tier": "TIER_1"
            }
        )
        
        # Publish internal event
        fraud_bridge.event_dispatcher.publish(event)
        
        # Check that Kafka event was published
        kafka_events = fraud_bridge.event_bus.get_events(NEXUM_CUSTOMER_TOPIC)
        assert len(kafka_events) == 1
        
        topic, kafka_event, key = kafka_events[0]
        assert topic == NEXUM_CUSTOMER_TOPIC
        assert key == "cust-789"
        assert kafka_event.event_type == "customer.created"
        assert kafka_event.data["customer_id"] == "cust-789"
        assert kafka_event.data["first_name"] == "John"
        assert kafka_event.data["last_name"] == "Doe"
    
    def test_fraud_decision_consumption(self, fraud_bridge, mock_storage):
        """Test consuming fraud decision events from Bastion"""
        fraud_bridge.start()
        
        # Mock transaction for update
        mock_transaction = Mock()
        mock_transaction.metadata = {}
        mock_storage.get_transaction.return_value = mock_transaction
        
        # Create fraud decision event
        decision_event = EventSchema(
            event_id="decision-123",
            event_type="fraud.decision",
            timestamp=datetime.now(timezone.utc),
            source="bastion",
            data={
                "transaction_id": "txn-456",
                "score": 0.75,
                "decision": "BLOCK",
                "risk_level": "HIGH",
                "reasons": ["High velocity", "Unusual location"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Simulate receiving decision from Bastion
        fraud_bridge._on_fraud_decision(decision_event)
        
        # Check transaction was updated
        mock_storage.get_transaction.assert_called_once_with("txn-456")
        mock_storage.save_transaction.assert_called_once_with(mock_transaction)
        
        # Check metadata was updated
        assert mock_transaction.metadata["fraud_score"] == 0.75
        assert mock_transaction.metadata["fraud_decision"] == "BLOCK"
        assert mock_transaction.metadata["fraud_risk_level"] == "HIGH"
        assert "High velocity" in mock_transaction.metadata["fraud_reasons"]
        
        # Check compliance alert was created
        fraud_bridge.compliance_manager.create_alert.assert_called_once()
        alert_data = fraud_bridge.compliance_manager.create_alert.call_args[0][0]
        assert alert_data["type"] == "FRAUD_DETECTION"
        assert alert_data["severity"] == "HIGH"
        assert alert_data["transaction_id"] == "txn-456"
    
    def test_fraud_alert_consumption(self, fraud_bridge):
        """Test consuming fraud alert events from Bastion"""
        fraud_bridge.start()
        
        # Create fraud alert event
        alert_event = EventSchema(
            event_id="alert-123",
            event_type="fraud.alert",
            timestamp=datetime.now(timezone.utc),
            source="bastion",
            data={
                "alert_id": "alert-789",
                "customer_id": "cust-456",
                "alert_type": "VELOCITY",
                "severity": "HIGH",
                "description": "Multiple large transactions in short period",
                "related_transactions": ["txn-1", "txn-2", "txn-3"]
            }
        )
        
        # Simulate receiving alert from Bastion
        fraud_bridge._on_fraud_alert(alert_event)
        
        # Check compliance alert was created
        fraud_bridge.compliance_manager.create_alert.assert_called_once()
        alert_data = fraud_bridge.compliance_manager.create_alert.call_args[0][0]
        assert alert_data["type"] == "FRAUD_PATTERN"
        assert alert_data["customer_id"] == "cust-456"
        assert alert_data["alert_type"] == "VELOCITY"
        assert alert_data["severity"] == "HIGH"
        assert len(alert_data["related_transactions"]) == 3
    
    def test_graceful_degradation_missing_transaction_id(self, fraud_bridge):
        """Test handling of malformed fraud decision events"""
        fraud_bridge.start()
        
        # Create decision event without transaction_id
        decision_event = EventSchema(
            event_id="decision-123",
            event_type="fraud.decision",
            timestamp=datetime.now(timezone.utc),
            source="bastion",
            data={
                "score": 0.5,
                "decision": "REVIEW",
                "risk_level": "MEDIUM"
            }
        )
        
        # Should handle gracefully without crashing
        fraud_bridge._on_fraud_decision(decision_event)
        
        # Storage should not be called
        fraud_bridge.storage.get_transaction.assert_not_called()
    
    def test_graceful_degradation_storage_error(self, fraud_bridge, mock_storage):
        """Test handling of storage errors during transaction update"""
        fraud_bridge.start()
        
        # Mock storage error
        mock_storage.get_transaction.side_effect = Exception("Storage error")
        
        # Create fraud decision event
        decision_event = EventSchema(
            event_id="decision-123",
            event_type="fraud.decision", 
            timestamp=datetime.now(timezone.utc),
            source="bastion",
            data={
                "transaction_id": "txn-456",
                "score": 0.5,
                "decision": "REVIEW",
                "risk_level": "MEDIUM",
                "reasons": []
            }
        )
        
        # Should handle gracefully without crashing
        fraud_bridge._on_fraud_decision(decision_event)
        
        # Storage was attempted but failed
        mock_storage.get_transaction.assert_called_once_with("txn-456")
    
    def test_customer_id_extraction(self, fraud_bridge):
        """Test extraction of customer ID from different field names"""
        # Test direct customer_id
        data1 = {"customer_id": "cust-123"}
        assert fraud_bridge._extract_customer_id(data1) == "cust-123"
        
        # Test cif_id fallback
        data2 = {"cif_id": "cif-456"}
        assert fraud_bridge._extract_customer_id(data2) == "cif-456"
        
        # Test from_customer_id fallback
        data3 = {"from_customer_id": "from-789"}
        assert fraud_bridge._extract_customer_id(data3) == "from-789"
        
        # Test missing customer ID
        data4 = {"transaction_id": "txn-123"}
        assert fraud_bridge._extract_customer_id(data4) is None
    
    def test_metadata_building(self, fraud_bridge):
        """Test building metadata for Bastion consumption"""
        transaction_data = {
            "device_id": "device-123",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0...",
            "reference": "ref-456",
            "correlation_id": "corr-789",
            "extra_field": "ignored"
        }
        
        metadata = fraud_bridge._build_metadata(transaction_data)
        
        assert metadata["device_id"] == "device-123"
        assert metadata["ip_address"] == "192.168.1.1" 
        assert metadata["user_agent"] == "Mozilla/5.0..."
        assert metadata["reference"] == "ref-456"
        assert metadata["correlation_id"] == "corr-789"
        assert "extra_field" not in metadata
    
    def test_bridge_stats(self, fraud_bridge):
        """Test getting bridge statistics"""
        stats = fraud_bridge.get_stats()
        
        assert "running" in stats
        assert "event_bus_running" in stats
        assert "subscribed_topics" in stats
        assert "published_topics" in stats
        
        assert BASTION_DECISIONS_TOPIC in stats["subscribed_topics"]
        assert BASTION_ALERTS_TOPIC in stats["subscribed_topics"]
        assert NEXUM_TRANSACTION_TOPIC in stats["published_topics"]
        assert NEXUM_CUSTOMER_TOPIC in stats["published_topics"]


class TestFraudBridgeUtilities:
    """Test utility functions for fraud bridge"""
    
    def test_create_fraud_bridge_default(self):
        """Test creating fraud bridge with default event bus"""
        from core_banking.fraud_events import create_fraud_bridge
        
        bridge = create_fraud_bridge()
        assert bridge is not None
        assert bridge.event_bus is not None
        
    def test_create_fraud_bridge_custom(self):
        """Test creating fraud bridge with custom event bus"""
        from core_banking.fraud_events import create_fraud_bridge
        
        custom_bus = InMemoryEventBus()
        bridge = create_fraud_bridge(event_bus=custom_bus)
        assert bridge.event_bus is custom_bus
    
    @patch('core_banking.kafka_integration.KafkaEventBus')
    def test_start_fraud_bridge_with_kafka(self, mock_kafka_bus):
        """Test starting fraud bridge with Kafka configuration"""
        from core_banking.fraud_events import start_fraud_bridge_with_storage
        
        mock_storage = Mock()
        mock_compliance = Mock()
        kafka_config = {'bootstrap.servers': 'localhost:9092'}
        
        # Mock Kafka event bus
        mock_kafka_instance = Mock()
        mock_kafka_bus.return_value = mock_kafka_instance
        
        with patch('core_banking.fraud_events.get_global_dispatcher') as mock_dispatcher:
            mock_dispatcher.return_value = EventDispatcher()
            
            bridge = start_fraud_bridge_with_storage(
                storage=mock_storage,
                compliance_manager=mock_compliance,
                kafka_config=kafka_config
            )
            
            assert bridge is not None
            assert bridge.running is True
    
    @patch('core_banking.kafka_integration.LogEventBus')
    def test_start_fraud_bridge_fallback_to_log(self, mock_log_bus):
        """Test fallback to LogEventBus when Kafka fails"""
        from core_banking.fraud_events import start_fraud_bridge_with_storage
        
        mock_storage = Mock()
        mock_log_instance = Mock()
        mock_log_bus.return_value = mock_log_instance
        
        with patch('core_banking.fraud_events.get_global_dispatcher') as mock_dispatcher:
            mock_dispatcher.return_value = EventDispatcher()
            
            # No Kafka config should use LogEventBus
            bridge = start_fraud_bridge_with_storage(storage=mock_storage)
            
            assert bridge is not None
            mock_log_bus.assert_called_once()


@pytest.mark.integration
class TestFraudBridgeIntegration:
    """Integration tests for fraud event bridge"""
    
    def test_end_to_end_transaction_flow(self):
        """Test complete transaction fraud detection flow"""
        # This would be an integration test with actual Kafka
        # For now, using in-memory event bus
        
        event_bus = InMemoryEventBus()
        event_bus.start()
        
        mock_storage = Mock()
        mock_compliance = Mock()
        
        with patch('core_banking.fraud_events.get_global_dispatcher') as mock_dispatcher:
            dispatcher = EventDispatcher()
            mock_dispatcher.return_value = dispatcher
            
            bridge = FraudEventBridge(event_bus, mock_storage, mock_compliance)
            bridge.start()
            
            # Step 1: Transaction posted in Nexum
            txn_event = EventPayload(
                event_type=DomainEvent.TRANSACTION_POSTED,
                entity_type="transaction",
                entity_id="txn-integration-test",
                data={
                    "transaction_type": "TRANSFER",
                    "amount": "500.00",
                    "currency": "USD",
                    "from_account_id": "acc-1",
                    "to_account_id": "acc-2",
                    "from_customer_id": "cust-integration-test"
                }
            )
            
            dispatcher.publish(txn_event)
            
            # Step 2: Verify event published to Kafka
            kafka_events = event_bus.get_events(NEXUM_TRANSACTION_TOPIC)
            assert len(kafka_events) == 1
            
            # Step 3: Simulate fraud decision from Bastion
            decision_event = EventSchema(
                event_id="decision-integration",
                event_type="fraud.decision",
                timestamp=datetime.now(timezone.utc),
                source="bastion",
                data={
                    "transaction_id": "txn-integration-test",
                    "score": 0.85,
                    "decision": "BLOCK",
                    "risk_level": "HIGH",
                    "reasons": ["Integration test high risk"]
                }
            )
            
            # Mock transaction for storage update
            mock_transaction = Mock()
            mock_transaction.metadata = {}
            mock_storage.get_transaction.return_value = mock_transaction
            
            bridge._on_fraud_decision(decision_event)
            
            # Step 4: Verify transaction updated and alert created
            mock_storage.save_transaction.assert_called_once()
            mock_compliance.create_alert.assert_called_once()
            
            bridge.stop()