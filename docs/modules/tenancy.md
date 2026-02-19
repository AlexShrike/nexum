# Multi-Tenancy Module

The Tenancy module provides comprehensive multi-tenant support for Nexum, allowing multiple financial institutions to share the same deployment while maintaining complete data isolation and customization.

## Overview

Multi-tenancy enables Software-as-a-Service (SaaS) deployment where each financial institution (tenant) gets isolated data, custom branding, and separate configuration within the same Nexum instance. This reduces operational costs while maintaining security and compliance requirements.

## Key Concepts

### Tenant
A tenant represents a financial institution (bank, credit union, fintech) using the Nexum platform. Each tenant has:

- **Isolated Data**: Complete data separation from other tenants
- **Custom Branding**: Logo, colors, display name
- **Subscription Tier**: Feature and quota limits
- **Configuration**: Tenant-specific settings and overrides

### Tenant Context
The current tenant is maintained using Python's `contextvars` for thread-safe, async-compatible tenant switching. All database operations automatically filter by the current tenant ID.

### Isolation Strategies

The module supports multiple tenant isolation approaches:

- **SHARED_TABLE**: All tenants share tables, filtered by tenant_id (default)
- **SCHEMA_PER_TENANT**: Each tenant gets a separate PostgreSQL schema
- **DATABASE_PER_TENANT**: Each tenant gets a separate database (future)

## Key Classes

### TenantIsolationStrategy (Enum)

```python
class TenantIsolationStrategy(Enum):
    SHARED_TABLE = "shared_table"           # Shared tables with tenant_id filtering
    SCHEMA_PER_TENANT = "schema_per_tenant" # Separate PostgreSQL schemas  
    DATABASE_PER_TENANT = "database_per_tenant" # Separate databases
```

### SubscriptionTier (Enum)

```python
class SubscriptionTier(Enum):
    FREE = "free"                 # Basic features, limited quotas
    BASIC = "basic"              # Standard features
    PROFESSIONAL = "professional" # Advanced features
    ENTERPRISE = "enterprise"     # Full features, custom quotas
```

### Tenant

Core tenant data class:

```python
@dataclass
class Tenant:
    id: str                                    # Unique tenant identifier
    name: str                                  # Internal name
    code: str                                  # Short code (e.g., "ACME_BANK")
    display_name: str                          # Customer-facing name
    description: str = ""                      # Optional description
    is_active: bool = True                     # Whether tenant is active
    created_at: datetime                       # Creation timestamp
    updated_at: datetime                       # Last update timestamp
    settings: Dict[str, Any] = {}              # Tenant-specific config overrides
    database_schema: Optional[str] = None      # For schema-per-tenant isolation
    max_users: Optional[int] = None            # User quota (None = unlimited)
    max_accounts: Optional[int] = None         # Account quota (None = unlimited)
    subscription_tier: SubscriptionTier = SubscriptionTier.FREE
    contact_email: Optional[str] = None        # Primary contact email
    contact_phone: Optional[str] = None        # Primary contact phone
    logo_url: Optional[str] = None             # Tenant logo URL
    primary_color: Optional[str] = None        # Branding color (#RRGGBB)
```

**Methods:**
- `to_dict()` - Serialize to dictionary for storage
- `from_dict(data)` - Deserialize from dictionary

### TenantAwareStorage

Storage wrapper that adds tenant isolation to any `StorageInterface`:

```python
class TenantAwareStorage(StorageInterface):
    def __init__(self, inner_storage: StorageInterface, 
                 isolation: TenantIsolationStrategy = TenantIsolationStrategy.SHARED_TABLE):
        # Wraps existing storage with tenant filtering
```

**Features:**
- Automatically adds `_tenant_id` field to all records
- Filters all queries by current tenant context
- Prevents cross-tenant data access
- Maintains full `StorageInterface` compatibility

### TenantManager

Manager for tenant operations and quota enforcement:

```python
class TenantManager:
    def __init__(self, storage: StorageInterface):
        # Initialize with raw storage (not tenant-aware)
        
    def create_tenant(self, name: str, code: str, **kwargs) -> Tenant:
        """Create a new tenant"""
        
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        
    def get_tenant_by_code(self, code: str) -> Optional[Tenant]:
        """Get tenant by code"""
        
    def list_tenants(self, is_active: Optional[bool] = None) -> List[Tenant]:
        """List all tenants"""
        
    def update_tenant(self, tenant_id: str, **kwargs) -> Optional[Tenant]:
        """Update tenant fields"""
        
    def activate_tenant(self, tenant_id: str) -> bool:
        """Activate a tenant"""
        
    def deactivate_tenant(self, tenant_id: str) -> bool:
        """Deactivate a tenant"""
        
    def check_quota(self, tenant_id: str, resource_type: str) -> bool:
        """Check if tenant has quota for resource"""
        
    def get_tenant_stats(self, tenant_id: str) -> Optional[TenantStats]:
        """Get usage statistics for tenant"""
```

### TenantStats

Usage statistics for monitoring and billing:

```python
@dataclass
class TenantStats:
    tenant_id: str
    user_count: int = 0
    account_count: int = 0  
    transaction_count: int = 0
    total_balance: Decimal = Decimal('0.00')
    last_activity: Optional[datetime] = None
```

### TenantMiddleware

Middleware for extracting tenant context from HTTP requests:

```python
class TenantMiddleware:
    def __init__(self, tenant_manager: TenantManager):
        # Initialize with tenant manager
        
    def extract_tenant_from_header(self, headers: Dict[str, str]) -> Optional[str]:
        """Extract tenant ID from X-Tenant-ID header"""
        
    def extract_tenant_from_subdomain(self, host: str) -> Optional[str]:
        """Extract tenant from subdomain (e.g., acme.nexum.io -> acme)"""
        
    def extract_tenant_from_jwt(self, token: str) -> Optional[str]:
        """Extract tenant ID from JWT claim"""
        
    async def extract_tenant(self, request) -> Optional[str]:
        """Extract tenant ID from request (tries multiple methods)"""
```

## Tenant Context Management

### Context Variables

Thread-safe, async-compatible tenant context:

```python
# Get current tenant ID
tenant_id = get_current_tenant()

# Set tenant context  
set_current_tenant("tenant_abc123")

# Context manager for temporary tenant switching
with tenant_context("tenant_xyz789"):
    # All operations here use tenant_xyz789
    customers = customer_manager.list_customers()
# Context automatically restored
```

### Context Extraction Priority

The middleware extracts tenant context in this order:

1. **X-Tenant-ID Header** (highest priority) - Explicit tenant specification
2. **Subdomain** - Extract from request hostname (e.g., `acme.nexum.io`)
3. **JWT Claims** - Extract from `tenant_id` claim in JWT token

## Usage Examples

### Basic Tenant Setup

```python
from core_banking.tenancy import TenantManager, TenantAwareStorage, SubscriptionTier

# Initialize tenant-aware storage
raw_storage = PostgreSQLStorage(connection_string)
tenant_storage = TenantAwareStorage(raw_storage)

# Initialize tenant manager (uses raw storage)
tenant_manager = TenantManager(raw_storage)

# Create a new tenant
acme_bank = tenant_manager.create_tenant(
    name="ACME Bank",
    code="ACME_BANK",
    display_name="ACME Community Bank",
    description="Leading community bank serving local businesses",
    subscription_tier=SubscriptionTier.PROFESSIONAL,
    contact_email="admin@acmebank.com",
    max_users=50,
    max_accounts=5000,
    logo_url="https://acmebank.com/logo.png",
    primary_color="#1976D2"
)

print(f"Created tenant: {acme_bank.id}")
```

### Multi-Tenant Data Access

```python
from core_banking.tenancy import set_current_tenant, tenant_context

# Set global tenant context
set_current_tenant("tenant_acme_123")

# All operations now scoped to ACME Bank
customers = customer_manager.list_customers()  # Only ACME's customers
accounts = account_manager.list_accounts()     # Only ACME's accounts

# Temporary context switching
with tenant_context("tenant_xyz_456"):
    # Operations here use XYZ Bank's data
    xyz_customers = customer_manager.list_customers()
    
    # Create account for XYZ Bank
    account = account_manager.create_account({
        "customer_id": "cust_xyz_789",
        "product_type": "checking",
        "initial_deposit": "1000.00"
    })

# Back to ACME Bank context
acme_accounts = account_manager.list_accounts()
```

### FastAPI Integration

```python
from fastapi import FastAPI, Request, HTTPException
from core_banking.tenancy import TenantMiddleware, tenant_context

app = FastAPI()
tenant_middleware = TenantMiddleware(tenant_manager)

@app.middleware("http")
async def tenant_middleware_func(request: Request, call_next):
    """Extract tenant context from request"""
    tenant_id = await tenant_middleware.extract_tenant(request)
    
    if tenant_id:
        # Set tenant context for this request
        with tenant_context(tenant_id):
            response = await call_next(request)
            return response
    else:
        # No tenant context - super-admin mode or public endpoint
        response = await call_next(request)
        return response

# Dependency to get current tenant info
async def get_current_tenant_info() -> Optional[Tenant]:
    tenant_id = get_current_tenant()
    if tenant_id:
        return tenant_manager.get_tenant(tenant_id)
    return None

@app.get("/accounts")
async def list_accounts(tenant: Tenant = Depends(get_current_tenant_info)):
    """List accounts - automatically filtered by tenant"""
    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")
    
    # This will only return accounts for the current tenant
    return account_manager.list_accounts()

@app.get("/tenant/info")
async def get_tenant_info(tenant: Tenant = Depends(get_current_tenant_info)):
    """Get current tenant information"""
    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant context required")
    
    return {
        "id": tenant.id,
        "display_name": tenant.display_name,
        "subscription_tier": tenant.subscription_tier.value,
        "primary_color": tenant.primary_color
    }
```

### Tenant Request Examples

```bash
# Using X-Tenant-ID header
curl -H "X-Tenant-ID: tenant_acme_123" \
     -H "Authorization: Bearer <token>" \
     https://api.nexum.io/accounts

# Using subdomain (requires DNS setup)
curl -H "Authorization: Bearer <token>" \
     https://acme.nexus.io/accounts

# Using JWT with tenant claim
curl -H "Authorization: Bearer <token-with-tenant-claim>" \
     https://api.nexus.io/accounts
```

### Tenant Administration

```python
# List all tenants (super-admin only)
tenants = tenant_manager.list_tenants()
for tenant in tenants:
    print(f"{tenant.code}: {tenant.display_name} ({tenant.subscription_tier.value})")

# Get usage statistics
stats = tenant_manager.get_tenant_stats("tenant_acme_123")
print(f"ACME Bank: {stats.user_count} users, {stats.account_count} accounts")

# Update tenant settings
tenant_manager.update_tenant(
    "tenant_acme_123",
    max_users=100,  # Increase user limit
    subscription_tier=SubscriptionTier.ENTERPRISE,
    primary_color="#2196F3"  # Update branding
)

# Deactivate tenant (soft delete)
tenant_manager.deactivate_tenant("tenant_old_123")
```

### Custom Tenant Settings

```python
# Set tenant-specific configuration
tenant_manager.update_tenant(
    "tenant_acme_123",
    settings={
        "interest_rate_override": "2.5",  # Custom interest rate
        "max_daily_transfer": "50000.00",  # Custom transfer limit
        "require_dual_approval": True,     # Custom workflow requirement
        "notification_sender": "ACME Bank <notifications@acmebank.com>",
        "custom_fees": {
            "overdraft": "25.00",
            "wire_transfer": "15.00"
        }
    }
)

# Access custom settings in business logic
def get_overdraft_fee(account):
    tenant = get_current_tenant_info()
    if tenant and tenant.settings:
        custom_fees = tenant.settings.get("custom_fees", {})
        return Decimal(custom_fees.get("overdraft", "35.00"))  # Default $35
    return Decimal("35.00")
```

## Configuration

Configure multi-tenancy via environment variables:

```bash
# Enable multi-tenant mode
export NEXUM_MULTI_TENANT="true"

# Tenant isolation strategy
export NEXUM_TENANT_ISOLATION="shared_table"  # or "schema_per_tenant"

# Default subscription tier for new tenants
export NEXUM_DEFAULT_SUBSCRIPTION_TIER="free"

# Maximum tenants per instance
export NEXUM_MAX_TENANTS="100"

# Default tenant quotas
export NEXUM_DEFAULT_MAX_USERS="25"
export NEXUM_DEFAULT_MAX_ACCOUNTS="1000"

# Tenant context extraction
export NEXUM_TENANT_HEADER="X-Tenant-ID"
export NEXUM_ENABLE_SUBDOMAIN_TENANCY="true"
export NEXUM_DOMAIN_SUFFIX=".nexum.io"  # For subdomain extraction
```

## Schema Per Tenant

For the `SCHEMA_PER_TENANT` isolation strategy:

```python
# PostgreSQL schema-per-tenant setup
def setup_tenant_schema(tenant_id: str, tenant_code: str):
    """Create dedicated PostgreSQL schema for tenant"""
    schema_name = f"tenant_{tenant_code.lower()}"
    
    with postgresql_connection() as conn:
        # Create schema
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
        
        # Run migrations for this schema
        migration_manager.run_migrations(schema=schema_name)
        
        # Update tenant record
        tenant_manager.update_tenant(
            tenant_id,
            database_schema=schema_name
        )

# Usage with schema-aware storage
tenant_storage = TenantAwareStorage(
    PostgreSQLStorage(connection_string),
    isolation=TenantIsolationStrategy.SCHEMA_PER_TENANT
)
```

## Security Considerations

### Data Isolation
- All tenant data is strictly isolated by default
- No cross-tenant data leakage possible through storage layer
- Super-admin mode requires explicit no-tenant context

### Authentication
- JWT tokens can include tenant claims for automatic context
- Multi-tenant SSO integration supported
- Per-tenant user management and RBAC

### Audit Trail
- All operations logged with tenant context
- Cross-tenant administrative actions clearly marked
- Tenant activation/deactivation fully audited

## Performance Considerations

### Database Performance
- **Shared Table**: Best performance, requires proper indexing on `_tenant_id`
- **Schema Per Tenant**: Good isolation, moderate overhead per schema
- **Database Per Tenant**: Maximum isolation, highest resource usage

### Indexing Strategy
```sql
-- Recommended indexes for shared table approach
CREATE INDEX CONCURRENTLY idx_customers_tenant_id ON customers(_tenant_id);
CREATE INDEX CONCURRENTLY idx_accounts_tenant_id ON accounts(_tenant_id);
CREATE INDEX CONCURRENTLY idx_transactions_tenant_id ON transactions(_tenant_id);

-- Composite indexes for common queries
CREATE INDEX CONCURRENTLY idx_customers_tenant_email ON customers(_tenant_id, email);
CREATE INDEX CONCURRENTLY idx_accounts_tenant_customer ON accounts(_tenant_id, customer_id);
```

### Caching
- Tenant metadata cached in memory
- Per-tenant configuration cached
- Storage query results can be cached per tenant

## Monitoring and Analytics

### Tenant Metrics
```python
# Get usage report for all tenants
usage_report = tenant_manager.get_usage_report()
for stats in usage_report:
    print(f"{stats.tenant_id}: {stats.transaction_count} transactions")

# Monitor quotas
for tenant in tenant_manager.list_tenants(is_active=True):
    if tenant.max_users:
        current_users = get_user_count(tenant.id)
        if current_users >= tenant.max_users * 0.9:  # 90% threshold
            send_quota_warning(tenant, "users", current_users, tenant.max_users)
```

### Billing Integration
```python
# Generate billing data
def generate_tenant_billing(tenant_id: str, period_start: datetime, period_end: datetime):
    stats = tenant_manager.get_tenant_stats(tenant_id)
    tenant = tenant_manager.get_tenant(tenant_id)
    
    return {
        "tenant_id": tenant_id,
        "subscription_tier": tenant.subscription_tier.value,
        "period": {"start": period_start, "end": period_end},
        "usage": {
            "users": stats.user_count,
            "accounts": stats.account_count,
            "transactions": stats.transaction_count,
            "storage_gb": calculate_storage_usage(tenant_id)
        },
        "billing_amount": calculate_billing(tenant, stats)
    }
```

## Testing Multi-Tenancy

```python
import pytest
from core_banking.tenancy import tenant_context, TenantAwareStorage

@pytest.fixture
def tenant_storage():
    """Create tenant-aware storage for testing"""
    base_storage = InMemoryStorage()
    return TenantAwareStorage(base_storage)

@pytest.fixture
def test_tenants(tenant_manager):
    """Create test tenants"""
    tenant_a = tenant_manager.create_tenant("Tenant A", "TENANT_A", display_name="Tenant A Bank")
    tenant_b = tenant_manager.create_tenant("Tenant B", "TENANT_B", display_name="Tenant B Bank")
    return tenant_a, tenant_b

def test_tenant_isolation(tenant_storage, test_tenants):
    """Test that tenants can't see each other's data"""
    tenant_a, tenant_b = test_tenants
    
    # Create data for tenant A
    with tenant_context(tenant_a.id):
        tenant_storage.save("customers", "cust_1", {"name": "Customer A"})
        
        # Verify tenant A can see their data
        customer = tenant_storage.load("customers", "cust_1")
        assert customer["name"] == "Customer A"
    
    # Switch to tenant B
    with tenant_context(tenant_b.id):
        # Verify tenant B cannot see tenant A's data
        customer = tenant_storage.load("customers", "cust_1")
        assert customer is None
        
        # Create data for tenant B
        tenant_storage.save("customers", "cust_1", {"name": "Customer B"})
        
        # Verify tenant B can see their own data
        customer = tenant_storage.load("customers", "cust_1")
        assert customer["name"] == "Customer B"
    
    # Verify tenant A still sees their data
    with tenant_context(tenant_a.id):
        customer = tenant_storage.load("customers", "cust_1")
        assert customer["name"] == "Customer A"
```

## Migration from Single-Tenant

```python
def migrate_to_multitenant(default_tenant_id: str = "default_tenant"):
    """Migrate existing single-tenant data to multi-tenant structure"""
    
    # Create default tenant for existing data
    tenant = tenant_manager.create_tenant(
        name="Default Tenant",
        code="DEFAULT",
        display_name="Default Organization",
        subscription_tier=SubscriptionTier.ENTERPRISE
    )
    
    # Add _tenant_id to existing records
    tables = ["customers", "accounts", "transactions", "loans", ...]
    
    for table in tables:
        records = raw_storage.load_all(table)
        for record in records:
            if "_tenant_id" not in record:
                record["_tenant_id"] = tenant.id
                raw_storage.save(table, record["id"], record)
    
    print(f"Migrated {len(tables)} tables to multi-tenant structure")
    return tenant
```

## Future Enhancements

- Tenant-specific database connection pools
- Tenant data export/import capabilities  
- Tenant-specific feature flags
- Cross-tenant reporting and analytics
- Tenant marketplace and app store
- Automated tenant provisioning
- Tenant data archiving and retention policies