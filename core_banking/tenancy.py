"""
Multi-Tenancy Support Module

Provides comprehensive multi-tenant support for Nexum core banking system.
Each financial institution gets isolated data within the same deployment.
"""

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from decimal import Decimal

from .storage import StorageInterface


class TenantIsolationStrategy(Enum):
    """Strategy for isolating tenant data"""
    SHARED_TABLE = "shared_table"  # All tenants in same tables, filtered by tenant_id
    SCHEMA_PER_TENANT = "schema_per_tenant"  # Each tenant gets its own PostgreSQL schema  
    DATABASE_PER_TENANT = "database_per_tenant"  # Each tenant gets its own database


class SubscriptionTier(Enum):
    """Subscription tier options for tenants"""
    FREE = "free"
    BASIC = "basic" 
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


@dataclass
class Tenant:
    """Tenant data class representing a financial institution"""
    id: str
    name: str
    code: str  # Unique short code, e.g., "ACME_BANK"
    display_name: str
    description: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    settings: Dict[str, Any] = field(default_factory=dict)  # Tenant-specific config overrides
    database_schema: Optional[str] = None  # For schema-per-tenant isolation
    max_users: Optional[int] = None  # Optional quota
    max_accounts: Optional[int] = None  # Optional quota
    subscription_tier: SubscriptionTier = SubscriptionTier.FREE
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None  # Branding color in hex format
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        result = {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'display_name': self.display_name,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'settings': self.settings,
            'database_schema': self.database_schema,
            'max_users': self.max_users,
            'max_accounts': self.max_accounts,
            'subscription_tier': self.subscription_tier.value,
            'contact_email': self.contact_email,
            'contact_phone': self.contact_phone,
            'logo_url': self.logo_url,
            'primary_color': self.primary_color
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Tenant':
        """Create Tenant from dictionary"""
        # Convert string timestamps back to datetime
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        # Convert string subscription tier back to enum
        if isinstance(data.get('subscription_tier'), str):
            data['subscription_tier'] = SubscriptionTier(data['subscription_tier'])
        
        return cls(**data)


# Thread-local tenant context using contextvars
_current_tenant = contextvars.ContextVar('current_tenant', default=None)


def get_current_tenant() -> Optional[str]:
    """Get the current tenant ID for this context"""
    return _current_tenant.get()


def set_current_tenant(tenant_id: str) -> None:
    """Set the current tenant ID for this context"""
    _current_tenant.set(tenant_id)


@contextmanager
def tenant_context(tenant_id: str):
    """Context manager for temporary tenant switching"""
    token = _current_tenant.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant.reset(token)


class TenantAwareStorage(StorageInterface):
    """Storage wrapper that adds tenant isolation to any StorageInterface"""
    
    def __init__(self, inner_storage: StorageInterface, 
                 isolation: TenantIsolationStrategy = TenantIsolationStrategy.SHARED_TABLE):
        self.inner = inner_storage
        self.isolation = isolation
    
    def _add_tenant_filter(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add tenant ID to data if current tenant is set"""
        tenant_id = get_current_tenant()
        if tenant_id:
            data = data.copy()
            data['_tenant_id'] = tenant_id
        return data
    
    def _check_tenant_access(self, data: Dict[str, Any]) -> bool:
        """Check if current tenant can access this data"""
        tenant_id = get_current_tenant()
        if not tenant_id:
            # No tenant set - super-admin mode, can see all data
            return True
        
        record_tenant = data.get('_tenant_id')
        if not record_tenant:
            # Record has no tenant - accessible in super-admin mode only
            return False
        
        return record_tenant == tenant_id
    
    def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        """Save a record with tenant filtering"""
        tenant_data = self._add_tenant_filter(data)
        self.inner.save(table, record_id, tenant_data)
    
    def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Load a record with tenant isolation"""
        result = self.inner.load(table, record_id)
        if result and not self._check_tenant_access(result):
            return None  # Tenant isolation - can't see other tenant's data
        return result
    
    def load_all(self, table: str) -> List[Dict[str, Any]]:
        """Load all records with tenant filtering"""
        all_records = self.inner.load_all(table)
        return [record for record in all_records if self._check_tenant_access(record)]
    
    def delete(self, table: str, record_id: str) -> bool:
        """Delete a record with tenant verification"""
        # First check if we can access this record
        record = self.inner.load(table, record_id)
        if not record or not self._check_tenant_access(record):
            return False  # Can't delete what we can't see
        
        return self.inner.delete(table, record_id)
    
    def exists(self, table: str, record_id: str) -> bool:
        """Check if record exists and is accessible by current tenant"""
        record = self.inner.load(table, record_id)
        return record is not None and self._check_tenant_access(record)
    
    def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find records with tenant filtering"""
        tenant_filters = self._add_tenant_filter(filters)
        return self.inner.find(table, tenant_filters)
    
    def count(self, table: str) -> int:
        """Count records accessible by current tenant"""
        return len(self.load_all(table))
    
    def clear_table(self, table: str) -> None:
        """Clear table - only for super-admin (no tenant set)"""
        tenant_id = get_current_tenant()
        if tenant_id:
            raise PermissionError("Cannot clear table with tenant context active")
        self.inner.clear_table(table)
    
    def close(self) -> None:
        """Close underlying storage"""
        self.inner.close()
    
    def begin_transaction(self) -> None:
        """Begin transaction on underlying storage"""
        self.inner.begin_transaction()
    
    def commit(self) -> None:
        """Commit transaction on underlying storage"""
        self.inner.commit()
    
    def rollback(self) -> None:
        """Rollback transaction on underlying storage"""
        self.inner.rollback()


@dataclass
class TenantStats:
    """Statistics for a tenant"""
    tenant_id: str
    user_count: int = 0
    account_count: int = 0
    transaction_count: int = 0
    total_balance: Decimal = Decimal('0.00')
    last_activity: Optional[datetime] = None


class TenantManager:
    """Manager for tenant operations and quota enforcement"""
    
    TENANT_TABLE = "tenants"
    
    def __init__(self, storage: StorageInterface):
        # Use raw storage (not tenant-aware) for tenant registry
        self.storage = storage
    
    def create_tenant(self, name: str, code: str, display_name: str,
                     description: str = "",
                     settings: Optional[Dict[str, Any]] = None,
                     database_schema: Optional[str] = None,
                     max_users: Optional[int] = None,
                     max_accounts: Optional[int] = None,
                     subscription_tier: SubscriptionTier = SubscriptionTier.FREE,
                     contact_email: Optional[str] = None,
                     contact_phone: Optional[str] = None,
                     logo_url: Optional[str] = None,
                     primary_color: Optional[str] = None,
                     tenant_id: Optional[str] = None) -> Tenant:
        """Create a new tenant"""
        import uuid
        
        if not tenant_id:
            tenant_id = str(uuid.uuid4())
        
        # Check if code is unique
        existing = self.get_tenant_by_code(code)
        if existing:
            raise ValueError(f"Tenant code '{code}' already exists")
        
        tenant = Tenant(
            id=tenant_id,
            name=name,
            code=code,
            display_name=display_name,
            description=description,
            settings=settings or {},
            database_schema=database_schema,
            max_users=max_users,
            max_accounts=max_accounts,
            subscription_tier=subscription_tier,
            contact_email=contact_email,
            contact_phone=contact_phone,
            logo_url=logo_url,
            primary_color=primary_color
        )
        
        self.storage.save(self.TENANT_TABLE, tenant.id, tenant.to_dict())
        return tenant
    
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        data = self.storage.load(self.TENANT_TABLE, tenant_id)
        if data:
            return Tenant.from_dict(data)
        return None
    
    def get_tenant_by_code(self, code: str) -> Optional[Tenant]:
        """Get tenant by code"""
        tenants = self.storage.find(self.TENANT_TABLE, {'code': code})
        if tenants:
            return Tenant.from_dict(tenants[0])
        return None
    
    def list_tenants(self, is_active: Optional[bool] = None) -> List[Tenant]:
        """List all tenants, optionally filtered by active status"""
        filters = {}
        if is_active is not None:
            filters['is_active'] = is_active
        
        tenant_data = self.storage.find(self.TENANT_TABLE, filters)
        return [Tenant.from_dict(data) for data in tenant_data]
    
    def update_tenant(self, tenant_id: str, **kwargs) -> Optional[Tenant]:
        """Update tenant fields"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return None
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        
        tenant.updated_at = datetime.now(timezone.utc)
        self.storage.save(self.TENANT_TABLE, tenant.id, tenant.to_dict())
        return tenant
    
    def activate_tenant(self, tenant_id: str) -> bool:
        """Activate a tenant"""
        tenant = self.update_tenant(tenant_id, is_active=True)
        return tenant is not None
    
    def deactivate_tenant(self, tenant_id: str) -> bool:
        """Deactivate a tenant"""
        tenant = self.update_tenant(tenant_id, is_active=False)
        return tenant is not None
    
    def check_quota(self, tenant_id: str, resource_type: str) -> bool:
        """Check if tenant has quota available for resource"""
        tenant = self.get_tenant(tenant_id)
        if not tenant or not tenant.is_active:
            return False
        
        # For basic quota checking, we'll implement simple limits
        # In production, this would integrate with actual usage metrics
        if resource_type == "users" and tenant.max_users:
            # This would need to count actual users for the tenant
            return True  # Simplified for now
        
        if resource_type == "accounts" and tenant.max_accounts:
            # This would need to count actual accounts for the tenant  
            return True  # Simplified for now
        
        return True  # No quota limit set
    
    def get_tenant_stats(self, tenant_id: str, storage_manager=None) -> Optional[TenantStats]:
        """Get usage statistics for a tenant"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return None
        
        stats = TenantStats(tenant_id=tenant_id)
        
        # If we have a storage manager, we can gather actual stats
        if storage_manager:
            with tenant_context(tenant_id):
                # Count users, accounts, transactions, etc.
                # This would integrate with the actual data tables
                # For now, return basic stats
                pass
        
        return stats
    
    def get_usage_report(self) -> List[TenantStats]:
        """Get usage statistics for all tenants"""
        tenants = self.list_tenants(is_active=True)
        return [self.get_tenant_stats(tenant.id) or TenantStats(tenant_id=tenant.id) 
                for tenant in tenants]


class TenantMiddleware:
    """Middleware for extracting tenant information from requests"""
    
    def __init__(self, tenant_manager: TenantManager):
        self.tenant_manager = tenant_manager
    
    def extract_tenant_from_header(self, headers: Dict[str, str]) -> Optional[str]:
        """Extract tenant ID from X-Tenant-ID header"""
        return headers.get('x-tenant-id') or headers.get('X-Tenant-ID')
    
    def extract_tenant_from_subdomain(self, host: str) -> Optional[str]:
        """Extract tenant from subdomain (e.g., acme.nexum.io -> acme)"""
        if '.' in host:
            subdomain = host.split('.')[0]
            # Look up tenant by code
            tenant = self.tenant_manager.get_tenant_by_code(subdomain.upper())
            if tenant:
                return tenant.id
        return None
    
    def extract_tenant_from_jwt(self, token: str) -> Optional[str]:
        """Extract tenant ID from JWT claim"""
        try:
            # Simple JWT parsing without signature verification for testing
            # In production, this would use proper JWT validation
            if '.' not in token:
                return None
            
            parts = token.split('.')
            if len(parts) < 2:
                return None
            
            # Decode the payload (second part)
            import base64
            import json
            payload_part = parts[1]
            
            # Add padding if needed
            padding = 4 - len(payload_part) % 4
            if padding != 4:
                payload_part += '=' * padding
            
            payload_bytes = base64.urlsafe_b64decode(payload_part)
            payload = json.loads(payload_bytes)
            return payload.get('tenant_id')
        except Exception:
            return None
    
    async def extract_tenant(self, request) -> Optional[str]:
        """Extract tenant ID from various sources in priority order"""
        # Option 1: X-Tenant-ID header (highest priority)
        tenant_id = self.extract_tenant_from_header(dict(request.headers))
        if tenant_id:
            # Validate tenant exists and is active
            tenant = self.tenant_manager.get_tenant(tenant_id)
            if tenant and tenant.is_active:
                return tenant_id
        
        # Option 2: Subdomain extraction
        if hasattr(request, 'url') and request.url.hostname:
            tenant_id = self.extract_tenant_from_subdomain(request.url.hostname)
            if tenant_id:
                tenant = self.tenant_manager.get_tenant(tenant_id)
                if tenant and tenant.is_active:
                    return tenant_id
        
        # Option 3: JWT claim
        auth_header = request.headers.get('authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            tenant_id = self.extract_tenant_from_jwt(token)
            if tenant_id:
                tenant = self.tenant_manager.get_tenant(tenant_id)
                if tenant and tenant.is_active:
                    return tenant_id
        
        return None


# Convenience functions for FastAPI integration
async def tenant_middleware_func(request, call_next, tenant_manager: TenantManager):
    """FastAPI middleware function for tenant extraction"""
    middleware = TenantMiddleware(tenant_manager)
    tenant_id = await middleware.extract_tenant(request)
    
    if tenant_id:
        with tenant_context(tenant_id):
            response = await call_next(request)
            return response
    else:
        # No tenant context - super-admin mode
        response = await call_next(request)
        return response


def get_current_tenant_info(tenant_manager: TenantManager) -> Optional[Tenant]:
    """Get current tenant information (for use in FastAPI dependencies)"""
    tenant_id = get_current_tenant()
    if tenant_id:
        return tenant_manager.get_tenant(tenant_id)
    return None