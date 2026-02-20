"""
Kafka event bridge — Nexum publishes transaction events for Bastion to consume,
and consumes fraud decision events from Bastion.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from decimal import Decimal

from .events import DomainEvent, EventDispatcher, EventPayload, get_global_dispatcher
from .kafka_integration import EventBus, EventSchema, InMemoryEventBus

# Topic constants - shared contract between Nexum and Bastion
NEXUM_TRANSACTION_TOPIC = "nexum.transactions"
NEXUM_CUSTOMER_TOPIC = "nexum.customers"
BASTION_DECISIONS_TOPIC = "bastion.fraud.decisions"
BASTION_ALERTS_TOPIC = "bastion.fraud.alerts"

logger = logging.getLogger(__name__)


class TransactionEvent:
    """Published by Nexum when a transaction is processed"""
    schema = {
        "event_type": "transaction.processed",
        "transaction_id": "string",
        "amount": "decimal_string",
        "currency": "string",
        "from_account_id": "string",
        "to_account_id": "string", 
        "customer_id": "string",
        "transaction_type": "string",  # DEPOSIT, WITHDRAWAL, TRANSFER, etc.
        "channel": "string",  # ONLINE, BRANCH, ATM, etc.
        "description": "string",
        "timestamp": "iso8601",
        "metadata": "dict"
    }


class FraudDecisionEvent:
    """Published by Bastion after scoring a transaction"""
    schema = {
        "event_type": "fraud.decision",
        "transaction_id": "string",
        "score": "float",
        "decision": "string",  # APPROVE, REVIEW, BLOCK
        "risk_level": "string",
        "reasons": "list[string]",
        "timestamp": "iso8601"
    }


class FraudAlertEvent:
    """Published by Bastion when suspicious patterns detected"""
    schema = {
        "event_type": "fraud.alert",
        "alert_id": "string",
        "customer_id": "string",
        "alert_type": "string",  # VELOCITY, PATTERN, NETWORK, etc.
        "severity": "string",
        "description": "string",
        "related_transactions": "list[string]",
        "timestamp": "iso8601"
    }


class FraudEventBridge:
    """Bridge between Nexum's internal events and Kafka topics for Bastion integration.
    
    Responsibilities:
    1. Listen to Nexum's TRANSACTION_POSTED events
    2. Publish them to Kafka for Bastion consumption
    3. Consume fraud decisions from Bastion
    4. Update transaction metadata and trigger compliance alerts
    """
    
    def __init__(self, event_bus: EventBus, storage=None, compliance_manager=None):
        """
        Args:
            event_bus: Kafka event bus for publishing/consuming
            storage: Storage interface for updating transaction metadata
            compliance_manager: Manager for creating compliance alerts
        """
        self.event_bus = event_bus
        self.storage = storage
        self.compliance_manager = compliance_manager
        self.running = False
        self._lock = threading.RLock()
        
        # Subscribe to Nexum's internal events
        self.event_dispatcher = get_global_dispatcher()
        
    def start(self) -> None:
        """Start the fraud event bridge"""
        with self._lock:
            if self.running:
                return
                
            try:
                # Subscribe to internal Nexum events
                self.event_dispatcher.subscribe(DomainEvent.TRANSACTION_POSTED, self._on_transaction_posted)
                self.event_dispatcher.subscribe(DomainEvent.CUSTOMER_CREATED, self._on_customer_created)
                self.event_dispatcher.subscribe(DomainEvent.CUSTOMER_UPDATED, self._on_customer_updated)
                
                # Subscribe to Bastion fraud events via Kafka
                self.event_bus.subscribe(BASTION_DECISIONS_TOPIC, self._on_fraud_decision)
                self.event_bus.subscribe(BASTION_ALERTS_TOPIC, self._on_fraud_alert)
                
                # Start the event bus if not already running
                if not self.event_bus.is_running():
                    self.event_bus.start()
                
                self.running = True
                logger.info("FraudEventBridge started")
                
            except Exception as e:
                logger.error(f"Failed to start FraudEventBridge: {e}")
                raise
    
    def stop(self) -> None:
        """Stop the fraud event bridge"""
        with self._lock:
            if not self.running:
                return
                
            try:
                # Unsubscribe from internal events
                self.event_dispatcher.unsubscribe(DomainEvent.TRANSACTION_POSTED, self._on_transaction_posted)
                self.event_dispatcher.unsubscribe(DomainEvent.CUSTOMER_CREATED, self._on_customer_created)
                self.event_dispatcher.unsubscribe(DomainEvent.CUSTOMER_UPDATED, self._on_customer_updated)
                
                self.running = False
                logger.info("FraudEventBridge stopped")
                
            except Exception as e:
                logger.error(f"Error stopping FraudEventBridge: {e}")
    
    def _on_transaction_posted(self, event: EventPayload) -> None:
        """Handle TRANSACTION_POSTED events from Nexum"""
        try:
            # Convert internal event to Kafka event for Bastion
            kafka_event = EventSchema(
                event_id=event.event_id,
                event_type="transaction.processed",
                timestamp=datetime.now(timezone.utc),
                source="nexum",
                entity_type="transaction",
                entity_id=event.entity_id,
                data={
                    "transaction_id": event.entity_id,
                    "amount": event.data.get("amount", "0"),
                    "currency": event.data.get("currency", "USD"),
                    "from_account_id": event.data.get("from_account_id"),
                    "to_account_id": event.data.get("to_account_id"),
                    "customer_id": self._extract_customer_id(event.data),
                    "transaction_type": event.data.get("transaction_type", "UNKNOWN"),
                    "channel": event.data.get("channel", "UNKNOWN"),
                    "description": event.data.get("description", ""),
                    "timestamp": event.timestamp.isoformat(),
                    "metadata": self._build_metadata(event.data)
                }
            )
            
            # Publish to Kafka for Bastion
            self.event_bus.publish(NEXUM_TRANSACTION_TOPIC, kafka_event, key=event.entity_id)
            logger.debug(f"Published transaction {event.entity_id} to Bastion")
            
        except Exception as e:
            logger.error(f"Failed to publish transaction event: {e}")
    
    def _on_customer_created(self, event: EventPayload) -> None:
        """Handle CUSTOMER_CREATED events from Nexum"""
        try:
            kafka_event = EventSchema(
                event_id=event.event_id,
                event_type="customer.created",
                timestamp=datetime.now(timezone.utc),
                source="nexum",
                entity_type="customer",
                entity_id=event.entity_id,
                data={
                    "customer_id": event.entity_id,
                    "first_name": event.data.get("first_name"),
                    "last_name": event.data.get("last_name"),
                    "email": event.data.get("email"),
                    "phone": event.data.get("phone"),
                    "kyc_status": event.data.get("kyc_status", "UNKNOWN"),
                    "kyc_tier": event.data.get("kyc_tier"),
                    "timestamp": event.timestamp.isoformat()
                }
            )
            
            self.event_bus.publish(NEXUM_CUSTOMER_TOPIC, kafka_event, key=event.entity_id)
            logger.debug(f"Published customer {event.entity_id} to Bastion")
            
        except Exception as e:
            logger.error(f"Failed to publish customer event: {e}")
    
    def _on_customer_updated(self, event: EventPayload) -> None:
        """Handle CUSTOMER_UPDATED events from Nexum"""
        try:
            kafka_event = EventSchema(
                event_id=event.event_id,
                event_type="customer.updated",
                timestamp=datetime.now(timezone.utc),
                source="nexum",
                entity_type="customer", 
                entity_id=event.entity_id,
                data={
                    "customer_id": event.entity_id,
                    "first_name": event.data.get("first_name"),
                    "last_name": event.data.get("last_name"),
                    "email": event.data.get("email"),
                    "phone": event.data.get("phone"),
                    "timestamp": event.timestamp.isoformat()
                }
            )
            
            self.event_bus.publish(NEXUM_CUSTOMER_TOPIC, kafka_event, key=event.entity_id)
            logger.debug(f"Published customer update {event.entity_id} to Bastion")
            
        except Exception as e:
            logger.error(f"Failed to publish customer update event: {e}")
    
    def _on_fraud_decision(self, event: EventSchema) -> None:
        """Handle fraud decision events from Bastion"""
        try:
            transaction_id = event.data.get("transaction_id")
            if not transaction_id:
                logger.warning("Fraud decision missing transaction_id")
                return
                
            fraud_score = event.data.get("score", 0.0)
            decision = event.data.get("decision", "UNKNOWN")
            risk_level = event.data.get("risk_level", "UNKNOWN")
            reasons = event.data.get("reasons", [])
            
            logger.info(f"Received fraud decision for transaction {transaction_id}: {decision} (score={fraud_score})")
            
            # Update transaction metadata if storage is available
            if self.storage:
                try:
                    transaction = self.storage.get_transaction(transaction_id)
                    if transaction:
                        # Update fraud metadata
                        if not hasattr(transaction, 'metadata'):
                            transaction.metadata = {}
                        
                        transaction.metadata.update({
                            'fraud_score': fraud_score,
                            'fraud_decision': decision,
                            'fraud_risk_level': risk_level,
                            'fraud_reasons': reasons,
                            'fraud_timestamp': event.timestamp.isoformat()
                        })
                        
                        self.storage.save_transaction(transaction)
                        logger.debug(f"Updated transaction {transaction_id} with fraud decision")
                        
                except Exception as e:
                    logger.error(f"Failed to update transaction {transaction_id}: {e}")
            
            # Create compliance alert for REVIEW/BLOCK decisions
            if decision in ("REVIEW", "BLOCK") and self.compliance_manager:
                try:
                    alert_data = {
                        "type": "FRAUD_DETECTION",
                        "severity": "HIGH" if decision == "BLOCK" else "MEDIUM",
                        "transaction_id": transaction_id,
                        "description": f"Fraud detection: {decision} (score={fraud_score})",
                        "reasons": reasons,
                        "score": fraud_score,
                        "decision": decision,
                        "risk_level": risk_level
                    }
                    
                    self.compliance_manager.create_alert(alert_data)
                    logger.info(f"Created compliance alert for transaction {transaction_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to create compliance alert: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to process fraud decision: {e}")
    
    def _on_fraud_alert(self, event: EventSchema) -> None:
        """Handle fraud alert events from Bastion"""
        try:
            customer_id = event.data.get("customer_id")
            alert_type = event.data.get("alert_type", "UNKNOWN")
            severity = event.data.get("severity", "MEDIUM")
            description = event.data.get("description", "")
            related_transactions = event.data.get("related_transactions", [])
            
            logger.info(f"Received fraud alert for customer {customer_id}: {alert_type}")
            
            # Create compliance alert if compliance manager is available
            if self.compliance_manager:
                try:
                    alert_data = {
                        "type": "FRAUD_PATTERN",
                        "severity": severity,
                        "customer_id": customer_id,
                        "description": f"Fraud pattern detected: {alert_type} - {description}",
                        "alert_type": alert_type,
                        "related_transactions": related_transactions,
                        "source": "bastion"
                    }
                    
                    self.compliance_manager.create_alert(alert_data)
                    logger.info(f"Created compliance alert for customer {customer_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to create compliance alert from fraud alert: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to process fraud alert: {e}")
    
    def _extract_customer_id(self, transaction_data: Dict[str, Any]) -> Optional[str]:
        """Extract customer ID from transaction data"""
        # Try different possible field names
        for field in ["customer_id", "cif_id", "from_customer_id"]:
            if transaction_data.get(field):
                return transaction_data[field]
        return None
    
    def _build_metadata(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build metadata dict for Bastion consumption"""
        metadata = {}
        
        # Add any additional fields that might be useful for fraud detection
        for field in ["device_id", "ip_address", "user_agent", "geolocation", 
                     "reference", "correlation_id", "user_id"]:
            if transaction_data.get(field):
                metadata[field] = transaction_data[field]
        
        return metadata
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the bridge"""
        return {
            "running": self.running,
            "event_bus_running": self.event_bus.is_running() if self.event_bus else False,
            "subscribed_topics": [
                BASTION_DECISIONS_TOPIC,
                BASTION_ALERTS_TOPIC
            ],
            "published_topics": [
                NEXUM_TRANSACTION_TOPIC,
                NEXUM_CUSTOMER_TOPIC
            ]
        }


# Utility functions for easy integration

def create_fraud_bridge(event_bus: Optional[EventBus] = None, **kwargs) -> FraudEventBridge:
    """Create a fraud event bridge with default configuration"""
    if event_bus is None:
        # Default to in-memory for testing/development
        event_bus = InMemoryEventBus()
        
    return FraudEventBridge(event_bus, **kwargs)


def start_fraud_bridge_with_storage(storage, compliance_manager=None, 
                                  kafka_config: Optional[Dict] = None) -> FraudEventBridge:
    """Start fraud bridge with storage integration"""
    from .kafka_integration import KafkaEventBus, LogEventBus
    
    # Try to create Kafka event bus, fall back to logging
    try:
        if kafka_config:
            event_bus = KafkaEventBus(**kafka_config)
        else:
            logger.warning("No Kafka config provided, using LogEventBus")
            event_bus = LogEventBus()
    except Exception as e:
        logger.warning(f"Failed to create Kafka event bus: {e}, using LogEventBus")
        event_bus = LogEventBus()
    
    bridge = FraudEventBridge(event_bus, storage, compliance_manager)
    bridge.start()
    
    return bridge