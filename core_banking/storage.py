"""
Storage Backend Module

Provides abstract storage interface and implementations for in-memory (testing)
and SQLite (persistence). All monetary values stored as Decimal strings.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal
from datetime import datetime, timezone
import sqlite3
import json
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from contextlib import contextmanager


@dataclass
class StorageRecord:
    """Base class for all stored records"""
    id: str
    created_at: datetime
    updated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        result = asdict(self)
        # Convert datetime objects to ISO strings
        result['created_at'] = self.created_at.isoformat()
        result['updated_at'] = self.updated_at.isoformat()
        # Convert Decimal objects to strings
        for key, value in result.items():
            if isinstance(value, Decimal):
                result[key] = str(value)
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StorageRecord':
        """Create instance from dictionary"""
        # Convert ISO strings back to datetime objects
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data and isinstance(data['updated_at'], str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        return cls(**data)


class StorageInterface(ABC):
    """Abstract interface for storage backends"""
    
    @abstractmethod
    def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        """Save a record to storage"""
        pass
    
    @abstractmethod
    def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Load a record from storage"""
        pass
    
    @abstractmethod
    def load_all(self, table: str) -> List[Dict[str, Any]]:
        """Load all records from a table"""
        pass
    
    @abstractmethod
    def delete(self, table: str, record_id: str) -> bool:
        """Delete a record from storage"""
        pass
    
    @abstractmethod
    def exists(self, table: str, record_id: str) -> bool:
        """Check if a record exists"""
        pass
    
    @abstractmethod
    def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find records matching filters"""
        pass
    
    @abstractmethod
    def count(self, table: str) -> int:
        """Count records in table"""
        pass
    
    @abstractmethod
    def clear_table(self, table: str) -> None:
        """Clear all records from a table"""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close storage connection"""
        pass
    
    def begin_transaction(self) -> None:
        """Start a database transaction (default no-op)"""
        pass
    
    def commit(self) -> None:
        """Commit current transaction (default no-op)"""
        pass
    
    def rollback(self) -> None:
        """Rollback current transaction (default no-op)"""
        pass
    
    @contextmanager
    def atomic(self):
        """Context manager for atomic operations"""
        self.begin_transaction()
        try:
            yield
            self.commit()
        except Exception:
            self.rollback()
            raise


class InMemoryStorage(StorageInterface):
    """In-memory storage implementation for testing"""
    
    def __init__(self):
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._lock = threading.RLock()
    
    def _ensure_table(self, table: str) -> None:
        """Ensure table exists"""
        if table not in self._data:
            self._data[table] = {}
    
    def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        """Save a record to memory"""
        with self._lock:
            self._ensure_table(table)
            # Deep copy to prevent external mutation
            self._data[table][record_id] = json.loads(json.dumps(data, default=str))
    
    def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Load a record from memory"""
        with self._lock:
            self._ensure_table(table)
            record = self._data[table].get(record_id)
            if record:
                # Deep copy to prevent external mutation
                return json.loads(json.dumps(record))
            return None
    
    def load_all(self, table: str) -> List[Dict[str, Any]]:
        """Load all records from a table"""
        with self._lock:
            self._ensure_table(table)
            return [json.loads(json.dumps(record)) for record in self._data[table].values()]
    
    def delete(self, table: str, record_id: str) -> bool:
        """Delete a record from memory"""
        with self._lock:
            self._ensure_table(table)
            if record_id in self._data[table]:
                del self._data[table][record_id]
                return True
            return False
    
    def exists(self, table: str, record_id: str) -> bool:
        """Check if a record exists"""
        with self._lock:
            self._ensure_table(table)
            return record_id in self._data[table]
    
    def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find records matching filters"""
        with self._lock:
            self._ensure_table(table)
            results = []
            for record in self._data[table].values():
                match = True
                for key, value in filters.items():
                    if key not in record or record[key] != value:
                        match = False
                        break
                if match:
                    results.append(json.loads(json.dumps(record)))
            return results
    
    def count(self, table: str) -> int:
        """Count records in table"""
        with self._lock:
            self._ensure_table(table)
            return len(self._data[table])
    
    def clear_table(self, table: str) -> None:
        """Clear all records from a table"""
        with self._lock:
            self._data[table] = {}
    
    def close(self) -> None:
        """Close storage (no-op for in-memory)"""
        pass
    
    def get_all_data(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get all data for debugging/inspection"""
        with self._lock:
            return json.loads(json.dumps(self._data, default=str))


class SQLiteStorage(StorageInterface):
    """SQLite storage implementation for persistence"""
    
    def __init__(self, db_path: Union[str, Path] = ":memory:"):
        self.db_path = str(db_path)
        # Set isolation_level to 'DEFERRED' to enable manual transaction control
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level='DEFERRED')
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._in_transaction = False
        
        # Enable WAL mode for better concurrent access
        if self.db_path != ":memory:":
            with self._lock:
                self._connection.execute("PRAGMA journal_mode = WAL")
                self._connection.execute("PRAGMA synchronous = NORMAL")
                self._connection.commit()
    
    def _ensure_table(self, table: str) -> None:
        """Ensure table exists with proper schema"""
        with self._lock:
            self._connection.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # Create index on timestamps for better query performance
            self._connection.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table}_created_at 
                ON {table}(created_at)
            """)
            self._connection.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table}_updated_at 
                ON {table}(updated_at)
            """)
            self._connection.commit()
    
    def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        """Save a record to SQLite"""
        with self._lock:
            self._ensure_table(table)
            
            now = datetime.now(timezone.utc).isoformat()
            data_json = json.dumps(data, default=str)
            
            # Use INSERT OR REPLACE to handle updates
            self._connection.execute(f"""
                INSERT OR REPLACE INTO {table} (id, data, created_at, updated_at)
                VALUES (?, ?, 
                    COALESCE((SELECT created_at FROM {table} WHERE id = ?), ?),
                    ?)
            """, (record_id, data_json, record_id, now, now))
            
            # Only commit if not in transaction
            if not self._in_transaction:
                self._connection.commit()
    
    def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Load a record from SQLite"""
        with self._lock:
            self._ensure_table(table)
            cursor = self._connection.execute(f"""
                SELECT data FROM {table} WHERE id = ?
            """, (record_id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row['data'])
            return None
    
    def load_all(self, table: str) -> List[Dict[str, Any]]:
        """Load all records from a table"""
        with self._lock:
            self._ensure_table(table)
            cursor = self._connection.execute(f"""
                SELECT data FROM {table} ORDER BY created_at
            """)
            return [json.loads(row['data']) for row in cursor.fetchall()]
    
    def delete(self, table: str, record_id: str) -> bool:
        """Delete a record from SQLite"""
        with self._lock:
            self._ensure_table(table)
            cursor = self._connection.execute(f"""
                DELETE FROM {table} WHERE id = ?
            """, (record_id,))
            
            # Only commit if not in transaction
            if not self._in_transaction:
                self._connection.commit()
            return cursor.rowcount > 0
    
    def exists(self, table: str, record_id: str) -> bool:
        """Check if a record exists"""
        with self._lock:
            self._ensure_table(table)
            cursor = self._connection.execute(f"""
                SELECT 1 FROM {table} WHERE id = ? LIMIT 1
            """, (record_id,))
            return cursor.fetchone() is not None
    
    def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find records matching filters (simple JSON key matching)"""
        with self._lock:
            self._ensure_table(table)
            cursor = self._connection.execute(f"""
                SELECT data FROM {table} ORDER BY created_at
            """)
            
            results = []
            for row in cursor.fetchall():
                record = json.loads(row['data'])
                match = True
                for key, value in filters.items():
                    if key not in record or record[key] != value:
                        match = False
                        break
                if match:
                    results.append(record)
            
            return results
    
    def count(self, table: str) -> int:
        """Count records in table"""
        with self._lock:
            self._ensure_table(table)
            cursor = self._connection.execute(f"""
                SELECT COUNT(*) as count FROM {table}
            """)
            return cursor.fetchone()['count']
    
    def clear_table(self, table: str) -> None:
        """Clear all records from a table"""
        with self._lock:
            self._ensure_table(table)
            self._connection.execute(f"DELETE FROM {table}")
            
            # Only commit if not in transaction
            if not self._in_transaction:
                self._connection.commit()
    
    def begin_transaction(self) -> None:
        """Start a database transaction"""
        with self._lock:
            if not self._in_transaction:
                # SQLite with isolation_level='DEFERRED' automatically starts transactions
                # We just need to track the state
                self._in_transaction = True
    
    def commit(self) -> None:
        """Commit current transaction"""
        with self._lock:
            if self._in_transaction:
                self._connection.commit()
                self._in_transaction = False
    
    def rollback(self) -> None:
        """Rollback current transaction"""
        with self._lock:
            if self._in_transaction:
                self._connection.rollback()
                self._in_transaction = False
    
    def close(self) -> None:
        """Close SQLite connection"""
        with self._lock:
            if self._connection:
                self._connection.close()
                self._connection = None


class PostgreSQLStorage(StorageInterface):
    """PostgreSQL storage backend with ACID transaction support"""
    
    def __init__(self, connection_string: str):
        try:
            import psycopg2
            import psycopg2.extras
            self.psycopg2 = psycopg2
            self.extras = psycopg2.extras
        except ImportError:
            raise ImportError("psycopg2 is required for PostgreSQL storage. Install with: pip install psycopg2-binary")
        
        self.connection_string = connection_string
        self._connection = None
        self._lock = threading.RLock()
        self._in_transaction = False
        self._connect()
    
    def _connect(self) -> None:
        """Establish database connection"""
        with self._lock:
            if self._connection:
                try:
                    self._connection.close()
                except Exception:
                    pass
            
            self._connection = self.psycopg2.connect(
                self.connection_string,
                cursor_factory=self.extras.RealDictCursor
            )
            self._connection.autocommit = False  # We handle transactions manually
    
    def _ensure_table(self, table: str) -> None:
        """Ensure table exists with proper schema"""
        with self._lock:
            cursor = self._connection.cursor()
            try:
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id TEXT PRIMARY KEY,
                        data JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{table}_data 
                    ON {table} USING gin(data)
                """)
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{table}_created_at 
                    ON {table}(created_at)
                """)
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{table}_updated_at 
                    ON {table}(updated_at)
                """)
                
                # Only commit if not in transaction
                if not self._in_transaction:
                    self._connection.commit()
            finally:
                cursor.close()
    
    def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        """Save a record to PostgreSQL using UPSERT"""
        with self._lock:
            self._ensure_table(table)
            
            now = datetime.now(timezone.utc)
            data_json = json.dumps(data, default=str)
            
            cursor = self._connection.cursor()
            try:
                # UPSERT with ON CONFLICT
                cursor.execute(f"""
                    INSERT INTO {table} (id, data, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        data = EXCLUDED.data,
                        updated_at = EXCLUDED.updated_at
                """, (record_id, data_json, now, now))
                
                # Only commit if not in transaction
                if not self._in_transaction:
                    self._connection.commit()
            finally:
                cursor.close()
    
    def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Load a record from PostgreSQL"""
        with self._lock:
            self._ensure_table(table)
            
            cursor = self._connection.cursor()
            try:
                cursor.execute(f"""
                    SELECT data FROM {table} WHERE id = %s
                """, (record_id,))
                row = cursor.fetchone()
                if row:
                    return dict(row['data'])
                return None
            finally:
                cursor.close()
    
    def load_all(self, table: str) -> List[Dict[str, Any]]:
        """Load all records from a table"""
        with self._lock:
            self._ensure_table(table)
            
            cursor = self._connection.cursor()
            try:
                cursor.execute(f"""
                    SELECT data FROM {table} ORDER BY created_at
                """)
                return [dict(row['data']) for row in cursor.fetchall()]
            finally:
                cursor.close()
    
    def delete(self, table: str, record_id: str) -> bool:
        """Delete a record from PostgreSQL"""
        with self._lock:
            self._ensure_table(table)
            
            cursor = self._connection.cursor()
            try:
                cursor.execute(f"""
                    DELETE FROM {table} WHERE id = %s
                """, (record_id,))
                
                # Only commit if not in transaction
                if not self._in_transaction:
                    self._connection.commit()
                
                return cursor.rowcount > 0
            finally:
                cursor.close()
    
    def exists(self, table: str, record_id: str) -> bool:
        """Check if a record exists"""
        with self._lock:
            self._ensure_table(table)
            
            cursor = self._connection.cursor()
            try:
                cursor.execute(f"""
                    SELECT 1 FROM {table} WHERE id = %s LIMIT 1
                """, (record_id,))
                return cursor.fetchone() is not None
            finally:
                cursor.close()
    
    def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find records matching filters using JSONB operators"""
        with self._lock:
            self._ensure_table(table)
            
            cursor = self._connection.cursor()
            try:
                if not filters:
                    cursor.execute(f"""
                        SELECT data FROM {table} ORDER BY created_at
                    """)
                else:
                    # Build WHERE clause using JSONB operators
                    conditions = []
                    params = []
                    for key, value in filters.items():
                        conditions.append("data ->> %s = %s")
                        params.extend([key, str(value)])
                    
                    where_clause = " AND ".join(conditions)
                    cursor.execute(f"""
                        SELECT data FROM {table} 
                        WHERE {where_clause}
                        ORDER BY created_at
                    """, params)
                
                return [dict(row['data']) for row in cursor.fetchall()]
            finally:
                cursor.close()
    
    def count(self, table: str) -> int:
        """Count records in table"""
        with self._lock:
            self._ensure_table(table)
            
            cursor = self._connection.cursor()
            try:
                cursor.execute(f"""
                    SELECT COUNT(*) as count FROM {table}
                """)
                return cursor.fetchone()['count']
            finally:
                cursor.close()
    
    def clear_table(self, table: str) -> None:
        """Clear all records from a table"""
        with self._lock:
            self._ensure_table(table)
            
            cursor = self._connection.cursor()
            try:
                cursor.execute(f"DELETE FROM {table}")
                
                # Only commit if not in transaction
                if not self._in_transaction:
                    self._connection.commit()
            finally:
                cursor.close()
    
    def begin_transaction(self) -> None:
        """Start a database transaction"""
        with self._lock:
            if not self._in_transaction:
                # PostgreSQL transactions start automatically
                self._in_transaction = True
    
    def commit(self) -> None:
        """Commit current transaction"""
        with self._lock:
            if self._in_transaction:
                self._connection.commit()
                self._in_transaction = False
    
    def rollback(self) -> None:
        """Rollback current transaction"""
        with self._lock:
            if self._in_transaction:
                self._connection.rollback()
                self._in_transaction = False
    
    def close(self) -> None:
        """Close PostgreSQL connection"""
        with self._lock:
            if self._connection:
                try:
                    self._connection.close()
                except Exception:
                    pass
                self._connection = None


class StorageManager:
    """Manages storage backend selection and provides convenience methods"""
    
    def __init__(self, storage: StorageInterface):
        self.storage = storage
    
    def save_record(self, record: StorageRecord, table: str) -> None:
        """Save a StorageRecord to storage"""
        self.storage.save(table, record.id, record.to_dict())
    
    def load_record(self, record_type: type, table: str, record_id: str) -> Optional[StorageRecord]:
        """Load and convert to StorageRecord"""
        data = self.storage.load(table, record_id)
        if data:
            return record_type.from_dict(data)
        return None
    
    def load_all_records(self, record_type: type, table: str) -> List[StorageRecord]:
        """Load all records and convert to StorageRecord objects"""
        all_data = self.storage.load_all(table)
        return [record_type.from_dict(data) for data in all_data]
    
    def find_records(self, record_type: type, table: str, filters: Dict[str, Any]) -> List[StorageRecord]:
        """Find records and convert to StorageRecord objects"""
        found_data = self.storage.find(table, filters)
        return [record_type.from_dict(data) for data in found_data]
    
    def close(self) -> None:
        """Close storage backend"""
        self.storage.close()