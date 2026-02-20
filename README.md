<p align="center">
  <h1 align="center">Nexum</h1>
  <p align="center"><strong>Production-Grade Core Banking System</strong></p>
  <p align="center"><em>Enterprise-ready financial infrastructure with built-in fraud detection</em></p>
</p>

---

Nexum is a production-ready core banking platform that processes financial transactions with **double-entry precision** and **immutable audit trails** at enterprise scale. With 29+ specialized modules, 130+ REST endpoints, and comprehensive fraud detection via Bastion integration, it delivers ACID-compliant financial operations with PostgreSQL persistence, multi-tenancy, and real-time event streaming — all deployable via single `docker-compose up`.

**Status:** Production-ready · 707+ automated tests passing · 29 specialized modules · 130+ API endpoints · 14-page operations dashboard

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Test Coverage | 707+ tests, all passing |
| API Endpoints | 130+ REST endpoints with OpenAPI docs |
| Core Modules | 29+ specialized financial modules |
| Storage Options | PostgreSQL → SQLite → InMemory (layered) |
| Lines of Code | ~17K core logic + ~14K test coverage |
| Transaction Speed | Sub-second ACID transactions |
| Multi-Tenancy | 3 isolation strategies with encryption |
| Fraud Detection | Real-time via Bastion integration |
| Event Topics | 27 Kafka event types |
| Dashboard Pages | 14 SPA pages (Preact + HTM) |

---

## Architecture

```
                     ┌─────────────────────────┐
                     │     FastAPI Gateway     │
                     │    (130+ endpoints)     │
                     └────────────┬────────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                │                 │                 │
     ┌──────────▼──────────┐ ┌────▼────┐ ┌─────────▼─────────┐
     │  Authentication     │ │ Rate    │ │   RBAC Engine     │
     │  (JWT + scrypt)     │ │ Limit   │ │  (8 roles/30+     │
     └──────────┬──────────┘ └────┬────┘ │   permissions)    │
                │                 │      └─────────┬─────────┘
                └─────────────────┼──────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │      Transaction Processing       │
                │   (Deposits, Transfers, Loans)    │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │      Fraud Detection Layer       │
                │    (Bastion REST + Kafka)        │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │      Business Logic Layer        │
                │ (Ledger, Accounts, Customers,    │
                │  Loans, Credit, Collections)     │
                └─────────────────┬─────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
   ┌──────▼──────┐    ┌──────────▼──────────┐    ┌───────▼────────┐
   │   Audit     │    │   Event Bus Layer    │    │   Notification │
   │ (SHA-256    │    │  (27 Kafka topics,   │    │   Engine       │
   │  chained)   │    │   Observer pattern)  │    │ (5 channels)   │
   └──────┬──────┘    └──────────┬──────────┘    └───────┬────────┘
          │                      │                       │
          └──────────────────────┼───────────────────────┘
                                 │
                ┌────────────────▼────────────────┐
                │        Storage Layer            │
                │ (Multi-tenant + Encryption)     │
                └────────────────┬────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
  ┌─────▼─────┐        ┌────────▼────────┐      ┌─────────▼──────────┐
  │PostgreSQL │        │     SQLite      │      │    InMemory        │
  │(JSONB +   │        │ (WAL + indexes) │      │ (Thread-safe dict) │
  │GIN index) │        │                 │      │                    │
  └───────────┘        └─────────────────┘      └────────────────────┘
```

---

## Module Overview

### Core Banking (8 modules)

| Module | Description |
|--------|-------------|
| `ledger.py` | Double-entry bookkeeping engine with hash-chained audit trail |
| `accounts.py` | Account management, balance calculations, holds and freezes |
| `transactions.py` | Transaction processing with ACID compliance and validation |
| `customers.py` | Customer profiles, KYC management, and beneficiary handling |
| `credit.py` | Credit line management, statements, and revolving credit |
| `loans.py` | Loan origination, French amortization, and payment processing |
| `interest.py` | Interest calculations, daily accrual, and monthly posting |
| `currency.py` | Multi-currency support with decimal precision |

### Risk & Compliance (4 modules)

| Module | Description |
|--------|-------------|
| `compliance.py` | KYC/AML checks, transaction monitoring, and regulatory compliance |
| `collections.py` | Delinquency management with automated escalation strategies |
| `audit.py` | Immutable audit trail with SHA-256 hash chaining |
| `fraud_client.py` | Real-time fraud scoring via Bastion API integration |

### Infrastructure (9 modules)

| Module | Description |
|--------|-------------|
| `storage.py` | Pluggable storage abstraction (PostgreSQL/SQLite/InMemory) |
| `encryption.py` | PII encryption at rest with AES-GCM/Fernet and key rotation |
| `tenancy.py` | Multi-tenant isolation with 3 strategies and tenant branding |
| `rbac.py` | Role-based access control with 8 roles and 30+ permissions |
| `notifications.py` | Multi-channel notification engine (email/SMS/push/webhook/in-app) |
| `events.py` | Observer pattern implementation for domain events |
| `workflows.py` | Configurable approval chains with SLA management |
| `custom_fields.py` | Dynamic field management for entity extension |
| `api.py` | Main FastAPI application with modular router architecture |

### Integration (8 modules)

| Module | Description |
|--------|-------------|
| `kafka_integration.py` | Event streaming support with 27 topic types |
| `fraud_events.py` | Kafka event publishing for fraud decisions and alerts |
| `products.py` | Banking product configuration and template engine |
| `reporting.py` | Report generation, analytics, and custom report definitions |
| `config.py` | Environment-based configuration management |
| `migrations.py` | Database migration system with rollback support |
| `logging_config.py` | Structured JSON logging with correlation IDs |
| `event_hooks.py` | Kafka event hooks for real-time system integration |

---

## Bastion Integration

Nexum integrates seamlessly with **Bastion** for real-time fraud detection, combining REST-based synchronous scoring with Kafka-based asynchronous event streaming for comprehensive fraud prevention.

### Integration Architecture

```
Transaction Request
        │
        ▼
┌───────────────────┐    ┌──────────────────────┐
│  fraud_client.py  │───▶│  Bastion /score API  │
│                   │◀───│  (REST endpoint)     │
└───────────────────┘    └──────────────────────┘
        │                           │
        ▼                           ▼
┌───────────────────┐         Risk Score
│ Decision Engine   │         0-100 scale
│ • score < 30:     │              │
│   → APPROVE       │              ▼
│ • score 30-70:    │    ┌─────────────────────┐
│   → REVIEW        │    │   Decision Logic    │
│ • score > 70:     │    │                     │
│   → BLOCK         │    │ APPROVE → Process   │
└───────────────────┘    │ REVIEW  → Queue     │
        │                │ BLOCK   → Reject    │
        ▼                └─────────────────────┘
┌───────────────────┐              │
│ fraud_events.py   │              ▼
│ (Kafka Publisher) │    ┌─────────────────────┐
└───────────────────┘    │   Audit Trail       │
        │                │ (Hash-chained log)  │
        ▼                └─────────────────────┘
┌───────────────────┐
│ Kafka Topics:     │
│ • bastion.fraud.  │
│   decisions       │
│ • bastion.fraud.  │
│   alerts          │
└───────────────────┘
```

### Fraud Detection Flow

**1. Synchronous Scoring (REST)**
```python
# Real-time transaction scoring
fraud_result = fraud_client.score_transaction({
    "transaction_id": "txn_abc123",
    "account_id": "acc_xyz789", 
    "amount": 4500.00,
    "merchant_id": "merch_456",
    "location": {"country": "US", "city": "San Francisco"}
})

# Immediate decision: APPROVE/REVIEW/BLOCK
if fraud_result.score < 30:
    action = "APPROVE"    # Low risk - process immediately
elif fraud_result.score < 70:  
    action = "REVIEW"     # Medium risk - queue for analyst
else:
    action = "BLOCK"      # High risk - reject transaction
```

**2. Asynchronous Event Streaming (Kafka)**
```python
# Publish fraud decision to Kafka
await fraud_events.publish_fraud_decision({
    "transaction_id": "txn_abc123",
    "decision": "approve",
    "score": 25.5,
    "risk_factors": ["unusual_time", "new_merchant"],
    "processing_time_ms": 45
})

# High-risk alerts trigger immediate notifications
if fraud_result.score > 70:
    await fraud_events.publish_fraud_alert({
        "transaction_id": "txn_abc123",
        "alert_type": "high_risk_transaction",
        "requires_immediate_review": True
    })
```

### Configuration & Fallback

```bash
# Environment configuration
NEXUM_BASTION_URL=https://bastion.example.com
NEXUM_BASTION_API_KEY=your_api_key_here
NEXUM_BASTION_TIMEOUT=5.0           # Request timeout in seconds
NEXUM_BASTION_FALLBACK=approve      # Action when Bastion unavailable
```

**Fallback Strategy:** When Bastion is unavailable (network timeout, service down), Nexum uses the configured fallback action while logging the event for later analysis. All decisions, including fallbacks, are recorded in the immutable audit trail.

---

## Quick Start

### Docker Compose (Recommended)

```bash
# Clone repository
git clone https://github.com/AlexShrike/nexum
cd nexum

# Start full stack (PostgreSQL + Kafka + Nexum + Dashboard)
docker-compose up -d

# Verify services
curl http://localhost:8090/health
```

### Manual Installation

```bash
# Install with Poetry
poetry install

# Configure environment
export NEXUM_DATABASE_URL="postgresql://user:pass@localhost/nexum"
export NEXUM_JWT_SECRET="your-secret-key-change-in-production"
export NEXUM_ENCRYPTION_ENABLED="true"
export NEXUM_ENCRYPTION_MASTER_KEY="your-256-bit-master-key"

# Start server
python run.py

# API available at http://localhost:8090 with docs at /docs
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXUM_DATABASE_URL` | PostgreSQL connection string | SQLite fallback |
| `NEXUM_JWT_SECRET` | JWT signing key (change in production) | auto-generated |
| `NEXUM_ENCRYPTION_ENABLED` | Enable PII encryption at rest | false |
| `NEXUM_ENCRYPTION_PROVIDER` | Encryption provider (aesgcm/fernet) | aesgcm |
| `NEXUM_MULTI_TENANT` | Enable multi-tenancy support | false |
| `NEXUM_KAFKA_ENABLED` | Enable Kafka event streaming | false |
| `NEXUM_BASTION_URL` | Bastion fraud detection endpoint | disabled |
| `NEXUM_RATE_LIMIT` | API rate limit (req/min) | 60 |

---

## API Highlights

Core endpoints with production-ready examples:

```bash
# Create customer with KYC
curl -X POST http://localhost:8090/customers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Jane",
    "last_name": "Smith", 
    "email": "jane@example.com",
    "phone": "+1-555-0199",
    "date_of_birth": "1985-03-15"
  }'

# Open savings account
curl -X POST http://localhost:8090/accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123",
    "product_type": "savings",
    "currency": "USD", 
    "interest_rate": "0.025"
  }'

# Process deposit with fraud check
curl -X POST http://localhost:8090/transactions/deposit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "acc_xyz789",
    "amount": {"amount": "1000.00", "currency": "USD"},
    "description": "Initial deposit",
    "channel": "mobile"
  }'

# Originate loan with French amortization
curl -X POST http://localhost:8090/loans \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123",
    "terms": {
      "principal_amount": {"amount": "25000.00", "currency": "USD"},
      "annual_interest_rate": "0.0649",
      "term_months": 60,
      "amortization_method": "equal_installment"
    }
  }'
```

---

## Dashboard

Comprehensive **14-page SPA** operations dashboard on port **8890**:

- **Overview** — Real-time portfolio metrics, transaction volumes, alert summaries
- **Transactions** — Live transaction feed with fraud scoring and status indicators  
- **Accounts** — Account management, balance monitoring, holds and freezes
- **Customers** — Customer profiles, KYC status, relationship mapping
- **Loans** — Loan portfolio, amortization schedules, payment tracking
- **Credit Lines** — Credit utilization, statement generation, payment history
- **Collections** — Delinquency management, collection strategies, recovery tracking
- **Compliance** — KYC alerts, AML monitoring, regulatory reporting
- **Fraud Detection** — Bastion integration status, risk scoring analytics
- **Workflows** — Approval queues, SLA monitoring, task assignments  
- **Reports** — Financial reporting, custom analytics, data export
- **Notifications** — Multi-channel messaging, delivery tracking, preferences
- **Administration** — User management, RBAC configuration, system health
- **Audit Trail** — Hash-chained audit log with integrity verification

**Tech Stack:** Preact + HTM frontend (no build step), FastAPI backend, WebSocket real-time updates

---

## Security

### Authentication & Authorization
- **JWT Authentication** — Bearer tokens with configurable expiry (default 24h)
- **scrypt Password Hashing** — Replacing legacy SHA-256 with memory-hard scrypt
- **Role-Based Access Control** — 8 built-in roles, 30+ granular permissions
- **Rate Limiting** — 60 requests/minute per IP, configurable per endpoint
- **Session Management** — Secure session handling with logout invalidation

### Data Protection  
- **PII Encryption at Rest** — Field-level encryption with AES-GCM or Fernet
- **Master Key Derivation** — PBKDF2-based key derivation with salt rotation
- **Selective Encryption** — Automatic detection and encryption of PII fields
- **Key Rotation** — Built-in key rotation with background re-encryption
- **Multi-Tenant Isolation** — Data separation via tenant-aware encryption keys

### Audit & Compliance
- **Hash-Chained Audit Trail** — SHA-256 linked immutable journal entries
- **ACID Transaction Logging** — Every financial operation atomically audited
- **Integrity Verification** — Tamper-evident audit log with chain validation
- **Compliance Reporting** — Built-in regulatory reporting and alert generation
- **Data Retention** — Configurable retention policies with automated archival

---

## Configuration

| Environment Variable | Description | Default Value |
|---------------------|-------------|---------------|
| `NEXUM_HOST` | Server bind address | 0.0.0.0 |
| `NEXUM_PORT` | Server port | 8090 |
| `NEXUM_DATABASE_URL` | PostgreSQL connection string | sqlite:///nexum.db |
| `NEXUM_REDIS_URL` | Redis URL for caching | None (disabled) |
| `NEXUM_JWT_SECRET` | JWT token signing key | auto-generated |
| `NEXUM_JWT_EXPIRY_HOURS` | Token expiration time | 24 |
| `NEXUM_LOG_LEVEL` | Logging level | INFO |
| `NEXUM_ENCRYPTION_ENABLED` | Enable PII encryption | false |
| `NEXUM_ENCRYPTION_PROVIDER` | Encryption backend | aesgcm |
| `NEXUM_ENCRYPTION_MASTER_KEY` | 256-bit master encryption key | None |
| `NEXUM_MULTI_TENANT` | Enable multi-tenancy | false |
| `NEXUM_KAFKA_ENABLED` | Enable event streaming | false |
| `NEXUM_KAFKA_BOOTSTRAP_SERVERS` | Kafka broker endpoints | localhost:9092 |
| `NEXUM_BASTION_URL` | Bastion fraud detection API | None |
| `NEXUM_BASTION_API_KEY` | Bastion API authentication | None |
| `NEXUM_BASTION_TIMEOUT` | Fraud API request timeout | 5.0 |
| `NEXUM_RATE_LIMIT` | API rate limit (req/min) | 60 |

---

## Documentation

- **[Architecture Guide](docs/architecture.md)** — System design, data flow, and module dependencies
- **[API Reference](docs/api-reference.md)** — Complete REST endpoint documentation  
- **[Getting Started](docs/getting-started.md)** — Installation, configuration, and first steps
- **[Deployment Guide](docs/deployment.md)** — Production deployment patterns and scaling
- **[Security Guide](docs/security.md)** — Authentication, encryption, and compliance features
- **[Integration Guide](docs/integration.md)** — Kafka events, webhooks, and external system integration
- **[Developer Guide](docs/development.md)** — Contributing guidelines and development setup
- **[Migration Guide](docs/migrations.md)** — Database schema changes and upgrade procedures

---

## Technology Stack

**Backend Infrastructure**
- **Language:** Python 3.14+
- **Web Framework:** FastAPI with automatic OpenAPI documentation
- **Database:** PostgreSQL with JSONB + SQLite + InMemory storage options
- **Message Queue:** Apache Kafka for event streaming and system integration
- **Authentication:** JWT tokens with scrypt password hashing
- **Encryption:** AES-GCM and Fernet for PII protection at rest

**Financial Engineering**
- **Precision:** Decimal arithmetic throughout — no floating-point for money
- **Accounting:** Double-entry bookkeeping with immutable journal entries  
- **Audit Trail:** SHA-256 hash-chained audit log for tamper evidence
- **Compliance:** Built-in KYC/AML monitoring and regulatory reporting
- **Risk Management:** Real-time fraud detection via Bastion integration

**Operations & DevOps**
- **Containerization:** Docker and docker-compose for consistent deployments
- **CI/CD:** GitHub Actions with automated testing and deployment
- **Monitoring:** Structured JSON logging with correlation IDs
- **Configuration:** Environment-based configuration management
- **Testing:** 707+ comprehensive tests with pytest

**Frontend Dashboard**
- **Framework:** Preact + HTM (no build step required)
- **Styling:** Modern responsive design with dark/light theme support
- **Real-time:** WebSocket integration for live updates
- **Charts:** Interactive financial charts and analytics
- **Accessibility:** WCAG 2.1 compliant interface design

---

<p align="center">
  Built by <strong>AlexShrike</strong> • Production-ready core banking infrastructure
</p>