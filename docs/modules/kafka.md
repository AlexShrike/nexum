# Kafka Integration Module

The Kafka Integration module provides event-driven architecture capabilities for the Nexum core banking system through Apache Kafka. It enables the system to publish banking events and consume commands, supporting CQRS and event sourcing patterns.

## Overview

The integration follows CloudEvents specification loosely and provides multiple implementation options:

- **InMemoryEventBus**: For testing and development (no external dependencies)
- **LogEventBus**: For development with event logging
- **KafkaEventBus**: Real Kafka integration (requires confluent-kafka)

## Architecture

```
Banking Operations → Event Hooks → Event Publisher → Event Bus → Kafka Topics
                                                    ↓
External Systems ← Command Handler ← Event Bus ← Command Topics
```

## Key Components

### 1. Event Schema (EventSchema)

CloudEvents-inspired schema for all events:

```python
@dataclass
class EventSchema:
    event_id: str           # UUID for event
    event_type: str         # Type of event (e.g., "transaction_created")
    timestamp: datetime     # When event occurred (ISO 8601)
    source: str = "nexum"   # Always "nexum" for our system
    version: str = "1.0"    # Schema version
    entity_type: str        # Type of entity (e.g., "transaction")
    entity_id: str          # ID of the entity
    data: Dict[str, Any]    # Event payload
    metadata: Dict[str, Any] # Additional metadata
```

### 2. Topic Structure (KafkaTopics)

Topics follow the naming pattern: `nexum.{domain}.{event_type}`

**Event Topics (Outbound):**
- `nexum.transactions.{created|posted|failed}`
- `nexum.accounts.{created|updated}`
- `nexum.customers.{created|updated|kyc_changed}`
- `nexum.loans.{originated|disbursed|payment|paid_off|defaulted}`
- `nexum.credit.{statement_generated|payment}`
- `nexum.collections.{case_created|case_escalated|case_resolved}`
- `nexum.compliance.{alert|suspicious_activity}`
- `nexum.audit.events`
- `nexum.workflows.{step_completed|completed|rejected}`

**Command Topics (Inbound):**
- `nexum.commands.transactions` - Transaction commands
- `nexum.commands.customers` - Customer commands
- `nexum.commands.loans` - Loan operation commands

### 3. Event Bus Interface

Abstract interface implemented by all event bus types:

```python
class EventBus(ABC):
    @abstractmethod
    def publish(self, topic: str, event: EventSchema, key: str = None) -> None
    
    @abstractmethod
    def publish_batch(self, topic: str, events: List[EventSchema], keys: List[str] = None) -> None
    
    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[EventSchema], None]) -> None
    
    @abstractmethod
    def start() -> None
    
    @abstractmethod
    def stop() -> None
    
    @abstractmethod
    def is_running() -> bool
```

## Event Publishers

### NexumEventPublisher

High-level publisher that creates standardized events for banking operations:

```python
publisher = NexumEventPublisher(event_bus)

# Transaction events
publisher.on_transaction_created(transaction)
publisher.on_transaction_posted(transaction)
publisher.on_transaction_failed(transaction, error_message)

# Account events
publisher.on_account_created(account)
publisher.on_account_updated(account)

# Customer events
publisher.on_customer_created(customer)
publisher.on_customer_updated(customer)
publisher.on_customer_kyc_changed(customer, old_status, old_tier)

# Loan events
publisher.on_loan_originated(loan)
publisher.on_loan_disbursed(loan)
publisher.on_loan_payment(loan, payment_amount)

# Compliance events
publisher.on_compliance_alert(alert)

# Collections events
publisher.on_collection_case_created(case)

# Workflow events
publisher.on_workflow_completed(workflow)

# Audit events
publisher.on_audit_event(audit_event)
```

## Event Payload Schemas

### Transaction Events

**Created Event:**
```json
{
  "event_id": "uuid",
  "event_type": "transaction_created",
  "timestamp": "2024-01-01T12:00:00Z",
  "entity_type": "transaction",
  "entity_id": "txn_123",
  "data": {
    "transaction_type": "deposit",
    "amount": "100.50",
    "currency": "USD",
    "from_account_id": "acc_from",
    "to_account_id": "acc_to",
    "description": "Cash deposit",
    "reference": "REF123"
  },
  "metadata": {
    "correlation_id": "corr_123",
    "user_id": "user_456"
  }
}
```

**Posted Event:**
```json
{
  "event_id": "uuid",
  "event_type": "transaction_posted",
  "entity_type": "transaction",
  "entity_id": "txn_123",
  "data": {
    "transaction_type": "deposit",
    "amount": "100.50",
    "currency": "USD",
    "from_account_id": "acc_from",
    "to_account_id": "acc_to",
    "final_balance": "1100.50",
    "journal_entry_id": "je_789"
  }
}
```

### Customer Events

**Created Event:**
```json
{
  "event_id": "uuid",
  "event_type": "customer_created",
  "entity_type": "customer",
  "entity_id": "cust_123",
  "data": {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "+1234567890",
    "kyc_status": "verified",
    "kyc_tier": "tier_2"
  }
}
```

**KYC Changed Event:**
```json
{
  "event_type": "kyc_status_changed",
  "entity_type": "customer",
  "entity_id": "cust_123",
  "data": {
    "old_status": "pending",
    "new_status": "verified",
    "old_tier": "tier_1",
    "new_tier": "tier_2"
  }
}
```

### Loan Events

**Originated Event:**
```json
{
  "event_type": "loan_originated",
  "entity_type": "loan",
  "entity_id": "loan_123",
  "data": {
    "customer_id": "cust_123",
    "principal": "10000.00",
    "currency": "USD",
    "interest_rate": "5.5",
    "term_months": 60,
    "payment_frequency": "monthly"
  }
}
```

## Command Processing

### Command Message Format

Commands use the same EventSchema structure with specific data fields:

**Transaction Command:**
```json
{
  "event_type": "transaction_command",
  "data": {
    "action": "deposit",
    "account_id": "acc_123",
    "amount": "100.00",
    "currency": "USD",
    "description": "External deposit"
  }
}
```

**Customer Command:**
```json
{
  "event_type": "customer_command",
  "data": {
    "action": "create",
    "first_name": "Jane",
    "last_name": "Smith",
    "email": "jane@example.com"
  }
}
```

**Loan Command:**
```json
{
  "event_type": "loan_command",
  "data": {
    "action": "originate",
    "customer_id": "cust_123",
    "principal": "10000.00",
    "currency": "USD",
    "interest_rate": "5.5",
    "term_months": 60
  }
}
```

### NexumCommandHandler

Processes inbound commands from Kafka:

```python
handler = NexumCommandHandler(event_bus, banking_system)
handler.start()  # Subscribes to command topics
```

## Event Hooks

The `event_hooks.py` module provides automatic event publishing integration with existing banking modules:

```python
from core_banking.event_hooks import create_event_enabled_banking_system

# Enable events for all components
banking_components = {
    'transaction_processor': transaction_processor,
    'account_manager': account_manager,
    'customer_manager': customer_manager,
    'loan_manager': loan_manager,
    'compliance_engine': compliance_engine,
    'audit_trail': audit_trail
}

hook_manager = create_event_enabled_banking_system(event_bus, banking_components)
```

This automatically publishes events when:
- Transactions are created/processed
- Accounts are created/updated
- Customers are created/updated/KYC changed
- Loans are originated/disbursed/paid
- Compliance alerts are generated
- Collection cases are created
- Workflows are completed
- Audit events are logged

## Configuration Examples

### Development Setup (In-Memory)

```python
from core_banking.kafka_integration import InMemoryEventBus
from core_banking.event_hooks import create_event_enabled_banking_system

# Create in-memory event bus
event_bus = InMemoryEventBus()
event_bus.start()

# Enable events for banking system
hook_manager = create_event_enabled_banking_system(event_bus, banking_components)

# Access events for testing
events = event_bus.get_events()
transaction_events = event_bus.get_events("nexum.transactions.created")
```

### Production Setup (Real Kafka)

```python
from core_banking.kafka_integration import KafkaEventBus
from core_banking.event_hooks import create_event_enabled_banking_system

# Create Kafka event bus
event_bus = KafkaEventBus(
    bootstrap_servers="localhost:9092",
    client_id="nexum-banking",
    # Additional Kafka configs
    acks='all',
    retries=3,
    batch_size=16384
)

event_bus.start()

# Enable events for banking system
hook_manager = create_event_enabled_banking_system(event_bus, banking_components)
```

### Logging Setup (Development)

```python
from core_banking.kafka_integration import LogEventBus
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexum.events")

# Create log event bus
event_bus = LogEventBus(logger)
event_bus.start()
```

## API Endpoints

The following REST endpoints are available for Kafka management:

### POST /kafka/publish-test
Publish a test event (development only)

**Request:**
```json
{
  "topic": "nexum.test.events",
  "event_type": "test_event",
  "entity_type": "test",
  "entity_id": "test_123",
  "data": {"message": "Hello Kafka"}
}
```

### GET /kafka/status
Get event bus status

**Response:**
```json
{
  "status": "running",
  "type": "InMemoryEventBus",
  "total_events": 42,
  "events_by_topic": {
    "nexum.transactions.created": 15,
    "nexum.customers.created": 8
  }
}
```

### GET /kafka/events
List recent events (InMemoryEventBus only)

**Query Parameters:**
- `topic` (optional): Filter by topic
- `limit` (default: 50): Maximum events to return

**Response:**
```json
{
  "events": [...],
  "total": 42,
  "showing": 25
}
```

### POST /kafka/config
Configure event bus type and connection

**Request:**
```json
{
  "bus_type": "kafka",
  "bootstrap_servers": "localhost:9092",
  "client_id": "nexum"
}
```

## Integration Patterns

### CQRS (Command Query Responsibility Segregation)

Separate read and write models using events:

```python
# Write side: Process commands
def handle_create_account_command(command):
    account = account_manager.create_account(...)
    # Event automatically published via hooks
    
# Read side: Update projections from events
def on_account_created(event):
    # Update read model/projection
    account_projection.create(event.data)
```

### Event Sourcing

Store events as the source of truth:

```python
class EventStore:
    def append_event(self, stream_id, event):
        # Store event
        self.storage.save(f"stream_{stream_id}", event.to_dict())
        
    def get_events(self, stream_id):
        # Replay events to rebuild state
        events = self.storage.load_all(f"stream_{stream_id}")
        return [EventSchema.from_dict(e) for e in events]
```

### Saga Pattern

Coordinate distributed transactions using events:

```python
class LoanApplicationSaga:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        
    def handle_customer_created(self, event):
        if self.should_pre_approve_loan(event):
            # Trigger loan pre-approval
            command = self.create_loan_command(event.entity_id)
            self.event_bus.publish("nexum.commands.loans", command)
```

## Error Handling

The system provides robust error handling:

1. **Event Publishing Failures**: Logged but don't break the main operation
2. **Command Processing Errors**: Logged with detailed error information
3. **Kafka Connection Issues**: Graceful degradation to logging mode
4. **Serialization Errors**: Decimal and Money objects automatically handled

## Monitoring and Observability

Monitor your event-driven system:

```python
# Track event publishing rates
def track_event_metrics():
    events = event_bus.get_events()
    metrics = {
        'total_events': len(events),
        'events_per_topic': {},
        'recent_events': len([e for e in events if recent(e[1].timestamp)])
    }
    return metrics

# Health check
def kafka_health_check():
    return {
        'event_bus_running': event_bus.is_running(),
        'last_event_time': get_last_event_time(),
        'connection_status': check_kafka_connection()
    }
```

## Best Practices

1. **Event Design**: Make events immutable and include all necessary context
2. **Topic Naming**: Follow consistent naming conventions (nexum.domain.action)
3. **Error Handling**: Never let event processing break core operations
4. **Idempotency**: Design event handlers to be idempotent
5. **Ordering**: Use partition keys for events that need ordering
6. **Monitoring**: Track event publishing and processing rates
7. **Schema Evolution**: Plan for schema changes and versioning

## Testing

Use InMemoryEventBus for comprehensive testing:

```python
def test_customer_creation_publishes_event():
    bus = InMemoryEventBus()
    bus.start()
    
    # Set up event-enabled system
    hook_manager = create_event_enabled_banking_system(bus, components)
    
    # Perform operation
    customer = customer_manager.create_customer(...)
    
    # Verify event was published
    events = bus.get_events("nexum.customers.created")
    assert len(events) == 1
    assert events[0][1].entity_id == customer.id
```

This comprehensive event-driven architecture enables the Nexum banking system to integrate with external systems, implement CQRS patterns, and provide real-time event streaming capabilities while maintaining backward compatibility and testability.