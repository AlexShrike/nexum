# Nexum
### Production-grade core banking system

![Nexum Logo](https://via.placeholder.com/150x75/4CAF50/FFFFFF?text=NEXUM)

[![Tests Passing](https://img.shields.io/badge/tests-467%20passing-brightgreen)](./tests/)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue)](https://python.org)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## What is Nexum?

Nexum is an open-source, modular, API-first core banking system built for production environments. With 19 specialized modules, 112 REST endpoints, and 467 comprehensive tests, Nexum provides enterprise-grade financial infrastructure. Built on double-entry accounting principles with hash-chained audit trails, it ensures data integrity and regulatory compliance from day one.

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
🚀 **112 REST API endpoints** with OpenAPI/Swagger docs

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
pip install -r requirements.txt

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

**Total: 112 REST endpoints**

## 🛠️ Technology Stack

- **Language**: Python 3.14+
- **Web Framework**: FastAPI with automatic OpenAPI docs
- **Precision**: Decimal arithmetic (never floats for money)
- **Security**: SHA-256 hash-chained audit trail
- **Storage**: Pluggable storage (SQLite, PostgreSQL ready)
- **Testing**: Pytest with 467 comprehensive tests
- **API Documentation**: Auto-generated OpenAPI/Swagger

## 🧪 Testing

Run the complete test suite:

```bash
python -m pytest tests/ -v
```

**Test Coverage**: 467 tests across 16 test modules covering:
- Unit tests for all financial calculations
- Integration tests for complete workflows
- Edge cases and error conditions
- Compliance and audit trail validation

## 📁 Project Structure

```
nexum/
├── core_banking/           # Main package (19 modules)
│   ├── api.py             # REST API endpoints (112 endpoints)
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
│   └── products.py       # Product configuration
├── tests/                 # Test suite (467 tests)
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

**Nexum** is built by [Gradient Mind](https://gradientmind.ai) — Production-grade financial infrastructure for the modern world.

GitHub: [https://github.com/AlexShrike/nexum](https://github.com/AlexShrike/nexum)