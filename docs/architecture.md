# System Architecture

## Overview

Nexum is built on a modular architecture that follows core banking principles while maintaining flexibility and scalability. Each module has clear responsibilities and well-defined interfaces, making the system maintainable and extensible.

## Core Principles

### 1. Double-Entry Accounting
Every financial transaction creates balanced journal entries where total debits equal total credits. This ensures data integrity and provides a complete audit trail.

### 2. Immutable Audit Trail
All operations are recorded in a hash-chained audit log using SHA-256 hashing. Each audit entry contains a hash of the previous entry, making tampering detectable.

### 3. Decimal Precision
All monetary calculations use Python's `decimal.Decimal` type to avoid floating-point precision errors. This is critical for financial accuracy.

### 4. Event Sourcing
Account balances are derived from journal entries rather than stored as mutable values. This provides complete transaction history and makes the system resilient to corruption.

## Module Dependencies

```mermaid
graph TD
    API[API Layer] --> ALL[All Modules]
    
    ACCOUNTS[Account Manager] --> LEDGER[General Ledger]
    ACCOUNTS --> PRODUCTS[Product Engine]
    ACCOUNTS --> AUDIT[Audit Trail]
    
    TRANSACTIONS[Transaction Processor] --> LEDGER
    TRANSACTIONS --> ACCOUNTS
    TRANSACTIONS --> COMPLIANCE[Compliance Engine]
    TRANSACTIONS --> AUDIT
    
    CREDIT[Credit Line Manager] --> ACCOUNTS
    CREDIT --> TRANSACTIONS
    CREDIT --> INTEREST[Interest Engine]
    
    LOANS[Loan Manager] --> ACCOUNTS
    LOANS --> TRANSACTIONS
    LOANS --> INTEREST
    
    COLLECTIONS[Collections Manager] --> LOANS
    COLLECTIONS --> CREDIT
    COLLECTIONS --> WORKFLOWS[Workflow Engine]
    
    CUSTOMERS[Customer Manager] --> COMPLIANCE
    CUSTOMERS --> AUDIT
    
    WORKFLOWS --> RBAC[RBAC Engine]
    WORKFLOWS --> AUDIT
    
    REPORTING[Reporting Engine] --> LEDGER
    REPORTING --> ACCOUNTS
    REPORTING --> LOANS
    REPORTING --> CREDIT
    
    CUSTOM_FIELDS[Custom Fields] --> STORAGE[Storage Layer]
    
    ALL --> CURRENCY[Currency Engine]
    ALL --> STORAGE
```

## Data Flow

### Transaction Processing Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant TxProcessor as Transaction Processor
    participant Compliance
    participant Ledger
    participant Audit
    participant Storage

    Client->>API: POST /transactions
    API->>TxProcessor: process_transaction()
    TxProcessor->>Compliance: check_transaction_limits()
    Compliance-->>TxProcessor: validation_result
    TxProcessor->>Ledger: create_journal_entry()
    Ledger->>Audit: log_event()
    Audit->>Storage: store_audit_entry()
    Ledger->>Storage: store_journal_entry()
    TxProcessor-->>API: transaction_result
    API-->>Client: HTTP Response
```

### ACID Transaction Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Storage
    participant DB as Database

    Client->>API: Transaction Request
    API->>Storage: Begin Transaction
    Storage->>DB: START TRANSACTION
    
    API->>Storage: Save Account Update
    Storage->>DB: INSERT/UPDATE (not committed)
    
    API->>Storage: Save Journal Entry  
    Storage->>DB: INSERT (not committed)
    
    API->>Storage: Save Audit Record
    Storage->>DB: INSERT (not committed)
    
    alt Success Path
        API->>Storage: Commit Transaction
        Storage->>DB: COMMIT
        API-->>Client: Success Response
    else Error Path  
        API->>Storage: Rollback Transaction
        Storage->>DB: ROLLBACK
        API-->>Client: Error Response
    end
```

### Atomic Operations with Context Manager

```python
# All critical operations use atomic context manager
with storage.atomic():
    # Account balance update
    storage.save('accounts', account_id, updated_account)
    
    # Journal entry creation
    storage.save('journal_entries', entry_id, journal_entry)
    
    # Audit trail logging
    storage.save('audit_logs', audit_id, audit_entry)
    
    # If any operation fails, all are rolled back automatically
```

### Account Balance Calculation

```mermaid
flowchart TD
    QUERY[Balance Query] --> LEDGER[General Ledger]
    LEDGER --> JOURNAL[Journal Entries]
    JOURNAL --> FILTER[Filter by Account]
    FILTER --> SUM[Sum Debits/Credits]
    SUM --> BALANCE[Calculate Balance]
    BALANCE --> HOLDS[Apply Account Holds]
    HOLDS --> AVAILABLE[Available Balance]
```

## Storage Architecture

### Storage Layer Diagram

```mermaid
flowchart TD
    API[API Layer] --> STORAGE_MGR[Storage Manager]
    
    STORAGE_MGR --> |Development| INMEM[In-Memory Storage]
    STORAGE_MGR --> |Single Instance| SQLITE[SQLite Storage]
    STORAGE_MGR --> |Production| POSTGRES[PostgreSQL Storage]
    
    INMEM --> |Thread-Safe| DICT[Dict with RLock]
    
    SQLITE --> |WAL Mode| SQLITE_FILE[(SQLite File)]
    SQLITE --> |Indexes| SQLITE_IDX[Created Indexes]
    
    POSTGRES --> |JSONB| PG_TABLES[(PostgreSQL Tables)]
    POSTGRES --> |GIN Indexes| PG_JSONB_IDX[JSONB Indexes]
    POSTGRES --> |ACID| PG_TRANSACTIONS[Transaction Support]
    
    style POSTGRES fill:#e1f5fe
    style PG_TRANSACTIONS fill:#c8e6c9
```

## Phase 2 Architecture Enhancements

### Multi-Tenancy Layer

```mermaid
graph LR
    subgraph "Request Flow"
        REQ[Request] --> MW[Tenant Middleware]
        MW --> CTX[Tenant Context]
    end
    
    subgraph "Storage Stack"
        APP[Application Layer] --> ES[EncryptedStorage]
        ES --> TAS[TenantAwareStorage]
        TAS --> BASE[Base Storage]
        BASE --> DB[Database]
    end
    
    subgraph "Tenant Extraction"
        MW --> H[X-Tenant-ID Header]
        MW --> SUB[Subdomain Detection]
        MW --> JWT[JWT Claims]
    end
```

### Event-Driven Architecture (Observer Pattern)

```mermaid
graph TD
    subgraph "Domain Events"
        TX[Transaction Events] 
        ACC[Account Events]
        CUST[Customer Events]
        LOAN[Loan Events]
        COMP[Compliance Events]
    end
    
    subgraph "Event Dispatcher"
        ED[EventDispatcher]
        SUB[Subscribers]
        PUB[Publishers]
    end
    
    subgraph "Event Consumers"
        NOT[Notification Engine]
        AUDIT[Audit Logger]
        KAFKA[Kafka Publisher]
        CUSTOM[Custom Handlers]
    end
    
    TX --> ED
    ACC --> ED
    CUST --> ED
    LOAN --> ED
    COMP --> ED
    
    ED --> SUB
    SUB --> NOT
    SUB --> AUDIT
    SUB --> KAFKA
    SUB --> CUSTOM
```

### Notification Engine Flow

```mermaid
graph LR
    subgraph "Event Sources"
        DOMAIN[Domain Events] --> ENGINE[Notification Engine]
        API[Direct API Calls] --> ENGINE
    end
    
    subgraph "Processing"
        ENGINE --> TEMP[Template Engine]
        TEMP --> PREF[User Preferences]
        PREF --> QUIET[Quiet Hours Check]
    end
    
    subgraph "Delivery Channels"
        QUIET --> EMAIL[Email Provider]
        QUIET --> SMS[SMS Provider]
        QUIET --> PUSH[Push Provider]
        QUIET --> WH[Webhook Provider]
        QUIET --> APP[In-App Provider]
    end
    
    subgraph "Tracking"
        EMAIL --> TRACK[Delivery Tracking]
        SMS --> TRACK
        PUSH --> TRACK
        WH --> TRACK
        APP --> TRACK
    end
```

### Encryption Layer Architecture

```mermaid
graph TD
    subgraph "Application Layer"
        APP[Business Logic] --> ES[EncryptedStorage]
    end
    
    subgraph "Encryption Layer"
        ES --> DETECT{Is PII Field?}
        DETECT -->|Yes| ENC[Encrypt]
        DETECT -->|No| PASS[Pass Through]
        ENC --> STORE[Storage Layer]
        PASS --> STORE
    end
    
    subgraph "Encryption Providers"
        ENC --> FERNET[Fernet Provider]
        ENC --> AES[AES-GCM Provider]
        ENC --> NOOP[NoOp Provider]
    end
    
    subgraph "Key Management"
        MASTER[Master Key] --> KDF[Key Derivation]
        KDF --> FIELD[Field-Specific Keys]
    end
```

### Full Storage Stack

```mermaid
graph TD
    subgraph "Application"
        BL[Business Logic]
    end
    
    subgraph "Storage Wrappers"
        BL --> ES[EncryptedStorage]
        ES --> TAS[TenantAwareStorage]
        TAS --> BASE[Base Storage Interface]
    end
    
    subgraph "Storage Implementations"
        BASE --> PG[PostgreSQLStorage]
        BASE --> LITE[SQLiteStorage]
        BASE --> MEM[InMemoryStorage]
    end
    
    subgraph "Features"
        ES --> E1[PII Encryption]
        ES --> E2[Key Rotation]
        TAS --> T1[Tenant Isolation]
        TAS --> T2[Multi-Tenancy]
        BASE --> B1[ACID Transactions]
        BASE --> B2[Query Interface]
    end
```

### Storage Abstraction
The storage layer provides a pluggable interface supporting multiple backends:

- **In-Memory**: Thread-safe dictionary storage for testing and development
- **SQLite**: WAL mode with automatic indexing for single-instance deployments  
- **PostgreSQL**: JSONB storage with GIN indexes for production deployments

### PostgreSQL Implementation Features

- **JSONB Storage**: Native JSON storage with indexing and query optimization
- **ACID Transactions**: Full transaction support with rollback capabilities
- **GIN Indexes**: Fast queries on JSON document fields
- **Connection Pooling**: Managed connections with automatic reconnection
- **Migration System**: Versioned schema changes with rollback support

### Data Persistence
```python
# Storage Interface
class StorageInterface:
    def store(self, record: StorageRecord) -> str
    def retrieve(self, key: str) -> Optional[StorageRecord]
    def query(self, filters: Dict[str, Any]) -> List[StorageRecord]
    def update(self, key: str, record: StorageRecord) -> bool
    def delete(self, key: str) -> bool
```

## Security Model

### Hash-Chained Audit Trail
```python
# Each audit entry contains:
@dataclass
class AuditEntry:
    id: str                    # Unique identifier
    timestamp: datetime        # UTC timestamp
    event_type: AuditEventType # Type of operation
    entity_id: str            # Target entity
    user_id: Optional[str]    # User who performed action
    details: Dict[str, Any]   # Event details
    previous_hash: str        # Hash of previous entry
    current_hash: str         # SHA-256 of this entry
```

### Authentication Middleware Flow

```mermaid
flowchart TD
    REQUEST[HTTP Request] --> AUTH_CHECK{Has Bearer Token?}
    
    AUTH_CHECK -->|No| UNAUTHORIZED[401 Unauthorized]
    AUTH_CHECK -->|Yes| JWT_DECODE[Decode JWT Token]
    
    JWT_DECODE --> TOKEN_VALID{Token Valid?}
    TOKEN_VALID -->|No| UNAUTHORIZED
    TOKEN_VALID -->|Yes| USER_LOOKUP[Lookup User]
    
    USER_LOOKUP --> USER_EXISTS{User Exists & Active?}
    USER_EXISTS -->|No| UNAUTHORIZED
    USER_EXISTS -->|Yes| ROLE_CHECK[Check User Roles]
    
    ROLE_CHECK --> PERM_CHECK[Check Endpoint Permissions]
    PERM_CHECK --> HAS_PERM{Has Permission?}
    
    HAS_PERM -->|No| FORBIDDEN[403 Forbidden]
    HAS_PERM -->|Yes| PROCEED[Process Request]
```

### JWT Token Structure

```python
# JWT Payload
{
    "sub": "user_id",           # Subject (user ID)  
    "username": "admin",        # Username
    "roles": ["admin"],         # User roles
    "exp": 1735689600,         # Expiration timestamp
    "iat": 1735603200,         # Issued at timestamp
    "session_id": "sess_123"    # Session identifier
}
```

### Role-Based Access Control (RBAC)

```python
# 8 Built-in Roles:
SUPER_ADMIN    # Full system access
ADMIN          # Administrative operations
MANAGER        # Department management
OFFICER        # Daily operations
TELLER         # Basic transactions
COMPLIANCE     # Compliance operations
AUDITOR        # Read-only access
GUEST          # Limited read access

# 30 Permissions covering all operations
CREATE_ACCOUNT, VIEW_ACCOUNT, MODIFY_ACCOUNT,
CREATE_TRANSACTION, APPROVE_TRANSACTION, REVERSE_TRANSACTION,
CREATE_LOAN, APPROVE_LOAN, DISBURSE_LOAN,
# ... and more
```

## Performance Considerations

### Database Optimization
- Indexed queries for account lookups
- Partitioned tables for large transaction volumes
- Connection pooling for concurrent access

### Caching Strategy
- Account balance caching with invalidation
- Product configuration caching
- User session and permission caching

### Scalability Patterns
- Horizontal scaling through database sharding
- Microservice decomposition for high-volume operations
- Event streaming for real-time processing

## Integration Points

### Modular API Structure

```mermaid
flowchart TD
    MAIN_API[Main API Server] --> ROUTER_INCLUDE[Include Routers]
    
    ROUTER_INCLUDE --> AUTH_ROUTER[auth.py - Authentication]
    ROUTER_INCLUDE --> CUST_ROUTER[customers.py - Customer Management]
    ROUTER_INCLUDE --> ACCT_ROUTER[accounts.py - Account Operations]
    ROUTER_INCLUDE --> TXN_ROUTER[transactions.py - Transactions]
    ROUTER_INCLUDE --> LOAN_ROUTER[loans.py - Loan Management] 
    ROUTER_INCLUDE --> CREDIT_ROUTER[credit.py - Credit Lines]
    ROUTER_INCLUDE --> KAFKA_ROUTER[kafka.py - Event Streaming]
    ROUTER_INCLUDE --> ADMIN_ROUTER[admin.py - Administration]
    
    AUTH_ROUTER --> AUTH_ENDPOINTS[/auth/login, /auth/logout, /auth/refresh]
    CUST_ROUTER --> CUST_ENDPOINTS[/customers, /customers/{id}/kyc]
    ACCT_ROUTER --> ACCT_ENDPOINTS[/accounts, /accounts/{id}/balance]
    TXN_ROUTER --> TXN_ENDPOINTS[/transactions/deposit, /transactions/transfer]
    LOAN_ROUTER --> LOAN_ENDPOINTS[/loans, /loans/{id}/payment]
    CREDIT_ROUTER --> CREDIT_ENDPOINTS[/credit/{id}/draw, /credit/{id}/payment]
    KAFKA_ROUTER --> KAFKA_ENDPOINTS[/kafka/status, /kafka/events]
    ADMIN_ROUTER --> ADMIN_ENDPOINTS[/admin/users, /admin/system]
```

### API Router Architecture

```python
# Main API application
app = FastAPI(
    title="Nexum Core Banking API", 
    version="1.0.0",
    description="Production-grade core banking system"
)

# Include modular routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(customers.router, prefix="/customers", tags=["Customers"])
app.include_router(accounts.router, prefix="/accounts", tags=["Accounts"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
app.include_router(loans.router, prefix="/loans", tags=["Loans"])
app.include_router(credit.router, prefix="/credit", tags=["Credit"])
app.include_router(kafka.router, prefix="/kafka", tags=["Events"])
app.include_router(admin.router, prefix="/admin", tags=["Administration"])
```

### Middleware Stack

```python
# Security middleware
app.add_middleware(JWTAuthenticationMiddleware)
app.add_middleware(RateLimitingMiddleware, requests_per_minute=60)

# CORS middleware for web clients  
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Logging middleware
app.add_middleware(StructuredLoggingMiddleware)
```

### Kafka Event Flow Diagram

```mermaid
flowchart TD
    TRANSACTION[Transaction Processing] --> EVENT_HOOK[Event Hook Triggered]
    CUSTOMER_UPDATE[Customer Update] --> EVENT_HOOK
    LOAN_CREATION[Loan Creation] --> EVENT_HOOK
    
    EVENT_HOOK --> EVENT_BUILDER[Event Builder]
    EVENT_BUILDER --> KAFKA_PRODUCER[Kafka Producer]
    
    KAFKA_PRODUCER --> |Publish| KAFKA_TOPICS[Kafka Topics]
    
    KAFKA_TOPICS --> TOPIC_TX[nexum.transactions.created]
    KAFKA_TOPICS --> TOPIC_CUST[nexum.customers.updated] 
    KAFKA_TOPICS --> TOPIC_LOAN[nexum.loans.originated]
    KAFKA_TOPICS --> TOPIC_ACCT[nexum.accounts.created]
    
    KAFKA_TOPICS --> |Subscribe| EXTERNAL_CONSUMER[External Systems]
    KAFKA_TOPICS --> |Subscribe| INTERNAL_CONSUMER[Internal Processors]
    
    EXTERNAL_CONSUMER --> RISK_SYSTEM[Risk Management]
    EXTERNAL_CONSUMER --> REPORTING_SYSTEM[Reporting System]
    EXTERNAL_CONSUMER --> NOTIFICATION_SERVICE[Notification Service]
    
    INTERNAL_CONSUMER --> AUDIT_PROCESSOR[Audit Event Processor]
    INTERNAL_CONSUMER --> INTEREST_PROCESSOR[Interest Calculator]
```

### Event Message Format (CloudEvents Compatible)

```json
{
  "specversion": "1.0",
  "type": "nexum.transactions.created",
  "source": "nexum-core-banking",
  "id": "txn_abc123def456",
  "time": "2026-02-19T15:32:00.000000Z",
  "datacontenttype": "application/json",
  "subject": "transaction/txn_abc123def456",
  "data": {
    "transaction_id": "txn_abc123def456",
    "account_id": "acc_xyz789ghi012", 
    "amount": "1000.00",
    "currency": "USD",
    "transaction_type": "deposit",
    "status": "completed"
  }
}
```

### External System Integration
- **Payment Processors**: ACH, wire transfers, card networks
- **Regulatory Reporting**: Automated compliance reporting
- **Risk Management**: Real-time fraud detection via Kafka events
- **Customer Channels**: Web, mobile, ATM integration
- **Event Streaming**: Real-time event publishing to downstream systems

## Deployment Architecture

### Single Instance Deployment
```
┌─────────────────┐
│   Load Balancer │
└─────────────────┘
         │
┌─────────────────┐
│   Nexum API     │
│   (FastAPI)     │
└─────────────────┘
         │
┌─────────────────┐
│   SQLite DB     │
└─────────────────┘
```

### Production Deployment
```
┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │────│   Load Balancer │
└─────────────────┘    └─────────────────┘
         │                       │
┌─────────────────┐    ┌─────────────────┐
│   Nexum API     │    │   Nexum API     │
│   Instance 1    │    │   Instance 2    │
└─────────────────┘    └─────────────────┘
         │                       │
         └───────┬───────────────┘
                 │
    ┌─────────────────┐    ┌─────────────────┐
    │   PostgreSQL    │────│   PostgreSQL    │
    │   Primary       │    │   Replica       │
    └─────────────────┘    └─────────────────┘
```

## Error Handling

### Exception Hierarchy
```python
class NexumException(Exception):
    """Base exception for all Nexum errors"""

class InsufficientFundsError(NexumException):
    """Raised when account has insufficient funds"""

class ComplianceViolationError(NexumException):
    """Raised when transaction violates compliance rules"""

class AuditIntegrityError(NexumException):
    """Raised when audit trail integrity is compromised"""
```

### Idempotency Handling
All transaction endpoints support idempotency keys to prevent duplicate processing:

```python
@app.post("/transactions")
async def create_transaction(
    request: CreateTransactionRequest,
    idempotency_key: Optional[str] = Header(None)
):
    # Duplicate detection and handling
    if idempotency_key and transaction_exists(idempotency_key):
        return get_existing_transaction(idempotency_key)
```

## Monitoring and Observability

### Health Checks
- `/health` - Basic system health
- `/health/detailed` - Component-level health status

### Metrics Collection
- Transaction volumes and rates
- Account balance changes
- Interest calculations
- Compliance check results
- API response times

### Audit and Compliance
- Complete transaction audit trail
- Regulatory reporting capabilities
- Suspicious activity monitoring
- Data retention policies