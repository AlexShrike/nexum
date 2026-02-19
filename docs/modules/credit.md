# Credit Lines Module

The credit lines module manages revolving credit accounts with sophisticated grace period logic, statement generation, minimum payment calculations, and late payment handling. It provides the foundation for credit card accounts, personal lines of credit, and other revolving credit products.

## Overview

Credit lines differ from traditional loans in that they provide revolving credit where customers can borrow, repay, and borrow again up to their credit limit. Key features include:

- **Revolving Credit**: Borrow and repay repeatedly within credit limits
- **Grace Periods**: Interest-free periods for purchases when paid in full
- **Statement Cycles**: Monthly statements with payment due dates
- **Minimum Payments**: Calculated minimum payment requirements
- **Transaction Categories**: Different treatment for purchases, cash advances, and fees

## Key Concepts

### Grace Periods
Grace periods provide interest-free financing for purchases when the previous balance is paid in full by the due date. Cash advances and balance transfers typically don't qualify for grace periods.

### Statement Cycles
Credit lines generate monthly statements showing:
- Previous balance
- New charges during the period
- Payments and credits applied
- Interest and fees charged
- Current balance and minimum payment due

### Transaction Categories
Different transaction types receive different treatment:

- **PURCHASE**: Regular purchases (eligible for grace periods)
- **CASH_ADVANCE**: Cash advances (immediate interest)
- **BALANCE_TRANSFER**: Transfers from other accounts
- **FEE**: Account fees (late fees, over-limit fees)
- **PAYMENT**: Payments toward balance
- **INTEREST**: Interest charges
- **REVERSAL**: Transaction corrections

## Core Classes

### CreditStatement

Represents a monthly credit statement:

```python
from core_banking.credit import CreditStatement, StatementStatus
from core_banking.currency import Money, Currency
from datetime import date
from decimal import Decimal

# Create monthly statement
statement = CreditStatement(
    account_id="cc_123456",
    statement_date=date(2026, 2, 1),
    due_date=date(2026, 2, 25),  # 25-day grace period
    
    # Balance breakdown
    previous_balance=Money(Decimal("1500.00"), Currency.USD),
    new_charges=Money(Decimal("250.00"), Currency.USD),
    payments_credits=Money(Decimal("500.00"), Currency.USD),
    interest_charged=Money(Decimal("24.66"), Currency.USD),
    fees_charged=Money(Decimal("0.00"), Currency.USD),
    current_balance=Money(Decimal("1274.66"), Currency.USD),
    
    # Payment information
    minimum_payment_due=Money(Decimal("35.00"), Currency.USD),
    available_credit=Money(Decimal("3725.34"), Currency.USD),
    credit_limit=Money(Decimal("5000.00"), Currency.USD),
    
    # Grace period status
    grace_period_active=True,
    status=StatementStatus.CURRENT
)

# Check statement status
print(statement.is_overdue)      # False (not past due date)
print(statement.days_overdue)    # 0 (current)
```

### CreditTransaction

Individual transaction on a credit line:

```python
from core_banking.credit import CreditTransaction, TransactionCategory

@dataclass
class CreditTransaction(StorageRecord):
    account_id: str
    transaction_date: date
    post_date: date
    category: TransactionCategory
    amount: Money
    description: str
    merchant: Optional[str] = None
    
    # Grace period tracking
    eligible_for_grace: bool = True
    grace_period_applied: bool = False
    
    # Interest tracking
    interest_from_date: Optional[date] = None
    daily_interest_accrued: Money = None

# Create purchase transaction
purchase = CreditTransaction(
    account_id="cc_123456",
    transaction_date=date(2026, 2, 15),
    post_date=date(2026, 2, 15),
    category=TransactionCategory.PURCHASE,
    amount=Money(Decimal("89.99"), Currency.USD),
    description="Online purchase - Amazon",
    merchant="Amazon.com",
    eligible_for_grace=True  # Purchases eligible for grace period
)
```

### CreditLineManager

Main interface for credit line operations:

```python
from core_banking.credit import CreditLineManager

class CreditLineManager:
    def __init__(self, storage: StorageInterface, account_manager: AccountManager):
        self.storage = storage
        self.account_manager = account_manager
    
    def create_credit_line(
        self,
        customer_id: str,
        credit_limit: Money,
        annual_interest_rate: Decimal,
        grace_period_days: int = 25
    ) -> Account:
        """Create new credit line account"""
        
        account = self.account_manager.create_account(
            customer_id=customer_id,
            product_type=ProductType.CREDIT_LINE,
            currency=credit_limit.currency,
            name="Credit Line",
            credit_limit=credit_limit,
            interest_rate=annual_interest_rate
        )
        
        # Initialize credit line settings
        account.settings.update({
            "grace_period_days": grace_period_days,
            "statement_cycle_day": 1,  # Generate statements on 1st of month
            "minimum_payment_percentage": Decimal("0.02"),  # 2%
            "minimum_payment_amount": Money(Decimal("25.00"), credit_limit.currency),
            "cash_advance_fee": Decimal("0.03"),  # 3% or $10, whichever is greater
            "overlimit_fee": Money(Decimal("35.00"), credit_limit.currency)
        })
        
        return account
```

## Transaction Processing

### Making Purchases

```python
def process_purchase(
    account_id: str,
    amount: Money,
    description: str,
    merchant: Optional[str] = None,
    transaction_date: Optional[date] = None
) -> CreditTransaction:
    """Process purchase transaction"""
    
    account = self.account_manager.get_account(account_id)
    
    if transaction_date is None:
        transaction_date = date.today()
    
    # Check credit limit
    current_balance = account.balance
    available_credit = account.credit_limit - current_balance
    
    if amount > available_credit:
        # Assess over-limit fee if configured
        overlimit_fee = account.settings.get("overlimit_fee")
        if overlimit_fee:
            self.assess_fee(account_id, overlimit_fee, "Over-limit fee")
    
    # Create purchase transaction
    transaction = CreditTransaction(
        account_id=account_id,
        transaction_date=transaction_date,
        post_date=transaction_date,
        category=TransactionCategory.PURCHASE,
        amount=amount,
        description=description,
        merchant=merchant,
        eligible_for_grace=True,  # Purchases eligible for grace period
        interest_from_date=None   # Interest starts later if no grace period
    )
    
    # Process the transaction
    self.transaction_processor.process_transaction(
        account_id=account_id,
        transaction_type=TransactionType.CHARGE,
        amount=amount,
        description=description,
        channel=TransactionChannel.MERCHANT
    )
    
    # Determine if grace period applies
    if self.has_active_grace_period(account_id):
        transaction.grace_period_applied = True
        # Interest starts after statement due date if not paid in full
        current_statement = self.get_current_statement(account_id)
        transaction.interest_from_date = current_statement.due_date
    else:
        # No grace period - interest starts immediately
        transaction.interest_from_date = transaction_date
    
    self.storage.store(transaction)
    return transaction
```

### Cash Advances

Cash advances are treated differently - they don't qualify for grace periods:

```python
def process_cash_advance(
    account_id: str,
    amount: Money,
    fee_percentage: Decimal = Decimal("0.03"),
    minimum_fee: Money = Money(Decimal("10.00"), Currency.USD)
) -> Tuple[CreditTransaction, CreditTransaction]:
    """Process cash advance with immediate interest and fees"""
    
    # Calculate cash advance fee
    fee_amount = max(amount * fee_percentage, minimum_fee)
    
    # Create cash advance transaction
    advance_transaction = CreditTransaction(
        account_id=account_id,
        transaction_date=date.today(),
        post_date=date.today(),
        category=TransactionCategory.CASH_ADVANCE,
        amount=amount,
        description="Cash advance",
        eligible_for_grace=False,  # No grace period
        interest_from_date=date.today()  # Interest starts immediately
    )
    
    # Create fee transaction
    fee_transaction = CreditTransaction(
        account_id=account_id,
        transaction_date=date.today(),
        post_date=date.today(),
        category=TransactionCategory.FEE,
        amount=fee_amount,
        description="Cash advance fee",
        eligible_for_grace=False,
        interest_from_date=date.today()
    )
    
    # Process both transactions
    self.transaction_processor.process_transaction(
        account_id=account_id,
        transaction_type=TransactionType.CASH_ADVANCE,
        amount=amount,
        description="Cash advance"
    )
    
    self.transaction_processor.process_transaction(
        account_id=account_id,
        transaction_type=TransactionType.FEE,
        amount=fee_amount,
        description="Cash advance fee"
    )
    
    self.storage.store(advance_transaction)
    self.storage.store(fee_transaction)
    
    return advance_transaction, fee_transaction
```

## Grace Period Logic

Grace periods are one of the most complex aspects of credit line management:

```python
class GracePeriodTracker:
    """Tracks grace period eligibility and application"""
    
    def has_active_grace_period(self, account_id: str) -> bool:
        """Check if account has active grace period for new purchases"""
        
        # Grace period is active if:
        # 1. Previous statement was paid in full by due date
        # 2. No cash advances or balance transfers in current cycle
        # 3. Account has grace period configured
        
        account = self.account_manager.get_account(account_id)
        grace_days = account.settings.get("grace_period_days", 0)
        
        if grace_days == 0:
            return False
        
        # Check previous statement payment status
        previous_statement = self.get_previous_statement(account_id)
        if not previous_statement:
            return True  # First statement cycle
        
        # Must have paid previous balance in full
        if not self.was_paid_in_full_by_due_date(previous_statement):
            return False
        
        # Check for grace-period-killing transactions
        current_transactions = self.get_current_cycle_transactions(account_id)
        
        for transaction in current_transactions:
            if transaction.category in [TransactionCategory.CASH_ADVANCE, 
                                      TransactionCategory.BALANCE_TRANSFER]:
                return False
        
        return True
    
    def was_paid_in_full_by_due_date(self, statement: CreditStatement) -> bool:
        """Check if statement was paid in full by due date"""
        
        if not statement.paid_date:
            return False
        
        return (statement.paid_date <= statement.due_date and 
                statement.paid_amount >= statement.current_balance)
```

## Statement Generation

Monthly statements are generated on a cycle date:

```python
def generate_monthly_statement(
    account_id: str,
    statement_date: date,
    cycle_start_date: date
) -> CreditStatement:
    """Generate monthly credit statement"""
    
    account = self.account_manager.get_account(account_id)
    previous_statement = self.get_previous_statement(account_id)
    
    # Get transactions for this cycle
    cycle_transactions = self.get_transactions_for_cycle(
        account_id, cycle_start_date, statement_date
    )
    
    # Calculate statement components
    previous_balance = previous_statement.current_balance if previous_statement else Money(Decimal("0"), account.currency)
    
    new_charges = sum(
        t.amount for t in cycle_transactions 
        if t.category in [TransactionCategory.PURCHASE, 
                         TransactionCategory.CASH_ADVANCE,
                         TransactionCategory.BALANCE_TRANSFER]
    )
    
    payments_credits = sum(
        t.amount for t in cycle_transactions 
        if t.category == TransactionCategory.PAYMENT
    )
    
    interest_charged = sum(
        t.amount for t in cycle_transactions 
        if t.category == TransactionCategory.INTEREST
    )
    
    fees_charged = sum(
        t.amount for t in cycle_transactions 
        if t.category == TransactionCategory.FEE
    )
    
    current_balance = (previous_balance + new_charges + 
                      interest_charged + fees_charged - payments_credits)
    
    # Calculate minimum payment
    minimum_payment = self.calculate_minimum_payment(account, current_balance)
    
    # Calculate due date (typically 25 days from statement date)
    grace_period_days = account.settings.get("grace_period_days", 25)
    due_date = statement_date + timedelta(days=grace_period_days)
    
    # Determine grace period status
    grace_period_active = self.has_active_grace_period(account_id)
    
    statement = CreditStatement(
        account_id=account_id,
        statement_date=statement_date,
        due_date=due_date,
        previous_balance=previous_balance,
        new_charges=new_charges,
        payments_credits=payments_credits,
        interest_charged=interest_charged,
        fees_charged=fees_charged,
        current_balance=current_balance,
        minimum_payment_due=minimum_payment,
        available_credit=account.credit_limit - current_balance,
        credit_limit=account.credit_limit,
        grace_period_active=grace_period_active,
        status=StatementStatus.CURRENT
    )
    
    self.storage.store(statement)
    
    # Update account next statement date
    next_statement_date = self.calculate_next_statement_date(statement_date)
    account.settings["next_statement_date"] = next_statement_date.isoformat()
    self.account_manager.update_account(account_id, account)
    
    return statement
```

## Minimum Payment Calculation

Minimum payments are calculated based on various factors:

```python
def calculate_minimum_payment(
    account: Account,
    current_balance: Money
) -> Money:
    """Calculate minimum payment due"""
    
    if current_balance.is_zero():
        return Money(Decimal("0"), current_balance.currency)
    
    # Get minimum payment settings
    min_percentage = account.settings.get("minimum_payment_percentage", Decimal("0.02"))
    min_amount = account.settings.get("minimum_payment_amount", 
                                     Money(Decimal("25.00"), current_balance.currency))
    
    # Calculate percentage-based minimum
    percentage_payment = current_balance * min_percentage
    
    # Take the greater of percentage or minimum amount
    calculated_minimum = max(percentage_payment, min_amount)
    
    # But never more than the current balance
    minimum_payment = min(calculated_minimum, current_balance)
    
    return minimum_payment

# Enhanced minimum payment with past due amounts
def calculate_minimum_payment_with_past_due(
    account: Account,
    current_statement: CreditStatement,
    previous_statements: List[CreditStatement]
) -> Money:
    """Calculate minimum payment including past due amounts"""
    
    base_minimum = self.calculate_minimum_payment(account, current_statement.current_balance)
    
    # Add any past due amounts
    past_due_amount = Money(Decimal("0"), base_minimum.currency)
    
    for statement in previous_statements:
        if statement.is_overdue:
            unpaid_minimum = statement.minimum_payment_due - statement.paid_amount
            if unpaid_minimum > Money(Decimal("0"), base_minimum.currency):
                past_due_amount += unpaid_minimum
    
    return base_minimum + past_due_amount
```

## Payment Processing

Credit line payments are allocated in a specific order:

```python
def process_payment(
    account_id: str,
    payment_amount: Money,
    payment_date: Optional[date] = None
) -> CreditPaymentResult:
    """Process payment to credit line with proper allocation"""
    
    if payment_date is None:
        payment_date = date.today()
    
    account = self.account_manager.get_account(account_id)
    current_statement = self.get_current_statement(account_id)
    
    # Allocate payment according to regulatory requirements
    allocation = self.allocate_credit_payment(account, payment_amount, payment_date)
    
    # Create payment transaction
    payment_transaction = CreditTransaction(
        account_id=account_id,
        transaction_date=payment_date,
        post_date=payment_date,
        category=TransactionCategory.PAYMENT,
        amount=payment_amount,
        description="Payment received"
    )
    
    # Process payment transaction
    self.transaction_processor.process_transaction(
        account_id=account_id,
        transaction_type=TransactionType.PAYMENT,
        amount=payment_amount,
        description="Credit line payment"
    )
    
    # Update statement payment tracking
    if current_statement:
        current_statement.paid_amount += payment_amount
        current_statement.paid_date = payment_date
        
        # Update statement status
        if current_statement.paid_amount >= current_statement.current_balance:
            current_statement.status = StatementStatus.PAID_FULL
        elif current_statement.paid_amount >= current_statement.minimum_payment_due:
            current_statement.status = StatementStatus.PAID_MINIMUM
        
        self.storage.update(current_statement.id, current_statement)
    
    self.storage.store(payment_transaction)
    
    return CreditPaymentResult(
        payment_transaction=payment_transaction,
        allocation=allocation,
        new_balance=account.balance - payment_amount
    )

@dataclass
class PaymentAllocation:
    """How payment is allocated across different categories"""
    total_payment: Money
    
    # Allocation order per CARD Act
    fees_applied: Money
    interest_applied: Money
    principal_applied: Money
    
    def validate(self):
        total = self.fees_applied + self.interest_applied + self.principal_applied
        if total != self.total_payment:
            raise ValueError(f"Allocation mismatch: {total} != {self.total_payment}")
```

## Interest Calculations

Interest calculations vary based on transaction type and grace periods:

```python
def calculate_daily_interest(account_id: str, calculation_date: date) -> Money:
    """Calculate daily interest for credit line"""
    
    account = self.account_manager.get_account(account_id)
    
    # Get all transactions with outstanding balances
    transactions = self.get_interest_bearing_transactions(account_id, calculation_date)
    
    total_interest = Money(Decimal("0"), account.currency)
    daily_rate = account.interest_rate / 365
    
    for transaction in transactions:
        # Skip transactions still in grace period
        if (transaction.grace_period_applied and 
            transaction.interest_from_date and
            calculation_date < transaction.interest_from_date):
            continue
        
        # Calculate days since interest started accruing
        interest_start_date = transaction.interest_from_date or transaction.post_date
        days = (calculation_date - interest_start_date).days
        
        if days > 0:
            daily_interest = transaction.amount * daily_rate
            total_interest += daily_interest
            
            # Track interest accrued per transaction
            if transaction.daily_interest_accrued is None:
                transaction.daily_interest_accrued = Money(Decimal("0"), account.currency)
            transaction.daily_interest_accrued += daily_interest
            
            self.storage.update(transaction.id, transaction)
    
    return total_interest
```

## Late Fee Assessment

```python
def assess_late_fee(account_id: str, assessment_date: date) -> Optional[Money]:
    """Assess late fee for missed payment"""
    
    account = self.account_manager.get_account(account_id)
    current_statement = self.get_current_statement(account_id)
    
    if not current_statement or not current_statement.is_overdue:
        return None
    
    # Check if late fee already assessed for this statement
    existing_fees = self.get_late_fees_for_statement(current_statement.id)
    if existing_fees:
        return None  # Already assessed
    
    # Calculate late fee (typically fixed amount or percentage, whichever is less)
    late_fee_amount = account.settings.get("late_fee_amount", 
                                          Money(Decimal("39.00"), account.currency))
    
    # Create fee transaction
    fee_transaction = CreditTransaction(
        account_id=account_id,
        transaction_date=assessment_date,
        post_date=assessment_date,
        category=TransactionCategory.FEE,
        amount=late_fee_amount,
        description="Late payment fee",
        eligible_for_grace=False,
        interest_from_date=assessment_date
    )
    
    # Process fee
    self.transaction_processor.process_transaction(
        account_id=account_id,
        transaction_type=TransactionType.FEE,
        amount=late_fee_amount,
        description="Late payment fee"
    )
    
    self.storage.store(fee_transaction)
    
    return late_fee_amount
```

## Reporting and Analytics

```python
def get_credit_portfolio_summary() -> CreditPortfolioSummary:
    """Generate credit line portfolio summary"""
    
    active_accounts = self.get_active_credit_accounts()
    
    summary = CreditPortfolioSummary()
    
    for account in active_accounts:
        current_statement = self.get_current_statement(account.id)
        
        summary.total_accounts += 1
        summary.total_credit_limit += account.credit_limit
        summary.total_outstanding += account.balance
        summary.total_available_credit += (account.credit_limit - account.balance)
        
        # Utilization analysis
        utilization = (account.balance / account.credit_limit) if not account.credit_limit.is_zero() else Decimal("0")
        
        if utilization > Decimal("0.9"):
            summary.high_utilization_accounts += 1
        elif utilization > Decimal("0.5"):
            summary.medium_utilization_accounts += 1
        
        # Delinquency analysis
        if current_statement and current_statement.is_overdue:
            summary.delinquent_accounts += 1
            summary.delinquent_balance += account.balance
            
            if current_statement.days_overdue > 90:
                summary.charge_off_candidates += 1
    
    return summary
```

## Testing Credit Line Operations

```python
def test_grace_period_logic():
    """Test grace period application"""
    
    # Create credit line
    credit_line = create_test_credit_line()
    
    # Make purchase (should have grace period)
    purchase = credit_manager.process_purchase(
        account_id=credit_line.id,
        amount=Money(Decimal("100.00"), Currency.USD),
        description="Test purchase"
    )
    
    assert purchase.eligible_for_grace
    assert purchase.grace_period_applied
    assert purchase.interest_from_date > purchase.transaction_date
    
    # Generate statement
    statement = credit_manager.generate_monthly_statement(
        account_id=credit_line.id,
        statement_date=date(2026, 3, 1),
        cycle_start_date=date(2026, 2, 1)
    )
    
    # Pay in full - should maintain grace period
    credit_manager.process_payment(
        account_id=credit_line.id,
        payment_amount=statement.current_balance,
        payment_date=statement.due_date
    )
    
    # Next purchase should still have grace period
    assert credit_manager.has_active_grace_period(credit_line.id)

def test_minimum_payment_calculation():
    """Test minimum payment calculation rules"""
    
    account = create_test_credit_line()
    balance = Money(Decimal("1000.00"), Currency.USD)
    
    minimum = credit_manager.calculate_minimum_payment(account, balance)
    
    # Should be greater of 2% or $25
    expected_percentage = balance * Decimal("0.02")  # $20
    expected_minimum = Money(Decimal("25.00"), Currency.USD)  # $25
    
    assert minimum == expected_minimum  # $25 is greater
```

The credit lines module provides sophisticated revolving credit management with proper grace period handling, regulatory compliance, and comprehensive payment processing capabilities.