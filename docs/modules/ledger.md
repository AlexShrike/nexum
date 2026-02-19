# Ledger Module

The ledger module implements the double-entry bookkeeping engine, the foundation of all financial operations in Nexum. Every transaction creates balanced journal entries where total debits equal total credits, ensuring data integrity and providing a complete audit trail.

## Overview

Double-entry bookkeeping is the fundamental principle that ensures financial data integrity. Every transaction affects at least two accounts, with the total debits always equaling the total credits. This creates a self-balancing system where discrepancies are immediately detectable.

## Key Concepts

### Journal Entries
A journal entry represents a single business transaction and contains multiple lines that must balance. Each line affects one account with either a debit or credit.

### Account Types
The system supports standard accounting account types:

- **Asset**: Debit increases balance (cash, loans receivable)
- **Liability**: Credit increases balance (deposits, loans payable)
- **Equity**: Credit increases balance (capital, retained earnings)
- **Revenue**: Credit increases balance (interest income, fees)
- **Expense**: Debit increases balance (operating costs, loan losses)

### Immutability
Once posted, journal entries become immutable. Corrections are made through reversing entries, preserving the complete audit trail.

## Core Classes

### JournalEntry

Represents a complete double-entry transaction.

```python
from core_banking.ledger import JournalEntry, JournalEntryLine, JournalEntryState
from core_banking.currency import Money, Currency
from decimal import Decimal

# Create a deposit transaction
lines = [
    JournalEntryLine(
        account_id="cash_account",
        description="Customer deposit",
        debit_amount=Money(Decimal("1000.00"), Currency.USD),
        credit_amount=Money(Decimal("0"), Currency.USD)
    ),
    JournalEntryLine(
        account_id="customer_deposit_account",
        description="Customer deposit",
        debit_amount=Money(Decimal("0"), Currency.USD),
        credit_amount=Money(Decimal("1000.00"), Currency.USD)
    )
]

journal_entry = JournalEntry(
    reference="TXN_123",
    description="Customer deposit - John Doe",
    lines=lines,
    state=JournalEntryState.PENDING
)

# Validate that entry balances
journal_entry.validate_balance()  # Raises ValueError if unbalanced
```

### JournalEntryLine

Individual line within a journal entry affecting one account.

```python
from core_banking.ledger import JournalEntryLine

# Debit line (increases asset account)
debit_line = JournalEntryLine(
    account_id="checking_account_123",
    description="Wire transfer received",
    debit_amount=Money(Decimal("5000.00"), Currency.USD),
    credit_amount=Money(Decimal("0"), Currency.USD)
)

# Check properties
print(debit_line.is_debit)      # True
print(debit_line.is_credit)     # False
print(debit_line.amount)        # Money(5000.00, USD)
print(debit_line.currency)      # Currency.USD
```

### GeneralLedger

Main interface for ledger operations.

```python
from core_banking.ledger import GeneralLedger
from core_banking.storage import InMemoryStorage

# Initialize ledger with storage backend
storage = InMemoryStorage()
ledger = GeneralLedger(storage)

# Post journal entry
posted_entry = ledger.post_entry(journal_entry)
print(posted_entry.state)  # JournalEntryState.POSTED

# Calculate account balance
balance = ledger.get_account_balance("checking_account_123", Currency.USD)
print(balance)  # Money(5000.00, USD)
```

## Account Balance Calculation

Account balances are derived from journal entries, not stored as mutable values. This ensures data integrity and provides complete transaction history.

```python
# Balance calculation considers account type
def get_account_balance(account_id: str, currency: Currency) -> Money:
    # Get all journal entry lines for this account
    lines = get_lines_for_account(account_id, currency)
    
    # Sum based on account type
    if account_type in [AccountType.ASSET, AccountType.EXPENSE]:
        # Debit increases balance
        balance = sum(debits) - sum(credits)
    else:
        # Credit increases balance (LIABILITY, EQUITY, REVENUE)
        balance = sum(credits) - sum(debits)
    
    return balance
```

## Multi-Currency Support

The ledger supports transactions in multiple currencies within a single journal entry.

```python
# Multi-currency transfer (requires exchange rates)
lines = [
    # Debit USD cash account
    JournalEntryLine(
        account_id="cash_usd",
        description="FX conversion",
        debit_amount=Money(Decimal("1000.00"), Currency.USD),
        credit_amount=Money(Decimal("0"), Currency.USD)
    ),
    # Credit EUR cash account
    JournalEntryLine(
        account_id="cash_eur", 
        description="FX conversion",
        debit_amount=Money(Decimal("0"), Currency.EUR),
        credit_amount=Money(Decimal("850.00"), Currency.EUR)
    ),
    # FX gain/loss account
    JournalEntryLine(
        account_id="fx_gain_loss",
        description="FX conversion gain",
        debit_amount=Money(Decimal("0"), Currency.USD),
        credit_amount=Money(Decimal("15.00"), Currency.USD)
    )
]
```

## Chart of Accounts

The system maintains a chart of accounts with proper categorization.

```python
from core_banking.ledger import AccountType

# Create chart of accounts
chart_of_accounts = {
    # Assets
    "1000": {"name": "Cash", "type": AccountType.ASSET},
    "1100": {"name": "Customer Deposits", "type": AccountType.ASSET},
    "1200": {"name": "Loans Receivable", "type": AccountType.ASSET},
    
    # Liabilities  
    "2000": {"name": "Customer Accounts", "type": AccountType.LIABILITY},
    "2100": {"name": "Accrued Interest", "type": AccountType.LIABILITY},
    
    # Equity
    "3000": {"name": "Paid-in Capital", "type": AccountType.EQUITY},
    "3100": {"name": "Retained Earnings", "type": AccountType.EQUITY},
    
    # Revenue
    "4000": {"name": "Interest Income", "type": AccountType.REVENUE},
    "4100": {"name": "Fee Income", "type": AccountType.REVENUE},
    
    # Expenses
    "5000": {"name": "Interest Expense", "type": AccountType.EXPENSE},
    "5100": {"name": "Operating Expenses", "type": AccountType.EXPENSE}
}
```

## Transaction Examples

### Customer Deposit

```python
# Customer deposits $1,000 cash
def create_deposit_entry(customer_account_id: str, amount: Money) -> JournalEntry:
    return JournalEntry(
        reference=f"DEP_{uuid.uuid4().hex[:8]}",
        description=f"Customer deposit - {customer_account_id}",
        lines=[
            # Increase bank's cash (asset)
            JournalEntryLine(
                account_id="cash_account",
                description="Cash received",
                debit_amount=amount,
                credit_amount=Money(Decimal("0"), amount.currency)
            ),
            # Increase customer's deposit balance (liability to bank)
            JournalEntryLine(
                account_id=customer_account_id,
                description="Deposit credited",
                debit_amount=Money(Decimal("0"), amount.currency),
                credit_amount=amount
            )
        ],
        state=JournalEntryState.PENDING
    )
```

### Loan Disbursement

```python
# Disburse $10,000 loan to customer account
def create_loan_disbursement_entry(loan_account_id: str, customer_account_id: str, amount: Money) -> JournalEntry:
    return JournalEntry(
        reference=f"LOAN_{uuid.uuid4().hex[:8]}",
        description=f"Loan disbursement - {loan_account_id}",
        lines=[
            # Create loan receivable (asset to bank)
            JournalEntryLine(
                account_id=loan_account_id,
                description="Loan principal",
                debit_amount=amount,
                credit_amount=Money(Decimal("0"), amount.currency)
            ),
            # Credit customer's account (liability to bank)
            JournalEntryLine(
                account_id=customer_account_id,
                description="Loan proceeds",
                debit_amount=Money(Decimal("0"), amount.currency),
                credit_amount=amount
            )
        ],
        state=JournalEntryState.PENDING
    )
```

### Interest Accrual

```python
# Accrue $50 interest on loan
def create_interest_accrual_entry(loan_account_id: str, interest_amount: Money) -> JournalEntry:
    return JournalEntry(
        reference=f"INT_{uuid.uuid4().hex[:8]}",
        description=f"Interest accrual - {loan_account_id}",
        lines=[
            # Increase interest receivable (asset)
            JournalEntryLine(
                account_id=f"{loan_account_id}_interest",
                description="Accrued interest",
                debit_amount=interest_amount,
                credit_amount=Money(Decimal("0"), interest_amount.currency)
            ),
            # Recognize interest income (revenue)
            JournalEntryLine(
                account_id="interest_income",
                description="Interest earned",
                debit_amount=Money(Decimal("0"), interest_amount.currency),
                credit_amount=interest_amount
            )
        ],
        state=JournalEntryState.PENDING
    )
```

## Reversal Handling

Corrections are made through reversing entries, not by modifying existing entries.

```python
def reverse_entry(original_entry: JournalEntry, reason: str) -> JournalEntry:
    """Create a reversing entry that cancels the original"""
    
    # Create opposite lines
    reversed_lines = []
    for line in original_entry.lines:
        reversed_lines.append(
            JournalEntryLine(
                account_id=line.account_id,
                description=f"Reversal: {line.description}",
                # Swap debit and credit amounts
                debit_amount=line.credit_amount,
                credit_amount=line.debit_amount
            )
        )
    
    reversal = JournalEntry(
        reference=f"REV_{original_entry.reference}",
        description=f"Reversal: {reason}",
        lines=reversed_lines,
        state=JournalEntryState.PENDING,
        reverses=original_entry.id
    )
    
    return reversal
```

## Balance Inquiry Methods

```python
# Get current balance for an account
balance = ledger.get_account_balance("acc_123", Currency.USD)

# Get balance as of specific date
historical_balance = ledger.get_account_balance_as_of("acc_123", Currency.USD, date(2026, 1, 31))

# Get detailed transaction history
transactions = ledger.get_account_transactions("acc_123", 
                                             start_date=date(2026, 1, 1),
                                             end_date=date(2026, 1, 31))

# Get trial balance (all accounts)
trial_balance = ledger.get_trial_balance(Currency.USD, date(2026, 1, 31))
```

## Integration with Other Modules

The ledger integrates with all other financial modules:

### Transaction Processing
```python
from core_banking.transactions import TransactionProcessor

processor = TransactionProcessor(storage, ledger)

# Processor automatically creates appropriate journal entries
result = processor.process_deposit(account_id, amount, description)
print(result.journal_entry_id)  # Generated journal entry
```

### Interest Engine
```python
from core_banking.interest import InterestEngine

interest_engine = InterestEngine(storage, ledger)

# Interest calculations post to ledger
interest_engine.accrue_daily_interest(account_id)
```

## Data Integrity Features

### Hash-Chained Audit Trail
Journal entries are linked to the audit trail with cryptographic hashing:

```python
# Each entry creates audit events
audit_entry = AuditEntry(
    event_type=AuditEventType.JOURNAL_ENTRY_POSTED,
    entity_id=journal_entry.id,
    details={"reference": journal_entry.reference},
    previous_hash=get_last_audit_hash(),
    current_hash=calculate_hash(entry_data + previous_hash)
)
```

### Balance Validation
```python
def validate_ledger_integrity():
    """Validate that ledger is in balance"""
    
    # Check that all journal entries balance
    for entry in get_all_journal_entries():
        entry.validate_balance()
    
    # Verify trial balance sums to zero
    trial_balance = get_trial_balance()
    total_debits = sum(balance for balance in trial_balance if balance > 0)
    total_credits = sum(abs(balance) for balance in trial_balance if balance < 0)
    
    assert total_debits == total_credits, "Ledger out of balance!"
```

## Performance Considerations

### Indexed Queries
Account balance calculations use indexed queries for performance:

```sql
-- Database indexes for fast account lookups
CREATE INDEX idx_journal_lines_account_id ON journal_entry_lines(account_id);
CREATE INDEX idx_journal_lines_posted_at ON journal_entry_lines(posted_at);
CREATE INDEX idx_journal_entries_state ON journal_entries(state);
```

### Balance Caching
For high-volume accounts, consider caching calculated balances:

```python
class CachedLedger(GeneralLedger):
    def __init__(self, storage, cache):
        super().__init__(storage)
        self.cache = cache
    
    def get_account_balance(self, account_id: str, currency: Currency) -> Money:
        cache_key = f"balance:{account_id}:{currency.code}"
        
        # Try cache first
        cached_balance = self.cache.get(cache_key)
        if cached_balance:
            return cached_balance
        
        # Calculate and cache
        balance = super().get_account_balance(account_id, currency)
        self.cache.set(cache_key, balance, ttl=300)  # 5 minute TTL
        return balance
```

## Testing Double-Entry Logic

```python
def test_deposit_journal_entry():
    """Test that deposit creates proper journal entry"""
    
    ledger = GeneralLedger(InMemoryStorage())
    
    # Create deposit entry
    deposit_amount = Money(Decimal("1000.00"), Currency.USD)
    entry = create_deposit_entry("customer_acc_123", deposit_amount)
    
    # Post to ledger
    posted_entry = ledger.post_entry(entry)
    
    # Verify balances
    cash_balance = ledger.get_account_balance("cash_account", Currency.USD)
    customer_balance = ledger.get_account_balance("customer_acc_123", Currency.USD)
    
    assert cash_balance == deposit_amount
    assert customer_balance == deposit_amount
    assert posted_entry.state == JournalEntryState.POSTED

def test_journal_entry_must_balance():
    """Test that unbalanced entries are rejected"""
    
    lines = [
        JournalEntryLine(
            account_id="acc1",
            description="Test",
            debit_amount=Money(Decimal("100.00"), Currency.USD),
            credit_amount=Money(Decimal("0"), Currency.USD)
        ),
        JournalEntryLine(
            account_id="acc2", 
            description="Test",
            debit_amount=Money(Decimal("0"), Currency.USD),
            credit_amount=Money(Decimal("50.00"), Currency.USD)  # Unbalanced!
        )
    ]
    
    with pytest.raises(ValueError, match="Journal entry not balanced"):
        JournalEntry(
            reference="TEST",
            description="Unbalanced entry",
            lines=lines,
            state=JournalEntryState.PENDING
        )
```

The ledger module provides the foundation for all financial operations in Nexum, ensuring data integrity through double-entry bookkeeping principles while maintaining high performance and auditability.