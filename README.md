# Nexum
### Production-grade core banking system

![Nexum Logo](https://via.placeholder.com/150x75/4CAF50/FFFFFF?text=NEXUM)

[![Tests Passing](https://img.shields.io/badge/tests-642%20passing-brightgreen)](./tests/)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue)](https://python.org)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## What is Nexum?

Nexum is an open-source, modular, API-first core banking system built for production environments. With 29+ specialized modules, 130+ REST endpoints, and 642 comprehensive tests, Nexum provides enterprise-grade financial infrastructure with PostgreSQL support, JWT authentication, and Kafka integration. Built on double-entry accounting principles with hash-chained audit trails, it ensures data integrity and regulatory compliance from day one.

## ✨ Key Features

🏦 **Double-entry ledger** with hash-chained audit trail  
🔧 **Configurable Product Engine** (launch products without code)  
💳 **Loan origination & amortization** (French, equal principal, bullet)  
📊 **Credit line management** (revolving credit, grace periods, statements)  
⚡ **Collections management** with auto-escalation  
🌍 **Multi-currency support**  
🔍 **KYC/AML compliance engine**  
📈 **Dynamic reporting & analytics**  
⚙️ **Configurable workflow engine** (approval chains, SLA)  
🔐 **Role-based access control** (8 roles, 30 permissions)  
🏷️ **Custom fields** on any entity  
🚀 **130+ REST API endpoints** with OpenAPI/Swagger docs  
🏭 **Production-Ready Infrastructure** (PostgreSQL, JWT auth, Kafka events)  
⚡ **ACID transactions** with migration system  
📊 **Rate limiting** (60 req/min) and structured JSON logging  
🔒 **PII Encryption at Rest** (AES-256-GCM/Fernet) for sensitive data  
🏢 **Multi-Tenancy Support** with tenant isolation and branding  
📧 **Notification Engine** (Email, SMS, Push, Webhook, In-App)  
🎯 **Event-Driven Architecture** with Observer pattern (publish/subscribe)

## 🏭 Production Ready Features

Nexum includes enterprise-grade infrastructure components for production deployment:

**🔐 Security & Authentication**
- JWT bearer token authentication with configurable expiry
- scrypt password hashing (replacing legacy SHA-256)
- Rate limiting middleware (60 requests/minute per IP)
- Role-based access control with permission enforcement

**💾 Storage & Data**
- PostgreSQL backend with JSONB support and GIN indexes
- ACID transaction support with atomic() context managers
- Database migration system (8 migrations: v001-v008)
- SQLite and in-memory storage for testing

**📊 Configuration & Monitoring**
- Environment-based configuration (NEXUM_* environment variables)
- Structured JSON logging with configurable levels
- Modular API architecture (15+ router modules)
- Comprehensive pagination (skip/limit/total) on list endpoints

**⚡ Event-Driven Architecture**
- Kafka integration for real-time event streaming
- Event hooks system for custom business logic
- CloudEvents-compatible message format
- Async event processing and publishing

## 🛡️ Fraud Detection Integration (Bastion)

Nexum integrates seamlessly with **Bastion**, a real-time fraud scoring engine, to provide intelligent transaction monitoring and risk assessment.

**🔍 Key Components:**
- **fraud_client.py** - REST client for real-time fraud scoring
- **fraud_events.py** - Kafka event publishing for fraud alerts

**⚡ Real-time Processing Flow:**
```
Transaction → fraud_client.py → Bastion /score → Decision → Action
    ↓              ↓                ↓           ↓        ↓
  Created    →  Score API    →    Risk Score  → Rule  → APPROVE/REVIEW/BLOCK
```

**📋 Decision Flow:**
- **APPROVE** - Low risk score, transaction proceeds automatically
- **REVIEW** - Medium risk score, flagged for manual review
- **BLOCK** - High risk score, transaction blocked immediately

**⚙️ Configuration Variables:**
```bash
export NEXUM_BASTION_URL="https://bastion.example.com"
export NEXUM_BASTION_API_KEY="your-api-key"
export NEXUM_BASTION_TIMEOUT="5.0"           # Request timeout in seconds
export NEXUM_BASTION_FALLBACK="approve"      # Fallback action if Bastion unavailable
```

**🎯 Integration Points:**
- **REST API**: Real-time transaction scoring via `/score` endpoint
- **Kafka Events**: Asynchronous fraud alerts and decision publishing
- **Fallback Mode**: Configurable behavior when fraud service is unavailable
- **Audit Trail**: All fraud decisions logged in hash-chained audit system

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   REST API      │    │   Workflows     │    │   Reporting     │
│   112 endpoints │    │   Approval      │    │   Analytics     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Customers     │    │   Compliance    │    │   Custom Fields │
│   KYC/AML       │    │   Risk Mgmt     │    │   Validation    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Accounts      │    │   Products      │    │   Collections   │
│   Management    │    │   Configuration │    │   Strategies    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Transactions  │    │   Credit Lines  │    │   Loans         │
│   Processing    │    │   Statements    │    │   Amortization  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Interest      │    │   Ledger        │    │   Audit Trail   │
│   Calculations  │    │   Double Entry  │    │   Hash Chain    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Storage       │    │   Currency      │    │   RBAC          │
│   Abstraction   │    │   Multi-Support │    │   Authorization │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/AlexShrike/nexum
cd nexum

# Install dependencies
poetry install

# Configure database (optional - defaults to SQLite)
export NEXUM_DATABASE_URL="postgresql://user:pass@localhost/nexum"
export NEXUM_JWT_SECRET="your-secret-key-change-in-production"

# Configure encryption for PII data (optional)
export NEXUM_ENCRYPTION_ENABLED="true"
export NEXUM_ENCRYPTION_PROVIDER="aesgcm"  # or "fernet"
export NEXUM_ENCRYPTION_MASTER_KEY="your-256-bit-encryption-master-key"

# Configure multi-tenancy (optional)
export NEXUM_MULTI_TENANT="true"

# Start the server
python run.py

# Test the API
curl http://localhost:8090/health
```

The API will be available at `http://localhost:8090` with interactive docs at `/docs`.

## 📦 Module Overview

| Module | Description | Lines of Code |
|--------|-------------|---------------|
| **api.py** | REST API endpoints and Pydantic models | 2,923 |
| **ledger.py** | Double-entry bookkeeping engine | 551 |
| **accounts.py** | Account management and chart of accounts | 678 |
| **customers.py** | Customer profiles and KYC management | 676 |
| **transactions.py** | Transaction processing and validation | 1,052 |
| **interest.py** | Interest calculations and accrual | 969 |
| **credit.py** | Credit line management and statements | 885 |
| **loans.py** | Loan origination and amortization | 1,236 |
| **collections.py** | Delinquency management and strategies | 1,156 |
| **compliance.py** | KYC/AML checks and monitoring | 700 |
| **workflows.py** | Approval chains and SLA management | 1,010 |
| **rbac.py** | Role-based access control | 942 |
| **reporting.py** | Report generation and analytics | 1,329 |
| **custom_fields.py** | Dynamic field management | 793 |
| **audit.py** | Hash-chained audit trail | 434 |
| **currency.py** | Multi-currency support | 265 |
| **storage.py** | Storage abstraction layer | 358 |
| **products.py** | Product configuration engine | 692 |
| **events.py** | Event dispatcher and observer pattern | 412 |
| **notifications.py** | Multi-channel notification engine | 1,068 |
| **tenancy.py** | Multi-tenant isolation and management | 495 |
| **encryption.py** | PII encryption at rest with key rotation | 488 |
| **__init__.py** | Package initialization | 5 |

## 🔌 API Overview

| Module | Endpoints | Description |
|--------|-----------|-------------|
| **Health & Status** | 2 | System health and status checks |
| **Customers** | 12 | Customer CRUD, KYC management, beneficiaries |
| **Accounts** | 15 | Account operations, balance queries, holds |
| **Transactions** | 18 | Deposits, withdrawals, transfers, reversals |
| **Credit Lines** | 10 | Credit management, statements, payments |
| **Loans** | 12 | Loan creation, payments, amortization |
| **Interest** | 8 | Interest calculations and posting |
| **Collections** | 9 | Delinquency management, strategies |
| **Compliance** | 6 | KYC checks, AML monitoring |
| **Workflows** | 8 | Approval chains, task management |
| **RBAC** | 7 | User management, roles, permissions |
| **Reporting** | 5 | Report generation, custom reports |
| **Products** | 4 | Product configuration, templates |
| **Custom Fields** | 4 | Dynamic field management |
| **Audit** | 2 | Audit trail queries, integrity checks |

| **Notifications** | 10 | Notification templates, sending, preferences |
| **Tenancy** | 8 | Multi-tenant management, stats, branding |
| **Encryption** | 3 | Key management, encryption status, rotation |
| **Kafka Events** | 6 | Event streaming, consumer management |  
| **Authentication** | 3 | Login, logout, token refresh |

**Total: 130+ REST endpoints**

## 🛠️ Technology Stack

- **Language**: Python 3.14+
- **Web Framework**: FastAPI with automatic OpenAPI docs
- **Database**: PostgreSQL with JSONB + SQLite + In-Memory
- **Precision**: Decimal arithmetic (never floats for money)  
- **Security**: JWT authentication + scrypt password hashing
- **Auditing**: Hash-chained audit trail with integrity verification
- **Events**: Kafka integration for real-time event streaming
- **Configuration**: Environment-based config (NEXUS_* variables)
- **Testing**: Pytest with 514 comprehensive tests
- **API Documentation**: Auto-generated OpenAPI/Swagger

## 🧪 Testing

Run the complete test suite:

```bash
python -m pytest tests/ -v
```

**Test Coverage**: 642 tests across 16 test modules covering:
- Unit tests for all financial calculations
- Integration tests for complete workflows
- Edge cases and error conditions
- Compliance and audit trail validation

## 📁 Project Structure

```
nexum/
├── core_banking/           # Main package (29+ modules)
│   ├── api.py             # Main API server
│   ├── api_modular/       # Modular API routers (15 modules)
│   ├── config.py          # Environment-based configuration
│   ├── migrations.py      # Database migration system
│   ├── kafka_integration.py # Event streaming support
│   ├── logging_config.py  # Structured JSON logging
│   ├── ledger.py          # Double-entry bookkeeping
│   ├── accounts.py        # Account management
│   ├── customers.py       # Customer & KYC
│   ├── transactions.py    # Transaction processing
│   ├── interest.py        # Interest calculations
│   ├── credit.py          # Credit line management
│   ├── loans.py           # Loan processing
│   ├── collections.py     # Delinquency management
│   ├── compliance.py      # KYC/AML compliance
│   ├── workflows.py       # Approval workflows
│   ├── rbac.py           # Role-based access control
│   ├── reporting.py       # Reports & analytics
│   ├── custom_fields.py   # Dynamic fields
│   ├── audit.py          # Audit trail
│   ├── currency.py       # Multi-currency
│   ├── storage.py        # Storage abstraction
│   ├── products.py       # Product configuration
│   ├── events.py         # Event dispatcher (observer pattern)
│   ├── notifications.py  # Multi-channel notifications
│   ├── tenancy.py        # Multi-tenant support
│   ├── encryption.py     # PII encryption at rest
│   └── event_hooks.py    # Kafka event hooks
├── tests/                 # Test suite (514 tests)
│   ├── test_ledger.py    # Ledger tests
│   ├── test_accounts.py  # Account tests
│   └── ...               # (16 test modules)
├── docs/                 # Documentation
│   ├── architecture.md   # System architecture
│   ├── getting-started.md # Setup guide
│   ├── api-reference.md  # API documentation
│   └── modules/          # Module-specific docs
└── run.py                # Server startup script
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Ensure all tests pass (`python -m pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Guidelines

- All monetary calculations must use `decimal.Decimal`
- Every financial operation requires comprehensive tests
- Maintain the hash-chained audit trail integrity
- Follow double-entry accounting principles
- Document API changes in OpenAPI format

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🏢 About

**Nexum** — Production-grade financial infrastructure for the modern world.

GitHub: [https://github.com/AlexShrike/nexum](https://github.com/AlexShrike/nexum)