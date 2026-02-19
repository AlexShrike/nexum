"""
Async Storage Backend Module

Provides async storage interface and implementations for compatibility and
production async PostgreSQL using asyncpg. All monetary values stored as Decimal strings.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal
from datetime import datetime, timezone
import json
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from contextlib import asynccontextmanager
import asyncio
import os

# Import the sync storage for compatibility
from .storage import StorageInterface, InMemoryStorage, StorageRecord


class AsyncStorageInterface(ABC):
    """Abstract interface for async storage backends"""
    
    @abstractmethod
    async def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        """Save a record to storage"""
        pass
    
    @abstractmethod
    async def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Load a record from storage"""
        pass
    
    @abstractmethod
    async def load_all(self, table: str) -> List[Dict[str, Any]]:
        """Load all records from a table"""
        pass
    
    @abstractmethod
    async def delete(self, table: str, record_id: str) -> bool:
        """Delete a record from storage"""
        pass
    
    @abstractmethod
    async def exists(self, table: str, record_id: str) -> bool:
        """Check if a record exists"""
        pass
    
    @abstractmethod
    async def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find records matching filters"""
        pass
    
    @abstractmethod
    async def count(self, table: str) -> int:
        """Count records in table"""
        pass
    
    @abstractmethod
    async def clear_table(self, table: str) -> None:
        """Clear all records from a table"""
        pass
    
    async def close(self) -> None:
        """Close storage connection (default no-op)"""
        pass
    
    async def begin_transaction(self) -> None:
        """Start a database transaction (default no-op)"""
        pass
    
    async def commit(self) -> None:
        """Commit current transaction (default no-op)"""
        pass
    
    async def rollback(self) -> None:
        """Rollback current transaction (default no-op)"""
        pass
    
    @asynccontextmanager
    async def atomic(self):
        """Context manager for atomic operations"""
        await self.begin_transaction()
        try:
            yield
            await self.commit()
        except Exception:
            await self.rollback()
            raise


class AsyncInMemoryStorage(AsyncStorageInterface):
    """Async wrapper around InMemoryStorage for compatibility"""
    
    def __init__(self):
        self._sync_storage = InMemoryStorage()
        self._lock = asyncio.Lock()
    
    async def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        """Save a record to memory"""
        async with self._lock:
            # Run sync operation in thread pool to avoid blocking
            await asyncio.to_thread(self._sync_storage.save, table, record_id, data)
    
    async def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Load a record from memory"""
        async with self._lock:
            return await asyncio.to_thread(self._sync_storage.load, table, record_id)
    
    async def load_all(self, table: str) -> List[Dict[str, Any]]:
        """Load all records from a table"""
        async with self._lock:
            return await asyncio.to_thread(self._sync_storage.load_all, table)
    
    async def delete(self, table: str, record_id: str) -> bool:
        """Delete a record from storage"""
        async with self._lock:
            return await asyncio.to_thread(self._sync_storage.delete, table, record_id)
    
    async def exists(self, table: str, record_id: str) -> bool:
        """Check if a record exists"""
        async with self._lock:
            return await asyncio.to_thread(self._sync_storage.exists, table, record_id)
    
    async def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find records matching filters"""
        async with self._lock:
            return await asyncio.to_thread(self._sync_storage.find, table, filters)
    
    async def count(self, table: str) -> int:
        """Count records in table"""
        async with self._lock:
            return await asyncio.to_thread(self._sync_storage.count, table)
    
    async def clear_table(self, table: str) -> None:
        """Clear all records from a table"""
        async with self._lock:
            await asyncio.to_thread(self._sync_storage.clear_table, table)
    
    async def close(self) -> None:
        """Close storage connection"""
        await asyncio.to_thread(self._sync_storage.close)
    
    async def begin_transaction(self) -> None:
        """Start a database transaction"""
        await asyncio.to_thread(self._sync_storage.begin_transaction)
    
    async def commit(self) -> None:
        """Commit current transaction"""
        await asyncio.to_thread(self._sync_storage.commit)
    
    async def rollback(self) -> None:
        """Rollback current transaction"""
        await asyncio.to_thread(self._sync_storage.rollback)


class AsyncPostgreSQLStorage(AsyncStorageInterface):
    """True async PostgreSQL using asyncpg"""
    
    def __init__(self, connection_string: str, pool_size: int = 10):
        self.connection_string = connection_string
        self.pool_size = pool_size
        self.pool = None
        self._transaction_stack = []
    
    async def initialize(self):
        """Create connection pool — call on app startup"""
        try:
            import asyncpg
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=2,
                max_size=self.pool_size,
                command_timeout=60
            )
        except ImportError:
            raise ImportError("asyncpg is required for AsyncPostgreSQLStorage")
    
    async def close(self):
        """Close pool — call on app shutdown"""
        if self.pool:
            await self.pool.close()
    
    def _serialize_value(self, value: Any) -> Any:
        """Serialize value for PostgreSQL storage"""
        if isinstance(value, Decimal):
            return str(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, dict) or isinstance(value, list):
            return json.dumps(value, default=str)
        return value
    
    def _deserialize_value(self, value: Any, target_type: type = None) -> Any:
        """Deserialize value from PostgreSQL storage"""
        if value is None:
            return None
        
        if isinstance(value, str):
            # Try to parse as JSON first
            try:
                parsed = json.loads(value)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            
            # Try datetime parsing
            if target_type == datetime:
                try:
                    return datetime.fromisoformat(value)
                except ValueError:
                    pass
            
            # Try decimal parsing
            if target_type == Decimal:
                try:
                    return Decimal(value)
                except:
                    pass
        
        return value
    
    async def _ensure_table(self, table: str) -> None:
        """Ensure table exists"""
        if not self.pool:
            raise RuntimeError("Pool not initialized. Call initialize() first.")
        
        async with self.pool.acquire() as conn:
            await conn.execute(f'''
                CREATE TABLE IF NOT EXISTS "{table}" (
                    id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            ''')
    
    async def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        """Save a record to PostgreSQL"""
        await self._ensure_table(table)
        
        # Serialize all values
        serialized_data = {}
        for key, value in data.items():
            serialized_data[key] = self._serialize_value(value)
        
        async with self.pool.acquire() as conn:
            await conn.execute(f'''
                INSERT INTO "{table}" (id, data, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (id)
                DO UPDATE SET data = $2, updated_at = NOW()
            ''', record_id, json.dumps(serialized_data))
    
    async def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Load a record from PostgreSQL"""
        await self._ensure_table(table)
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(f'SELECT data FROM "{table}" WHERE id = $1', record_id)
            
            if row:
                data = row['data']
                if isinstance(data, str):
                    data = json.loads(data)
                
                # Deserialize values
                result = {}
                for key, value in data.items():
                    result[key] = self._deserialize_value(value)
                
                return result
            
            return None
    
    async def load_all(self, table: str) -> List[Dict[str, Any]]:
        """Load all records from a table"""
        await self._ensure_table(table)
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(f'SELECT data FROM "{table}" ORDER BY created_at')
            
            results = []
            for row in rows:
                data = row['data']
                if isinstance(data, str):
                    data = json.loads(data)
                
                # Deserialize values
                result = {}
                for key, value in data.items():
                    result[key] = self._deserialize_value(value)
                
                results.append(result)
            
            return results
    
    async def delete(self, table: str, record_id: str) -> bool:
        """Delete a record from storage"""
        await self._ensure_table(table)
        
        async with self.pool.acquire() as conn:
            result = await conn.execute(f'DELETE FROM "{table}" WHERE id = $1', record_id)
            return result != 'DELETE 0'
    
    async def exists(self, table: str, record_id: str) -> bool:
        """Check if a record exists"""
        await self._ensure_table(table)
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(f'SELECT 1 FROM "{table}" WHERE id = $1', record_id)
            return row is not None
    
    async def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find records matching filters"""
        await self._ensure_table(table)
        
        # Build WHERE clause for JSONB queries
        conditions = []
        params = []
        
        for key, value in filters.items():
            param_index = len(params) + 1
            if isinstance(value, str):
                conditions.append(f"data->>'{key}' = ${param_index}")
            else:
                conditions.append(f"data->>'{key}' = ${param_index}")
            params.append(str(value))
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(f'SELECT data FROM "{table}" WHERE {where_clause}', *params)
            
            results = []
            for row in rows:
                data = row['data']
                if isinstance(data, str):
                    data = json.loads(data)
                
                # Deserialize values
                result = {}
                for key, value in data.items():
                    result[key] = self._deserialize_value(value)
                
                results.append(result)
            
            return results
    
    async def count(self, table: str) -> int:
        """Count records in table"""
        await self._ensure_table(table)
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(f'SELECT COUNT(*) FROM "{table}"')
            return row[0]
    
    async def clear_table(self, table: str) -> None:
        """Clear all records from a table"""
        await self._ensure_table(table)
        
        async with self.pool.acquire() as conn:
            await conn.execute(f'DELETE FROM "{table}"')
    
    async def begin_transaction(self) -> None:
        """Start a database transaction"""
        if not self.pool:
            raise RuntimeError("Pool not initialized")
        
        conn = await self.pool.acquire()
        transaction = conn.transaction()
        await transaction.start()
        
        self._transaction_stack.append((conn, transaction))
    
    async def commit(self) -> None:
        """Commit current transaction"""
        if not self._transaction_stack:
            return
        
        conn, transaction = self._transaction_stack.pop()
        try:
            await transaction.commit()
        finally:
            await self.pool.release(conn)
    
    async def rollback(self) -> None:
        """Rollback current transaction"""
        if not self._transaction_stack:
            return
        
        conn, transaction = self._transaction_stack.pop()
        try:
            await transaction.rollback()
        finally:
            await self.pool.release(conn)


def create_async_storage(
    storage_type: str = None,
    connection_string: str = None,
    pool_size: int = 10
) -> AsyncStorageInterface:
    """Factory function to create async storage instances"""
    
    # Check environment variables
    if storage_type is None:
        storage_type = os.getenv('NEXUM_STORAGE_TYPE', 'memory')
    
    if connection_string is None:
        connection_string = os.getenv('NEXUM_DATABASE_URL')
    
    # Determine if async should be used
    use_async = os.getenv('NEXUM_ASYNC', 'false').lower() == 'true'
    
    if storage_type.lower() == 'postgresql' and connection_string and use_async:
        return AsyncPostgreSQLStorage(connection_string, pool_size)
    else:
        # Default to async in-memory storage for compatibility
        return AsyncInMemoryStorage()


# Compatibility adapter - allows sync code to work with async storage
class SyncToAsyncAdapter(StorageInterface):
    """Adapter that allows sync code to use async storage via asyncio.run"""
    
    def __init__(self, async_storage: AsyncStorageInterface):
        self.async_storage = async_storage
    
    def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        asyncio.run(self.async_storage.save(table, record_id, data))
    
    def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        return asyncio.run(self.async_storage.load(table, record_id))
    
    def load_all(self, table: str) -> List[Dict[str, Any]]:
        return asyncio.run(self.async_storage.load_all(table))
    
    def delete(self, table: str, record_id: str) -> bool:
        return asyncio.run(self.async_storage.delete(table, record_id))
    
    def exists(self, table: str, record_id: str) -> bool:
        return asyncio.run(self.async_storage.exists(table, record_id))
    
    def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        return asyncio.run(self.async_storage.find(table, filters))
    
    def count(self, table: str) -> int:
        return asyncio.run(self.async_storage.count(table))
    
    def clear_table(self, table: str) -> None:
        asyncio.run(self.async_storage.clear_table(table))
    
    def close(self) -> None:
        asyncio.run(self.async_storage.close())
    
    def begin_transaction(self) -> None:
        asyncio.run(self.async_storage.begin_transaction())
    
    def commit(self) -> None:
        asyncio.run(self.async_storage.commit())
    
    def rollback(self) -> None:
        asyncio.run(self.async_storage.rollback())