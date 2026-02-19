"""
Database Migration System

Simple migration system for managing database schema changes without external dependencies.
Supports both PostgreSQL and SQLite backends.
"""

from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timezone
import logging
from .storage import StorageInterface


logger = logging.getLogger(__name__)


class Migration:
    """Represents a single database migration"""
    
    def __init__(self, version: int, name: str, up_sql: str, down_sql: Optional[str] = None):
        self.version = version
        self.name = name
        self.up_sql = up_sql
        self.down_sql = down_sql
        self.applied_at: Optional[datetime] = None
    
    def __str__(self) -> str:
        return f"Migration v{self.version:03d}: {self.name}"
    
    def __repr__(self) -> str:
        return f"Migration(version={self.version}, name='{self.name}')"


class MigrationManager:
    """Manages database migrations"""
    
    def __init__(self, storage: StorageInterface):
        self.storage = storage
        self.migrations: List[Migration] = []
        self._migration_table = "schema_migrations"
        self._init_migrations()
        self._ensure_migration_table()
    
    def _init_migrations(self) -> None:
        """Initialize built-in migrations"""
        
        # v001: Create core customer and account tables
        self.add_migration(1, "Create core tables", """
            -- This migration is handled by storage backend auto-creation
            -- Tables: customers, accounts, transactions, journal_entries
            SELECT 1; -- No-op for JSONB storage
        """, """
            -- Tables will be dropped by clear operations if needed
            SELECT 1; -- No-op for JSONB storage
        """)
        
        # v002: Create product definition tables
        self.add_migration(2, "Create product tables", """
            -- Product definitions stored as JSON documents
            -- Tables: products, product_templates, fee_schedules
            SELECT 1; -- No-op for JSONB storage
        """, """
            SELECT 1; -- No-op for JSONB storage
        """)
        
        # v003: Create collections and recovery tables
        self.add_migration(3, "Create collections tables", """
            -- Collections workflow and recovery tracking
            -- Tables: collection_cases, recovery_actions, payment_plans
            SELECT 1; -- No-op for JSONB storage
        """, """
            SELECT 1; -- No-op for JSONB storage
        """)
        
        # v004: Create workflow and approval tables
        self.add_migration(4, "Create workflow tables", """
            -- Workflow states and approval chains
            -- Tables: workflows, workflow_states, approvals, approval_chains
            SELECT 1; -- No-op for JSONB storage
        """, """
            SELECT 1; -- No-op for JSONB storage
        """)
        
        # v005: Create RBAC (Role-Based Access Control) tables
        self.add_migration(5, "Create RBAC tables", """
            -- User roles and permissions
            -- Tables: users, roles, permissions, user_roles, role_permissions
            SELECT 1; -- No-op for JSONB storage
        """, """
            SELECT 1; -- No-op for JSONB storage
        """)
        
        # v006: Create custom fields and metadata tables
        self.add_migration(6, "Create custom fields tables", """
            -- Flexible custom fields for extensibility
            -- Tables: custom_fields, field_definitions, entity_fields
            SELECT 1; -- No-op for JSONB storage
        """, """
            SELECT 1; -- No-op for JSONB storage
        """)
        
        # v007: Create audit and change tracking tables
        self.add_migration(7, "Create audit tables", """
            -- Audit logs and change tracking
            -- Tables: audit_logs, change_history, user_sessions
            SELECT 1; -- No-op for JSONB storage
        """, """
            SELECT 1; -- No-op for JSONB storage
        """)
        
        # v008: Create Kafka event and integration tables
        self.add_migration(8, "Create kafka event tables", """
            -- Event sourcing and external integrations
            -- Tables: events, event_handlers, integration_configs, message_queue
            SELECT 1; -- No-op for JSONB storage
        """, """
            SELECT 1; -- No-op for JSONB storage
        """)
    
    def _ensure_migration_table(self) -> None:
        """Ensure the migration tracking table exists"""
        try:
            # Try to load from migration table to see if it exists
            self.storage.load_all(self._migration_table)
        except Exception:
            # Table doesn't exist, create it by saving a dummy record and deleting it
            migration_record = {
                "version": 0,
                "name": "init",
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "checksum": "init"
            }
            self.storage.save(self._migration_table, "init", migration_record)
            self.storage.delete(self._migration_table, "init")
            logger.info("Created migration tracking table")
    
    def add_migration(self, version: int, name: str, up_sql: str, down_sql: Optional[str] = None) -> None:
        """Add a migration to the manager"""
        migration = Migration(version, name, up_sql, down_sql)
        self.migrations.append(migration)
        # Keep migrations sorted by version
        self.migrations.sort(key=lambda m: m.version)
    
    def get_current_version(self) -> int:
        """Get the current database version"""
        try:
            applied_migrations = self.storage.load_all(self._migration_table)
            if not applied_migrations:
                return 0
            
            versions = [m["version"] for m in applied_migrations if isinstance(m.get("version"), int)]
            return max(versions) if versions else 0
        except Exception as e:
            logger.warning(f"Could not determine current version: {e}")
            return 0
    
    def get_pending_migrations(self, target_version: Optional[int] = None) -> List[Migration]:
        """Get list of pending migrations"""
        current_version = self.get_current_version()
        max_version = target_version or max((m.version for m in self.migrations), default=0)
        
        pending = []
        for migration in self.migrations:
            if current_version < migration.version <= max_version:
                pending.append(migration)
        
        return pending
    
    def get_applied_migrations(self) -> List[Dict[str, Any]]:
        """Get list of applied migrations"""
        try:
            return self.storage.load_all(self._migration_table)
        except Exception:
            return []
    
    def migrate_up(self, target_version: Optional[int] = None) -> List[Migration]:
        """Apply pending migrations up to target version"""
        pending = self.get_pending_migrations(target_version)
        applied = []
        
        if not pending:
            logger.info("No pending migrations to apply")
            return applied
        
        logger.info(f"Applying {len(pending)} pending migrations")
        
        for migration in pending:
            try:
                logger.info(f"Applying {migration}")
                
                with self.storage.atomic():
                    # Execute the migration SQL if it's not a no-op
                    if migration.up_sql.strip() != "SELECT 1;":
                        self._execute_sql(migration.up_sql)
                    
                    # Record the migration as applied
                    migration_record = {
                        "version": migration.version,
                        "name": migration.name,
                        "applied_at": datetime.now(timezone.utc).isoformat(),
                        "checksum": self._calculate_checksum(migration.up_sql)
                    }
                    self.storage.save(
                        self._migration_table, 
                        f"v{migration.version:03d}", 
                        migration_record
                    )
                
                migration.applied_at = datetime.now(timezone.utc)
                applied.append(migration)
                logger.info(f"Successfully applied {migration}")
                
            except Exception as e:
                logger.error(f"Failed to apply {migration}: {e}")
                raise RuntimeError(f"Migration failed: {migration}") from e
        
        logger.info(f"Successfully applied {len(applied)} migrations")
        return applied
    
    def migrate_down(self, target_version: int) -> List[Migration]:
        """Rollback migrations down to target version"""
        current_version = self.get_current_version()
        
        if target_version >= current_version:
            logger.info("Target version is not lower than current version")
            return []
        
        # Find migrations to rollback (in reverse order)
        rollback_migrations = []
        for migration in reversed(self.migrations):
            if target_version < migration.version <= current_version:
                rollback_migrations.append(migration)
        
        rolledback = []
        
        logger.info(f"Rolling back {len(rollback_migrations)} migrations")
        
        for migration in rollback_migrations:
            try:
                if not migration.down_sql:
                    logger.warning(f"No rollback SQL for {migration}, skipping")
                    continue
                
                logger.info(f"Rolling back {migration}")
                
                with self.storage.atomic():
                    # Execute the rollback SQL if it's not a no-op
                    if migration.down_sql.strip() != "SELECT 1;":
                        self._execute_sql(migration.down_sql)
                    
                    # Remove the migration record
                    self.storage.delete(self._migration_table, f"v{migration.version:03d}")
                
                rolledback.append(migration)
                logger.info(f"Successfully rolled back {migration}")
                
            except Exception as e:
                logger.error(f"Failed to rollback {migration}: {e}")
                raise RuntimeError(f"Rollback failed: {migration}") from e
        
        logger.info(f"Successfully rolled back {len(rolledback)} migrations")
        return rolledback
    
    def _execute_sql(self, sql: str) -> None:
        """Execute raw SQL (placeholder for actual implementation)"""
        # For JSONB storage backends, most migrations are no-ops
        # since tables are created automatically
        # This method would be extended for actual DDL execution in SQL databases
        logger.debug(f"Executing SQL: {sql[:100]}...")
    
    def _calculate_checksum(self, sql: str) -> str:
        """Calculate checksum for migration SQL"""
        import hashlib
        return hashlib.md5(sql.encode()).hexdigest()
    
    def validate_migrations(self) -> bool:
        """Validate that applied migrations match expected checksums"""
        applied = self.get_applied_migrations()
        
        for applied_migration in applied:
            version = applied_migration["version"]
            stored_checksum = applied_migration.get("checksum", "")
            
            # Find the corresponding migration definition
            migration = next((m for m in self.migrations if m.version == version), None)
            if not migration:
                logger.warning(f"Applied migration v{version} not found in definitions")
                continue
            
            expected_checksum = self._calculate_checksum(migration.up_sql)
            if stored_checksum != expected_checksum:
                logger.error(f"Checksum mismatch for v{version}: expected {expected_checksum}, got {stored_checksum}")
                return False
        
        logger.info("All applied migrations validated successfully")
        return True
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get detailed migration status"""
        current_version = self.get_current_version()
        pending = self.get_pending_migrations()
        applied = self.get_applied_migrations()
        
        return {
            "current_version": current_version,
            "latest_version": max((m.version for m in self.migrations), default=0),
            "pending_count": len(pending),
            "applied_count": len(applied),
            "pending_migrations": [
                {"version": m.version, "name": m.name} for m in pending
            ],
            "needs_migration": len(pending) > 0
        }