# Core Banking System

A production-grade core banking system with double-entry bookkeeping, proper financial math using Decimal precision, and comprehensive audit trails.

## 🏗️ Architecture

### Core Principles

1. **Double-Entry Bookkeeping**: Every transaction creates balanced journal entries (debits = credits)
2. **Decimal Precision**: All monetary calculations use `decimal.Decimal` - **NEVER** float
3. **Immutable Audit Trail**: Hash-chained SHA-256 audit log for tamper detection
4. **Balance Derivation**: Account balances derived from journal entries (source of truth)
5. **Idempotency**: All transaction endpoints support idempotency keys
6. **Comprehensive Testing**: Full test coverage for all financial calculations

### System Components

#### 1. **Ledger Engine** (`ledger.py`)
- Double-entry journal entries with automatic balancing validation
- Immutable entries once posted
- Support for pending/posted/reversed states
- Balance calculation from journal entries

#### 2. **Account Management** (`accounts.py`)
- Chart of accounts with proper account types (Asset, Liability, Equity, Revenue, Expense)
- Product types: Savings, Checking, Credit Lines, Loans
- Account holds and available balance calculations
- Multi-currency support

#### 3. **Customer Management** (`customers.py`)
- Customer profiles with KYC status tracking
- KYC tiers with transaction limits
- Beneficiary management
- Address and contact information

#### 4. **Transaction Processing** (`transactions.py`)
- Deposits, withdrawals, transfers, payments, fees
- Comprehensive compliance checking
- Automatic journal entry creation
- Reversal support (creates counter-entries)

#### 5. **Interest Engine** (`interest.py`)
- Daily interest accrual with multiple calculation methods
- Compound interest support
- Grace period logic for credit products
- Monthly interest posting

#### 6. **Credit Line Management** (`credit.py`)
- Revolving credit with grace periods
- Statement generation with proper payment allocation
- Minimum payment calculations
- Late fee handling

#### 7. **Loan Management** (`loans.py`)
- Loan origination and disbursement
- Amortization schedule generation (Equal Installment, Equal Principal, Bullet)
- Payment processing with proper principal/interest allocation
- Prepayment handling with optional penalties

#### 8. **Compliance Engine** (`compliance.py`)
- Transaction limits based on KYC tiers
- Large transaction reporting
- Suspicious activity detection
- Account freezes and holds

#### 9. **Audit Trail** (`audit.py`)
- Hash-chained immutable audit log
- Every state change logged
- Tamper detection with integrity verification
- Comprehensive audit queries

#### 10. **Multi-Currency Support** (`currency.py`)
- ISO 4217 currency codes
- Exchange rate management
- Proper decimal rounding per currency
- Currency conversion in transactions

#### 11. **Storage Layer** (`storage.py`)
- Abstract storage interface
- In-memory implementation (testing)
- SQLite implementation (persistence)
- All monetary values stored as Decimal strings

#### 12. **REST API** (`api.py`)
- FastAPI with comprehensive endpoints
- Customer CRUD + KYC management
- Account operations and balance inquiries
- Transaction processing
- Credit line and loan operations
- Audit log queries

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Virtual environment (recommended)

### Installation

```bash
# Clone or navigate to the project directory
cd /Users/alexshrike/.openclaw/workspace/core-banking

# Use the shared virtual environment
source /Users/alexshrike/.openclaw/workspace/rustcluster/.venv/bin/activate

# Install additional dependencies if needed
pip install fastapi uvicorn pytest

# Start the banking system
python run.py
```

The API will be available at:
- **API**: http://localhost:8090
- **Documentation**: http://localhost:8090/docs
- **ReDoc**: http://localhost:8090/redoc

## 📊 API Examples

### Create a Customer

```bash
curl -X POST "http://localhost:8090/customers" \
     -H "Content-Type: application/json" \
     -d '{
       "first_name": "John",
       "last_name": "Doe", 
       "email": "john.doe@example.com",
       "phone": "+1-555-123-4567"
     }'
```

### Create a Savings Account

```bash
curl -X POST "http://localhost:8090/accounts" \
     -H "Content-Type: application/json" \
     -d '{
       "customer_id": "CUSTOMER_ID_FROM_ABOVE",
       "product_type": "savings",
       "currency": "USD",
       "name": "Primary Savings Account",
       "minimum_balance": {"amount": "100.00", "currency": "USD"}
     }'
```

### Make a Deposit

```bash
curl -X POST "http://localhost:8090/transactions/deposit" \
     -H "Content-Type: application/json" \
     -d '{
       "account_id": "ACCOUNT_ID_FROM_ABOVE",
       "amount": {"amount": "1000.00", "currency": "USD"},
       "description": "Initial deposit",
       "channel": "online"
     }'
```

### Check Account Balance

```bash
curl -X GET "http://localhost:8090/accounts/ACCOUNT_ID"
```

## 🧪 Testing

The system includes comprehensive tests for all components:

```bash
# Run all tests
cd /Users/alexshrike/.openclaw/workspace/core-banking
python -m pytest tests/ -v

# Run specific test modules
python -m pytest tests/test_ledger.py -v
python -m pytest tests/test_accounts.py -v
python -m pytest tests/test_transactions.py -v
```

### Test Coverage

- **Ledger**: Double-entry validation, balance calculations, journal entry lifecycle
- **Accounts**: Account management, holds, balance calculations
- **Transactions**: All transaction types, reversals, idempotency
- **Interest**: Daily accrual, compound interest, grace periods
- **Credit**: Statement generation, grace period logic, minimum payments
- **Loans**: Amortization schedules, payment allocation, prepayments
- **Currency**: Decimal precision, rounding, multi-currency operations
- **Compliance**: Limits, suspicious activity detection
- **Audit**: Hash chain integrity, tamper detection
- **Integration**: End-to-end banking scenarios

## 🔐 Security Features

### Financial Security
- **Decimal Precision**: All monetary calculations use `decimal.Decimal`
- **Double-Entry Validation**: Automatic debit/credit balance checking
- **Immutable Entries**: Journal entries cannot be modified once posted
- **Balance Derivation**: Balances calculated from entries (no stored balances)

### Audit Security
- **Hash-Chained Logs**: SHA-256 hash chain prevents tampering
- **Complete Audit Trail**: Every state change logged with metadata
- **Integrity Verification**: Built-in tamper detection
- **Immutable History**: Audit events cannot be modified or deleted

### Operational Security
- **Idempotency**: Prevents duplicate transaction processing
- **Compliance Checking**: Automatic limit and rule enforcement
- **Suspicious Activity Detection**: Pattern-based fraud detection
- **Account Controls**: Freezing, holds, and state management

## 🏦 Banking Operations

### Account Types & Normal Balances

- **Assets** (Debit Normal): Checking, Savings accounts - customer deposits
- **Liabilities** (Credit Normal): Credit lines, Loans - customer owes bank
- **Equity** (Credit Normal): Bank capital accounts
- **Revenue** (Credit Normal): Fee income, Interest income
- **Expenses** (Debit Normal): Interest expense, Operating expenses

### Transaction Flow

1. **Create Transaction** → Pending state
2. **Compliance Check** → KYC limits, suspicious activity
3. **Account Validation** → Sufficient funds, account state
4. **Journal Entry Creation** → Balanced debit/credit entries
5. **Journal Entry Posting** → Immutable, affects balances
6. **Transaction Completion** → Updated account balances
7. **Audit Logging** → Immutable audit trail

### Interest Calculations

#### Savings/Checking (Asset Accounts)
- Interest **earned** on positive balances
- Credited to customer account (increases asset)
- Monthly posting of accrued interest

#### Credit Lines (Liability Accounts)  
- Interest **charged** on outstanding balances
- Grace period: No interest if paid in full by due date
- Cash advances: No grace period, immediate interest

#### Loans (Liability Accounts)
- Interest **charged** on principal balance
- Multiple amortization methods supported
- Prepayment options with optional penalties

## 📈 Performance Considerations

### Storage Optimization
- Efficient indexing on account IDs and timestamps
- Batch processing for interest calculations
- Connection pooling for database operations

### Memory Management
- Streaming for large result sets
- Proper cleanup of decimal contexts
- Efficient date/time handling

### Scalability Features
- Stateless API design
- Database abstraction layer
- Modular component architecture
- Background processing for maintenance tasks

## 🔧 Configuration

### Environment Variables
- `DB_PATH`: SQLite database path (default: `core_banking.db`)
- `API_HOST`: API host (default: `0.0.0.0`)
- `API_PORT`: API port (default: `8090`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

### System Accounts
The system uses internal accounts for external transactions:
- `EXT_DEP_001`: External deposit source
- `EXT_WITH_001`: External withdrawal destination  
- `FEE_INC_001`: Fee income account
- `INT_EXP_001`: Interest expense account
- `INT_INC_001`: Interest income account

## 📋 Compliance Features

### KYC Tiers & Limits
- **Tier 0** (No KYC): $100 daily, $1,000 monthly
- **Tier 1** (Basic KYC): $1,000 daily, $10,000 monthly
- **Tier 2** (Enhanced KYC): $10,000 daily, $100,000 monthly
- **Tier 3** (Full KYC): $100,000 daily, $1,000,000 monthly

### Suspicious Activity Detection
- Round dollar amounts (potential structuring)
- Transactions just below reporting thresholds
- High-velocity transactions
- Unusual amounts for customer profile
- Geographic anomalies

### Regulatory Reporting
- Large transaction reports (>$10,000)
- Suspicious activity reports (SARs)
- Currency transaction reports (CTRs)

## 🐛 Troubleshooting

### Common Issues

1. **Decimal Precision Errors**
   ```python
   # ❌ Wrong
   amount = Money(10.5, Currency.USD)
   
   # ✅ Correct  
   amount = Money(Decimal('10.50'), Currency.USD)
   ```

2. **Journal Entry Balance Errors**
   - Ensure total debits equal total credits
   - Check currency consistency across entry lines
   - Verify account types match debit/credit rules

3. **Transaction Failures**
   - Check account states (active, frozen, closed)
   - Verify sufficient available balance
   - Review compliance limit violations

### Debugging
- Enable detailed logging: Set `LOG_LEVEL=DEBUG`
- Check audit trail: `/audit/events` endpoint
- Verify integrity: `/audit/integrity` endpoint
- Review compliance alerts: `/compliance/alerts` endpoint

## 🤝 Contributing

### Code Standards
- All monetary values must use `decimal.Decimal`
- Double-entry bookkeeping rules must be enforced
- Comprehensive tests required for all financial calculations
- Proper error handling with descriptive messages
- Audit logging for all state changes

### Testing Requirements
- Unit tests for all modules
- Integration tests for end-to-end scenarios  
- Financial math verification tests
- Edge case testing (zero balances, negative amounts, etc.)
- Performance tests for large datasets

## 📜 License

This core banking system is built for educational and demonstration purposes. 
For production use, ensure compliance with local banking regulations and security requirements.

---

**⚠️ CRITICAL REMINDERS:**
- Always use `decimal.Decimal` for monetary calculations
- Never store account balances - derive from journal entries
- Every transaction must create balanced journal entries
- All state changes must be logged to audit trail
- Test all financial calculations thoroughly