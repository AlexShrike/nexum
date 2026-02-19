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
pip install -r requirements.txt
```

### 4. Start the Server

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

These provide a complete interactive interface to explore and test all 112 API endpoints.

## First Steps

### 1. Create a Customer

```bash
curl -X POST "http://localhost:8090/customers" \
  -H "Content-Type: application/json" \
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
collected 467 items

tests/test_accounts.py::test_create_account PASSED    [  1%]
tests/test_accounts.py::test_deposit PASSED          [  2%]
...
tests/test_workflows.py::test_workflow_completion PASSED [100%]

====================== 467 passed in 15.43s ======================
```

## Next Steps

Now that you have Nexum running:

1. **Explore the API**: Use the interactive docs at `/docs`
2. **Read Module Documentation**: Check `docs/modules/` for detailed guides
3. **Customize Products**: Configure your own banking products
4. **Set Up Workflows**: Define approval processes for your operations
5. **Configure Compliance**: Set up KYC and AML rules for your requirements

For production deployment, see the [Architecture Guide](architecture.md) for scaling and security considerations.