# Getting Started with Nexum Core Banking

Welcome! This guide will walk you through setting up Nexum from scratch. No prior core banking experience needed — we'll explain every concept along the way.

---

## Table of Contents

1. [What is Nexum?](#what-is-nexum)
2. [How Core Banking Works](#how-core-banking-works)
3. [Installation](#installation)
4. [Your First Customer and Account](#your-first-customer-and-account)
5. [Making Transactions](#making-transactions)
6. [Opening a Loan](#opening-a-loan)
7. [Creating a Credit Line](#creating-a-credit-line)
8. [Checking Audit Trail](#checking-audit-trail)
9. [PostgreSQL Setup](#postgresql-setup)
10. [Running with Docker](#running-with-docker)
11. [Common Scenarios](#common-scenarios)
12. [Next Steps](#next-steps)

---

## What is Nexum?

Nexum is a **core banking platform** — a piece of software that manages financial accounts, processes transactions, and handles lending operations. It's the brain behind:

- ✅ **Customer accounts** — Savings, checking, credit lines
- ✅ **Transactions** — Deposits, withdrawals, transfers, payments
- ✅ **Lending** — Loans with amortization schedules, payment processing
- ✅ **Credit lines** — Revolving credit with statements and minimum payments
- ✅ **Compliance** — KYC/AML checks, transaction limits, audit trails

Think of it like the engine that powers a bank's operations. Every time someone makes a deposit, transfers money, or makes a loan payment, Nexum processes it with proper double-entry bookkeeping.

### Who is this for?

- **Fintech companies** building digital banking products
- **Credit unions** modernizing their core systems
- **Microfinance institutions** managing lending operations
- **Neo-banks** launching new banking services
- **Developers** who want to understand core banking systems

---

## How Core Banking Works

Before we start coding, let's understand the basics.

### Double-Entry Bookkeeping

Every financial transaction creates **two journal entries** that balance:

| Transaction | Debit Account | Credit Account |
|-------------|---------------|----------------|
| Customer deposits $100 | Cash (Asset) | Customer's Account (Liability) |
| Customer withdraws $50 | Customer's Account (Liability) | Cash (Asset) |
| Bank pays interest | Interest Expense | Customer's Account (Liability) |

The fundamental rule: **Debits = Credits**. This ensures the books always balance and nothing gets lost.

### The Transaction Pipeline

```
Customer initiates transaction
        ↓
   Compliance checks (KYC, limits)    ← ComplianceEngine
        ↓
   Create journal entry               ← GeneralLedger
        ↓
   Update account balances            ← AccountManager
        ↓
   Log to audit trail                 ← AuditTrail
        ↓
   Notify external systems            ← EventDispatcher
```

Every step happens atomically. If any step fails, the entire transaction rolls back.

---

## Installation

### Prerequisites

- **Python 3.12 or higher** — Check with `python --version`
- **Poetry** — Nexum's package manager
- **Git** — To clone the repository

### Step-by-Step Install

**1. Clone the repository:**

```bash
git clone https://github.com/AlexShrike/nexum.git
cd nexum
```

**2. (Recommended) Use the shared virtual environment:**

```bash
source /Users/alexshrike/.openclaw/workspace/rustcluster/.venv/bin/activate
```

**3. Install Nexum:**

```bash
# Basic install (SQLite storage)
poetry install

# With PostgreSQL support (recommended for production)
poetry install -E postgres

# With PII encryption (recommended for compliance)
poetry install -E encryption

# Everything (recommended)
poetry install -E full
```

**4. Verify it works:**

```bash
python -c "from core_banking import *; print('Nexum is ready!')"
```

You should see: `Nexum is ready!`

**5. Start the API server:**

```bash
python run.py
```

This starts the server on `http://localhost:8090`. You should see:

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8090 (Press CTRL+C to quit)
```

**6. Verify the server is running:**

```bash
curl http://localhost:8090/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2024-02-19T15:32:00.000000",
  "version": "1.0.0"
}
```

---

## Production Setup

For production deployment, you'll need additional configuration for security, persistence, and compliance.

### Environment Configuration

Create a `.env` file with your settings:

```bash
# Database (PostgreSQL recommended for production)
NEXUM_DATABASE_URL=postgresql://nexum_user:secure_password@localhost:5432/nexum_prod

# Security
NEXUM_JWT_SECRET=your-secure-256-bit-secret-here
NEXUM_JWT_EXPIRY_HOURS=8

# PII Encryption
NEXUM_ENCRYPTION_ENABLED=true
NEXUM_ENCRYPTION_MASTER_KEY=your-base64-master-key-here
NEXUM_ENCRYPTION_PROVIDER=aesgcm

# API Configuration
NEXUM_API_HOST=0.0.0.0
NEXUM_API_PORT=8090
NEXUM_API_WORKERS=4

# Business Rules
NEXUM_MAX_DAILY_TRANSACTION_LIMIT=50000.00
NEXUM_MIN_ACCOUNT_BALANCE=0.00
NEXUM_ENABLE_RATE_LIMITING=true

# Audit and Compliance
NEXUM_ENABLE_AUDIT_LOGGING=true
NEXUM_LOG_LEVEL=INFO
NEXUM_LOG_FORMAT=json
```

### Authentication Setup

Enable JWT authentication for production:

**1. Generate a secure JWT secret:**

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**2. Set environment variable:**

```bash
export NEXUM_JWT_SECRET="your-secure-secret-from-step-1"
```

**3. Create admin user:**

```bash
curl -X POST http://localhost:8090/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "SecurePassword123!",
    "email": "admin@yourbank.com",
    "full_name": "Bank Administrator"
  }'
```

**4. Login to get token:**

```bash
curl -X POST http://localhost:8090/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin", 
    "password": "SecurePassword123!"
  }'
```

**5. Use the token in API requests:**

```bash
curl -X GET http://localhost:8090/customers \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE"
```

### PII Encryption Setup

Enable field-level encryption for sensitive customer data:

**1. Generate a master encryption key:**

```bash
python -c "
from core_banking.encryption import KeyManager
import base64, secrets
key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
print(f'Master key: {key}')
"
```

**2. Configure encryption:**

```bash
export NEXUM_ENCRYPTION_ENABLED=true
export NEXUM_ENCRYPTION_MASTER_KEY="your-base64-master-key"
export NEXUM_ENCRYPTION_PROVIDER=aesgcm  # or fernet
```

**3. Restart the server to enable encryption:**

```bash
python run.py
```

Now all PII fields (customer names, emails, phone numbers, addresses) will be automatically encrypted at rest.

---

## Your First Customer and Account

Let's create your first customer and banking account. 

**Note**: All examples assume JWT authentication. Get your token first:

```bash
# Login and save token
export JWT_TOKEN=$(curl -s -X POST http://localhost:8090/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "SecurePassword123!"}' | \
  jq -r '.access_token')
```

### Step 1: Create a Customer

```bash
curl -X POST http://localhost:8090/customers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "first_name": "Sarah",
    "last_name": "Johnson", 
    "email": "sarah.johnson@example.com",
    "phone": "+1-555-0199",
    "date_of_birth": "1985-03-15",
    "address": {
      "line1": "456 Oak Avenue",
      "city": "Portland",
      "state": "OR", 
      "postal_code": "97201",
      "country": "US"
    }
  }'
```

**Response:**
```json
{
  "customer_id": "cust_01HPH123ABC456DEF789",
  "first_name": "Sarah",
  "last_name": "Johnson",
  "email": "sarah.johnson@example.com",
  "phone": "+1-555-0199", 
  "date_of_birth": "1985-03-15",
  "kyc_status": "none",
  "kyc_tier": "tier_0",
  "is_active": true,
  "created_at": "2024-02-19T15:32:00.000000"
}
```

**What happened?**
- Customer record was created and stored
- PII fields were encrypted if encryption is enabled
- An audit event was logged
- Customer gets KYC status "none" (needs verification before opening accounts)

### Step 2: Complete KYC Verification

Before creating accounts, update the customer's Know Your Customer (KYC) status:

```bash
curl -X PUT http://localhost:8090/customers/cust_01HPH123ABC456DEF789/kyc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "status": "verified",
    "tier": "tier_2",
    "documents": ["drivers_license", "proof_of_address"],
    "expiry_days": 365
  }'
```

**Response:**
```json
{
  "customer_id": "cust_01HPH123ABC456DEF789",
  "kyc_status": "verified",
  "kyc_tier": "tier_2",
  "documents": ["drivers_license", "proof_of_address"],
  "verified_at": "2024-02-19T15:35:00.000000",
  "expires_at": "2025-02-19T15:35:00.000000"
}
```

### Step 3: Create a Savings Account

Now we can create a savings account for the customer:

```bash
curl -X POST http://localhost:8090/accounts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_01HPH123ABC456DEF789",
    "product_type": "savings",
    "currency": "USD",
    "name": "Primary Savings Account",
    "interest_rate": "0.0225",
    "minimum_balance": {
      "amount": "100.00",
      "currency": "USD"
    }
  }'
```

**Response:**
```json
{
  "account_id": "acc_01HPH456GHI789JKL012",
  "customer_id": "cust_01HPH123ABC456DEF789", 
  "product_type": "savings",
  "account_number": "1001234567",
  "currency": "USD",
  "name": "Primary Savings Account",
  "status": "active",
  "balance": {
    "amount": "0.00",
    "currency": "USD"
  },
  "available_balance": {
    "amount": "0.00", 
    "currency": "USD"
  },
  "interest_rate": "0.0225",
  "minimum_balance": {
    "amount": "100.00",
    "currency": "USD"
  },
  "created_at": "2024-02-19T15:38:00.000000"
}
```

**What happened?**
- A general ledger account was created
- Account number was auto-generated
- Interest rate was set to 2.25% annual
- Minimum balance hold will be enforced
- All changes were logged to audit trail

---

## Making Transactions

Now let's process some banking transactions using proper double-entry bookkeeping.

### Deposit Money

Make an initial deposit to the savings account:

```bash
curl -X POST http://localhost:8090/transactions/deposit \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "account_id": "acc_01HPH456GHI789JKL012",
    "amount": {
      "amount": "2500.00",
      "currency": "USD"
    },
    "description": "Initial deposit - payroll transfer",
    "channel": "online",
    "reference": "PAY20240219001",
    "idempotency_key": "deposit_001_sarah"
  }'
```

**Response:**
```json
{
  "transaction_id": "txn_01HPH789MNO012PQR345",
  "transaction_type": "deposit",
  "account_id": "acc_01HPH456GHI789JKL012",
  "amount": {
    "amount": "2500.00", 
    "currency": "USD"
  },
  "description": "Initial deposit - payroll transfer",
  "channel": "online",
  "reference": "PAY20240219001",
  "status": "completed",
  "journal_entry_id": "je_01HPH789ABC123DEF456",
  "created_at": "2024-02-19T15:40:00.000000",
  "processed_at": "2024-02-19T15:40:00.000000"
}
```

**Behind the scenes:** 
The deposit created this journal entry:
```
Debit:  Cash Account        $2,500.00
Credit: Customer Account    $2,500.00
```

### Check Account Balance

```bash
curl http://localhost:8090/accounts/acc_01HPH456GHI789JKL012/balance \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Response:**
```json
{
  "account_id": "acc_01HPH456GHI789JKL012",
  "balance": {
    "amount": "2500.00",
    "currency": "USD"
  },
  "available_balance": {
    "amount": "2400.00",
    "currency": "USD"
  },
  "holds": [
    {
      "hold_id": "hold_minimum_balance",
      "amount": {
        "amount": "100.00",
        "currency": "USD"  
      },
      "reason": "minimum_balance_requirement",
      "created_at": "2024-02-19T15:40:00.000000"
    }
  ],
  "as_of": "2024-02-19T15:41:00.000000"
}
```

**Note:** Available balance is $2,400 because $100 is held for the minimum balance requirement.

### Make a Withdrawal

```bash
curl -X POST http://localhost:8090/transactions/withdraw \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "account_id": "acc_01HPH456GHI789JKL012",
    "amount": {
      "amount": "500.00",
      "currency": "USD"
    },
    "description": "ATM withdrawal",
    "channel": "atm",
    "reference": "ATM20240219001"
  }'
```

**Response:**
```json
{
  "transaction_id": "txn_01HPH890STU345VWX678",
  "transaction_type": "withdrawal", 
  "account_id": "acc_01HPH456GHI789JKL012",
  "amount": {
    "amount": "500.00",
    "currency": "USD"
  },
  "status": "completed",
  "new_balance": {
    "amount": "2000.00",
    "currency": "USD"
  },
  "processed_at": "2024-02-19T15:43:00.000000"
}
```

### Create a Checking Account and Transfer

Let's create a checking account and transfer some money:

```bash
# Create checking account
curl -X POST http://localhost:8090/accounts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_01HPH123ABC456DEF789",
    "product_type": "checking",
    "currency": "USD",
    "name": "Primary Checking Account",
    "daily_transaction_limit": {
      "amount": "5000.00",
      "currency": "USD"
    }
  }'
```

```bash
# Transfer from savings to checking
curl -X POST http://localhost:8090/transactions/transfer \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "from_account_id": "acc_01HPH456GHI789JKL012", 
    "to_account_id": "acc_01HPH567JKL890MNO123",
    "amount": {
      "amount": "800.00",
      "currency": "USD"
    },
    "description": "Transfer to checking for expenses",
    "channel": "online",
    "reference": "XFR20240219001"
  }'
```

---

## Opening a Loan

Nexum supports full loan lifecycle management with amortization schedules, payment processing, and interest calculations.

### Step 1: Create a Loan

```bash
curl -X POST http://localhost:8090/loans \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_01HPH123ABC456DEF789",
    "terms": {
      "principal_amount": {
        "amount": "25000.00",
        "currency": "USD"
      },
      "annual_interest_rate": "0.0675",
      "term_months": 60,
      "payment_frequency": "monthly", 
      "amortization_method": "equal_installment",
      "first_payment_date": "2024-03-19",
      "allow_prepayment": true,
      "grace_period_days": 10,
      "late_fee": {
        "amount": "35.00",
        "currency": "USD"
      }
    },
    "currency": "USD"
  }'
```

**Response:**
```json
{
  "loan_id": "loan_01HPH678PQR901STU234",
  "customer_id": "cust_01HPH123ABC456DEF789",
  "account_id": "acc_01HPH678RST012UVW345",
  "state": "originated",
  "terms": {
    "principal_amount": {
      "amount": "25000.00",
      "currency": "USD"
    },
    "annual_interest_rate": "0.0675",
    "term_months": 60,
    "payment_frequency": "monthly",
    "monthly_payment": {
      "amount": "495.84",
      "currency": "USD"
    }
  },
  "current_balance": {
    "amount": "25000.00",
    "currency": "USD"
  },
  "next_payment_date": "2024-03-19",
  "maturity_date": "2029-02-19"
}
```

### Step 2: Disburse the Loan

Transfer loan funds to the customer's checking account:

```bash
curl -X POST http://localhost:8090/loans/loan_01HPH678PQR901STU234/disburse \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "to_account_id": "acc_01HPH567JKL890MNO123",
    "disbursement_date": "2024-02-19"
  }'
```

### Step 3: View Loan Payment Schedule

```bash
curl http://localhost:8090/loans/loan_01HPH678PQR901STU234/schedule \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Response (first 3 payments):**
```json
{
  "loan_id": "loan_01HPH678PQR901STU234",
  "total_payments": 60,
  "schedule": [
    {
      "payment_number": 1,
      "payment_date": "2024-03-19",
      "payment_amount": {
        "amount": "495.84",
        "currency": "USD"
      },
      "principal_amount": {
        "amount": "355.09", 
        "currency": "USD"
      },
      "interest_amount": {
        "amount": "140.75",
        "currency": "USD"
      },
      "remaining_balance": {
        "amount": "24644.91",
        "currency": "USD"
      }
    },
    {
      "payment_number": 2,
      "payment_date": "2024-04-19",
      "payment_amount": {
        "amount": "495.84",
        "currency": "USD"
      },
      "principal_amount": {
        "amount": "357.08",
        "currency": "USD"
      },
      "interest_amount": {
        "amount": "138.76",
        "currency": "USD"
      },
      "remaining_balance": {
        "amount": "24287.83",
        "currency": "USD"
      }
    }
  ]
}
```

### Step 4: Make a Loan Payment

```bash
curl -X POST http://localhost:8090/loans/loan_01HPH678PQR901STU234/payment \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "amount": {
      "amount": "495.84", 
      "currency": "USD"
    },
    "payment_date": "2024-03-19",
    "source_account_id": "acc_01HPH567JKL890MNO123"
  }'
```

**Response:**
```json
{
  "payment_id": "pay_01HPH789XYZ123ABC456",
  "loan_id": "loan_01HPH678PQR901STU234",
  "amount": {
    "amount": "495.84",
    "currency": "USD"
  },
  "principal_payment": {
    "amount": "355.09",
    "currency": "USD"
  },
  "interest_payment": {
    "amount": "140.75", 
    "currency": "USD"
  },
  "new_balance": {
    "amount": "24644.91",
    "currency": "USD"
  },
  "next_payment_date": "2024-04-19",
  "status": "completed"
}
```

---

## Creating a Credit Line

Nexum supports revolving credit lines with monthly statements, minimum payments, and grace periods.

### Step 1: Create Credit Line Account

```bash
curl -X POST http://localhost:8090/accounts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_01HPH123ABC456DEF789",
    "product_type": "credit_line", 
    "currency": "USD",
    "name": "Personal Line of Credit",
    "credit_limit": {
      "amount": "10000.00",
      "currency": "USD"
    },
    "interest_rate": "0.1899"
  }'
```

### Step 2: Make a Credit Draw

```bash
curl -X POST http://localhost:8090/credit/acc_01HPH789ABC123DEF456/draw \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "amount": {
      "amount": "1500.00",
      "currency": "USD"
    },
    "description": "Cash advance for home repairs",
    "category": "cash_advance"
  }'
```

### Step 3: Make a Credit Payment

```bash
curl -X POST http://localhost:8090/credit/acc_01HPH789ABC123DEF456/payment \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "amount": {
      "amount": "200.00",
      "currency": "USD"
    },
    "source_account_id": "acc_01HPH567JKL890MNO123"
  }'
```

### Step 4: Generate Monthly Statement

```bash
curl -X POST http://localhost:8090/credit/acc_01HPH789ABC123DEF456/statement \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "statement_date": "2024-02-29"
  }'
```

---

## Checking Audit Trail

Every operation in Nexum is logged to an immutable, hash-chained audit trail for compliance and transparency.

### View Recent Audit Events

```bash
curl "http://localhost:8090/audit/events?limit=10" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Response:**
```json
{
  "events": [
    {
      "id": "ae_01HPH890DEF567GHI890",
      "event_type": "transaction_posted",
      "entity_type": "transaction", 
      "entity_id": "txn_01HPH789MNO012PQR345",
      "created_at": "2024-02-19T15:40:00.000000",
      "user_id": "admin",
      "metadata": {
        "transaction_type": "deposit",
        "amount": "2500.00",
        "currency": "USD",
        "account_id": "acc_01HPH456GHI789JKL012"
      },
      "current_hash": "abc123def456789...",
      "previous_hash": "def456ghi789012..."
    },
    {
      "id": "ae_01HPH891GHI678JKL901", 
      "event_type": "account_created",
      "entity_type": "account",
      "entity_id": "acc_01HPH456GHI789JKL012",
      "created_at": "2024-02-19T15:38:00.000000",
      "metadata": {
        "customer_id": "cust_01HPH123ABC456DEF789",
        "product_type": "savings", 
        "currency": "USD"
      }
    }
  ],
  "total_count": 847,
  "has_more": true
}
```

### Verify Audit Trail Integrity

```bash
curl -X POST http://localhost:8090/audit/verify-integrity \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Response:**
```json
{
  "is_valid": true,
  "total_events": 847,
  "verified_events": 847,
  "hash_chain_valid": true,
  "verification_time": "2024-02-19T15:45:00.000000"
}
```

---

## PostgreSQL Setup

For production deployments, PostgreSQL is strongly recommended for its JSONB support, ACID transactions, and performance.

### Install PostgreSQL

```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# macOS
brew install postgresql

# Start PostgreSQL
sudo service postgresql start  # Linux
brew services start postgresql # macOS
```

### Create Database and User

```bash
sudo -u postgres psql

-- Create database
CREATE DATABASE nexum_production;

-- Create user with secure password
CREATE USER nexum_user WITH PASSWORD 'SecurePassword123!';

-- Grant privileges  
GRANT ALL PRIVILEGES ON DATABASE nexum_production TO nexum_user;

-- For PostgreSQL 15+, also grant schema privileges
\c nexum_production
GRANT ALL ON SCHEMA public TO nexum_user;

\q
```

### Configure Connection

```bash
export NEXUM_DATABASE_URL="postgresql://nexum_user:SecurePassword123!@localhost:5432/nexum_production"
```

### Install PostgreSQL Driver

```bash
poetry install -E postgres
```

### Database Migrations

Nexum includes built-in migrations. They run automatically on startup:

```bash
python run.py
```

**Manual migration:**

```bash
python -c "
from core_banking.storage import PostgreSQLStorage
from core_banking.migrations import MigrationManager
from core_banking.config import get_config

config = get_config()
storage = PostgreSQLStorage(config.database_url)
mm = MigrationManager(storage)

print(f'Current version: {mm.get_current_version()}')
applied = mm.migrate_up()
for migration in applied:
    print(f'Applied: {migration}')
"
```

---

## Running with Docker

For containerized deployment with PostgreSQL and optional Kafka:

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Copy dependency files  
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install -E full --no-dev

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash nexum
USER nexum

# Expose port
EXPOSE 8090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8090/health || exit 1

# Run server
CMD ["python", "run.py"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  nexum:
    build: .
    ports:
      - "8090:8090"
    environment:
      - NEXUM_DATABASE_URL=postgresql://nexum:nexumpass@postgres:5432/nexum
      - NEXUM_JWT_SECRET=your-secure-jwt-secret-here
      - NEXUM_ENCRYPTION_ENABLED=true
      - NEXUM_ENCRYPTION_MASTER_KEY=your-encryption-key-here
      - NEXUM_LOG_LEVEL=INFO
      - NEXUM_ENABLE_KAFKA_EVENTS=true
      - NEXUM_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    depends_on:
      - postgres
      - kafka
    volumes:
      - ./logs:/app/logs
      
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=nexum
      - POSTGRES_USER=nexum
      - POSTGRES_PASSWORD=nexumpass
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    
  kafka:
    image: confluentinc/cp-kafka:7.4.0
    environment:
      - KAFKA_BROKER_ID=1
      - KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181
      - KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
      - KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1
      - KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1
      - KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
      
  zookeeper:
    image: confluentinc/cp-zookeeper:7.4.0
    environment:
      - ZOOKEEPER_CLIENT_PORT=2181
      - ZOOKEEPER_TICK_TIME=2000
    ports:
      - "2181:2181"

volumes:
  postgres_data:
```

**Start the stack:**

```bash
docker-compose up -d
```

**View logs:**

```bash
docker-compose logs -f nexum
```

---

## Common Scenarios

### Scenario 1: Microfinance Lender

Set up a microfinance operation with loan management and collections:

**1. Create customer with basic KYC:**

```bash
curl -X POST http://localhost:8090/customers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "first_name": "Maria",
    "last_name": "Rodriguez",
    "phone": "+1-555-0144",
    "address": {
      "line1": "123 Village Road",
      "city": "Sacramento", 
      "state": "CA",
      "postal_code": "95814",
      "country": "US"
    }
  }'

# Update KYC
curl -X PUT http://localhost:8090/customers/cust_maria/kyc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "status": "verified",
    "tier": "tier_1",
    "documents": ["national_id"]
  }'
```

**2. Create microloan with weekly payments:**

```bash
curl -X POST http://localhost:8090/loans \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_maria",
    "terms": {
      "principal_amount": {
        "amount": "5000.00",
        "currency": "USD"
      },
      "annual_interest_rate": "0.24",
      "term_months": 12,
      "payment_frequency": "weekly",
      "amortization_method": "equal_installment",
      "first_payment_date": "2024-02-26",
      "grace_period_days": 7,
      "late_fee": {
        "amount": "10.00", 
        "currency": "USD"
      }
    },
    "currency": "USD"
  }'
```

**3. Set up collections workflow for overdue payments:**

```bash
curl -X POST http://localhost:8090/collections/cases \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "loan_id": "loan_maria_001",
    "case_type": "overdue_payment",
    "priority": "medium",
    "assigned_collector": "collector_001"
  }'
```

### Scenario 2: Digital Wallet

Set up a digital wallet with instant transfers and compliance checks:

**1. Create wallet accounts:**

```bash
# Primary wallet account
curl -X POST http://localhost:8090/accounts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_wallet_user",
    "product_type": "checking",
    "currency": "USD",
    "name": "Digital Wallet",
    "daily_transaction_limit": {
      "amount": "2000.00",
      "currency": "USD"
    },
    "monthly_transaction_limit": {
      "amount": "10000.00",
      "currency": "USD"
    }
  }'
```

**2. Process instant P2P transfer:**

```bash
curl -X POST http://localhost:8090/transactions/transfer \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "from_account_id": "acc_sender_wallet",
    "to_account_id": "acc_recipient_wallet", 
    "amount": {
      "amount": "150.00",
      "currency": "USD"
    },
    "description": "Payment for dinner",
    "channel": "mobile",
    "reference": "P2P20240219001",
    "idempotency_key": "transfer_unique_key_001"
  }'
```

### Scenario 3: Credit Union Operations

Set up traditional credit union services with member accounts and loans:

**1. Create member with higher KYC requirements:**

```bash
curl -X PUT http://localhost:8090/customers/cust_member/kyc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "status": "verified",
    "tier": "tier_3",
    "documents": ["ssn", "drivers_license", "proof_of_income", "employment_verification"],
    "expiry_days": 365
  }'
```

**2. Create share savings and checking accounts:**

```bash
# Share savings (required for membership)
curl -X POST http://localhost:8090/accounts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_member",
    "product_type": "savings",
    "currency": "USD", 
    "name": "Share Savings",
    "interest_rate": "0.0125",
    "minimum_balance": {
      "amount": "25.00",
      "currency": "USD"
    }
  }'

# Checking account
curl -X POST http://localhost:8090/accounts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_member",
    "product_type": "checking",
    "currency": "USD",
    "name": "Primary Checking",
    "daily_transaction_limit": {
      "amount": "1000.00",
      "currency": "USD"
    }
  }'
```

**3. Create auto loan with competitive rates:**

```bash
curl -X POST http://localhost:8090/loans \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_member",
    "terms": {
      "principal_amount": {
        "amount": "35000.00",
        "currency": "USD"
      },
      "annual_interest_rate": "0.0425",
      "term_months": 72,
      "payment_frequency": "monthly",
      "amortization_method": "equal_installment", 
      "first_payment_date": "2024-03-19",
      "allow_prepayment": true,
      "prepayment_penalty_rate": null
    },
    "currency": "USD"
  }'
```

---

## Next Steps

Now that you have Nexum running and understand the basics:

**1. Explore the API Documentation**
- Interactive docs: http://localhost:8090/docs
- All 120+ endpoints with examples

**2. Configure Your Products**
- Create custom savings and loan products
- Set interest rates and fees
- Define transaction limits

**3. Set Up Workflows**
- Loan approval processes
- KYC verification workflows
- Collections procedures

**4. Enable Advanced Features**
- Multi-tenant deployment for multiple financial institutions
- PII encryption for compliance
- Event-driven integrations with Kafka

**5. Production Deployment**
- Read the [Security Guide](SECURITY.md) for hardening
- See [Best Practices](BEST_PRACTICES.md) for operational guidance
- Check [Deployment Guide](DEPLOYMENT.md) for scaling

**6. Custom Development**
- Use Nexum's modular architecture to build custom features
- Integrate with external systems using the event system
- Create custom compliance rules and reporting

For production deployment, see the [Security Guide](SECURITY.md) for hardening recommendations and the [Architecture Guide](architecture.md) for scaling considerations.