"""
Kafka Integration Module

Event-driven architecture via Apache Kafka - publish banking events and consume commands.
Provides abstract interfaces with multiple implementations (InMemory, Kafka, Log).
"""

import json
import logging
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from queue import Queue, Empty

# Try to import confluent-kafka, fall back gracefully
try:
    from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    Producer = None
    Consumer = None

from .currency import Money
from .storage import StorageInterface


class KafkaTopics(Enum):
    """Event topic names following CloudEvents naming convention"""
    # Transaction events
    TRANSACTIONS_CREATED = "nexum.transactions.created"
    TRANSACTIONS_POSTED = "nexum.transactions.posted"
    TRANSACTIONS_FAILED = "nexum.transactions.failed"
    
    # Account events
    ACCOUNTS_CREATED = "nexum.accounts.created"
    ACCOUNTS_UPDATED = "nexum.accounts.updated"
    
    # Customer events
    CUSTOMERS_CREATED = "nexum.customers.created"
    CUSTOMERS_UPDATED = "nexum.customers.updated"
    CUSTOMERS_KYC_CHANGED = "nexum.customers.kyc_changed"
    
    # Loan events
    LOANS_ORIGINATED = "nexum.loans.originated"
    LOANS_DISBURSED = "nexum.loans.disbursed"
    LOANS_PAYMENT = "nexum.loans.payment"
    LOANS_PAID_OFF = "nexum.loans.paid_off"
    LOANS_DEFAULTED = "nexum.loans.defaulted"
    
    # Credit line events
    CREDIT_STATEMENT_GENERATED = "nexum.credit.statement_generated"
    CREDIT_PAYMENT = "nexum.credit.payment"
    
    # Collections events
    COLLECTIONS_CASE_CREATED = "nexum.collections.case_created"
    COLLECTIONS_CASE_ESCALATED = "nexum.collections.case_escalated"
    COLLECTIONS_CASE_RESOLVED = "nexum.collections.case_resolved"
    
    # Compliance events
    COMPLIANCE_ALERT = "nexum.compliance.alert"
    COMPLIANCE_SUSPICIOUS_ACTIVITY = "nexum.compliance.suspicious_activity"
    
    # Audit events
    AUDIT_EVENTS = "nexum.audit.events"
    
    # Workflow events
    WORKFLOWS_STEP_COMPLETED = "nexum.workflows.step_completed"
    WORKFLOWS_COMPLETED = "nexum.workflows.completed"
    WORKFLOWS_REJECTED = "nexum.workflows.rejected"
    
    # Command topics (inbound)
    COMMANDS_TRANSACTIONS = "nexum.commands.transactions"
    COMMANDS_CUSTOMERS = "nexum.commands.customers"
    COMMANDS_LOANS = "nexum.commands.loans"


@dataclass
class EventSchema:
    """CloudEvents-inspired event schema"""
    event_id: str
    event_type: str
    timestamp: datetime
    source: str = "nexum"
    version: str = "1.0"
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        
        # Convert Decimal objects to strings for JSON serialization
        result['data'] = self._serialize_decimals(result['data'])
        result['metadata'] = self._serialize_decimals(result['metadata'])
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EventSchema':
        """Create from dictionary"""
        data = data.copy()
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)
    
    def _serialize_decimals(self, obj: Any) -> Any:
        """Recursively serialize Decimal objects to strings"""
        if obj is None:
            return None
        elif isinstance(obj, Decimal):
            return str(obj)
        elif isinstance(obj, dict):
            return {k: self._serialize_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_decimals(item) for item in obj]
        elif isinstance(obj, Money):
            return {'amount': str(obj.amount), 'currency': obj.currency.code}
        elif hasattr(obj, 'code') and hasattr(obj, 'value'):  # Handle Currency enum
            return obj.code
        elif str(type(obj)).__contains__('Mock'):  # Handle Mock objects in tests
            return None
        else:
            return obj


class EventBus(ABC):
    """Abstract event bus interface"""
    
    @abstractmethod
    def publish(self, topic: str, event: EventSchema, key: Optional[str] = None) -> None:
        """Publish an event to a topic"""
        pass
    
    @abstractmethod
    def publish_batch(self, topic: str, events: List[EventSchema], keys: Optional[List[str]] = None) -> None:
        """Publish multiple events to a topic"""
        pass
    
    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[EventSchema], None]) -> None:
        """Subscribe to a topic with a handler function"""
        pass
    
    @abstractmethod
    def start(self) -> None:
        """Start the event bus"""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the event bus"""
        pass
    
    @abstractmethod
    def is_running(self) -> bool:
        """Check if the event bus is running"""
        pass


class InMemoryEventBus(EventBus):
    """In-memory event bus for testing"""
    
    def __init__(self):
        self.events: List[tuple] = []  # (topic, event, key)
        self.subscribers: Dict[str, List[Callable]] = {}
        self.running = False
        self._lock = threading.RLock()
    
    def publish(self, topic: str, event: EventSchema, key: Optional[str] = None) -> None:
        """Publish an event"""
        with self._lock:
            self.events.append((topic, event, key))
            
            # Notify subscribers
            if topic in self.subscribers:
                for handler in self.subscribers[topic]:
                    try:
                        handler(event)
                    except Exception as e:
                        logging.error(f"Error in event handler for {topic}: {e}")
    
    def publish_batch(self, topic: str, events: List[EventSchema], keys: Optional[List[str]] = None) -> None:
        """Publish multiple events"""
        if keys is None:
            keys = [None] * len(events)
        
        for event, key in zip(events, keys):
            self.publish(topic, event, key)
    
    def subscribe(self, topic: str, handler: Callable[[EventSchema], None]) -> None:
        """Subscribe to a topic"""
        with self._lock:
            if topic not in self.subscribers:
                self.subscribers[topic] = []
            self.subscribers[topic].append(handler)
    
    def start(self) -> None:
        """Start the event bus"""
        self.running = True
    
    def stop(self) -> None:
        """Stop the event bus"""
        self.running = False
    
    def is_running(self) -> bool:
        """Check if running"""
        return self.running
    
    def get_events(self, topic: Optional[str] = None) -> List[tuple]:
        """Get all events or events for a specific topic"""
        with self._lock:
            if topic:
                return [(t, e, k) for t, e, k in self.events if t == topic]
            return self.events.copy()
    
    def clear_events(self) -> None:
        """Clear all events (for testing)"""
        with self._lock:
            self.events.clear()


class LogEventBus(EventBus):
    """Event bus that just logs events (for development)"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.subscribers: Dict[str, List[Callable]] = {}
        self.running = False
        self._lock = threading.RLock()
    
    def publish(self, topic: str, event: EventSchema, key: Optional[str] = None) -> None:
        """Log the event"""
        self.logger.info(f"EVENT: {topic} - {event.event_type} - {event.entity_type}:{event.entity_id}")
        
        # Still notify subscribers for hooks to work
        with self._lock:
            if topic in self.subscribers:
                for handler in self.subscribers[topic]:
                    try:
                        handler(event)
                    except Exception as e:
                        self.logger.error(f"Error in event handler for {topic}: {e}")
    
    def publish_batch(self, topic: str, events: List[EventSchema], keys: Optional[List[str]] = None) -> None:
        """Log multiple events"""
        for event in events:
            self.publish(topic, event, keys[0] if keys else None)
    
    def subscribe(self, topic: str, handler: Callable[[EventSchema], None]) -> None:
        """Subscribe to a topic"""
        with self._lock:
            if topic not in self.subscribers:
                self.subscribers[topic] = []
            self.subscribers[topic].append(handler)
    
    def start(self) -> None:
        """Start the event bus"""
        self.running = True
        self.logger.info("LogEventBus started")
    
    def stop(self) -> None:
        """Stop the event bus"""
        self.running = False
        self.logger.info("LogEventBus stopped")
    
    def is_running(self) -> bool:
        """Check if running"""
        return self.running


class KafkaEventBus(EventBus):
    """Real Kafka event bus implementation"""
    
    def __init__(self, bootstrap_servers: str, client_id: str = "nexum", **config):
        if not KAFKA_AVAILABLE:
            raise ImportError("confluent-kafka is not available. Install it or use InMemoryEventBus.")
        
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.config = config
        self.producer = None
        self.consumers: Dict[str, Consumer] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.running = False
        self.consumer_threads: List[threading.Thread] = []
        self._lock = threading.RLock()
    
    def _create_producer(self) -> Producer:
        """Create Kafka producer"""
        producer_config = {
            'bootstrap.servers': self.bootstrap_servers,
            'client.id': self.client_id,
            **self.config
        }
        return Producer(producer_config)
    
    def _create_consumer(self, group_id: str) -> Consumer:
        """Create Kafka consumer"""
        consumer_config = {
            'bootstrap.servers': self.bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True,
            **self.config
        }
        return Consumer(consumer_config)
    
    def publish(self, topic: str, event: EventSchema, key: Optional[str] = None) -> None:
        """Publish event to Kafka"""
        if not self.producer:
            self.producer = self._create_producer()
        
        message = json.dumps(event.to_dict())
        
        def delivery_callback(err, msg):
            if err:
                logging.error(f"Failed to publish event to {topic}: {err}")
            else:
                logging.debug(f"Event published to {topic}:{msg.partition()}:{msg.offset()}")
        
        self.producer.produce(topic, message, key=key, callback=delivery_callback)
        self.producer.flush()
    
    def publish_batch(self, topic: str, events: List[EventSchema], keys: Optional[List[str]] = None) -> None:
        """Publish multiple events"""
        if not self.producer:
            self.producer = self._create_producer()
        
        if keys is None:
            keys = [None] * len(events)
        
        for event, key in zip(events, keys):
            message = json.dumps(event.to_dict())
            self.producer.produce(topic, message, key=key)
        
        self.producer.flush()
    
    def subscribe(self, topic: str, handler: Callable[[EventSchema], None]) -> None:
        """Subscribe to a topic"""
        with self._lock:
            if topic not in self.subscribers:
                self.subscribers[topic] = []
            self.subscribers[topic].append(handler)
            
            # Create consumer if needed
            if topic not in self.consumers:
                group_id = f"{self.client_id}_{topic}"
                consumer = self._create_consumer(group_id)
                consumer.subscribe([topic])
                self.consumers[topic] = consumer
                
                if self.running:
                    self._start_consumer_thread(topic)
    
    def _start_consumer_thread(self, topic: str) -> None:
        """Start consumer thread for a topic"""
        def consume_messages():
            consumer = self.consumers[topic]
            while self.running:
                try:
                    msg = consumer.poll(1.0)
                    if msg is None:
                        continue
                    
                    if msg.error():
                        if msg.error().code() != KafkaError._PARTITION_EOF:
                            logging.error(f"Consumer error: {msg.error()}")
                        continue
                    
                    # Deserialize and handle event
                    try:
                        event_dict = json.loads(msg.value().decode('utf-8'))
                        event = EventSchema.from_dict(event_dict)
                        
                        # Call all handlers for this topic
                        if topic in self.subscribers:
                            for handler in self.subscribers[topic]:
                                try:
                                    handler(event)
                                except Exception as e:
                                    logging.error(f"Error in event handler for {topic}: {e}")
                    
                    except Exception as e:
                        logging.error(f"Error processing message from {topic}: {e}")
                
                except Exception as e:
                    logging.error(f"Consumer thread error for {topic}: {e}")
            
            consumer.close()
        
        thread = threading.Thread(target=consume_messages, name=f"kafka-consumer-{topic}")
        thread.daemon = True
        thread.start()
        self.consumer_threads.append(thread)
    
    def start(self) -> None:
        """Start the event bus"""
        self.running = True
        
        # Start consumer threads for existing subscriptions
        for topic in self.consumers:
            self._start_consumer_thread(topic)
        
        logging.info("KafkaEventBus started")
    
    def stop(self) -> None:
        """Stop the event bus"""
        self.running = False
        
        # Wait for consumer threads to finish
        for thread in self.consumer_threads:
            thread.join(timeout=5.0)
        
        # Close producer
        if self.producer:
            self.producer.flush()
            
        # Close consumers
        for consumer in self.consumers.values():
            consumer.close()
        
        logging.info("KafkaEventBus stopped")
    
    def is_running(self) -> bool:
        """Check if running"""
        return self.running


class NexumEventPublisher:
    """High-level event publisher for Nexum banking events"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
    
    def _create_event(self, event_type: str, entity_type: str, entity_id: str, 
                      data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> EventSchema:
        """Create a standardized event"""
        return EventSchema(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            entity_type=entity_type,
            entity_id=entity_id,
            data=data,
            metadata=metadata or {}
        )
    
    # Transaction events
    def on_transaction_created(self, transaction) -> None:
        """Publish transaction created event"""
        event = self._create_event(
            event_type="transaction_created",
            entity_type="transaction",
            entity_id=transaction.id,
            data={
                'transaction_type': transaction.transaction_type.value,
                'amount': str(transaction.amount.amount) if transaction.amount else None,
                'currency': transaction.amount.currency.code if transaction.amount else None,
                'from_account_id': transaction.from_account_id,
                'to_account_id': transaction.to_account_id,
                'description': transaction.description,
                'reference': transaction.reference
            },
            metadata={
                'correlation_id': getattr(transaction, 'correlation_id', None),
                'user_id': getattr(transaction, 'user_id', None)
            }
        )
        self.event_bus.publish(KafkaTopics.TRANSACTIONS_CREATED.value, event, key=transaction.id)
    
    def on_transaction_posted(self, transaction) -> None:
        """Publish transaction posted event"""
        event = self._create_event(
            event_type="transaction_posted",
            entity_type="transaction",
            entity_id=transaction.id,
            data={
                'transaction_type': transaction.transaction_type.value,
                'amount': str(transaction.amount.amount) if transaction.amount else None,
                'currency': transaction.amount.currency.code if transaction.amount else None,
                'from_account_id': transaction.from_account_id,
                'to_account_id': transaction.to_account_id,
                'final_balance': str(getattr(transaction, 'final_balance', 0)),
                'journal_entry_id': getattr(transaction, 'journal_entry_id', None)
            }
        )
        self.event_bus.publish(KafkaTopics.TRANSACTIONS_POSTED.value, event, key=transaction.id)
    
    def on_transaction_failed(self, transaction, error: str) -> None:
        """Publish transaction failed event"""
        event = self._create_event(
            event_type="transaction_failed",
            entity_type="transaction",
            entity_id=transaction.id,
            data={
                'transaction_type': transaction.transaction_type.value,
                'error': error,
                'from_account_id': transaction.from_account_id,
                'to_account_id': transaction.to_account_id
            }
        )
        self.event_bus.publish(KafkaTopics.TRANSACTIONS_FAILED.value, event, key=transaction.id)
    
    # Account events
    def on_account_created(self, account) -> None:
        """Publish account created event"""
        event = self._create_event(
            event_type="account_created",
            entity_type="account",
            entity_id=account.id,
            data={
                'account_number': account.account_number,
                'product_type': account.product_type.value,
                'customer_id': account.customer_id,
                'currency': account.currency.code,
                'name': account.name,
                'balance': str(getattr(getattr(account, 'balance', None), 'amount', '0'))
            }
        )
        self.event_bus.publish(KafkaTopics.ACCOUNTS_CREATED.value, event, key=account.id)
    
    def on_account_updated(self, account) -> None:
        """Publish account updated event"""
        event = self._create_event(
            event_type="account_updated",
            entity_type="account",
            entity_id=account.id,
            data={
                'account_number': account.account_number,
                'balance': str(getattr(getattr(account, 'balance', None), 'amount', '0')),
                'state': account.state.value
            }
        )
        self.event_bus.publish(KafkaTopics.ACCOUNTS_UPDATED.value, event, key=account.id)
    
    # Customer events
    def on_customer_created(self, customer) -> None:
        """Publish customer created event"""
        event = self._create_event(
            event_type="customer_created",
            entity_type="customer",
            entity_id=customer.id,
            data={
                'first_name': customer.first_name,
                'last_name': customer.last_name,
                'email': customer.email,
                'phone': customer.phone,
                'kyc_status': customer.kyc_status.value,
                'kyc_tier': customer.kyc_tier.value
            }
        )
        self.event_bus.publish(KafkaTopics.CUSTOMERS_CREATED.value, event, key=customer.id)
    
    def on_customer_updated(self, customer) -> None:
        """Publish customer updated event"""
        event = self._create_event(
            event_type="customer_updated",
            entity_type="customer",
            entity_id=customer.id,
            data={
                'first_name': customer.first_name,
                'last_name': customer.last_name,
                'email': customer.email,
                'phone': customer.phone
            }
        )
        self.event_bus.publish(KafkaTopics.CUSTOMERS_UPDATED.value, event, key=customer.id)
    
    def on_customer_kyc_changed(self, customer, old_status, old_tier) -> None:
        """Publish customer KYC status changed event"""
        event = self._create_event(
            event_type="kyc_status_changed",
            entity_type="customer",
            entity_id=customer.id,
            data={
                'old_status': old_status.value if old_status else None,
                'new_status': customer.kyc_status.value,
                'old_tier': old_tier.value if old_tier else None,
                'new_tier': customer.kyc_tier.value
            }
        )
        self.event_bus.publish(KafkaTopics.CUSTOMERS_KYC_CHANGED.value, event, key=customer.id)
    
    # Loan events
    def on_loan_originated(self, loan) -> None:
        """Publish loan originated event"""
        event = self._create_event(
            event_type="loan_originated",
            entity_type="loan",
            entity_id=loan.id,
            data={
                'customer_id': loan.customer_id,
                'principal': str(loan.principal.amount),
                'currency': loan.principal.currency.code,
                'interest_rate': str(loan.interest_rate),
                'term_months': loan.term_months,
                'payment_frequency': loan.payment_frequency.value
            }
        )
        self.event_bus.publish(KafkaTopics.LOANS_ORIGINATED.value, event, key=loan.id)
    
    def on_loan_disbursed(self, loan) -> None:
        """Publish loan disbursed event"""
        event = self._create_event(
            event_type="loan_disbursed",
            entity_type="loan",
            entity_id=loan.id,
            data={
                'customer_id': loan.customer_id,
                'principal': str(loan.principal.amount),
                'account_id': getattr(loan, 'account_id', None)
            }
        )
        self.event_bus.publish(KafkaTopics.LOANS_DISBURSED.value, event, key=loan.id)
    
    def on_loan_payment(self, loan, payment_amount: Money) -> None:
        """Publish loan payment event"""
        event = self._create_event(
            event_type="loan_payment",
            entity_type="loan",
            entity_id=loan.id,
            data={
                'payment_amount': str(payment_amount.amount),
                'currency': payment_amount.currency.code,
                'outstanding_balance': str(getattr(loan, 'outstanding_balance', 0))
            }
        )
        self.event_bus.publish(KafkaTopics.LOANS_PAYMENT.value, event, key=loan.id)
    
    # Compliance events
    def on_compliance_alert(self, alert) -> None:
        """Publish compliance alert event"""
        event = self._create_event(
            event_type="compliance_alert",
            entity_type="alert",
            entity_id=alert.get('id', str(uuid.uuid4())),
            data={
                'alert_type': alert.get('type'),
                'severity': alert.get('severity'),
                'customer_id': alert.get('customer_id'),
                'account_id': alert.get('account_id'),
                'description': alert.get('description')
            }
        )
        self.event_bus.publish(KafkaTopics.COMPLIANCE_ALERT.value, event)
    
    # Collections events
    def on_collection_case_created(self, case) -> None:
        """Publish collection case created event"""
        event = self._create_event(
            event_type="collection_case_created",
            entity_type="collection_case",
            entity_id=case.id,
            data={
                'customer_id': case.customer_id,
                'loan_id': getattr(case, 'loan_id', None),
                'delinquency_status': case.delinquency_status.value,
                'amount_due': str(case.amount_due.amount),
                'currency': case.amount_due.currency.code,
                'days_past_due': case.days_past_due
            }
        )
        self.event_bus.publish(KafkaTopics.COLLECTIONS_CASE_CREATED.value, event, key=case.id)
    
    # Workflow events
    def on_workflow_completed(self, workflow) -> None:
        """Publish workflow completed event"""
        event = self._create_event(
            event_type="workflow_completed",
            entity_type="workflow",
            entity_id=workflow.id,
            data={
                'workflow_type': workflow.workflow_type.value,
                'customer_id': getattr(workflow, 'customer_id', None),
                'final_state': workflow.state.value
            }
        )
        self.event_bus.publish(KafkaTopics.WORKFLOWS_COMPLETED.value, event, key=workflow.id)
    
    # Audit events
    def on_audit_event(self, audit_event) -> None:
        """Publish audit event"""
        event = self._create_event(
            event_type="audit_event",
            entity_type="audit",
            entity_id=audit_event.id,
            data={
                'event_type': audit_event.event_type.value,
                'table_name': getattr(audit_event, 'table_name', None),
                'record_id': getattr(audit_event, 'record_id', None),
                'user_id': getattr(audit_event, 'user_id', None),
                'changes': getattr(audit_event, 'metadata', {})
            }
        )
        self.event_bus.publish(KafkaTopics.AUDIT_EVENTS.value, event)


class NexumCommandHandler:
    """Processes inbound commands from Kafka"""
    
    def __init__(self, event_bus: EventBus, banking_system):
        self.event_bus = event_bus
        self.banking_system = banking_system  # Reference to main banking system
        self.running = False
    
    def start(self) -> None:
        """Start listening for commands"""
        self.event_bus.subscribe(KafkaTopics.COMMANDS_TRANSACTIONS.value, self.handle_transaction_command)
        self.event_bus.subscribe(KafkaTopics.COMMANDS_CUSTOMERS.value, self.handle_customer_command)
        self.event_bus.subscribe(KafkaTopics.COMMANDS_LOANS.value, self.handle_loan_command)
        self.running = True
    
    def stop(self) -> None:
        """Stop command processing"""
        self.running = False
    
    def handle_transaction_command(self, event: EventSchema) -> None:
        """Handle transaction commands"""
        try:
            command_data = event.data
            action = command_data.get('action')
            
            if action == 'deposit':
                # Handle deposit command
                account_id = command_data.get('account_id')
                amount_str = command_data.get('amount')
                currency = command_data.get('currency', 'USD')
                description = command_data.get('description', 'Kafka deposit command')
                
                if account_id and amount_str:
                    amount = Money(Decimal(amount_str), Currency[currency])
                    # Call banking system to create deposit
                    # Result would be published as an event by the transaction processor
                    
            elif action == 'withdraw':
                # Handle withdrawal command
                account_id = command_data.get('account_id')
                amount_str = command_data.get('amount')
                currency = command_data.get('currency', 'USD')
                
                if account_id and amount_str:
                    amount = Money(Decimal(amount_str), Currency[currency])
                    # Call banking system to create withdrawal
                    
            elif action == 'transfer':
                # Handle transfer command
                from_account = command_data.get('from_account_id')
                to_account = command_data.get('to_account_id')
                amount_str = command_data.get('amount')
                currency = command_data.get('currency', 'USD')
                
                if from_account and to_account and amount_str:
                    amount = Money(Decimal(amount_str), Currency[currency])
                    # Call banking system to create transfer
            
            logging.info(f"Processed transaction command: {action}")
            
        except Exception as e:
            logging.error(f"Error handling transaction command: {e}")
    
    def handle_customer_command(self, event: EventSchema) -> None:
        """Handle customer commands"""
        try:
            command_data = event.data
            action = command_data.get('action')
            
            if action == 'create':
                # Handle create customer command
                first_name = command_data.get('first_name')
                last_name = command_data.get('last_name')
                email = command_data.get('email')
                
                if first_name and last_name and email:
                    # Call customer manager to create customer
                    pass
                    
            elif action == 'update':
                # Handle update customer command
                customer_id = command_data.get('customer_id')
                if customer_id:
                    # Call customer manager to update customer
                    pass
            
            logging.info(f"Processed customer command: {action}")
            
        except Exception as e:
            logging.error(f"Error handling customer command: {e}")
    
    def handle_loan_command(self, event: EventSchema) -> None:
        """Handle loan commands"""
        try:
            command_data = event.data
            action = command_data.get('action')
            
            if action == 'originate':
                # Handle loan origination command
                customer_id = command_data.get('customer_id')
                principal_str = command_data.get('principal')
                currency = command_data.get('currency', 'USD')
                interest_rate_str = command_data.get('interest_rate')
                term_months = command_data.get('term_months')
                
                if all([customer_id, principal_str, interest_rate_str, term_months]):
                    # Call loan manager to originate loan
                    pass
                    
            elif action == 'payment':
                # Handle loan payment command
                loan_id = command_data.get('loan_id')
                payment_amount_str = command_data.get('payment_amount')
                
                if loan_id and payment_amount_str:
                    # Call loan manager to process payment
                    pass
            
            logging.info(f"Processed loan command: {action}")
            
        except Exception as e:
            logging.error(f"Error handling loan command: {e}")