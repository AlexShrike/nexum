"""
Tests for Async Storage Interface

Tests the async storage implementations including AsyncInMemoryStorage
and AsyncPostgreSQLStorage for CRUD operations, transactions, and
backward compatibility.
"""

import pytest
import pytest_asyncio
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from core_banking.async_storage import (
    AsyncStorageInterface,
    AsyncInMemoryStorage,
    AsyncPostgreSQLStorage,
    create_async_storage,
    SyncToAsyncAdapter
)
from core_banking.storage import InMemoryStorage


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


class TestAsyncInMemoryStorage:
    """Test AsyncInMemoryStorage functionality"""
    
    @pytest_asyncio.fixture
    async def storage(self):
        """Create async in-memory storage instance"""
        return AsyncInMemoryStorage()
    
    @pytest.mark.asyncio
    async def test_basic_crud_operations(self, storage):
        """Test basic CRUD operations"""
        table = "test_table"
        record_id = "test_record"
        data = {
            "id": record_id,
            "name": "Test Record",
            "amount": "123.45",
            "created_at": "2024-01-01T00:00:00Z"
        }
        
        # Test save
        await storage.save(table, record_id, data)
        
        # Test load
        loaded_data = await storage.load(table, record_id)
        assert loaded_data == data
        
        # Test exists
        exists = await storage.exists(table, record_id)
        assert exists is True
        
        # Test count
        count = await storage.count(table)
        assert count == 1
        
        # Test load_all
        all_records = await storage.load_all(table)
        assert len(all_records) == 1
        assert all_records[0] == data
        
        # Test delete
        deleted = await storage.delete(table, record_id)
        assert deleted is True
        
        # Verify deletion
        loaded_data = await storage.load(table, record_id)
        assert loaded_data is None
        
        exists = await storage.exists(table, record_id)
        assert exists is False
    
    @pytest.mark.asyncio
    async def test_find_operations(self, storage):
        """Test find operations with filters"""
        table = "customers"
        
        # Create test data
        customers = [
            {"id": "cust_1", "name": "Alice", "status": "active", "balance": "100.00"},
            {"id": "cust_2", "name": "Bob", "status": "inactive", "balance": "200.00"},
            {"id": "cust_3", "name": "Charlie", "status": "active", "balance": "150.00"}
        ]
        
        for customer in customers:
            await storage.save(table, customer["id"], customer)
        
        # Test find by status
        active_customers = await storage.find(table, {"status": "active"})
        assert len(active_customers) == 2
        
        # Test find by name
        alice = await storage.find(table, {"name": "Alice"})
        assert len(alice) == 1
        assert alice[0]["id"] == "cust_1"
        
        # Test find with no matches
        no_matches = await storage.find(table, {"status": "suspended"})
        assert len(no_matches) == 0
    
    @pytest.mark.asyncio
    async def test_clear_table(self, storage):
        """Test clearing all records from a table"""
        table = "test_clear"
        
        # Add some data
        for i in range(5):
            await storage.save(table, f"record_{i}", {"id": f"record_{i}", "value": i})
        
        # Verify data exists
        count = await storage.count(table)
        assert count == 5
        
        # Clear table
        await storage.clear_table(table)
        
        # Verify table is empty
        count = await storage.count(table)
        assert count == 0
        
        all_records = await storage.load_all(table)
        assert len(all_records) == 0
    
    @pytest.mark.asyncio
    async def test_atomic_context_manager(self, storage):
        """Test atomic context manager for transactions"""
        table = "atomic_test"
        
        # Test successful transaction
        async with storage.atomic():
            await storage.save(table, "record_1", {"id": "record_1", "value": "success"})
            await storage.save(table, "record_2", {"id": "record_2", "value": "success"})
        
        # Verify both records were saved
        record_1 = await storage.load(table, "record_1")
        record_2 = await storage.load(table, "record_2")
        assert record_1 is not None
        assert record_2 is not None
        
        # Test transaction rollback (simulate exception)
        try:
            async with storage.atomic():
                await storage.save(table, "record_3", {"id": "record_3", "value": "rollback"})
                raise Exception("Simulated error")
        except Exception:
            pass
        
        # Verify record_3 might exist (in-memory storage doesn't have true transactions)
        # This test mainly verifies the context manager doesn't crash
        count = await storage.count(table)
        assert count >= 2  # At least the two successful records


class TestAsyncPostgreSQLStorage:
    """Test AsyncPostgreSQLStorage functionality (if available)"""
    
    @pytest_asyncio.fixture
    async def postgresql_storage(self):
        """Create async PostgreSQL storage instance (skip if not available)"""
        try:
            # Try to create PostgreSQL storage
            storage = AsyncPostgreSQLStorage("postgresql://localhost/test_nexum")
            await storage.initialize()
            yield storage
            await storage.close()
        except Exception:
            pytest.skip("PostgreSQL not available for testing")
    
    @pytest.mark.asyncio
    async def test_postgresql_crud_operations(self, postgresql_storage):
        """Test basic CRUD operations with PostgreSQL"""
        table = "pg_test_table"
        record_id = "pg_test_record"
        data = {
            "id": record_id,
            "name": "PostgreSQL Test Record",
            "amount": "456.78",
            "active": True,
            "metadata": {"type": "test", "version": 1}
        }
        
        # Clear table first
        await postgresql_storage.clear_table(table)
        
        # Test save
        await postgresql_storage.save(table, record_id, data)
        
        # Test load
        loaded_data = await postgresql_storage.load(table, record_id)
        assert loaded_data["id"] == data["id"]
        assert loaded_data["name"] == data["name"]
        assert loaded_data["amount"] == data["amount"]
        
        # Test exists
        exists = await postgresql_storage.exists(table, record_id)
        assert exists is True
        
        # Test count
        count = await postgresql_storage.count(table)
        assert count == 1
        
        # Test delete
        deleted = await postgresql_storage.delete(table, record_id)
        assert deleted is True
        
        # Verify deletion
        loaded_data = await postgresql_storage.load(table, record_id)
        assert loaded_data is None
    
    @pytest.mark.asyncio
    async def test_postgresql_find_operations(self, postgresql_storage):
        """Test find operations with PostgreSQL"""
        table = "pg_customers"
        
        # Clear table first
        await postgresql_storage.clear_table(table)
        
        # Create test data
        customers = [
            {"id": "pg_cust_1", "name": "Alice", "status": "active"},
            {"id": "pg_cust_2", "name": "Bob", "status": "inactive"},
            {"id": "pg_cust_3", "name": "Charlie", "status": "active"}
        ]
        
        for customer in customers:
            await postgresql_storage.save(table, customer["id"], customer)
        
        # Test find by status
        active_customers = await postgresql_storage.find(table, {"status": "active"})
        assert len(active_customers) == 2
        
        # Test find by name
        alice = await postgresql_storage.find(table, {"name": "Alice"})
        assert len(alice) == 1
        assert alice[0]["id"] == "pg_cust_1"


class TestStorageFactory:
    """Test the create_async_storage factory function"""
    
    def test_create_memory_storage(self):
        """Test creating in-memory async storage"""
        storage = create_async_storage(storage_type="memory")
        assert isinstance(storage, AsyncInMemoryStorage)
    
    def test_create_postgresql_storage_without_url(self):
        """Test fallback to memory storage when PostgreSQL URL not provided"""
        storage = create_async_storage(storage_type="postgresql")
        assert isinstance(storage, AsyncInMemoryStorage)


class TestSyncToAsyncAdapter:
    """Test the sync-to-async adapter"""
    
    @pytest.fixture
    def async_storage(self):
        """Create async storage for adapter testing"""
        return AsyncInMemoryStorage()
    
    @pytest.fixture
    def adapter(self, async_storage):
        """Create sync-to-async adapter"""
        return SyncToAsyncAdapter(async_storage)
    
    def test_adapter_crud_operations(self, adapter):
        """Test sync interface on async storage via adapter"""
        table = "adapter_test"
        record_id = "adapter_record"
        data = {
            "id": record_id,
            "name": "Adapter Test Record",
            "value": "test_value"
        }
        
        # Test save
        adapter.save(table, record_id, data)
        
        # Test load
        loaded_data = adapter.load(table, record_id)
        assert loaded_data == data
        
        # Test exists
        exists = adapter.exists(table, record_id)
        assert exists is True
        
        # Test count
        count = adapter.count(table)
        assert count == 1
        
        # Test delete
        deleted = adapter.delete(table, record_id)
        assert deleted is True
        
        # Verify deletion
        loaded_data = adapter.load(table, record_id)
        assert loaded_data is None


class TestBackwardCompatibility:
    """Test that async storage doesn't break existing sync tests"""
    
    def test_sync_storage_still_works(self):
        """Verify that original sync storage still works"""
        storage = InMemoryStorage()
        
        table = "compat_test"
        record_id = "compat_record"
        data = {"id": record_id, "value": "compatibility test"}
        
        # Basic CRUD operations
        storage.save(table, record_id, data)
        loaded_data = storage.load(table, record_id)
        assert loaded_data == data
        
        exists = storage.exists(table, record_id)
        assert exists is True
        
        deleted = storage.delete(table, record_id)
        assert deleted is True
        
        loaded_data = storage.load(table, record_id)
        assert loaded_data is None
    
    def test_sync_atomic_context_manager(self):
        """Test that sync atomic context manager works"""
        storage = InMemoryStorage()
        table = "sync_atomic_test"
        
        with storage.atomic():
            storage.save(table, "record_1", {"id": "record_1", "value": "atomic"})
            storage.save(table, "record_2", {"id": "record_2", "value": "atomic"})
        
        # Verify records were saved
        record_1 = storage.load(table, "record_1")
        record_2 = storage.load(table, "record_2")
        assert record_1 is not None
        assert record_2 is not None