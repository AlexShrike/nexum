# Loans Module

The loans module handles the complete loan lifecycle from origination through payment processing, including amortization schedule generation, prepayment handling, and delinquency management. It supports multiple amortization methods and payment frequencies for flexible loan products.

## Overview

The loan system provides comprehensive loan management capabilities:

- **Loan Origination**: Create loans with flexible terms and conditions
- **Amortization Methods**: French method (equal installments), equal principal, bullet payments
- **Payment Processing**: Regular payments, prepayments, and partial payments
- **Schedule Management**: Generate and maintain amortization schedules
- **Lifecycle Tracking**: Monitor loan states from disbursement to payoff

## Key Concepts

### Loan States
Loans progress through defined states:

- **ORIGINATED**: Loan approved and created (not yet disbursed)
- **DISBURSED**: Funds disbursed to customer account
- **ACTIVE**: Regular payment schedule in effect
- **PAID_OFF**: Loan fully satisfied
- **DEFAULTED**: Loan in default status
- **WRITTEN_OFF**: Loan written off as uncollectible
- **CLOSED**: Loan account permanently closed

### Amortization Methods

**Equal Installment (French Method)**
- Equal payments throughout the loan term
- Interest decreases, principal increases over time
- Most common for consumer loans

**Equal Principal**
- Equal principal payments with declining interest
- Higher initial payments that decrease over time
- Common for commercial loans

**Bullet Payment**
- Interest-only payments during the term
- Full principal due at maturity
- Common for short-term business loans

## Core Classes

### LoanTerms

Defines the structure and terms of a loan:

```python
from core_banking.loans import LoanTerms, AmortizationMethod, PaymentFrequency
from core_banking.currency import Money, Currency
from datetime import date
from decimal import Decimal

# Define loan terms
terms = LoanTerms(
    principal_amount=Money(Decimal("25000.00"), Currency.USD),
    annual_interest_rate=Decimal("0.065"),  # 6.5% APR
    term_months=60,  # 5 years
    payment_frequency=PaymentFrequency.MONTHLY,
    amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
    first_payment_date=date(2026, 3, 15),
    allow_prepayment=True,
    prepayment_penalty_rate=Decimal("0.02"),  # 2% penalty
    grace_period_days=15,
    late_fee=Money(Decimal("39.00"), Currency.USD)
)

print(terms.total_payments)  # 60 payments
print(terms.payment_period_months)  # 1 month between payments
```

### Loan

Main loan entity tracking the complete loan state:

```python
from core_banking.loans import Loan, LoanState

@dataclass
class Loan(StorageRecord):
    customer_id: str
    loan_number: str
    terms: LoanTerms
    state: LoanState
    current_balance: Money
    interest_accrued: Money
    
    # Payment tracking
    total_payments_made: Money
    last_payment_date: Optional[date] = None
    next_payment_due: Optional[date] = None
    
    # Delinquency tracking
    days_past_due: int = 0
    late_fees_assessed: Money = None
    
    # Dates
    originated_at: datetime
    disbursed_at: Optional[datetime] = None
    maturity_date: Optional[date] = None
```

### AmortizationSchedule

Represents the payment schedule for a loan:

```python
from core_banking.loans import AmortizationSchedule, PaymentEntry

@dataclass
class PaymentEntry:
    payment_number: int
    payment_date: date
    beginning_balance: Money
    payment_amount: Money
    principal_amount: Money
    interest_amount: Money
    ending_balance: Money
    
    @property
    def is_final_payment(self) -> bool:
        return self.ending_balance.is_zero()

# Generate amortization schedule
schedule = loan_manager.generate_amortization_schedule(terms)

for entry in schedule.payments[:5]:  # Show first 5 payments
    print(f"Payment {entry.payment_number}: "
          f"Payment=${entry.payment_amount.amount}, "
          f"Principal=${entry.principal_amount.amount}, "
          f"Interest=${entry.interest_amount.amount}, "
          f"Balance=${entry.ending_balance.amount}")
```

## Amortization Calculations

### Equal Installment Method (French)

The most common method where payments are equal throughout the loan:

```python
def calculate_equal_installment_payment(
    principal: Money,
    annual_rate: Decimal,
    num_payments: int,
    payment_frequency: PaymentFrequency
) -> Money:
    """Calculate equal installment payment amount"""
    
    # Convert annual rate to payment period rate
    payments_per_year = payment_frequency.payments_per_year
    period_rate = annual_rate / payments_per_year
    
    if period_rate == 0:  # No interest
        payment = principal / num_payments
    else:
        # Standard amortization formula: P * (r(1+r)^n) / ((1+r)^n - 1)
        factor = period_rate * ((1 + period_rate) ** num_payments)
        divisor = ((1 + period_rate) ** num_payments) - 1
        payment = principal * (factor / divisor)
    
    return Money(payment.amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), 
                 principal.currency)

# Example: $25,000 loan at 6.5% for 60 months
payment = calculate_equal_installment_payment(
    principal=Money(Decimal("25000.00"), Currency.USD),
    annual_rate=Decimal("0.065"),
    num_payments=60,
    payment_frequency=PaymentFrequency.MONTHLY
)
print(f"Monthly payment: ${payment.amount}")  # ~$488.18
```

### Equal Principal Method

Equal principal payments with declining interest:

```python
def generate_equal_principal_schedule(terms: LoanTerms) -> AmortizationSchedule:
    """Generate equal principal amortization schedule"""
    
    principal_payment = terms.principal_amount / terms.total_payments
    payments = []
    remaining_balance = terms.principal_amount
    payment_date = terms.first_payment_date
    
    for payment_num in range(1, terms.total_payments + 1):
        # Calculate interest on remaining balance
        monthly_rate = terms.annual_interest_rate / 12
        interest_payment = remaining_balance * monthly_rate
        
        # Total payment = principal + interest
        total_payment = principal_payment + interest_payment
        
        # Update remaining balance
        new_balance = remaining_balance - principal_payment
        
        payment_entry = PaymentEntry(
            payment_number=payment_num,
            payment_date=payment_date,
            beginning_balance=remaining_balance,
            payment_amount=total_payment,
            principal_amount=principal_payment,
            interest_amount=interest_payment,
            ending_balance=new_balance
        )
        
        payments.append(payment_entry)
        
        # Advance to next payment date
        remaining_balance = new_balance
        payment_date = add_payment_period(payment_date, terms.payment_frequency)
    
    return AmortizationSchedule(payments=payments)
```

### Bullet Payment Method

Interest-only payments with principal due at maturity:

```python
def generate_bullet_schedule(terms: LoanTerms) -> AmortizationSchedule:
    """Generate bullet payment schedule (interest only + principal at end)"""
    
    # Calculate periodic interest payment
    payments_per_year = terms.payment_frequency.payments_per_year
    period_rate = terms.annual_interest_rate / payments_per_year
    interest_payment = terms.principal_amount * period_rate
    
    payments = []
    payment_date = terms.first_payment_date
    
    # All payments except last are interest-only
    for payment_num in range(1, terms.total_payments):
        payment_entry = PaymentEntry(
            payment_number=payment_num,
            payment_date=payment_date,
            beginning_balance=terms.principal_amount,
            payment_amount=interest_payment,
            principal_amount=Money(Decimal("0"), terms.principal_amount.currency),
            interest_amount=interest_payment,
            ending_balance=terms.principal_amount
        )
        
        payments.append(payment_entry)
        payment_date = add_payment_period(payment_date, terms.payment_frequency)
    
    # Final payment includes principal
    final_payment = interest_payment + terms.principal_amount
    final_entry = PaymentEntry(
        payment_number=terms.total_payments,
        payment_date=payment_date,
        beginning_balance=terms.principal_amount,
        payment_amount=final_payment,
        principal_amount=terms.principal_amount,
        interest_amount=interest_payment,
        ending_balance=Money(Decimal("0"), terms.principal_amount.currency)
    )
    
    payments.append(final_entry)
    
    return AmortizationSchedule(payments=payments)
```

## Loan Management

### LoanManager Class

```python
from core_banking.loans import LoanManager

class LoanManager:
    def __init__(self, storage: StorageInterface, account_manager: AccountManager):
        self.storage = storage
        self.account_manager = account_manager
    
    def originate_loan(self, customer_id: str, terms: LoanTerms) -> Loan:
        """Create new loan"""
        
        loan = Loan(
            customer_id=customer_id,
            loan_number=self.generate_loan_number(),
            terms=terms,
            state=LoanState.ORIGINATED,
            current_balance=terms.principal_amount,
            interest_accrued=Money(Decimal("0"), terms.principal_amount.currency),
            total_payments_made=Money(Decimal("0"), terms.principal_amount.currency),
            next_payment_due=terms.first_payment_date,
            originated_at=datetime.now(timezone.utc),
            maturity_date=self.calculate_maturity_date(terms)
        )
        
        # Create loan account
        loan_account = self.account_manager.create_account(
            customer_id=customer_id,
            product_type=ProductType.LOAN,
            currency=terms.principal_amount.currency,
            name=f"Loan {loan.loan_number}",
            credit_limit=terms.principal_amount
        )
        
        loan.account_id = loan_account.id
        
        self.storage.store(loan)
        return loan
    
    def disburse_loan(self, loan_id: str, target_account_id: str) -> Loan:
        """Disburse loan funds to customer account"""
        
        loan = self.get_loan(loan_id)
        
        if loan.state != LoanState.ORIGINATED:
            raise ValueError(f"Cannot disburse loan in state {loan.state}")
        
        # Create disbursement transaction
        self.transaction_processor.process_transfer(
            from_account_id=loan.account_id,
            to_account_id=target_account_id,
            amount=loan.terms.principal_amount,
            description=f"Loan disbursement - {loan.loan_number}",
            channel=TransactionChannel.SYSTEM
        )
        
        # Update loan state
        loan.state = LoanState.DISBURSED
        loan.disbursed_at = datetime.now(timezone.utc)
        
        # Start payment schedule
        loan.state = LoanState.ACTIVE
        
        self.storage.update(loan_id, loan)
        return loan
```

## Payment Processing

### Regular Loan Payments

```python
def process_loan_payment(
    loan_id: str,
    payment_amount: Money,
    payment_date: date,
    source_account_id: Optional[str] = None
) -> LoanPaymentResult:
    """Process loan payment with proper allocation"""
    
    loan = self.get_loan(loan_id)
    
    if loan.state not in [LoanState.ACTIVE, LoanState.DISBURSED]:
        raise ValueError(f"Cannot process payment for loan in state {loan.state}")
    
    # Get current payment from schedule
    current_payment = self.get_current_payment_entry(loan, payment_date)
    
    # Apply payment allocation rules
    allocation = self.allocate_payment(loan, payment_amount, payment_date)
    
    # Process payment transaction
    if source_account_id:
        self.transaction_processor.process_transfer(
            from_account_id=source_account_id,
            to_account_id=loan.account_id,
            amount=payment_amount,
            description=f"Loan payment - {loan.loan_number}",
            channel=TransactionChannel.ONLINE
        )
    
    # Update loan balances
    loan.current_balance -= allocation.principal_applied
    loan.interest_accrued -= allocation.interest_applied
    loan.total_payments_made += payment_amount
    loan.last_payment_date = payment_date
    
    # Update payment status
    if allocation.late_fees_applied > Money(Decimal("0"), loan.terms.principal_amount.currency):
        loan.late_fees_assessed += allocation.late_fees_applied
    
    # Check if loan is paid off
    if loan.current_balance.is_zero() and loan.interest_accrued.is_zero():
        loan.state = LoanState.PAID_OFF
        loan.next_payment_due = None
    else:
        loan.next_payment_due = self.calculate_next_payment_date(loan, payment_date)
    
    # Update days past due
    loan.days_past_due = max(0, (payment_date - current_payment.payment_date).days)
    
    self.storage.update(loan_id, loan)
    
    return LoanPaymentResult(
        loan=loan,
        allocation=allocation,
        new_balance=loan.current_balance
    )

@dataclass
class PaymentAllocation:
    """How a payment is allocated across different components"""
    total_payment: Money
    late_fees_applied: Money
    interest_applied: Money
    principal_applied: Money
    overpayment: Money
    
    def validate(self):
        """Ensure allocation adds up correctly"""
        total_applied = (self.late_fees_applied + 
                        self.interest_applied + 
                        self.principal_applied + 
                        self.overpayment)
        
        if total_applied != self.total_payment:
            raise ValueError("Payment allocation does not sum to total payment")
```

### Payment Allocation Logic

Payments are allocated in a specific order per banking regulations:

```python
def allocate_payment(
    loan: Loan, 
    payment_amount: Money, 
    payment_date: date
) -> PaymentAllocation:
    """Allocate payment according to regulatory requirements"""
    
    remaining_amount = payment_amount
    allocation = PaymentAllocation(
        total_payment=payment_amount,
        late_fees_applied=Money(Decimal("0"), payment_amount.currency),
        interest_applied=Money(Decimal("0"), payment_amount.currency),
        principal_applied=Money(Decimal("0"), payment_amount.currency),
        overpayment=Money(Decimal("0"), payment_amount.currency)
    )
    
    # 1. Apply to late fees first
    outstanding_late_fees = self.calculate_outstanding_late_fees(loan, payment_date)
    if outstanding_late_fees > Money(Decimal("0"), payment_amount.currency):
        late_fee_payment = min(remaining_amount, outstanding_late_fees)
        allocation.late_fees_applied = late_fee_payment
        remaining_amount -= late_fee_payment
    
    # 2. Apply to accrued interest
    if remaining_amount > Money(Decimal("0"), payment_amount.currency) and not loan.interest_accrued.is_zero():
        interest_payment = min(remaining_amount, loan.interest_accrued)
        allocation.interest_applied = interest_payment
        remaining_amount -= interest_payment
    
    # 3. Apply to principal
    if remaining_amount > Money(Decimal("0"), payment_amount.currency) and not loan.current_balance.is_zero():
        principal_payment = min(remaining_amount, loan.current_balance)
        allocation.principal_applied = principal_payment
        remaining_amount -= principal_payment
    
    # 4. Any remainder is overpayment
    if remaining_amount > Money(Decimal("0"), payment_amount.currency):
        allocation.overpayment = remaining_amount
    
    allocation.validate()
    return allocation
```

## Prepayment Handling

```python
def process_prepayment(
    loan_id: str,
    prepayment_amount: Money,
    payment_date: date
) -> PrepaymentResult:
    """Process loan prepayment with penalty calculation"""
    
    loan = self.get_loan(loan_id)
    
    if not loan.terms.allow_prepayment:
        raise ValueError("Prepayment not allowed for this loan")
    
    # Calculate prepayment penalty
    penalty = Money(Decimal("0"), prepayment_amount.currency)
    if loan.terms.prepayment_penalty_rate:
        penalty = loan.current_balance * loan.terms.prepayment_penalty_rate
    
    # Process prepayment (penalty is paid first)
    total_payment = prepayment_amount + penalty
    
    allocation = self.allocate_payment(loan, total_payment, payment_date)
    
    # Update loan
    loan.current_balance -= allocation.principal_applied
    loan.interest_accrued -= allocation.interest_applied
    loan.total_payments_made += total_payment
    
    # Recalculate payment schedule if partially prepaid
    if not loan.current_balance.is_zero():
        # Recalculate remaining payments
        remaining_schedule = self.recalculate_schedule_after_prepayment(loan, payment_date)
        loan.next_payment_due = remaining_schedule.payments[0].payment_date if remaining_schedule.payments else None
    else:
        # Loan fully paid off
        loan.state = LoanState.PAID_OFF
        loan.next_payment_due = None
    
    self.storage.update(loan_id, loan)
    
    return PrepaymentResult(
        loan=loan,
        prepayment_amount=prepayment_amount,
        penalty_amount=penalty,
        new_balance=loan.current_balance
    )
```

## Interest Accrual

```python
def accrue_interest(loan_id: str, accrual_date: date) -> Money:
    """Accrue daily interest on loan"""
    
    loan = self.get_loan(loan_id)
    
    if loan.state not in [LoanState.ACTIVE, LoanState.DISBURSED]:
        return Money(Decimal("0"), loan.terms.principal_amount.currency)
    
    # Calculate daily interest rate
    annual_rate = loan.terms.annual_interest_rate
    daily_rate = annual_rate / 365
    
    # Calculate interest on current balance
    daily_interest = loan.current_balance * daily_rate
    
    # Add to accrued interest
    loan.interest_accrued += daily_interest
    
    # Create journal entry for interest accrual
    self.ledger.post_entry(
        self.create_interest_accrual_entry(loan, daily_interest, accrual_date)
    )
    
    self.storage.update(loan_id, loan)
    
    return daily_interest
```

## Delinquency Management

```python
def update_delinquency_status(loan_id: str, as_of_date: date) -> DelinquencyStatus:
    """Update loan delinquency status"""
    
    loan = self.get_loan(loan_id)
    
    if not loan.next_payment_due or loan.state != LoanState.ACTIVE:
        return DelinquencyStatus.CURRENT
    
    # Calculate days past due
    days_past_due = max(0, (as_of_date - loan.next_payment_due).days)
    loan.days_past_due = days_past_due
    
    # Determine delinquency status
    if days_past_due == 0:
        status = DelinquencyStatus.CURRENT
    elif days_past_due <= 30:
        status = DelinquencyStatus.DAYS_1_30
    elif days_past_due <= 60:
        status = DelinquencyStatus.DAYS_31_60
    elif days_past_due <= 90:
        status = DelinquencyStatus.DAYS_61_90
    else:
        status = DelinquencyStatus.DAYS_90_PLUS
        
        # Consider default after 90 days
        if days_past_due >= 120:
            loan.state = LoanState.DEFAULTED
    
    # Apply late fees if past grace period
    if days_past_due > loan.terms.grace_period_days:
        self.assess_late_fee(loan, as_of_date)
    
    self.storage.update(loan_id, loan)
    
    return status
```

## Reporting and Analytics

```python
def get_loan_portfolio_summary(as_of_date: date) -> LoanPortfolioSummary:
    """Generate loan portfolio summary report"""
    
    active_loans = self.get_loans_by_state([LoanState.ACTIVE, LoanState.DISBURSED])
    
    summary = LoanPortfolioSummary()
    
    for loan in active_loans:
        summary.total_loans += 1
        summary.total_outstanding += loan.current_balance
        summary.total_interest_accrued += loan.interest_accrued
        
        # Delinquency breakdown
        status = self.get_delinquency_status(loan, as_of_date)
        if status == DelinquencyStatus.CURRENT:
            summary.current_loans += 1
            summary.current_balance += loan.current_balance
        elif status == DelinquencyStatus.DAYS_1_30:
            summary.delinquent_1_30 += 1
            summary.delinquent_1_30_balance += loan.current_balance
        # ... continue for other buckets
    
    return summary

def calculate_loan_yield(loan_id: str) -> Decimal:
    """Calculate effective yield on loan"""
    
    loan = self.get_loan(loan_id)
    schedule = self.generate_amortization_schedule(loan.terms)
    
    # Calculate IRR from payment cash flows
    cash_flows = [-loan.terms.principal_amount.amount]  # Initial disbursement
    
    for payment in schedule.payments:
        cash_flows.append(payment.payment_amount.amount)
    
    # Use numpy-financial or similar library for IRR calculation
    return calculate_irr(cash_flows)
```

## Testing Loan Calculations

```python
def test_equal_installment_calculation():
    """Test equal installment payment calculation"""
    
    terms = LoanTerms(
        principal_amount=Money(Decimal("10000.00"), Currency.USD),
        annual_interest_rate=Decimal("0.06"),  # 6%
        term_months=12,
        payment_frequency=PaymentFrequency.MONTHLY,
        amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
        first_payment_date=date(2026, 2, 1)
    )
    
    schedule = loan_manager.generate_amortization_schedule(terms)
    
    # All payments should be equal (except possibly the last due to rounding)
    payment_amounts = [p.payment_amount.amount for p in schedule.payments[:-1]]
    assert len(set(payment_amounts)) == 1  # All payments are the same
    
    # Total payments should equal principal + total interest
    total_paid = sum(p.payment_amount.amount for p in schedule.payments)
    total_interest = sum(p.interest_amount.amount for p in schedule.payments)
    
    assert total_paid == terms.principal_amount.amount + total_interest
    
    # Final balance should be zero
    assert schedule.payments[-1].ending_balance.is_zero()

def test_loan_payment_allocation():
    """Test payment allocation order"""
    
    loan = create_test_loan_with_late_fees()
    
    payment = Money(Decimal("100.00"), Currency.USD)
    allocation = loan_manager.allocate_payment(loan, payment, date.today())
    
    # Late fees should be paid first
    assert allocation.late_fees_applied > Money(Decimal("0"), Currency.USD)
    
    # Validate allocation sums to total payment
    allocation.validate()
```

The loans module provides comprehensive loan management capabilities with precise financial calculations, regulatory compliance, and flexible configuration options to support various lending products.