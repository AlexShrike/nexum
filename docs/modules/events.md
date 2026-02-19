# Event System Module

The Events module provides a clean observer pattern implementation using publish/subscribe mechanisms to replace monkey-patched event hooks with a proper event dispatcher.

## Overview

The event system enables loose coupling between domain modules by allowing components to publish domain events and subscribe to events they're interested in, without direct dependencies.

## Key Classes

### DomainEvent (Enum)

Domain events that can occur in the banking system:

**Transaction Events:**
- `TRANSACTION_CREATED` - New transaction initiated
- `TRANSACTION_POSTED` - Transaction posted to ledger
- `TRANSACTION_FAILED` - Transaction processing failed
- `TRANSACTION_REVERSED` - Transaction was reversed

**Account Events:**
- `ACCOUNT_CREATED` - New account opened
- `ACCOUNT_UPDATED` - Account details modified
- `ACCOUNT_CLOSED` - Account closed

**Customer Events:**
- `CUSTOMER_CREATED` - New customer onboarded
- `CUSTOMER_UPDATED` - Customer profile updated
- `CUSTOMER_KYC_CHANGED` - KYC status changed

**Loan Events:**
- `LOAN_ORIGINATED` - New loan created
- `LOAN_DISBURSED` - Loan funds disbursed
- `LOAN_PAYMENT` - Loan payment received
- `LOAN_PAID_OFF` - Loan fully repaid
- `LOAN_DEFAULTED` - Loan entered default

**Credit Events:**
- `CREDIT_STATEMENT` - Credit statement generated
- `CREDIT_PAYMENT` - Credit payment received

**Collection Events:**
- `COLLECTION_CASE_CREATED` - New collection case
- `COLLECTION_CASE_ESCALATED` - Case escalated
- `COLLECTION_CASE_RESOLVED` - Case resolved

**Compliance Events:**
- `COMPLIANCE_ALERT` - Compliance alert triggered
- `COMPLIANCE_SUSPICIOUS` - Suspicious activity detected

**Workflow Events:**
- `WORKFLOW_STEP_COMPLETED` - Workflow step finished
- `WORKFLOW_COMPLETED` - Workflow completed
- `WORKFLOW_REJECTED` - Workflow rejected

### EventPayload

Container for event data:

```python
@dataclass
class EventPayload:
    event_type: DomainEvent
    entity_type: str        # "transaction", "account", "customer"
    entity_id: str         # Unique identifier
    data: Dict[str, Any]   # Event-specific data
    timestamp: datetime    # When event occurred
    event_id: str         # Unique event identifier
```

**Methods:**
- `to_dict()` - Serialize to dictionary
- `from_dict(data)` - Deserialize from dictionary

### EventDispatcher

Central event dispatcher implementing publish/subscribe pattern:

```python
class EventDispatcher:
    def __init__(self):
        # Thread-safe event handling
        
    def subscribe(self, event_type: DomainEvent, handler: Callable) -> None
        # Subscribe to specific event type
        
    def subscribe_all(self, handler: Callable) -> None
        # Subscribe to all events (global handler)
        
    def unsubscribe(self, event_type: DomainEvent, handler: Callable) -> None
        # Remove specific subscription
        
    def publish(self, event: EventPayload) -> None
        # Publish event to all subscribers
        
    def clear(self) -> None
        # Remove all handlers
        
    def get_handler_count(self, event_type: Optional[DomainEvent]) -> int
        # Get subscription counts
```

**Features:**
- Thread-safe using RLock
- Error isolation (failed handlers don't break others)
- Both specific and global event subscriptions
- Comprehensive logging

### EventPublisherMixin

Mixin to add event publishing capabilities to domain classes:

```python
class EventPublisherMixin:
    def set_event_dispatcher(self, event_dispatcher: EventDispatcher) -> None
        # Set custom dispatcher
        
    def publish_event(self, event_type: DomainEvent, entity_type: str, 
                     entity_id: str, data: Dict[str, Any]) -> None
        # Publish domain event
```

## Global Dispatcher

The module provides a singleton global dispatcher:

```python
# Get global dispatcher instance
dispatcher = get_global_dispatcher()

# Set custom global dispatcher
set_global_dispatcher(custom_dispatcher)
```

## Usage Examples

### Basic Event Publishing

```python
from core_banking.events import get_global_dispatcher, DomainEvent, EventPayload

dispatcher = get_global_dispatcher()

# Publish transaction event
event = EventPayload(
    event_type=DomainEvent.TRANSACTION_CREATED,
    entity_type="transaction",
    entity_id="txn_123",
    data={
        "amount": "1000.00",
        "currency": "USD",
        "from_account_id": "acc_456",
        "to_account_id": "acc_789"
    }
)

dispatcher.publish(event)
```

### Event Subscription

```python
def handle_transaction_created(event: EventPayload):
    """Handle new transaction events"""
    print(f"Transaction {event.entity_id} created for {event.data['amount']}")

def handle_all_events(event: EventPayload):
    """Global event handler - catches everything"""
    print(f"Event: {event.event_type.value}")

# Subscribe to specific events
dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, handle_transaction_created)

# Subscribe to all events
dispatcher.subscribe_all(handle_all_events)
```

### Integration with Domain Classes

```python
class TransactionService(EventPublisherMixin):
    def process_transaction(self, transaction_data):
        # Process transaction
        transaction = self._create_transaction(transaction_data)
        
        # Publish event
        self.publish_event(
            event_type=DomainEvent.TRANSACTION_CREATED,
            entity_type="transaction", 
            entity_id=transaction.id,
            data={
                "transaction_type": transaction.transaction_type.value,
                "amount": str(transaction.amount.amount),
                "currency": transaction.currency.code
            }
        )
```

### Connecting to Notification Engine

```python
from core_banking.notifications import NotificationEngine, NotificationType

def notify_large_transaction(event: EventPayload):
    """Send notification for large transactions"""
    if event.event_type == DomainEvent.TRANSACTION_CREATED:
        amount = Decimal(event.data.get('amount', '0'))
        if amount > Decimal('10000.00'):  # Large transaction threshold
            # Send notification
            notification_engine.send_notification(
                notification_type=NotificationType.LARGE_TRANSACTION,
                recipient_id=event.data.get('customer_id'),
                data=event.data
            )

# Subscribe to transaction events
dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, notify_large_transaction)
```

## Convenience Functions

The module provides helper functions for creating common event types:

### Transaction Events

```python
def create_transaction_event(event_type: DomainEvent, transaction) -> EventPayload:
    """Create transaction-related event with standard fields"""
    
# Usage
event = create_transaction_event(DomainEvent.TRANSACTION_POSTED, transaction)
dispatcher.publish(event)
```

### Account Events

```python
def create_account_event(event_type: DomainEvent, account) -> EventPayload:
    """Create account-related event with standard fields"""
```

### Customer Events

```python
def create_customer_event(event_type: DomainEvent, customer) -> EventPayload:
    """Create customer-related event with standard fields"""
```

### Loan Events

```python
def create_loan_event(event_type: DomainEvent, loan) -> EventPayload:
    """Create loan-related event with standard fields"""
```

## Integration Points

### Notification Engine

Events automatically trigger notifications based on configured templates and user preferences.

### Audit Trail

All domain events are automatically logged to the audit trail for compliance.

### Kafka Integration

Events can be published to Kafka topics for external system integration.

### Workflow Engine

Workflow steps can subscribe to events to trigger automatic transitions.

### Collections Management

Collection cases can be created or escalated based on payment events.

## Configuration

Event system configuration via environment variables:

```bash
# Enable event publishing (default: true)
export NEXUM_EVENTS_ENABLED="true"

# Max event queue size (default: 1000)
export NEXUM_EVENTS_QUEUE_SIZE="1000"

# Event retention in days (default: 30)
export NEXUM_EVENTS_RETENTION_DAYS="30"
```

## Threading and Safety

- Thread-safe using RLock for concurrent access
- Event handlers are called synchronously but with error isolation
- Failed handlers are logged but don't affect other subscribers
- No guarantee on handler execution order

## Best Practices

### Event Design
- Keep event payloads focused and minimal
- Include essential identification fields (entity_type, entity_id)
- Use standardized data structures in event.data
- Don't include sensitive data that shouldn't be logged

### Handler Implementation
- Keep handlers fast and lightweight
- Use async patterns for heavy processing
- Handle exceptions gracefully
- Log meaningful debug information
- Avoid side effects that could break the main operation

### Performance
- Don't subscribe to events you don't need
- Unsubscribe handlers when components are destroyed
- Monitor handler performance with logging
- Consider using separate threads for heavy processing

### Testing
- Use a test-specific dispatcher instance
- Clear handlers between tests
- Verify events are published with correct data
- Test error scenarios in event handlers

## Error Handling

```python
# Handler errors are logged but don't break the main flow
def risky_handler(event: EventPayload):
    try:
        # Handler logic here
        risky_operation()
    except Exception as e:
        # Log error - event system will catch and log this too
        logger.error(f"Handler failed for {event.event_type}: {e}")
        # Don't re-raise - let other handlers continue
```

## Migration from Event Hooks

The new event system replaces the legacy `event_hooks.py` monkey patching approach:

**Old (event_hooks.py):**
```python
# Monkey patch methods
original_method = SomeClass.method
def new_method(self, *args, **kwargs):
    result = original_method(self, *args, **kwargs)
    # Send event
    return result
SomeClass.method = new_method
```

**New (events.py):**
```python
# Clean event publishing in domain classes
class SomeClass(EventPublisherMixin):
    def method(self, *args, **kwargs):
        # Business logic
        result = self._do_work(*args, **kwargs)
        
        # Publish event
        self.publish_event(
            event_type=DomainEvent.SOMETHING_HAPPENED,
            entity_type="entity",
            entity_id=result.id,
            data={"key": "value"}
        )
        return result
```

## Future Enhancements

- Event replay capabilities
- Event sourcing support
- Persistent event store
- Event versioning and schema evolution
- Dead letter queue for failed events
- Event aggregation and batching