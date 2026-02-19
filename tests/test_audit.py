"""
Test suite for audit module

Tests hash-chained audit trail, tamper detection, integrity verification,
and audit event logging. Critical for security and regulatory compliance.
"""

import pytest
import hashlib
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from core_banking.storage import InMemoryStorage
from core_banking.audit import (
    AuditTrail, AuditEvent, AuditEventType
)


class TestAuditEvent:
    """Test AuditEvent functionality"""
    
    def test_valid_audit_event(self):
        """Test creating valid audit event"""
        now = datetime.now(timezone.utc)
        
        event = AuditEvent(
            id="AUDIT001",
            created_at=now,
            updated_at=now,
            event_type=AuditEventType.CUSTOMER_CREATED,
            entity_type="customer",
            entity_id="CUST001",
            previous_hash="abc123",
            current_hash="def456",
            user_id="USER001",
            session_id="SESSION001",
            metadata={
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com"
            }
        )
        
        assert event.event_type == AuditEventType.CUSTOMER_CREATED
        assert event.entity_type == "customer"
        assert event.entity_id == "CUST001"
        assert event.previous_hash == "abc123"
        assert event.current_hash == "def456"
        assert event.user_id == "USER001"
        assert event.metadata["first_name"] == "John"
    
    def test_metadata_serialization(self):
        """Test that metadata is properly serialized"""
        now = datetime.now(timezone.utc)
        
        # Test with various data types
        metadata = {
            "decimal_amount": Decimal('1234.56'),
            "datetime_value": now,
            "enum_value": AuditEventType.ACCOUNT_CREATED,
            "nested_dict": {
                "inner_decimal": Decimal('99.99'),
                "inner_list": [Decimal('1.1'), Decimal('2.2')]
            }
        }
        
        event = AuditEvent(
            id="AUDIT002",
            created_at=now,
            updated_at=now,
            event_type=AuditEventType.ACCOUNT_CREATED,
            entity_type="account",
            entity_id="ACC001",
            previous_hash="",
            current_hash="hash123",
            metadata=metadata
        )
        
        # All values should be serialized to strings/basic types
        assert isinstance(event.metadata["decimal_amount"], str)
        assert isinstance(event.metadata["datetime_value"], str)
        assert isinstance(event.metadata["enum_value"], str)
        assert isinstance(event.metadata["nested_dict"]["inner_decimal"], str)
        assert isinstance(event.metadata["nested_dict"]["inner_list"][0], str)
    
    def test_hash_calculation(self):
        """Test hash calculation for audit event"""
        now = datetime.now(timezone.utc)
        
        event = AuditEvent(
            id="AUDIT003",
            created_at=now,
            updated_at=now,
            event_type=AuditEventType.TRANSACTION_CREATED,
            entity_type="transaction",
            entity_id="TXN001",
            previous_hash="prev_hash",
            current_hash="",  # Will be calculated
            user_id="USER001",
            session_id="SESSION001",
            metadata={"amount": "100.00", "currency": "USD"}
        )
        
        # Calculate hash manually
        expected_hash = event.calculate_hash()
        assert len(expected_hash) == 64  # SHA-256 produces 64 char hex string
        assert expected_hash.isalnum()  # Should be alphanumeric
        
        # Hash should be deterministic
        same_hash = event.calculate_hash()
        assert expected_hash == same_hash
    
    def test_hash_verification(self):
        """Test hash verification functionality"""
        now = datetime.now(timezone.utc)
        
        event = AuditEvent(
            id="AUDIT004",
            created_at=now,
            updated_at=now,
            event_type=AuditEventType.ACCOUNT_UPDATED,
            entity_type="account", 
            entity_id="ACC001",
            previous_hash="prev_hash",
            current_hash="",
            metadata={"field": "state", "old_value": "active", "new_value": "frozen"}
        )
        
        # Set correct hash
        event.current_hash = event.calculate_hash()
        assert event.verify_hash()
        
        # Tamper with hash
        event.current_hash = "tampered_hash"
        assert not event.verify_hash()
    
    def test_hash_includes_all_fields(self):
        """Test that hash calculation includes all relevant fields"""
        now = datetime.now(timezone.utc)
        
        # Create two identical events
        event1 = AuditEvent(
            id="AUDIT005",
            created_at=now,
            updated_at=now,
            event_type=AuditEventType.CUSTOMER_UPDATED,
            entity_type="customer",
            entity_id="CUST001",
            previous_hash="same_prev",
            current_hash="",
            user_id="USER001",
            metadata={"field": "email"}
        )
        
        event2 = AuditEvent(
            id="AUDIT005",  # Same ID
            created_at=now,  # Same timestamp
            updated_at=now,
            event_type=AuditEventType.CUSTOMER_UPDATED,
            entity_type="customer",
            entity_id="CUST001",
            previous_hash="same_prev",
            current_hash="",
            user_id="USER001",
            metadata={"field": "email"}  # Same metadata
        )
        
        # Should have identical hashes
        assert event1.calculate_hash() == event2.calculate_hash()
        
        # Change one field
        event2.entity_id = "CUST002"
        
        # Hashes should now be different
        assert event1.calculate_hash() != event2.calculate_hash()


class TestAuditTrail:
    """Test AuditTrail functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.storage = InMemoryStorage()
        self.audit_trail = AuditTrail(self.storage)
    
    def test_log_first_event(self):
        """Test logging the first audit event"""
        event = self.audit_trail.log_event(
            event_type=AuditEventType.SYSTEM_START,
            entity_type="system",
            entity_id="CORE_BANKING",
            metadata={"version": "1.0.0"},
            user_id="SYSTEM",
            session_id="INIT_SESSION"
        )
        
        assert event.event_type == AuditEventType.SYSTEM_START
        assert event.entity_type == "system"
        assert event.entity_id == "CORE_BANKING"
        assert event.previous_hash == ""  # First event has no previous hash
        assert len(event.current_hash) == 64  # SHA-256 hash
        assert event.user_id == "SYSTEM"
        assert event.session_id == "INIT_SESSION"
        
        # Verify it's saved
        retrieved = self.audit_trail.get_event_by_id(event.id)
        assert retrieved is not None
        assert retrieved.id == event.id
    
    def test_log_multiple_events_chain(self):
        """Test logging multiple events creates proper hash chain"""
        # Log first event
        event1 = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            entity_type="customer",
            entity_id="CUST001",
            metadata={"name": "John Doe"}
        )
        
        # Log second event
        event2 = self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_CREATED,
            entity_type="account",
            entity_id="ACC001",
            metadata={"customer_id": "CUST001", "type": "savings"}
        )
        
        # Second event should chain to first
        assert event2.previous_hash == event1.current_hash
        assert event2.previous_hash != ""
        
        # Log third event
        event3 = self.audit_trail.log_event(
            event_type=AuditEventType.TRANSACTION_CREATED,
            entity_type="transaction",
            entity_id="TXN001",
            metadata={"account_id": "ACC001", "amount": "1000.00"}
        )
        
        # Third event should chain to second
        assert event3.previous_hash == event2.current_hash
    
    def test_get_events_for_entity(self):
        """Test retrieving events for specific entity"""
        # Create events for different entities
        cust_event1 = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            entity_type="customer", 
            entity_id="CUST001",
            metadata={"action": "create"}
        )
        
        acc_event = self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_CREATED,
            entity_type="account",
            entity_id="ACC001",
            metadata={"customer_id": "CUST001"}
        )
        
        cust_event2 = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_UPDATED,
            entity_type="customer",
            entity_id="CUST001",
            metadata={"field": "email"}
        )
        
        # Get events for customer
        customer_events = self.audit_trail.get_events_for_entity("customer", "CUST001")
        
        assert len(customer_events) == 2
        event_ids = {e.id for e in customer_events}
        assert cust_event1.id in event_ids
        assert cust_event2.id in event_ids
        assert acc_event.id not in event_ids
        
        # Events should be sorted by creation time
        assert customer_events[0].created_at <= customer_events[1].created_at
    
    def test_get_events_by_type(self):
        """Test retrieving events by type"""
        # Create events of different types
        create_event = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            entity_type="customer",
            entity_id="CUST001"
        )
        
        update_event = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_UPDATED,
            entity_type="customer",
            entity_id="CUST001"
        )
        
        create_event2 = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            entity_type="customer",
            entity_id="CUST002"
        )
        
        # Get creation events only
        creation_events = self.audit_trail.get_events_by_type(AuditEventType.CUSTOMER_CREATED)
        
        assert len(creation_events) == 2
        event_ids = {e.id for e in creation_events}
        assert create_event.id in event_ids
        assert create_event2.id in event_ids
        assert update_event.id not in event_ids
    
    def test_get_events_by_type_with_time_range(self):
        """Test retrieving events by type within time range"""
        # Create event in the past
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        
        # Manually create and save event with past timestamp
        past_event_data = {
            "id": "PAST001",
            "created_at": past_time.isoformat(),
            "updated_at": past_time.isoformat(),
            "event_type": AuditEventType.CUSTOMER_CREATED.value,
            "entity_type": "customer",
            "entity_id": "CUST_PAST",
            "previous_hash": "",
            "current_hash": "past_hash",
            "metadata": {}
        }
        self.storage.save(self.audit_trail.table_name, "PAST001", past_event_data)
        
        # Create current event
        current_event = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            entity_type="customer",
            entity_id="CUST_NOW"
        )
        
        # Get events from last hour only
        recent_start = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_events = self.audit_trail.get_events_by_type(
            AuditEventType.CUSTOMER_CREATED,
            start_time=recent_start
        )
        
        # Should only include current event
        assert len(recent_events) == 1
        assert recent_events[0].id == current_event.id
    
    def test_get_all_events(self):
        """Test retrieving all events"""
        # Create several events
        events = []
        for i in range(5):
            event = self.audit_trail.log_event(
                event_type=AuditEventType.TRANSACTION_CREATED,
                entity_type="transaction",
                entity_id=f"TXN00{i}",
                metadata={"sequence": i}
            )
            events.append(event)
        
        # Get all events
        all_events = self.audit_trail.get_all_events()
        
        assert len(all_events) >= 5  # At least the 5 we created
        
        # Should be sorted by creation time
        for i in range(len(all_events) - 1):
            assert all_events[i].created_at <= all_events[i + 1].created_at
    
    def test_get_all_events_with_limit(self):
        """Test retrieving all events with limit"""
        # Create several events
        for i in range(10):
            self.audit_trail.log_event(
                event_type=AuditEventType.ACCOUNT_CREATED,
                entity_type="account",
                entity_id=f"ACC00{i}"
            )
        
        # Get with limit
        limited_events = self.audit_trail.get_all_events(limit=3)
        
        assert len(limited_events) == 3
        # Should get the 3 most recent events
    
    def test_verify_integrity_valid_chain(self):
        """Test integrity verification on valid chain"""
        # Create chain of events
        for i in range(5):
            self.audit_trail.log_event(
                event_type=AuditEventType.CUSTOMER_UPDATED,
                entity_type="customer",
                entity_id="CUST001",
                metadata={"update_sequence": i}
            )
        
        # Verify integrity
        integrity_result = self.audit_trail.verify_integrity()
        
        assert integrity_result["valid"] == True
        assert integrity_result["total_events"] == 5
        assert len(integrity_result["hash_errors"]) == 0
        assert len(integrity_result["chain_breaks"]) == 0
        assert integrity_result["details"]["event_types"] is not None
    
    def test_verify_integrity_detects_hash_tampering(self):
        """Test integrity verification detects hash tampering"""
        # Create some events
        event1 = self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_CREATED,
            entity_type="account",
            entity_id="ACC001"
        )
        
        event2 = self.audit_trail.log_event(
            event_type=AuditEventType.TRANSACTION_CREATED,
            entity_type="transaction", 
            entity_id="TXN001"
        )
        
        # Tamper with first event's hash
        tampered_event1_data = self.storage.load(self.audit_trail.table_name, event1.id)
        tampered_event1_data["current_hash"] = "tampered_hash"
        self.storage.save(self.audit_trail.table_name, event1.id, tampered_event1_data)
        
        # Verify integrity
        integrity_result = self.audit_trail.verify_integrity()
        
        assert integrity_result["valid"] == False
        assert len(integrity_result["hash_errors"]) == 1
        
        hash_error = integrity_result["hash_errors"][0]
        assert hash_error["event_id"] == event1.id
        assert hash_error["actual_hash"] == "tampered_hash"
        assert hash_error["expected_hash"] != "tampered_hash"
    
    def test_verify_integrity_detects_chain_break(self):
        """Test integrity verification detects chain breaks"""
        # Create chain of events
        event1 = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            entity_type="customer",
            entity_id="CUST001"
        )
        
        event2 = self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_CREATED,
            entity_type="account",
            entity_id="ACC001"
        )
        
        # Break the chain by tampering with previous_hash
        tampered_event2_data = self.storage.load(self.audit_trail.table_name, event2.id)
        tampered_event2_data["previous_hash"] = "broken_chain_hash"
        self.storage.save(self.audit_trail.table_name, event2.id, tampered_event2_data)
        
        # Verify integrity
        integrity_result = self.audit_trail.verify_integrity()
        
        assert integrity_result["valid"] == False
        assert len(integrity_result["chain_breaks"]) == 1
        
        chain_break = integrity_result["chain_breaks"][0]
        assert chain_break["event_id"] == event2.id
        assert chain_break["expected_previous_hash"] == event1.current_hash
        assert chain_break["actual_previous_hash"] == "broken_chain_hash"
    
    def test_verify_integrity_empty_trail(self):
        """Test integrity verification on empty trail"""
        integrity_result = self.audit_trail.verify_integrity()
        
        assert integrity_result["valid"] == True  # Empty trail is valid
        assert integrity_result["total_events"] == 0
        assert len(integrity_result["hash_errors"]) == 0
        assert len(integrity_result["chain_breaks"]) == 0
    
    def test_count_events(self):
        """Test counting events in audit trail"""
        initial_count = self.audit_trail.count_events()
        
        # Add some events
        for i in range(7):
            self.audit_trail.log_event(
                event_type=AuditEventType.INTEREST_ACCRUED,
                entity_type="account",
                entity_id=f"ACC00{i}"
            )
        
        final_count = self.audit_trail.count_events()
        assert final_count == initial_count + 7
    
    def test_get_latest_hash(self):
        """Test getting latest hash from chain"""
        # Initially no hash
        assert self.audit_trail.get_latest_hash() is None
        
        # Add first event
        event1 = self.audit_trail.log_event(
            event_type=AuditEventType.SYSTEM_START,
            entity_type="system",
            entity_id="BANKING_SYSTEM"
        )
        
        assert self.audit_trail.get_latest_hash() == event1.current_hash
        
        # Add second event
        event2 = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            entity_type="customer", 
            entity_id="CUST001"
        )
        
        assert self.audit_trail.get_latest_hash() == event2.current_hash
    
    def test_concurrent_event_logging(self):
        """Test that concurrent event logging maintains chain integrity"""
        import threading
        import time
        
        events_created = []
        errors = []
        
        def create_events(start_id: int):
            try:
                for i in range(5):
                    event = self.audit_trail.log_event(
                        event_type=AuditEventType.TRANSACTION_CREATED,
                        entity_type="transaction",
                        entity_id=f"CONCURRENT_TXN_{start_id}_{i}",
                        metadata={"thread_id": start_id, "sequence": i}
                    )
                    events_created.append(event)
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=create_events, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Should have created 15 events (3 threads * 5 events)
        assert len(events_created) == 15
        
        # Verify chain integrity is maintained
        integrity_result = self.audit_trail.verify_integrity()
        assert integrity_result["valid"] == True
    
    def test_large_metadata_handling(self):
        """Test handling of large metadata objects"""
        # Create large metadata
        large_metadata = {
            "large_list": [f"item_{i}" for i in range(1000)],
            "large_dict": {f"key_{i}": f"value_{i}" for i in range(500)},
            "description": "This is a test with large metadata to verify proper serialization and storage"
        }
        
        event = self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_UPDATED,
            entity_type="account",
            entity_id="ACC_LARGE_META",
            metadata=large_metadata
        )
        
        # Should be able to retrieve and verify
        retrieved = self.audit_trail.get_event_by_id(event.id)
        assert retrieved is not None
        assert len(retrieved.metadata["large_list"]) == 1000
        assert len(retrieved.metadata["large_dict"]) == 500
        
        # Hash should still be valid
        assert retrieved.verify_hash()
    
    def test_special_characters_in_metadata(self):
        """Test handling of special characters in metadata"""
        special_metadata = {
            "unicode_text": "Test with émojis 🏦💰 and spëcîál chars",
            "json_like": '{"nested": "json", "array": [1, 2, 3]}',
            "newlines": "Line 1\nLine 2\nLine 3",
            "quotes": 'Single \'quotes\' and double "quotes"',
            "backslashes": "Path\\to\\file and escape\\nsequences"
        }
        
        event = self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_UPDATED,
            entity_type="customer",
            entity_id="CUST_SPECIAL",
            metadata=special_metadata
        )
        
        # Should be retrievable and verifiable
        retrieved = self.audit_trail.get_event_by_id(event.id)
        assert retrieved is not None
        assert retrieved.verify_hash()
        assert "🏦💰" in retrieved.metadata["unicode_text"]
        assert "Line 1\nLine 2" in retrieved.metadata["newlines"]


if __name__ == "__main__":
    pytest.main([__file__])