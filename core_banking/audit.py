"""
Audit Trail Module

Hash-chained immutable audit log with SHA-256 for tamper detection.
Every state change in the system is logged here.
"""

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from decimal import Decimal
import uuid

from .storage import StorageInterface, StorageRecord


class AuditEventType(Enum):
    """Types of audit events"""
    # Customer events
    CUSTOMER_CREATED = "customer_created"
    CUSTOMER_UPDATED = "customer_updated"
    KYC_STATUS_CHANGED = "kyc_status_changed"
    
    # Account events
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_UPDATED = "account_updated"
    ACCOUNT_FROZEN = "account_frozen"
    ACCOUNT_UNFROZEN = "account_unfrozen"
    ACCOUNT_CLOSED = "account_closed"
    
    # Transaction events
    TRANSACTION_CREATED = "transaction_created"
    TRANSACTION_POSTED = "transaction_posted"
    TRANSACTION_FAILED = "transaction_failed"
    TRANSACTION_REVERSED = "transaction_reversed"
    
    # Journal entry events
    JOURNAL_ENTRY_CREATED = "journal_entry_created"
    JOURNAL_ENTRY_POSTED = "journal_entry_posted"
    JOURNAL_ENTRY_REVERSED = "journal_entry_reversed"
    
    # Credit line events
    CREDIT_LINE_CREATED = "credit_line_created"
    CREDIT_LINE_LIMIT_CHANGED = "credit_line_limit_changed"
    CREDIT_STATEMENT_GENERATED = "credit_statement_generated"
    CREDIT_PAYMENT_MADE = "credit_payment_made"
    
    # Product events
    PRODUCT_CREATED = "product_created"
    PRODUCT_UPDATED = "product_updated"
    PRODUCT_SUSPENDED = "product_suspended"
    PRODUCT_RETIRED = "product_retired"
    
    # Loan events
    LOAN_ORIGINATED = "loan_originated"
    LOAN_DISBURSED = "loan_disbursed"
    LOAN_PAYMENT_MADE = "loan_payment_made"
    LOAN_PAID_OFF = "loan_paid_off"
    
    # Interest events
    INTEREST_ACCRUED = "interest_accrued"
    INTEREST_POSTED = "interest_posted"
    
    # Compliance events
    ACCOUNT_HOLD_PLACED = "account_hold_placed"
    ACCOUNT_HOLD_RELEASED = "account_hold_released"
    SUSPICIOUS_ACTIVITY_FLAGGED = "suspicious_activity_flagged"
    LARGE_TRANSACTION_REPORTED = "large_transaction_reported"
    
    # Workflow events
    WORKFLOW_DEFINITION_CREATED = "workflow_definition_created"
    WORKFLOW_DEFINITION_UPDATED = "workflow_definition_updated"
    WORKFLOW_INSTANCE_CREATED = "workflow_instance_created"
    WORKFLOW_INSTANCE_UPDATED = "workflow_instance_updated"
    
    # Custom field events
    CUSTOM_FIELD_CREATED = "custom_field_created"
    CUSTOM_FIELD_UPDATED = "custom_field_updated"
    CUSTOM_FIELD_VALUE_SET = "custom_field_value_set"
    COMPLIANCE_CHECK = "compliance_check"
    
    # RBAC events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_LOCKED = "user_locked"
    USER_UNLOCKED = "user_unlocked"
    ROLE_CREATED = "role_created"
    ROLE_UPDATED = "role_updated"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGED = "password_changed"
    
    # System events
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    BACKUP_CREATED = "backup_created"
    AUDIT_INTEGRITY_CHECK = "audit_integrity_check"


@dataclass
class AuditEvent(StorageRecord):
    """
    Immutable audit event with hash chaining for tamper detection
    """
    event_type: AuditEventType
    entity_type: str  # Type of entity (customer, account, transaction, etc.)
    entity_id: str    # ID of the affected entity
    previous_hash: str  # Hash of previous audit event for chaining
    current_hash: str   # SHA-256 hash of this event
    metadata: Dict[str, Any]  # Additional event-specific data
    user_id: Optional[str] = None  # User who initiated the action
    session_id: Optional[str] = None  # Session identifier
    
    def __post_init__(self):
        # Ensure metadata is JSON serializable
        if self.metadata:
            # Convert Decimal to string for JSON serialization
            self._serialize_metadata()
    
    def _serialize_metadata(self) -> None:
        """Convert metadata values to JSON-serializable format"""
        def convert_value(value):
            if isinstance(value, Decimal):
                return str(value)
            elif isinstance(value, datetime):
                return value.isoformat()
            elif isinstance(value, Enum):
                return value.value
            elif isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [convert_value(v) for v in value]
            else:
                return value
        
        self.metadata = {k: convert_value(v) for k, v in self.metadata.items()}
    
    def calculate_hash(self) -> str:
        """
        Calculate SHA-256 hash of this event
        Hash includes all fields except current_hash to prevent circular reference
        """
        hash_data = {
            'id': self.id,
            'created_at': self.created_at.isoformat(),
            'event_type': self.event_type.value,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'previous_hash': self.previous_hash,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'metadata': self.metadata
        }
        
        # Create deterministic JSON string
        json_data = json.dumps(hash_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_data.encode('utf-8')).hexdigest()
    
    def verify_hash(self) -> bool:
        """Verify that the current hash is correct"""
        expected_hash = self.calculate_hash()
        return self.current_hash == expected_hash
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage with proper enum serialization"""
        result = super().to_dict()
        result['event_type'] = self.event_type.value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuditEvent':
        """Create AuditEvent from dictionary with proper enum deserialization"""
        # Convert datetime strings back to datetime objects
        if isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data['updated_at'], str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        # Convert event_type string back to enum
        if isinstance(data['event_type'], str):
            data['event_type'] = AuditEventType(data['event_type'])
        
        return cls(**data)


class AuditTrail:
    """
    Hash-chained audit trail for tamper detection
    """
    
    def __init__(self, storage: StorageInterface, table_name: str = "audit_events"):
        import threading
        self.storage = storage
        self.table_name = table_name
        self._last_hash: Optional[str] = None
        self._lock = threading.Lock()  # Thread safety for concurrent access
        self._load_last_hash()
    
    def _load_last_hash(self) -> None:
        """Load the hash of the most recent audit event"""
        events = self.storage.find(self.table_name, {})
        if events:
            # Sort by created_at to find the most recent
            sorted_events = sorted(events, key=lambda x: x.get('created_at', ''))
            if sorted_events:
                self._last_hash = sorted_events[-1].get('current_hash')
    
    def log_event(
        self,
        event_type: AuditEventType,
        entity_type: str,
        entity_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> AuditEvent:
        """
        Log an audit event with hash chaining
        
        Args:
            event_type: Type of audit event
            entity_type: Type of entity being audited
            entity_id: ID of the entity
            metadata: Additional event-specific data
            user_id: ID of user who initiated the action
            session_id: Session identifier
            
        Returns:
            Created AuditEvent
        """
        with self._lock:  # Thread-safe event creation and chaining
            now = datetime.now(timezone.utc)
            event_id = str(uuid.uuid4())
            
            # Re-load last hash to ensure we have the most recent one
            self._load_last_hash()
            
            # Create event with previous hash for chaining
            event = AuditEvent(
                id=event_id,
                created_at=now,
                updated_at=now,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                previous_hash=self._last_hash or "",
                current_hash="",  # Will be calculated below
                user_id=user_id,
                session_id=session_id,
                metadata=metadata or {}
            )
            
            # Calculate and set the hash
            event.current_hash = event.calculate_hash()
            
            # Save to storage
            self.storage.save(self.table_name, event.id, event.to_dict())
            
            # Update last hash for chain continuity
            self._last_hash = event.current_hash
            
            return event
    
    def get_events_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        limit: Optional[int] = None
    ) -> List[AuditEvent]:
        """
        Get all audit events for a specific entity
        
        Args:
            entity_type: Type of entity
            entity_id: ID of entity
            limit: Maximum number of events to return
            
        Returns:
            List of AuditEvent objects sorted by creation time
        """
        filters = {
            'entity_type': entity_type,
            'entity_id': entity_id
        }
        
        events_data = self.storage.find(self.table_name, filters)
        events = [AuditEvent.from_dict(data) for data in events_data]
        
        # Sort by creation time
        events.sort(key=lambda x: x.created_at)
        
        if limit:
            events = events[-limit:]  # Get most recent N events
        
        return events
    
    def get_events_by_type(
        self,
        event_type: AuditEventType,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[AuditEvent]:
        """
        Get audit events by type within time range
        
        Args:
            event_type: Type of events to retrieve
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            limit: Maximum number of events to return
            
        Returns:
            List of AuditEvent objects
        """
        all_events = self.storage.load_all(self.table_name)
        events = [AuditEvent.from_dict(data) for data in all_events]
        
        # Filter by event type
        filtered_events = [e for e in events if e.event_type == event_type]
        
        # Filter by time range
        if start_time:
            filtered_events = [e for e in filtered_events if e.created_at >= start_time]
        if end_time:
            filtered_events = [e for e in filtered_events if e.created_at <= end_time]
        
        # Sort by creation time
        filtered_events.sort(key=lambda x: x.created_at)
        
        if limit:
            filtered_events = filtered_events[-limit:]
        
        return filtered_events
    
    def get_all_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[AuditEvent]:
        """
        Get all audit events within time range
        
        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            limit: Maximum number of events to return
            
        Returns:
            List of AuditEvent objects sorted by creation time
        """
        all_events_data = self.storage.load_all(self.table_name)
        events = [AuditEvent.from_dict(data) for data in all_events_data]
        
        # Filter by time range
        if start_time:
            events = [e for e in events if e.created_at >= start_time]
        if end_time:
            events = [e for e in events if e.created_at <= end_time]
        
        # Sort by creation time
        events.sort(key=lambda x: x.created_at)
        
        if limit:
            events = events[-limit:]
        
        return events
    
    def verify_integrity(self) -> Dict[str, Any]:
        """
        Verify the integrity of the entire audit chain
        
        Returns:
            Dictionary with integrity check results
        """
        result = {
            'valid': True,
            'total_events': 0,
            'hash_errors': [],
            'chain_breaks': [],
            'details': {}
        }
        
        # Load all events and sort by creation time
        all_events_data = self.storage.load_all(self.table_name)
        if not all_events_data:
            return result
        
        events = [AuditEvent.from_dict(data) for data in all_events_data]
        events.sort(key=lambda x: x.created_at)
        
        result['total_events'] = len(events)
        
        # Verify each event's hash
        for i, event in enumerate(events):
            if not event.verify_hash():
                result['valid'] = False
                result['hash_errors'].append({
                    'event_id': event.id,
                    'position': i,
                    'expected_hash': event.calculate_hash(),
                    'actual_hash': event.current_hash
                })
        
        # Verify chain continuity
        previous_hash = ""
        for i, event in enumerate(events):
            if event.previous_hash != previous_hash:
                result['valid'] = False
                result['chain_breaks'].append({
                    'event_id': event.id,
                    'position': i,
                    'expected_previous_hash': previous_hash,
                    'actual_previous_hash': event.previous_hash
                })
            previous_hash = event.current_hash
        
        # Additional statistics
        result['details'] = {
            'first_event_time': events[0].created_at.isoformat() if events else None,
            'last_event_time': events[-1].created_at.isoformat() if events else None,
            'event_types': list(set(e.event_type.value for e in events)),
            'entity_types': list(set(e.entity_type for e in events))
        }
        
        return result
    
    def get_event_by_id(self, event_id: str) -> Optional[AuditEvent]:
        """Get a specific audit event by ID"""
        event_data = self.storage.load(self.table_name, event_id)
        if event_data:
            return AuditEvent.from_dict(event_data)
        return None
    
    def count_events(self) -> int:
        """Get total number of audit events"""
        return self.storage.count(self.table_name)
    
    def get_latest_hash(self) -> Optional[str]:
        """Get the hash of the most recent audit event"""
        return self._last_hash