"""
Event System Module

Provides a proper event dispatcher using the Observer pattern to replace
monkey-patched event hooks with a cleaner publish/subscribe mechanism.
"""

from enum import Enum
from typing import Callable, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import logging
from threading import RLock


class DomainEvent(Enum):
    """Domain events that can occur in the banking system"""
    
    # Transaction events
    TRANSACTION_CREATED = "transaction.created"
    TRANSACTION_POSTED = "transaction.posted"
    TRANSACTION_FAILED = "transaction.failed"
    TRANSACTION_REVERSED = "transaction.reversed"
    
    # Account events
    ACCOUNT_CREATED = "account.created"
    ACCOUNT_UPDATED = "account.updated"
    ACCOUNT_CLOSED = "account.closed"
    
    # Customer events
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    CUSTOMER_KYC_CHANGED = "customer.kyc_changed"
    
    # Loan events
    LOAN_ORIGINATED = "loan.originated"
    LOAN_DISBURSED = "loan.disbursed"
    LOAN_PAYMENT = "loan.payment"
    LOAN_PAID_OFF = "loan.paid_off"
    LOAN_DEFAULTED = "loan.defaulted"
    
    # Credit events
    CREDIT_STATEMENT = "credit.statement_generated"
    CREDIT_PAYMENT = "credit.payment"
    
    # Collection events
    COLLECTION_CASE_CREATED = "collection.case_created"
    COLLECTION_CASE_ESCALATED = "collection.case_escalated"
    COLLECTION_CASE_RESOLVED = "collection.case_resolved"
    
    # Compliance events
    COMPLIANCE_ALERT = "compliance.alert"
    COMPLIANCE_SUSPICIOUS = "compliance.suspicious_activity"
    
    # Workflow events
    WORKFLOW_STEP_COMPLETED = "workflow.step_completed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_REJECTED = "workflow.rejected"


@dataclass
class EventPayload:
    """Payload for domain events"""
    event_type: DomainEvent
    entity_type: str
    entity_id: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'event_type': self.event_type.value,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'event_id': self.event_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EventPayload':
        """Create from dictionary"""
        return cls(
            event_type=DomainEvent(data['event_type']),
            entity_type=data['entity_type'],
            entity_id=data['entity_id'],
            data=data['data'],
            timestamp=datetime.fromisoformat(data['timestamp']) if isinstance(data['timestamp'], str) else data['timestamp'],
            event_id=data['event_id']
        )


class EventDispatcher:
    """Central event dispatcher — publish/subscribe pattern"""
    
    def __init__(self):
        self._handlers: Dict[DomainEvent, List[Callable]] = {}
        self._global_handlers: List[Callable] = []  # catch-all handlers
        self._lock = RLock()  # Thread-safe access
        self.logger = logging.getLogger("nexum.events")
    
    def subscribe(self, event_type: DomainEvent, handler: Callable) -> None:
        """Subscribe to a specific event type"""
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
            self.logger.debug(f"Subscribed handler {getattr(handler, '__name__', repr(handler))} to {event_type.value}")
    
    def subscribe_all(self, handler: Callable) -> None:
        """Subscribe to ALL events"""
        with self._lock:
            self._global_handlers.append(handler)
            self.logger.debug(f"Subscribed global handler {getattr(handler, "__name__", repr(handler))}")
    
    def unsubscribe(self, event_type: DomainEvent, handler: Callable) -> None:
        """Unsubscribe from a specific event type"""
        with self._lock:
            if event_type in self._handlers:
                try:
                    self._handlers[event_type].remove(handler)
                    self.logger.debug(f"Unsubscribed handler {getattr(handler, "__name__", repr(handler))} from {event_type.value}")
                except ValueError:
                    self.logger.warning(f"Handler {getattr(handler, "__name__", repr(handler))} was not subscribed to {event_type.value}")
    
    def unsubscribe_all(self, handler: Callable) -> None:
        """Unsubscribe from all events"""
        with self._lock:
            try:
                self._global_handlers.remove(handler)
                self.logger.debug(f"Unsubscribed global handler {getattr(handler, "__name__", repr(handler))}")
            except ValueError:
                self.logger.warning(f"Global handler {getattr(handler, "__name__", repr(handler))} was not subscribed")
    
    def publish(self, event: EventPayload) -> None:
        """Publish event to all subscribers"""
        with self._lock:
            self.logger.debug(f"Publishing event {event.event_type.value} for {event.entity_type}:{event.entity_id}")
            
            # Specific handlers
            for handler in self._handlers.get(event.event_type, []):
                try:
                    handler(event)
                except Exception as e:
                    # Log but don't break the main operation
                    self.logger.error(f"Error in event handler {getattr(handler, "__name__", repr(handler))} for {event.event_type.value}: {e}")
            
            # Global handlers
            for handler in self._global_handlers:
                try:
                    handler(event)
                except Exception as e:
                    self.logger.error(f"Error in global event handler {getattr(handler, "__name__", repr(handler))} for {event.event_type.value}: {e}")
    
    def clear(self) -> None:
        """Clear all handlers"""
        with self._lock:
            self._handlers.clear()
            self._global_handlers.clear()
            self.logger.info("All event handlers cleared")
    
    def get_handler_count(self, event_type: Optional[DomainEvent] = None) -> int:
        """Get count of handlers for a specific event type or all"""
        with self._lock:
            if event_type:
                return len(self._handlers.get(event_type, []))
            else:
                total = sum(len(handlers) for handlers in self._handlers.values())
                total += len(self._global_handlers)
                return total
    
    def get_subscribed_events(self) -> List[DomainEvent]:
        """Get list of events that have subscribers"""
        with self._lock:
            return list(self._handlers.keys())


# Global event dispatcher instance (singleton pattern)
_global_dispatcher: Optional[EventDispatcher] = None


def get_global_dispatcher() -> EventDispatcher:
    """Get the global event dispatcher instance"""
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = EventDispatcher()
    return _global_dispatcher


def set_global_dispatcher(dispatcher: EventDispatcher) -> None:
    """Set a custom global event dispatcher"""
    global _global_dispatcher
    _global_dispatcher = dispatcher


class EventPublisherMixin:
    """Mixin to add event publishing capabilities to domain classes"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_dispatcher: Optional[EventDispatcher] = None
    
    def set_event_dispatcher(self, event_dispatcher: EventDispatcher) -> None:
        """Set the event dispatcher for this instance"""
        self._event_dispatcher = event_dispatcher
    
    def publish_event(self, event_type: DomainEvent, entity_type: str, entity_id: str, data: Dict[str, Any]) -> None:
        """Publish a domain event"""
        dispatcher = self._event_dispatcher or get_global_dispatcher()
        event = EventPayload(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            data=data
        )
        dispatcher.publish(event)


# Convenience functions for common event patterns
def create_transaction_event(event_type: DomainEvent, transaction) -> EventPayload:
    """Create a transaction-related event"""
    return EventPayload(
        event_type=event_type,
        entity_type="transaction",
        entity_id=transaction.id,
        data={
            "transaction_type": transaction.transaction_type.value,
            "amount": str(transaction.amount.amount),
            "currency": transaction.currency.code,
            "from_account_id": transaction.from_account_id,
            "to_account_id": transaction.to_account_id,
            "description": transaction.description,
            "channel": transaction.channel.value,
            "state": transaction.state.value
        }
    )


def create_account_event(event_type: DomainEvent, account) -> EventPayload:
    """Create an account-related event"""
    return EventPayload(
        event_type=event_type,
        entity_type="account",
        entity_id=account.id,
        data={
            "account_number": account.account_number,
            "customer_id": account.customer_id,
            "product_type": account.product_type.value if hasattr(account.product_type, 'value') else str(account.product_type),
            "status": account.status.value if hasattr(account.status, 'value') else str(account.status),
            "balance": str(account.current_balance.amount) if hasattr(account, 'current_balance') and account.current_balance else "0",
            "currency": account.currency.code if hasattr(account, 'currency') else "USD"
        }
    )


def create_customer_event(event_type: DomainEvent, customer) -> EventPayload:
    """Create a customer-related event"""
    return EventPayload(
        event_type=event_type,
        entity_type="customer",
        entity_id=customer.id,
        data={
            "customer_number": customer.customer_number,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "status": customer.status.value if hasattr(customer.status, 'value') else str(customer.status),
            "kyc_status": customer.kyc_status.value if hasattr(customer.kyc_status, 'value') else str(customer.kyc_status),
            "kyc_tier": customer.kyc_tier if hasattr(customer, 'kyc_tier') else None
        }
    )


def create_loan_event(event_type: DomainEvent, loan) -> EventPayload:
    """Create a loan-related event"""
    return EventPayload(
        event_type=event_type,
        entity_type="loan",
        entity_id=loan.id,
        data={
            "loan_number": loan.loan_number,
            "customer_id": loan.customer_id,
            "loan_type": loan.loan_type.value if hasattr(loan.loan_type, 'value') else str(loan.loan_type),
            "principal_amount": str(loan.principal_amount.amount),
            "currency": loan.currency.code,
            "status": loan.status.value if hasattr(loan.status, 'value') else str(loan.status),
            "current_balance": str(loan.current_balance.amount) if hasattr(loan, 'current_balance') and loan.current_balance else str(loan.principal_amount.amount),
            "interest_rate": str(loan.interest_rate) if hasattr(loan, 'interest_rate') else "0"
        }
    )