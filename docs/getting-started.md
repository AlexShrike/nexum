# Getting Started with Nexum

This guide will walk you through setting up Nexum and making your first API calls.

## Prerequisites

- Python 3.14 or higher
- Git

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/AlexShrike/nexum
cd nexum
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# On macOS/Linux
source venv/bin/activate

# On Windows
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
poetry install
```

### 4. Configure Environment Variables (Optional)

Nexum supports extensive configuration via environment variables with the `NEXUM_` prefix:

#### Database Configuration

```bash
# PostgreSQL (production recommended)
export NEXUM_DATABASE_URL="postgresql://user:password@localhost:5432/nexum"

# SQLite (default - good for development)
export NEXUM_DATABASE_URL="sqlite:///nexum.db"

# In-memory (testing only)
export NEXUM_DATABASE_URL="sqlite:///:memory:"
```

#### Security Configuration

```bash
# JWT authentication (required for production)
export NEXUM_JWT_SECRET="your-256-bit-secret-key-change-in-production"
export NEXUM_JWT_EXPIRY_HOURS="24"

# Password security
export NEXUM_PASSWORD_MIN_LENGTH="8"
```

#### API Configuration

```bash
export NEXUM_API_HOST="0.0.0.0"
export NEXUM_API_PORT="8090"
export NEXUM_API_WORKERS="4"
export NEXUM_ENABLE_RATE_LIMITING="true"
```

#### Kafka Integration (Optional)

```bash
export NEXUM_KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
export NEXUM_KAFKA_TOPIC_PREFIX="nexum"
export NEXUM_ENABLE_KAFKA_EVENTS="true"
```

#### Logging Configuration

```bash
export NEXUM_LOG_LEVEL="INFO"
export NEXUM_LOG_FORMAT="json"  # or "text"
export NEXUM_LOG_FILE="/var/log/nexum/app.log"  # optional, defaults to stdout
```

#### PII Encryption Configuration (Phase 2)

```bash
# Enable PII encryption at rest
export NEXUM_ENCRYPTION_ENABLED="true"

# Choose encryption provider (aesgcm recommended for new deployments)
export NEXUM_ENCRYPTION_PROVIDER="aesgcm"  # or "fernet" or "noop"

# 256-bit master key for encryption (keep this secret and backed up!)
export NEXUM_ENCRYPTION_MASTER_KEY="your-256-bit-encryption-master-key-change-in-production"

# Optional: Custom salt for key derivation (Fernet only)
export NEXUM_ENCRYPTION_SALT="custom-salt-for-key-derivation"
```

**Important Security Notes:**
- The master key is used to encrypt all PII data (customer names, emails, phone numbers, etc.)
- Store the master key securely (HSM, key vault, or encrypted config)
- Never commit the master key to version control
- If you lose the master key, encrypted data cannot be recovered
- Use `cryptography` library: `poetry install -E encryption`

#### Multi-Tenancy Configuration (Phase 2)

```bash
# Enable multi-tenant support
export NEXUM_MULTI_TENANT="true"

# Tenant isolation strategy
export NEXUM_TENANT_ISOLATION="shared_table"  # or "schema_per_tenant" or "database_per_tenant"

# Default subscription tier for new tenants
export NEXUM_DEFAULT_SUBSCRIPTION_TIER="free"  # or "basic", "professional", "enterprise"
```

**Tenant Context:**
- Tenants are identified via `X-Tenant-ID` header in API requests
- Each tenant gets isolated data within the same deployment
- Supports subdomain-based tenant detection (e.g., `acme.nexum.io`)
- JWT tokens can include tenant claims for automatic context switching

#### Notification Engine Configuration (Phase 2)

```bash
# SMTP configuration for email notifications
export NEXUM_SMTP_HOST="smtp.gmail.com"
export NEXUM_SMTP_PORT="587"
export NEXUM_SMTP_USERNAME="your-email@company.com"
export NEXUM_SMTP_PASSWORD="your-app-password"
export NEXUM_SMTP_USE_TLS="true"

# SMS configuration (Twilio)
export NEXUM_TWILIO_ACCOUNT_SID="your-twilio-account-sid"
export NEXUM_TWILIO_AUTH_TOKEN="your-twilio-auth-token"
export NEXUM_TWILIO_FROM_NUMBER="+1234567890"

# Webhook configuration
export NEXUM_WEBHOOK_DEFAULT_URL="https://your-app.com/webhooks/nexum"
export NEXUM_WEBHOOK_TIMEOUT="30"

# Push notification configuration (Firebase)
export NEXUM_FIREBASE_SERVER_KEY="your-firebase-server-key"
export NEXUM_FIREBASE_PROJECT_ID="your-firebase-project-id"
```

### 5. PostgreSQL Setup (Production Recommended)

For production deployments, PostgreSQL is recommended for its JSONB support and ACID guarantees.

#### Install PostgreSQL

```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# macOS
brew install postgresql

# Start PostgreSQL service
sudo service postgresql start  # Linux
brew services start postgresql  # macOS
```

#### Create Database

```bash
sudo -u postgres psql

CREATE DATABASE nexum;
CREATE USER nexum_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE nexum TO nexum_user;
\q
```

#### Configure Connection

```bash
export NEXUM_DATABASE_URL="postgresql://nexum_user:your_secure_password@localhost:5432/nexum"
```

#### Install PostgreSQL Driver

```bash
poetry install -E postgres
```

### 6. Database Migrations

Nexum includes a built-in migration system with 8 migrations (v001-v008):

#### Auto-Migration (Default)

Migrations run automatically on startup when `NEXUM_AUTO_MIGRATE=true` (default).

#### Manual Migration

```bash
# Check current version
python -c "
from core_banking.storage import PostgreSQLStorage
from core_banking.migrations import MigrationManager
from core_banking.config import get_config

config = get_config()
storage = PostgreSQLStorage(config.database_url)
mm = MigrationManager(storage)
print(f'Current version: {mm.get_current_version()}')
print(f'Available versions: {[m.version for m in mm.migrations]}')
"

# Apply all pending migrations
python -c "
from core_banking.storage import PostgreSQLStorage
from core_banking.migrations import MigrationManager  
from core_banking.config import get_config

config = get_config()
storage = PostgreSQLStorage(config.database_url)
mm = MigrationManager(storage)
applied = mm.migrate_up()
for migration in applied:
    print(f'Applied: {migration}')
"
```

### 7. Start the Server

```bash
python run.py
```

The server will start on `http://localhost:8090`. You should see output like:

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8090 (Press CTRL+C to quit)
```

### 5. Verify Installation

Test the health endpoint:

```bash
curl http://localhost:8090/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-19T15:32:00.000000",
  "version": "1.0.0"
}
```

## API Documentation

Once the server is running, visit:

- **Interactive API Docs**: http://localhost:8090/docs
- **Alternative API Docs**: http://localhost:8090/redoc

These provide a complete interactive interface to explore and test all 120 API endpoints.

## Authentication Setup

Nexum uses JWT (JSON Web Token) authentication for secure API access.

### Enable Authentication

Set the JWT secret (required for production):

```bash
export NEXUM_JWT_SECRET="your-256-bit-secret-key-change-in-production"
```

### Get JWT Token

First, you'll need to create a user and login to get a token:

```bash
# Create admin user (via API - this creates the first user)
curl -X POST "http://localhost:8090/auth/setup" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "secure_password_123",
    "email": "admin@example.com",
    "full_name": "Administrator"
  }'
```

```bash
# Login to get JWT token
curl -X POST "http://localhost:8090/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "secure_password_123"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "session_id": "sess_abc123def456",
  "expires_at": "2026-02-20T15:32:00.000000",
  "message": "Login successful"
}
```

### Using JWT Token

Include the token in the `Authorization` header for all API requests:

```bash
# Set token as environment variable
export JWT_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Use token in requests
curl -X GET "http://localhost:8090/customers" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Token Expiry and Refresh

Tokens expire after 24 hours by default (configurable via `NEXUM_JWT_EXPIRY_HOURS`). 
When a token expires, you'll receive a 401 Unauthorized response and need to login again.

## Docker Setup (Optional)

For containerized deployment:

### Dockerfile

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies  
COPY pyproject.toml poetry.lock .
RUN pip install poetry && poetry install --no-root

# Copy application code
COPY . .

# Expose port
EXPOSE 8090

# Run migrations and start server
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
      - NEXUM_DATABASE_URL=postgresql://nexum:password@postgres:5432/nexum
      - NEXUM_JWT_SECRET=your-secret-key-change-in-production
      - NEXUM_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    depends_on:
      - postgres
      - kafka
      
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=nexum
      - POSTGRES_USER=nexum
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
      
  kafka:
    image: confluentinc/cp-kafka:latest
    environment:
      - KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181
      - KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
      - KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1
    depends_on:
      - zookeeper
      
  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    environment:
      - ZOOKEEPER_CLIENT_PORT=2181

volumes:
  postgres_data:
```

Run with:
```bash
docker-compose up -d
```

## First Steps

**Note**: All examples below assume JWT authentication is enabled. Include the Authorization header in all requests:

```bash
export JWT_TOKEN="your_jwt_token_here"
```

### 1. Create a Customer

```bash
curl -X POST "http://localhost:8090/customers" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "phone": "+1-555-0123",
    "date_of_birth": "1990-01-15",
    "address": {
      "line1": "123 Main Street",
      "city": "Anytown",
      "state": "CA",
      "postal_code": "12345",
      "country": "US"
    }
  }'
```

Response:
```json
{
  "customer_id": "cust_abc123def456",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "phone": "+1-555-0123",
  "date_of_birth": "1990-01-15",
  "kyc_status": "none",
  "kyc_tier": "tier_0",
  "created_at": "2026-02-19T15:32:00.000000",
  "updated_at": "2026-02-19T15:32:00.000000"
}
```

### 2. Update KYC Status

Before creating accounts, update the customer's KYC status:

```bash
curl -X PUT "http://localhost:8090/customers/cust_abc123def456/kyc" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "status": "verified",
    "tier": "tier_2",
    "documents": ["drivers_license", "proof_of_address"],
    "expiry_days": 365
  }'
```

### 3. Create a Savings Account

```bash
curl -X POST "http://localhost:8090/accounts" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123def456",
    "product_type": "savings",
    "currency": "USD",
    "name": "Primary Savings",
    "interest_rate": "0.025",
    "minimum_balance": {
      "amount": "100.00",
      "currency": "USD"
    }
  }'
```

Response:
```json
{
  "account_id": "acc_xyz789ghi012",
  "customer_id": "cust_abc123def456",
  "product_type": "savings",
  "account_number": "1001234567",
  "currency": "USD",
  "name": "Primary Savings",
  "status": "active",
  "balance": {
    "amount": "0.00",
    "currency": "USD"
  },
  "available_balance": {
    "amount": "0.00",
    "currency": "USD"
  },
  "interest_rate": "0.025",
  "minimum_balance": {
    "amount": "100.00",
    "currency": "USD"
  },
  "created_at": "2026-02-19T15:35:00.000000"
}
```

### 4. Make a Deposit

```bash
curl -X POST "http://localhost:8090/transactions/deposit" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "acc_xyz789ghi012",
    "amount": {
      "amount": "1000.00",
      "currency": "USD"
    },
    "description": "Initial deposit",
    "channel": "online",
    "reference": "DEP001"
  }'
```

Response:
```json
{
  "transaction_id": "txn_def456jkl789",
  "transaction_type": "deposit",
  "account_id": "acc_xyz789ghi012",
  "amount": {
    "amount": "1000.00",
    "currency": "USD"
  },
  "description": "Initial deposit",
  "channel": "online",
  "reference": "DEP001",
  "status": "completed",
  "created_at": "2026-02-19T15:36:00.000000",
  "processed_at": "2026-02-19T15:36:00.000000"
}
```

### 5. Check Account Balance

```bash
curl "http://localhost:8090/accounts/acc_xyz789ghi012/balance"
```

Response:
```json
{
  "account_id": "acc_xyz789ghi012",
  "balance": {
    "amount": "1000.00",
    "currency": "USD"
  },
  "available_balance": {
    "amount": "900.00",
    "currency": "USD"
  },
  "holds": [
    {
      "amount": {
        "amount": "100.00",
        "currency": "USD"
      },
      "reason": "minimum_balance_hold",
      "created_at": "2026-02-19T15:36:00.000000"
    }
  ],
  "as_of": "2026-02-19T15:37:00.000000"
}
```

### 6. Create a Transfer

First, create another account:

```bash
curl -X POST "http://localhost:8090/accounts" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123def456",
    "product_type": "checking",
    "currency": "USD",
    "name": "Primary Checking"
  }'
```

Then transfer funds:

```bash
curl -X POST "http://localhost:8090/transactions/transfer" \
  -H "Content-Type: application/json" \
  -d '{
    "from_account_id": "acc_xyz789ghi012",
    "to_account_id": "acc_new_account_id",
    "amount": {
      "amount": "200.00",
      "currency": "USD"
    },
    "description": "Transfer to checking",
    "channel": "online",
    "reference": "TRF001"
  }'
```

## Working with Products

### Create a Custom Savings Product

```bash
curl -X POST "http://localhost:8090/products" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High Yield Savings",
    "description": "Premium savings account with higher interest rate",
    "product_type": "savings",
    "currency": "USD",
    "product_code": "HYS001",
    "interest_rate": "0.045"
  }'
```

### Create Account with Custom Product

```bash
curl -X POST "http://localhost:8090/accounts" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123def456",
    "product_type": "savings",
    "currency": "USD",
    "name": "High Yield Savings Account",
    "interest_rate": "0.045"
  }'
```

## Working with Credit Lines

### Create a Credit Line

```bash
curl -X POST "http://localhost:8090/accounts" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123def456",
    "product_type": "credit_line",
    "currency": "USD",
    "name": "Personal Line of Credit",
    "credit_limit": {
      "amount": "5000.00",
      "currency": "USD"
    },
    "interest_rate": "0.18"
  }'
```

### Make a Credit Draw

```bash
curl -X POST "http://localhost:8090/credit/acc_credit_id/draw" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": {
      "amount": "500.00",
      "currency": "USD"
    },
    "description": "Cash advance"
  }'
```

## Working with Loans

### Create a Loan

```bash
curl -X POST "http://localhost:8090/loans" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_abc123def456",
    "terms": {
      "principal_amount": {
        "amount": "10000.00",
        "currency": "USD"
      },
      "annual_interest_rate": "0.06",
      "term_months": 36,
      "payment_frequency": "monthly",
      "amortization_method": "equal_installment",
      "first_payment_date": "2026-03-19",
      "allow_prepayment": true,
      "grace_period_days": 10,
      "late_fee": {
        "amount": "25.00",
        "currency": "USD"
      }
    },
    "currency": "USD"
  }'
```

### Get Loan Payment Schedule

```bash
curl "http://localhost:8090/loans/loan_id/schedule"
```

### Make a Loan Payment

```bash
curl -X POST "http://localhost:8090/loans/loan_id/payment" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": {
      "amount": "304.22",
      "currency": "USD"
    },
    "payment_date": "2026-03-19",
    "source_account_id": "acc_xyz789ghi012"
  }'
```

## Interest Calculations

### Calculate Interest for Account

```bash
curl -X POST "http://localhost:8090/interest/calculate" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "acc_xyz789ghi012",
    "calculation_date": "2026-02-19"
  }'
```

### Post Interest to Account

```bash
curl -X POST "http://localhost:8090/interest/post" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "acc_xyz789ghi012",
    "calculation_date": "2026-02-19"
  }'
```

## Reporting

### Get Account Statement

```bash
curl "http://localhost:8090/reports/account-statement?account_id=acc_xyz789ghi012&start_date=2026-01-01&end_date=2026-02-19"
```

### Get Transaction History

```bash
curl "http://localhost:8090/reports/transaction-history?account_id=acc_xyz789ghi012&limit=10"
```

## Error Handling

Nexum uses standard HTTP status codes and provides detailed error messages:

### Example Error Response

```bash
curl -X POST "http://localhost:8090/transactions/deposit" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "invalid_account",
    "amount": {
      "amount": "100.00",
      "currency": "USD"
    },
    "description": "Test deposit"
  }'
```

Response (400 Bad Request):
```json
{
  "detail": "Account not found: invalid_account",
  "error_code": "ACCOUNT_NOT_FOUND",
  "timestamp": "2026-02-19T15:40:00.000000"
}
```

### Common Error Codes

- `ACCOUNT_NOT_FOUND` - Account ID does not exist
- `CUSTOMER_NOT_FOUND` - Customer ID does not exist
- `INSUFFICIENT_FUNDS` - Account balance too low
- `COMPLIANCE_VIOLATION` - Transaction violates compliance rules
- `INVALID_AMOUNT` - Amount must be positive
- `CURRENCY_MISMATCH` - Transaction currency doesn't match account
- `KYC_REQUIRED` - Customer needs KYC verification

## Configuration

### Environment Variables

```bash
export NEXUM_PORT=8090
export NEXUM_HOST=0.0.0.0
export NEXUM_DEBUG=False
export NEXUM_DATABASE_URL=sqlite:///nexum.db
```

### Development Mode

For development with auto-reload:

```bash
uvicorn core_banking.api:app --reload --port 8090
```

## Testing Your Setup

Run the complete test suite to verify everything is working:

```bash
python -m pytest tests/ -v
```

Expected output:
```
====================== test session starts ======================
collected 514 items

tests/test_accounts.py::test_create_account PASSED    [  1%]
tests/test_accounts.py::test_deposit PASSED          [  2%]
...
tests/test_workflows.py::test_workflow_completion PASSED [100%]

====================== 514 passed in 18.27s ======================
```

## Next Steps

Now that you have Nexum running:

1. **Explore the API**: Use the interactive docs at `/docs`
2. **Read Module Documentation**: Check `docs/modules/` for detailed guides
3. **Customize Products**: Configure your own banking products
4. **Set Up Workflows**: Define approval processes for your operations
5. **Configure Compliance**: Set up KYC and AML rules for your requirements

For production deployment, see the [Architecture Guide](architecture.md) for scaling and security considerations.