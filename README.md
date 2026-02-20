<p align="center">
  <h1 align="center">Nexum</h1>
  <p align="center"><strong>Production-Grade Core Banking System</strong></p>
  <p align="center"><em>Enterprise-ready financial infrastructure with built-in fraud detection</em></p>
</p>

---

Nexum is a production-ready core banking platform that processes financial transactions with **double-entry precision** and **immutable audit trails** at enterprise scale. With 29+ specialized modules, 130+ REST endpoints, and comprehensive fraud detection via Bastion integration, it delivers ACID-compliant financial operations with PostgreSQL persistence, multi-tenancy, and real-time event streaming — all deployable via single `docker-compose up`.

**Status:** Production-ready · 707+ automated tests passing · 29 specialized modules · 130+ API endpoints · 14-page operations dashboard

---

## Table of Contents

- [Key Metrics](#key-metrics)
- [Architecture](#architecture)
- [Modules](#modules)
- [Dashboard](#dashboard)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Fraud Detection Pipeline](#fraud-detection-pipeline)
- [Bastion Integration](#bastion-integration)
- [Security](#security)
- [Configuration](#configuration)
- [Docker Deployment](#docker-deployment)
- [Documentation](#documentation)
- [Tech Stack](#tech-stack)

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

The system provides a complete banking infrastructure with fraud detection, multi-tenancy, and real-time event streaming, designed for enterprise deployment.

📖 **Full guide:** [Architecture Overview](docs/architecture.md)

---

## Modules

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

📖 **Full guides:**
- Module Documentation — See individual module guides below
- [Best Practices](docs/BEST_PRACTICES.md) — Module integration patterns

---

## Dashboard

Comprehensive **14-page SPA** operations dashboard providing complete visibility into banking operations:

![Overview Dashboard](screenshots/01_overview.png)
*Real-time portfolio metrics, transaction volumes, and system health monitoring*

![Customer Management](screenshots/02_customers.png)
*Customer profiles, KYC status, relationship mapping, and account overview*

![Transaction Processing](screenshots/03_transactions.png)
*Live transaction feed with fraud scoring, status tracking, and decision audit*

![Account Management](screenshots/04_accounts.png)
*Account balances, holds, freezes, and detailed transaction history*

### Key Dashboard Features

**Operations Monitoring**
- **Portfolio Metrics** — Real-time loan volumes, deposit balances, credit utilization
- **Transaction Feed** — Live stream of all transactions with fraud scores
- **System Health** — Performance metrics, error rates, service availability
- **Alert Management** — Fraud alerts, compliance violations, system notifications

**Financial Management**
- **Account Overview** — Balance monitoring, holds, and account status tracking
- **Loan Portfolio** — Amortization schedules, payment tracking, delinquency management
- **Credit Lines** — Utilization monitoring, statement generation, payment history
- **Collections** — Delinquency strategies, recovery tracking, escalation workflows

**Compliance & Risk**
- **KYC Monitoring** — Customer verification status and document management
- **AML Alerts** — Transaction monitoring, suspicious activity reporting
- **Audit Trail** — Hash-chained audit log with integrity verification
- **Regulatory Reporting** — Compliance dashboards and automated report generation

**System Administration**
- **User Management** — RBAC configuration, role assignments, access control
- **Workflow Management** — Approval queues, SLA monitoring, task assignments
- **Notification Center** — Multi-channel messaging and delivery tracking
- **Configuration** — System settings, thresholds, and feature toggles

**Tech Stack:** Preact + HTM frontend (no build step), FastAPI backend, WebSocket real-time updates

📖 **Full guide:** [Deployment Guide](docs/DEPLOYMENT.md) — Production deployment and dashboard setup

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

# Access dashboard
open http://localhost:8890
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

### Quick Test

```bash
# Create customer
curl -X POST http://localhost:8090/customers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Jane",
    "last_name": "Smith",
    "email": "jane@example.com"
  }'

# Open account
curl -X POST http://localhost:8090/accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123",
    "product_type": "savings",
    "currency": "USD"
  }'

# Process deposit
curl -X POST http://localhost:8090/transactions/deposit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "acc_xyz789",
    "amount": {"amount": "1000.00", "currency": "USD"}
  }'
```

📖 **Full guides:**
- [Getting Started Guide](docs/GETTING_STARTED.md) — Complete installation and configuration
- [Quick Start Guide](docs/getting-started.md) — Fast-track development setup

---

## API Reference

**130+ REST endpoints** covering all banking operations with comprehensive fraud detection:

### Core Banking Operations

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
    "date_of_birth": "1985-03-15",
    "kyc_level": "enhanced"
  }'

# Open savings account with interest
curl -X POST http://localhost:8090/accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123",
    "product_type": "savings",
    "currency": "USD", 
    "interest_rate": "0.025",
    "minimum_balance": "100.00"
  }'
```

### Transaction Processing with Fraud Detection

```bash
# Process deposit with automatic fraud scoring
curl -X POST http://localhost:8090/transactions/deposit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "acc_xyz789",
    "amount": {"amount": "1000.00", "currency": "USD"},
    "description": "Initial deposit",
    "channel": "mobile",
    "metadata": {
      "ip_address": "192.168.1.100",
      "device_id": "mobile_12345"
    }
  }'

# Response includes fraud scoring
{
  "transaction_id": "txn_def456",
  "status": "approved",
  "fraud_score": 15.2,
  "fraud_decision": "approve",
  "fraud_reasons": ["known_device", "normal_amount"],
  "new_balance": "1000.00"
}
```

### Lending Operations

```bash
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
    },
    "disbursement_account": "acc_xyz789"
  }'

# Process loan payment
curl -X POST http://localhost:8090/loans/{loan_id}/payments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": {"amount": "485.32", "currency": "USD"},
    "payment_method": "ach_debit",
    "source_account": "acc_xyz789"
  }'
```

### System Management

```bash
# Health check with detailed status
curl http://localhost:8090/health

# System metrics
curl http://localhost:8090/metrics \
  -H "Authorization: Bearer $TOKEN"

# Audit trail search
curl "http://localhost:8090/audit?entity_id=cust_abc123&limit=50" \
  -H "Authorization: Bearer $TOKEN"
```

📖 **Full guide:** [API Reference](docs/api-reference.md) — Complete endpoint documentation with examples

---

## Fraud Detection Pipeline

Nexum integrates seamlessly with **Bastion** for comprehensive fraud protection across all banking transactions:

### Multi-Layer Detection

**1. Real-Time Transaction Scoring**
- Every transaction automatically scored via Bastion REST API
- Sub-millisecond response time with configurable timeout fallbacks
- Risk scores from 0-100 with calibrated probability interpretation

**2. Behavioral Analysis**
- Customer spending patterns and channel preferences
- Device fingerprinting and velocity tracking
- Geographic and temporal anomaly detection

**3. Network Analysis**
- Graph-based fraud ring detection using spectral analysis
- Identification of mule account networks and synthetic identities
- Cross-customer relationship mapping for coordinated attacks

### Decision Flow

```
Transaction → Bastion API → Risk Score → Decision Logic → Action
    ↓            ↓            ↓            ↓           ↓
  Created    → Fraud       → 0-100      → Rules    → APPROVE
  (Nexum)      Analysis     Scale         Engine     REVIEW
               (Bastion)                             BLOCK
```

### Automatic Actions

| Risk Score | Decision | Action |
|------------|----------|---------|
| 0-29 | APPROVE | Process immediately |
| 30-69 | REVIEW | Queue for analyst review |
| 70-100 | BLOCK | Reject transaction, alert customer |

### Fallback Protection

When Bastion is unavailable:
- Configurable fallback action (default: approve)
- All decisions logged in immutable audit trail
- Automatic retry with exponential backoff
- Alert generation for service degradation

📖 **Full guide:** [Kafka Integration](docs/KAFKA_INTEGRATION.md) — Complete event bridge setup

---

## Bastion Integration

Real-time fraud detection powered by **Bastion** with both REST API and Kafka event streaming:

### Integration Architecture

```
Nexum Transaction → fraud_client.py → Bastion /score → Decision → Action
     ↓                    ↓              ↓         ↓        ↓
  Created          → Score API    → Risk Score  → Rule  → APPROVE/REVIEW/BLOCK
     ↓                                           ↓
Event Stream ←─── fraud_events.py ←──────── Kafka Topics
     ↓                                    (decisions, alerts)
 Real-time
 Analytics
```

### Synchronous Fraud Scoring

```python
# Real-time transaction scoring
fraud_result = fraud_client.score_transaction({
    "transaction_id": "txn_abc123",
    "account_id": "acc_xyz789", 
    "amount": 4500.00,
    "merchant_id": "merch_456",
    "channel": "mobile",
    "location": {"country": "US", "city": "San Francisco"},
    "metadata": {
        "ip_address": "192.168.1.100",
        "device_id": "mobile_device_123",
        "session_id": "sess_abc789"
    }
})

# Decision logic
if fraud_result.score < 30:
    action = "APPROVE"    # Low risk - process immediately
elif fraud_result.score < 70:  
    action = "REVIEW"     # Medium risk - queue for analyst
else:
    action = "BLOCK"      # High risk - reject transaction
```

### Asynchronous Event Streaming

**Published Kafka Topics:**

```python
# Fraud decision events
await fraud_events.publish_fraud_decision({
    "transaction_id": "txn_abc123",
    "decision": "approve",
    "score": 25.5,
    "risk_factors": ["unusual_time", "new_merchant"],
    "processing_time_ms": 45,
    "model_version": "fraudboost-v2.1"
})

# High-risk alerts
await fraud_events.publish_fraud_alert({
    "transaction_id": "txn_abc123",
    "alert_type": "high_risk_transaction",
    "score": 87.3,
    "requires_immediate_review": True,
    "customer_id": "cust_xyz789",
    "risk_factors": ["velocity_spike", "new_device", "geographic_anomaly"]
})
```

**Consumed Topics:**
- `nexum.transactions` — Real-time transaction data for Bastion
- `nexum.customers` — Customer profile updates for behavioral modeling

### Configuration & Monitoring

```bash
# Core configuration
export NEXUM_BASTION_URL="https://bastion.example.com"
export NEXUM_BASTION_API_KEY="your_api_key_here"
export NEXUM_BASTION_TIMEOUT="5.0"
export NEXUM_BASTION_FALLBACK="approve"

# Kafka integration
export NEXUM_KAFKA_ENABLED="true"
export NEXUM_KAFKA_BOOTSTRAP_SERVERS="kafka:9092"

# Monitoring thresholds
export NEXUM_BASTION_ALERT_THRESHOLD="70"
export NEXUM_BASTION_REVIEW_THRESHOLD="30"
```

### Health Monitoring

- **Service availability** — Automatic health checks with alerting
- **Response time tracking** — Latency monitoring with SLA alerts
- **Error rate monitoring** — Failed request tracking and exponential backoff
- **Fraud model drift detection** — Score distribution monitoring

📖 **Full guides:**
- [Kafka Integration Guide](docs/KAFKA_INTEGRATION.md) — Complete event bridge setup
- [Kafka Integration](docs/KAFKA_INTEGRATION.md) — Event streaming patterns

---

## Security

Enterprise-grade security designed for financial institutions with comprehensive compliance features:

### Authentication & Authorization

- **JWT Authentication** — Bearer tokens with configurable expiry (default 24h)
- **scrypt Password Hashing** — Memory-hard password protection replacing SHA-256
- **Role-Based Access Control** — 8 built-in roles, 30+ granular permissions
- **API Key Management** — Multiple authentication methods for system integration
- **Session Management** — Secure session handling with automatic invalidation

### Data Protection

- **PII Encryption at Rest** — Field-level encryption with AES-GCM or Fernet
- **Master Key Derivation** — PBKDF2-based key derivation with salt rotation
- **Selective Encryption** — Automatic detection and encryption of sensitive fields
- **Key Rotation** — Built-in key rotation with background re-encryption
- **Multi-Tenant Isolation** — Data separation via tenant-aware encryption keys

### Audit & Compliance

- **Hash-Chained Audit Trail** — SHA-256 linked immutable journal entries
- **ACID Transaction Logging** — Every financial operation atomically audited
- **Integrity Verification** — Tamper-evident audit log with chain validation
- **Compliance Reporting** — Built-in regulatory reporting and alert generation
- **Data Retention** — Configurable retention policies with automated archival

### Network Security

- **Rate Limiting** — 60 requests/minute per IP, configurable per endpoint
- **CORS Protection** — Cross-origin request security with domain whitelisting
- **SQL Injection Prevention** — Parameterized queries and input validation
- **XSS Protection** — Content Security Policy and output encoding
- **HTTPS Enforcement** — TLS termination with certificate management

### Fraud Prevention Integration

- **Real-time Scoring** — Every transaction scored for fraud risk
- **Behavioral Monitoring** — Device fingerprinting and velocity tracking  
- **Network Analysis** — Graph-based fraud ring detection
- **Automated Response** — Configurable blocking and review workflows

📖 **Full guide:** [Security Guide](docs/SECURITY.md) — Complete security architecture and compliance

---

## Configuration

Comprehensive environment-based configuration for production deployment:

| Environment Variable | Description | Default Value |
|---------------------|-------------|---------------|
| `NEXUM_HOST` | Server bind address | 0.0.0.0 |
| `NEXUM_PORT` | Server port | 8090 |
| `NEXUM_DATABASE_URL` | PostgreSQL connection string | sqlite:///nexum.db |
| `NEXUM_REDIS_URL` | Redis URL for caching | None (disabled) |
| `NEXUM_JWT_SECRET` | JWT token signing key | auto-generated |
| `NEXUM_JWT_EXPIRY_HOURS` | Token expiration time | 24 |
| `NEXUM_LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | INFO |
| `NEXUM_ENCRYPTION_ENABLED` | Enable PII encryption at rest | false |
| `NEXUM_ENCRYPTION_PROVIDER` | Encryption backend (aesgcm/fernet) | aesgcm |
| `NEXUM_ENCRYPTION_MASTER_KEY` | 256-bit master encryption key | None |
| `NEXUM_MULTI_TENANT` | Enable multi-tenancy support | false |
| `NEXUM_KAFKA_ENABLED` | Enable event streaming | false |
| `NEXUM_KAFKA_BOOTSTRAP_SERVERS` | Kafka broker endpoints | localhost:9092 |
| `NEXUM_BASTION_URL` | Bastion fraud detection API | None |
| `NEXUM_BASTION_API_KEY` | Bastion API authentication key | None |
| `NEXUM_BASTION_TIMEOUT` | Fraud API request timeout (seconds) | 5.0 |
| `NEXUM_BASTION_FALLBACK` | Action when Bastion unavailable | approve |
| `NEXUM_RATE_LIMIT` | API rate limit (requests/minute) | 60 |

### Production-Specific Settings

```bash
# Database configuration
export NEXUM_DATABASE_URL="postgresql://nexum:secure_pass@db:5432/nexum_prod"
export NEXUM_DATABASE_POOL_SIZE="20"
export NEXUM_DATABASE_MAX_OVERFLOW="30"

# Security configuration
export NEXUM_JWT_SECRET="$(openssl rand -base64 32)"
export NEXUM_ENCRYPTION_ENABLED="true"
export NEXUM_ENCRYPTION_MASTER_KEY="$(openssl rand -base64 32)"

# Performance tuning
export NEXUM_WORKER_PROCESSES="4"
export NEXUM_MAX_CONNECTIONS="1000"
export NEXUM_REQUEST_TIMEOUT="30"

# Monitoring
export NEXUM_LOG_LEVEL="INFO"
export NEXUM_METRICS_ENABLED="true"
export NEXUM_HEALTH_CHECK_INTERVAL="30"
```

📖 **Full guide:** [Deployment Guide](docs/DEPLOYMENT.md) — Production configuration and tuning

---

## Docker Deployment

Production-ready containerized deployment with full observability and scaling:

### docker-compose.yml

```yaml
version: '3.8'

services:
  nexum:
    build: 
      context: .
      dockerfile: Dockerfile
    ports:
      - "8090:8090"
    environment:
      - NEXUM_DATABASE_URL=postgresql://postgres:secure_password@db:5432/nexum
      - NEXUM_REDIS_URL=redis://redis:6379/0
      - NEXUM_ENCRYPTION_ENABLED=true
      - NEXUM_KAFKA_ENABLED=true
      - NEXUM_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - NEXUM_BASTION_URL=http://bastion:8000
    depends_on:
      - db
      - redis
      - kafka
      - bastion
    volumes:
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  dashboard:
    build:
      context: ./dashboard
    ports:
      - "8890:8890"
    depends_on:
      - nexum
    environment:
      - NEXUM_API_URL=http://nexum:8090

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=nexum
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  kafka:
    image: confluentinc/cp-kafka:latest
    environment:
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    depends_on:
      - zookeeper
    volumes:
      - kafka_data:/var/lib/kafka/data

  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    volumes:
      - zookeeper_data:/var/lib/zookeeper/data

  bastion:
    image: alexshrike/bastion:latest
    ports:
      - "8000:8000"
    environment:
      - BASTION_DATABASE_URL=postgresql://postgres:secure_password@db:5432/bastion
      - BASTION_ENCRYPTION_ENABLED=true
    depends_on:
      - db

volumes:
  postgres_data:
  redis_data:
  kafka_data:
  zookeeper_data:
```

### Quick Deployment Commands

```bash
# Start full production stack
docker-compose up -d

# Scale Nexum horizontally
docker-compose up -d --scale nexum=3

# View service logs
docker-compose logs -f nexum

# Health check all services
docker-compose ps

# Monitor resource usage
docker stats

# Backup database
docker-compose exec db pg_dump -U postgres nexum > backup.sql

# Update services
docker-compose pull
docker-compose up -d --force-recreate
```

### Production Considerations

- **Load Balancing** — Use nginx or HAProxy for multi-instance deployments
- **SSL Termination** — Configure TLS certificates for HTTPS
- **Monitoring** — Integrate with Prometheus/Grafana for observability
- **Backup Strategy** — Automated PostgreSQL backups with point-in-time recovery
- **Secret Management** — Use Docker secrets or external secret stores
- **Log Management** — Centralized logging with ELK stack or similar

📖 **Full guide:** [Deployment Guide](docs/DEPLOYMENT.md) — Production deployment patterns and scaling

---

## Documentation

Comprehensive documentation for developers, operators, and financial institutions:

### **Getting Started**
- **[Getting Started Guide](docs/GETTING_STARTED.md)** (1,337 lines) — Complete installation, configuration, and setup walkthrough
- **[Quick Start Guide](docs/getting-started.md)** (875 lines) — Fast-track development setup and basic operations

### **Architecture & Design**  
- **[Architecture Overview](docs/architecture.md)** (800 lines) — System design, data flow, and component dependencies
- **[API Reference](docs/api-reference.md)** (1,232 lines) — Complete REST endpoint documentation with examples

### **Operations & Deployment**
- **[Deployment Guide](docs/DEPLOYMENT.md)** (1,506 lines) — Production deployment, scaling, and infrastructure patterns  
- **[Security Guide](docs/SECURITY.md)** (1,523 lines) — Authentication, encryption, RBAC, and compliance
- **[Best Practices](docs/BEST_PRACTICES.md)** (2,902 lines) — Operational guidelines, performance optimization, troubleshooting

### **Integration & Development**
- **[Cookbook](docs/COOKBOOK.md)** (2,238 lines) — Real-world recipes, common patterns, and integration examples
- **[Kafka Integration](docs/KAFKA_INTEGRATION.md)** (297 lines) — Event streaming setup, topics, and message patterns

### **Module Reference**
Complete documentation for all 15 specialized banking modules:

| Module | Documentation | Description |
|--------|---------------|-------------|
| **[Collections](docs/modules/collections.md)** | 1,037 lines | Delinquency management, collection strategies, recovery workflows |
| **[Compliance](docs/modules/compliance.md)** | 1,369 lines | KYC/AML monitoring, transaction screening, regulatory reporting |
| **[Credit](docs/modules/credit.md)** | 989 lines | Credit line management, revolving credit, statement generation |
| **[Custom Fields](docs/modules/custom-fields.md)** | 1,274 lines | Dynamic field management and entity extension capabilities |
| **[Encryption](docs/modules/encryption.md)** | 765 lines | PII encryption at rest, key rotation, data protection |
| **[Events](docs/modules/events.md)** | 433 lines | Observer pattern implementation and domain event publishing |
| **[Kafka](docs/modules/kafka.md)** | 542 lines | Message streaming, topic management, event processing |
| **[Ledger](docs/modules/ledger.md)** | 615 lines | Double-entry bookkeeping, journal entries, balance calculations |
| **[Loans](docs/modules/loans.md)** | 912 lines | Loan origination, amortization schedules, payment processing |
| **[Notifications](docs/modules/notifications.md)** | 753 lines | Multi-channel messaging (email, SMS, push, webhook, in-app) |
| **[Products](docs/modules/products.md)** | 818 lines | Banking product configuration, templates, lifecycle management |
| **[RBAC](docs/modules/rbac.md)** | 1,618 lines | Role-based access control, permissions, user management |
| **[Reporting](docs/modules/reporting.md)** | 1,171 lines | Report generation, analytics, custom report definitions |
| **[Tenancy](docs/modules/tenancy.md)** | 792 lines | Multi-tenant isolation strategies and tenant management |
| **[Workflows](docs/modules/workflows.md)** | 1,166 lines | Approval chains, SLA management, process automation |

### **Integration References**
- **[Bastion Fraud Detection](https://github.com/AlexShrike/bastion)** — Real-time fraud scoring via `fraud_client.py` and `fraud_events.py`
- **[fraud_client.py](fraud_client.py)** — Synchronous fraud API integration
- **[fraud_events.py](fraud_events.py)** — Asynchronous Kafka event publishing

---

## Tech Stack

**Financial Infrastructure**
- **Language:** Python 3.14+ with comprehensive type hints
- **Web Framework:** FastAPI with automatic OpenAPI documentation
- **Database:** PostgreSQL with JSONB support + SQLite + InMemory storage options
- **Message Queue:** Apache Kafka for real-time event streaming
- **Caching:** Redis for session management and performance optimization

**Financial Precision**
- **Decimal Arithmetic** — No floating-point for monetary calculations
- **Double-Entry Bookkeeping** — Immutable journal entries with balance verification
- **ACID Transactions** — Database-level consistency guarantees
- **Hash-Chained Audit Trail** — SHA-256 tamper-evident logging
- **Multi-Currency Support** — Precise decimal handling across currencies

**Security & Compliance**
- **Authentication:** JWT tokens with scrypt password hashing
- **Encryption:** AES-GCM and Fernet for PII protection at rest
- **RBAC:** 8 roles with 30+ granular permissions
- **Audit Compliance:** Immutable logs with integrity verification
- **Data Protection:** GDPR-ready with configurable retention policies

**Integration & Events**
- **REST API:** 130+ endpoints with comprehensive OpenAPI docs
- **Event Streaming:** 27 Kafka topic types for real-time integration
- **Fraud Detection:** Real-time Bastion integration via REST + Kafka
- **Multi-Tenancy:** 3 isolation strategies with encryption
- **Webhooks:** Outbound notification system for external integration

**Operations & Deployment**
- **Containerization:** Docker and docker-compose for consistent deployment
- **Observability:** Structured JSON logging with correlation IDs
- **Health Monitoring:** Comprehensive health checks and metrics
- **Testing:** 707+ automated tests with pytest
- **CI/CD:** GitHub Actions with automated testing and deployment

**Dashboard & Frontend**
- **Framework:** Preact + HTM (no build step required)
- **Real-time Updates:** WebSocket integration for live data
- **Responsive Design:** Modern UI with accessibility compliance
- **Charts & Analytics:** Interactive financial visualizations
- **Theme Support:** Dark/light themes with user preferences

---

<p align="center">
  <strong>Enterprise-ready core banking infrastructure</strong><br>
  Built by <strong>AlexShrike</strong> • Self-hosted • Production-grade • Fraud-protected
</p>