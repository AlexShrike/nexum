# Best Practices for Core Banking with Nexum

Best practices for building and operating a production core banking system, distilled from industry experience, regulatory requirements, and real-world deployments in microfinance, credit unions, and fintech companies.

---

## Table of Contents

1. [Double-Entry Bookkeeping Principles](#double-entry-bookkeeping-principles)
2. [Idempotency Keys — Always Use Them](#idempotency-keys--always-use-them)
3. [Transaction Atomicity](#transaction-atomicity)
4. [Currency Handling](#currency-handling)
5. [Product Configuration Patterns](#product-configuration-patterns)
6. [Loan Lifecycle Management](#loan-lifecycle-management)
7. [Credit Line Management](#credit-line-management)
8. [Collection Workflow](#collection-workflow)
9. [Event-Driven Architecture](#event-driven-architecture)
10. [Notification Templates](#notification-templates)
11. [Multi-Tenant Deployment Patterns](#multi-tenant-deployment-patterns)
12. [Performance Tuning](#performance-tuning)
13. [Error Handling & Recovery](#error-handling--recovery)
14. [Testing Strategies](#testing-strategies)
15. [Regulatory Compliance](#regulatory-compliance)

---

## Double-Entry Bookkeeping Principles

### The Golden Rules

Every financial transaction in Nexum must follow these fundamental principles:

**1. Debits must equal credits**
```python
# ✅ Good - balanced journal entry
lines = [
    JournalEntryLine("cash_account", "Cash deposit", debit=Money(1000, USD), credit=Money(0, USD)),
    JournalEntryLine("customer_liability", "Customer balance", debit=Money(0, USD), credit=Money(1000, USD))
]
# Total debits: $1000, Total credits: $1000 ✓
```

**2. Every transaction affects at least two accounts**
```python
# ❌ Bad - single account affected
def bad_deposit(account_id, amount):
    # This doesn't follow double-entry principles
    account.balance += amount
    
# ✅ Good - proper double-entry
def good_deposit(account_id, amount):
    journal_entry = ledger.create_journal_entry(
        reference=f"DEP_{transaction_id}",
        description="Customer deposit",
        lines=[
            JournalEntryLine("cash", "Cash received", debit=amount, credit=Money(0, USD)),
            JournalEntryLine(account_id, "Customer deposit", debit=Money(0, USD), credit=amount)
        ]
    )
    ledger.post_journal_entry(journal_entry.id)
```

**3. Account balances are derived, never stored**
```python
# ❌ Bad - storing balance separately creates consistency issues
def update_account_balance(account_id, new_balance):
    account.balance = new_balance  # Can get out of sync with journal entries
    
# ✅ Good - balance derived from journal entries
def get_account_balance(account_id):
    return ledger.calculate_balance(account_id)  # Always accurate
```

### Account Types and Normal Balances

| Account Type | Normal Balance | Increases With | Examples |
|--------------|----------------|----------------|----------|
| **Assets** | Debit | Debits | Cash, Customer Loans, Fixed Assets |
| **Liabilities** | Credit | Credits | Customer Deposits, Accounts Payable |
| **Equity** | Credit | Credits | Retained Earnings, Capital Stock |
| **Revenue** | Credit | Credits | Interest Income, Fee Income |
| **Expenses** | Debit | Debits | Interest Expense, Operating Costs |

### Common Banking Transactions

**Customer Deposit:**
```
Debit:  Cash Account           $1,000
Credit: Customer Account       $1,000
```

**Customer Withdrawal:**
```
Debit:  Customer Account       $500
Credit: Cash Account           $500
```

**Loan Disbursement:**
```
Debit:  Customer Account       $10,000  (customer receives money)
Credit: Loan Account           $10,000  (bank records loan asset)
```

**Loan Payment:**
```
Debit:  Cash Account           $500     (payment received)
Debit:  Interest Income        $200     (interest earned)
Credit: Loan Account           $300     (principal reduction)
Credit: Interest Revenue       $200     (revenue recognition)
```

**Interest Accrual:**
```
Debit:  Customer Account       $25      (customer earns interest)
Credit: Interest Expense       $25      (bank's expense)
```

---

## Idempotency Keys — Always Use Them

Idempotency keys prevent duplicate transactions when requests are retried due to network issues or user error.

### What is Idempotency?

Idempotency means that making the same request multiple times has the same effect as making it once.

```bash
# First request
curl -X POST http://localhost:8090/transactions/deposit \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "account_id": "acc_123",
    "amount": {"amount": "1000.00", "currency": "USD"},
    "description": "Payroll deposit",
    "idempotency_key": "payroll_2024_02_19_emp_001"
  }'

# Retry (network timeout, user clicks again, etc.)
curl -X POST http://localhost:8090/transactions/deposit \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "account_id": "acc_123",
    "amount": {"amount": "1000.00", "currency": "USD"}, 
    "description": "Payroll deposit",
    "idempotency_key": "payroll_2024_02_19_emp_001"  # Same key
  }'

# Second request returns the same result, no duplicate transaction created
```

### Idempotency Key Patterns

**Pattern 1: Business-meaningful keys**
```python
# Use meaningful identifiers from your business domain
idempotency_keys = [
    "payroll_2024_02_19_employee_001",
    "loan_payment_loan_123_payment_5", 
    "ach_return_trace_987654321",
    "interest_accrual_2024_02_acc_456"
]
```

**Pattern 2: UUID with context**
```python
import uuid

# Generate unique key with context
def generate_idempotency_key(operation_type, reference=None):
    unique_id = str(uuid.uuid4())
    if reference:
        return f"{operation_type}_{reference}_{unique_id}"
    return f"{operation_type}_{unique_id}"

# Examples
key1 = generate_idempotency_key("deposit", "external_ref_123")
# Result: "deposit_external_ref_123_550e8400-e29b-41d4-a716-446655440000"
```

**Pattern 3: Hash-based keys**
```python
import hashlib
import json

def create_deterministic_key(transaction_data):
    """Create deterministic key from transaction content"""
    # Include all fields that make transaction unique
    key_data = {
        'account_id': transaction_data['account_id'],
        'amount': str(transaction_data['amount']['amount']), 
        'currency': transaction_data['amount']['currency'],
        'reference': transaction_data.get('reference', ''),
        'date': transaction_data.get('date', datetime.now().date().isoformat())
    }
    
    # Create hash
    content = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]
```

### Implementation in Client Applications

**Web application (JavaScript):**
```javascript
class BankingAPI {
    constructor(baseUrl, token) {
        this.baseUrl = baseUrl;
        this.token = token;
        this.pendingRequests = new Map(); // Track in-flight requests
    }
    
    async makeDeposit(accountId, amount, description) {
        const idempotencyKey = `deposit_${accountId}_${Date.now()}_${Math.random()}`;
        
        // Prevent duplicate requests with same idempotency key
        if (this.pendingRequests.has(idempotencyKey)) {
            return this.pendingRequests.get(idempotencyKey);
        }
        
        const requestPromise = fetch(`${this.baseUrl}/transactions/deposit`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.token}`,
                'Idempotency-Key': idempotencyKey  // Can also put in body
            },
            body: JSON.stringify({
                account_id: accountId,
                amount: amount,
                description: description,
                idempotency_key: idempotencyKey
            })
        }).then(response => response.json())
          .finally(() => {
              // Remove from pending requests when complete
              this.pendingRequests.delete(idempotencyKey);
          });
          
        this.pendingRequests.set(idempotencyKey, requestPromise);
        return requestPromise;
    }
}
```

### Server-Side Implementation

Nexum automatically handles idempotency keys:

```python
# In TransactionProcessor
def process_transaction(self, transaction_request):
    idempotency_key = transaction_request.idempotency_key
    
    # Check if we've already processed this request
    existing_result = self.storage.find("idempotency_cache", 
                                       {"key": idempotency_key})
    
    if existing_result:
        # Return previous result, don't process again
        return TransactionResult.from_dict(existing_result[0]["result"])
    
    # Process transaction normally
    try:
        with self.storage.atomic():
            result = self._execute_transaction(transaction_request)
            
            # Cache result for future requests with same key
            self.storage.save("idempotency_cache", idempotency_key, {
                "key": idempotency_key,
                "result": result.to_dict(),
                "created_at": datetime.now(),
                "expires_at": datetime.now() + timedelta(hours=24)
            })
            
        return result
        
    except Exception as e:
        # Don't cache failures (allow retry with same key)
        raise
```

---

## Transaction Atomicity

### Use atomic() for Multi-Step Operations

Banking operations often require multiple database changes that must all succeed or all fail together.

```python
# ❌ Bad - not atomic, can leave system in inconsistent state
def transfer_funds(from_account, to_account, amount):
    # If system crashes between these operations, money could be lost!
    withdraw(from_account, amount)  # Succeeds
    deposit(to_account, amount)     # Fails - money disappears!

# ✅ Good - atomic transaction
def transfer_funds(from_account, to_account, amount):
    with storage.atomic():
        # Both operations succeed or both fail
        withdraw_result = withdraw(from_account, amount)
        deposit_result = deposit(to_account, amount)
        
        # Create transfer record linking both transactions
        transfer_record = create_transfer_record(
            withdraw_result.transaction_id,
            deposit_result.transaction_id,
            amount
        )
        
        return transfer_record
```

### Complex Multi-Step Example: Loan Payment

```python
def process_loan_payment(loan_id, payment_amount, source_account_id):
    """Process loan payment with proper atomicity"""
    
    with storage.atomic():
        # Step 1: Validate loan exists and calculate payment breakdown
        loan = loan_manager.get_loan(loan_id)
        if not loan:
            raise ValueError("Loan not found")
            
        payment_breakdown = loan_manager.calculate_payment_breakdown(
            loan, payment_amount
        )
        
        # Step 2: Withdraw funds from customer account
        withdrawal = transaction_processor.process_transaction(
            TransactionRequest(
                transaction_type=TransactionType.WITHDRAWAL,
                from_account_id=source_account_id,
                amount=payment_amount,
                description=f"Loan payment - Loan {loan_id}",
                reference=f"LOAN_PAY_{loan_id}_{datetime.now().strftime('%Y%m%d')}"
            )
        )
        
        # Step 3: Apply payment to loan (creates journal entries)
        payment_result = loan_manager.apply_payment(
            loan_id=loan_id,
            principal_payment=payment_breakdown.principal_amount,
            interest_payment=payment_breakdown.interest_amount,
            payment_date=datetime.now().date()
        )
        
        # Step 4: Update loan status if paid off
        if payment_result.new_balance.is_zero():
            loan_manager.mark_loan_paid_off(loan_id)
            
        # Step 5: Generate payment confirmation
        payment_confirmation = create_payment_confirmation(
            loan_id=loan_id,
            payment_amount=payment_amount,
            principal_applied=payment_breakdown.principal_amount,
            interest_applied=payment_breakdown.interest_amount,
            new_balance=payment_result.new_balance
        )
        
        # Step 6: Log audit event
        audit_trail.log_event(
            event_type=AuditEventType.LOAN_PAYMENT_MADE,
            entity_type="loan",
            entity_id=loan_id,
            metadata={
                "payment_amount": str(payment_amount.amount),
                "currency": payment_amount.currency.code,
                "principal_applied": str(payment_breakdown.principal_amount.amount),
                "interest_applied": str(payment_breakdown.interest_amount.amount),
                "new_balance": str(payment_result.new_balance.amount),
                "source_account_id": source_account_id
            }
        )
        
        return payment_confirmation
```

### Handling Compensation Actions

Sometimes you need to undo operations that were partially completed:

```python
def process_complex_transaction(request):
    """Example with compensation pattern"""
    completed_steps = []
    
    try:
        with storage.atomic():
            # Step 1: Compliance check
            compliance_result = compliance_engine.check_transaction(request)
            completed_steps.append("compliance_check")
            
            if compliance_result.action == ComplianceAction.BLOCK:
                raise ComplianceViolation("Transaction blocked by compliance")
            
            # Step 2: Hold funds
            hold_result = account_manager.place_hold(
                request.from_account_id, request.amount
            )
            completed_steps.append("funds_held")
            
            # Step 3: Process transaction
            transaction_result = transaction_processor.execute_transfer(request)
            completed_steps.append("transaction_processed")
            
            # Step 4: Release hold
            account_manager.release_hold(hold_result.hold_id)
            completed_steps.append("hold_released")
            
            return transaction_result
            
    except Exception as e:
        # Atomic transaction will rollback database changes automatically
        # But log what was attempted for debugging
        logger.error(f"Transaction failed after completing steps: {completed_steps}")
        
        # Notify monitoring systems
        metrics.increment("transaction_failures", tags={
            "failed_after": completed_steps[-1] if completed_steps else "start",
            "error_type": type(e).__name__
        })
        
        raise
```

---

## Currency Handling

### Always Use Decimal, Never Float

Financial calculations must use `decimal.Decimal` for precision:

```python
from decimal import Decimal, ROUND_HALF_UP

# ❌ Bad - floating point precision errors
bad_calculation = 0.1 + 0.2  # Result: 0.30000000000000004

# ✅ Good - precise decimal arithmetic  
good_calculation = Decimal('0.1') + Decimal('0.2')  # Result: 0.3
```

### Currency-Aware Money Class

Use Nexum's `Money` class for all monetary values:

```python
from core_banking.currency import Money, Currency

# ✅ Good - type-safe money handling
deposit = Money(Decimal('1500.00'), Currency.USD)
fee = Money(Decimal('2.50'), Currency.USD)
net_deposit = deposit - fee  # Result: Money(1497.50, USD)

# Prevents currency mismatch errors
usd_amount = Money(Decimal('100.00'), Currency.USD)
eur_amount = Money(Decimal('85.00'), Currency.EUR)
# This will raise an exception:
# total = usd_amount + eur_amount  # ValueError: Currency mismatch
```

### Interest Calculations

**Simple interest:**
```python
def calculate_simple_interest(principal, annual_rate, days):
    """Calculate simple interest for a number of days"""
    daily_rate = annual_rate / Decimal('365')
    interest = principal.amount * daily_rate * Decimal(str(days))
    return Money(interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), 
                 principal.currency)

# Example
principal = Money(Decimal('10000.00'), Currency.USD)
annual_rate = Decimal('0.05')  # 5%
interest = calculate_simple_interest(principal, annual_rate, 30)
# Result: Money(41.10, USD) for 30 days
```

**Compound interest:**
```python
def calculate_compound_interest(principal, annual_rate, compounding_frequency, years):
    """Calculate compound interest"""
    rate_per_period = annual_rate / Decimal(str(compounding_frequency))
    total_periods = Decimal(str(compounding_frequency)) * Decimal(str(years))
    
    # A = P(1 + r/n)^(nt)
    compound_factor = (Decimal('1') + rate_per_period) ** total_periods
    final_amount = principal.amount * compound_factor
    
    return Money(final_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                 principal.currency)
```

### Loan Payment Calculations

**Equal installment (French amortization):**
```python
def calculate_monthly_payment(principal, annual_rate, term_months):
    """Calculate equal monthly payment for loan"""
    if annual_rate == 0:
        # No interest - equal principal payments
        return Money(principal.amount / Decimal(str(term_months)), principal.currency)
    
    monthly_rate = annual_rate / Decimal('12')
    
    # PMT = P * [r(1+r)^n] / [(1+r)^n - 1]
    rate_factor = (Decimal('1') + monthly_rate) ** Decimal(str(term_months))
    payment = principal.amount * (monthly_rate * rate_factor) / (rate_factor - Decimal('1'))
    
    return Money(payment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                 principal.currency)

# Example
principal = Money(Decimal('25000.00'), Currency.USD)
annual_rate = Decimal('0.0675')  # 6.75%
term_months = 60
monthly_payment = calculate_monthly_payment(principal, annual_rate, term_months)
# Result: Money(495.84, USD)
```

### Multi-Currency Support

```python
class CurrencyConverter:
    def __init__(self, exchange_rate_service):
        self.rate_service = exchange_rate_service
        
    def convert(self, amount: Money, to_currency: Currency) -> Money:
        """Convert money from one currency to another"""
        if amount.currency == to_currency:
            return amount
            
        rate = self.rate_service.get_rate(amount.currency, to_currency)
        converted_amount = amount.amount * rate
        
        return Money(
            converted_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            to_currency
        )

# Multi-currency account balances
def get_account_balance_in_currency(account_id, currency):
    """Get account balance converted to specific currency"""
    native_balance = account_manager.get_balance(account_id)
    
    if native_balance.currency == currency:
        return native_balance
        
    converter = CurrencyConverter(exchange_rate_service)
    return converter.convert(native_balance, currency)
```

---

## Product Configuration Patterns

### Product Types and Features

Design flexible product configurations that can handle different banking products:

```python
# ✅ Good - flexible product configuration
@dataclass
class ProductConfiguration:
    name: str
    product_type: ProductType
    currency: Currency
    
    # Interest settings
    interest_rate: Optional[Decimal] = None
    interest_calculation_method: str = "daily_balance"  # daily_balance, average_balance
    interest_compounding_frequency: str = "monthly"    # daily, monthly, quarterly, annual
    interest_accrual_frequency: str = "daily"          # daily, monthly
    
    # Balance requirements
    minimum_balance: Optional[Money] = None
    minimum_balance_fee: Optional[Money] = None
    
    # Transaction limits
    daily_withdrawal_limit: Optional[Money] = None
    daily_transaction_limit: Optional[Money] = None
    monthly_transaction_limit: Optional[Money] = None
    max_transaction_amount: Optional[Money] = None
    
    # Fees
    monthly_maintenance_fee: Optional[Money] = None
    transaction_fee: Optional[Money] = None
    overdraft_fee: Optional[Money] = None
    overdraft_limit: Optional[Money] = None
    
    # Credit line specific
    credit_limit: Optional[Money] = None
    grace_period_days: int = 21
    late_payment_fee: Optional[Money] = None
    overlimit_fee: Optional[Money] = None
    
    # Loan specific
    default_loan_term_months: int = 12
    max_loan_term_months: int = 60
    prepayment_allowed: bool = True
    prepayment_penalty_rate: Optional[Decimal] = None
    
    # Business rules
    requires_kyc_tier: KYCTier = KYCTier.TIER_1
    allow_negative_balance: bool = False
    auto_pay_fees_from_balance: bool = True
    send_low_balance_alerts: bool = True
    low_balance_alert_threshold: Optional[Money] = None

# Product library examples
PRODUCT_LIBRARY = {
    "basic_savings": ProductConfiguration(
        name="Basic Savings Account",
        product_type=ProductType.SAVINGS,
        currency=Currency.USD,
        interest_rate=Decimal('0.0025'),  # 0.25% APY
        minimum_balance=Money(Decimal('100.00'), Currency.USD),
        minimum_balance_fee=Money(Decimal('10.00'), Currency.USD),
        monthly_maintenance_fee=Money(Decimal('5.00'), Currency.USD),
        daily_withdrawal_limit=Money(Decimal('500.00'), Currency.USD),
        requires_kyc_tier=KYCTier.TIER_1
    ),
    
    "premium_savings": ProductConfiguration(
        name="Premium High-Yield Savings",
        product_type=ProductType.SAVINGS, 
        currency=Currency.USD,
        interest_rate=Decimal('0.045'),   # 4.5% APY
        minimum_balance=Money(Decimal('2500.00'), Currency.USD),
        monthly_maintenance_fee=None,     # No fee for premium account
        daily_withdrawal_limit=Money(Decimal('2000.00'), Currency.USD),
        requires_kyc_tier=KYCTier.TIER_2,
        send_low_balance_alerts=True,
        low_balance_alert_threshold=Money(Decimal('2500.00'), Currency.USD)
    ),
    
    "business_checking": ProductConfiguration(
        name="Business Checking Account",
        product_type=ProductType.CHECKING,
        currency=Currency.USD,
        minimum_balance=Money(Decimal('1000.00'), Currency.USD),
        monthly_maintenance_fee=Money(Decimal('15.00'), Currency.USD),
        daily_transaction_limit=Money(Decimal('50000.00'), Currency.USD),
        monthly_transaction_limit=Money(Decimal('500000.00'), Currency.USD),
        transaction_fee=Money(Decimal('0.25'), Currency.USD),  # Per transaction
        overdraft_limit=Money(Decimal('5000.00'), Currency.USD),
        overdraft_fee=Money(Decimal('35.00'), Currency.USD),
        allow_negative_balance=True,
        requires_kyc_tier=KYCTier.TIER_3
    ),
    
    "personal_credit_line": ProductConfiguration(
        name="Personal Line of Credit",
        product_type=ProductType.CREDIT_LINE,
        currency=Currency.USD,
        credit_limit=Money(Decimal('10000.00'), Currency.USD),
        interest_rate=Decimal('0.1899'),  # 18.99% APR
        grace_period_days=21,
        late_payment_fee=Money(Decimal('35.00'), Currency.USD),
        overlimit_fee=Money(Decimal('25.00'), Currency.USD),
        minimum_payment_percentage=Decimal('0.02'),  # 2% of balance
        requires_kyc_tier=KYCTier.TIER_2
    ),
    
    "microfinance_loan": ProductConfiguration(
        name="Microfinance Business Loan",
        product_type=ProductType.LOAN,
        currency=Currency.USD,
        interest_rate=Decimal('0.24'),    # 24% APR (common for microfinance)
        default_loan_term_months=12,
        max_loan_term_months=24,
        prepayment_allowed=True,
        prepayment_penalty_rate=None,     # No prepayment penalty
        late_payment_fee=Money(Decimal('15.00'), Currency.USD),
        grace_period_days=7,
        requires_kyc_tier=KYCTier.TIER_1
    )
}
```

### Dynamic Product Selection

```python
def recommend_product(customer_profile, intended_use, initial_deposit=None):
    """Recommend products based on customer profile"""
    
    recommendations = []
    
    # Check KYC eligibility
    eligible_products = [
        product for product in PRODUCT_LIBRARY.values()
        if customer_profile.kyc_tier >= product.requires_kyc_tier
    ]
    
    # Filter by intended use
    if intended_use == "savings":
        candidates = [p for p in eligible_products if p.product_type == ProductType.SAVINGS]
    elif intended_use == "business":
        candidates = [p for p in eligible_products if "business" in p.name.lower()]
    elif intended_use == "credit":
        candidates = [p for p in eligible_products if p.product_type == ProductType.CREDIT_LINE]
    else:
        candidates = eligible_products
    
    # Rank by suitability
    for product in candidates:
        score = 0
        reasons = []
        
        # Higher score for products customer can afford
        if initial_deposit and product.minimum_balance:
            if initial_deposit >= product.minimum_balance:
                score += 10
                reasons.append("Meets minimum balance requirement")
            else:
                score -= 5
                reasons.append(f"Requires ${product.minimum_balance.amount} minimum balance")
        
        # Prefer products with better interest rates
        if product.interest_rate:
            score += float(product.interest_rate) * 100  # Convert to basis points
            reasons.append(f"{product.interest_rate:.2%} interest rate")
        
        # Penalize products with high fees
        if product.monthly_maintenance_fee:
            score -= float(product.monthly_maintenance_fee.amount)
            reasons.append(f"${product.monthly_maintenance_fee.amount}/month fee")
        else:
            score += 5
            reasons.append("No monthly maintenance fee")
        
        recommendations.append({
            "product": product,
            "score": score,
            "reasons": reasons
        })
    
    # Sort by score (highest first)
    recommendations.sort(key=lambda x: x["score"], reverse=True)
    
    return recommendations[:3]  # Return top 3 recommendations
```

---

## Loan Lifecycle Management

### Proper State Machine Implementation

Loans should follow a clear state machine to ensure data integrity:

```python
class LoanStateMachine:
    """Manages loan state transitions with validation"""
    
    ALLOWED_TRANSITIONS = {
        LoanState.ORIGINATED: [LoanState.DISBURSED, LoanState.CANCELLED],
        LoanState.DISBURSED: [LoanState.ACTIVE],
        LoanState.ACTIVE: [LoanState.PAID_OFF, LoanState.DEFAULTED],
        LoanState.PAID_OFF: [],  # Terminal state
        LoanState.DEFAULTED: [LoanState.WRITTEN_OFF, LoanState.ACTIVE],  # Can cure default
        LoanState.WRITTEN_OFF: [],  # Terminal state
        LoanState.CANCELLED: []  # Terminal state
    }
    
    def can_transition(self, from_state: LoanState, to_state: LoanState) -> bool:
        """Check if state transition is allowed"""
        return to_state in self.ALLOWED_TRANSITIONS.get(from_state, [])
    
    def transition(self, loan: Loan, to_state: LoanState, reason: str = None) -> None:
        """Execute state transition with validation"""
        if not self.can_transition(loan.state, to_state):
            raise ValueError(f"Invalid transition from {loan.state.value} to {to_state.value}")
        
        old_state = loan.state
        loan.state = to_state
        loan.updated_at = datetime.now(timezone.utc)
        
        # Log state change in audit trail
        audit_trail.log_event(
            event_type=AuditEventType.LOAN_STATE_CHANGED,
            entity_type="loan",
            entity_id=loan.id,
            metadata={
                "old_state": old_state.value,
                "new_state": to_state.value,
                "reason": reason
            }
        )
        
        # Trigger business logic for state changes
        self._handle_state_change(loan, old_state, to_state)
    
    def _handle_state_change(self, loan: Loan, old_state: LoanState, new_state: LoanState):
        """Handle side effects of state changes"""
        
        if new_state == LoanState.DISBURSED:
            # Start accruing interest
            interest_engine.start_interest_accrual(loan.account_id)
            
        elif new_state == LoanState.ACTIVE and old_state == LoanState.DISBURSED:
            # First payment received - loan is now active
            notification_engine.send_notification(
                customer_id=loan.customer_id,
                template="loan_activated",
                data={"loan_id": loan.id, "balance": str(loan.current_balance.amount)}
            )
            
        elif new_state == LoanState.PAID_OFF:
            # Stop interest accrual
            interest_engine.stop_interest_accrual(loan.account_id)
            
            # Send congratulations
            notification_engine.send_notification(
                customer_id=loan.customer_id,
                template="loan_paid_off",
                data={"loan_id": loan.id}
            )
            
        elif new_state == LoanState.DEFAULTED:
            # Create collection case
            collections_manager.create_case(
                loan_id=loan.id,
                case_type="loan_default",
                priority="high"
            )
            
            # Notify collections team
            notification_engine.send_notification(
                recipient="collections@yourbank.com",
                template="loan_default_alert",
                data={"loan_id": loan.id, "customer_id": loan.customer_id}
            )
```

### Payment Processing with Grace Periods

```python
def process_loan_payment(loan_id, payment_amount, payment_date=None):
    """Process loan payment with proper grace period handling"""
    
    if payment_date is None:
        payment_date = date.today()
    
    loan = loan_manager.get_loan(loan_id)
    if not loan:
        raise ValueError("Loan not found")
    
    # Calculate if payment is late
    next_payment_due = loan_manager.get_next_payment_date(loan_id)
    grace_period_end = next_payment_due + timedelta(days=loan.terms.grace_period_days)
    
    is_late = payment_date > grace_period_end
    days_late = (payment_date - grace_period_end).days if is_late else 0
    
    with storage.atomic():
        # Apply late fee if payment is late
        if is_late and loan.terms.late_fee:
            late_fee_amount = loan.terms.late_fee
            
            # Check if late fee already applied for this payment
            existing_late_fees = transaction_processor.find_transactions(
                filters={
                    "account_id": loan.account_id,
                    "transaction_type": TransactionType.FEE,
                    "description": f"Late fee - payment due {next_payment_due}"
                }
            )
            
            if not existing_late_fees:
                # Apply late fee
                fee_transaction = transaction_processor.process_transaction(
                    TransactionRequest(
                        transaction_type=TransactionType.FEE,
                        to_account_id=loan.account_id,  # Increases loan balance
                        amount=late_fee_amount,
                        description=f"Late fee - payment due {next_payment_due}",
                        reference=f"LATE_FEE_{loan_id}_{next_payment_due}"
                    )
                )
                
                # Update loan balance
                loan.current_balance += late_fee_amount
        
        # Calculate payment allocation (interest first, then principal)
        payment_breakdown = calculate_payment_breakdown(loan, payment_amount)
        
        # Apply payment to loan
        payment_result = apply_loan_payment(
            loan=loan,
            payment_amount=payment_amount,
            principal_payment=payment_breakdown.principal_amount,
            interest_payment=payment_breakdown.interest_amount,
            payment_date=payment_date
        )
        
        # Update loan status if needed
        if payment_result.new_balance.is_zero():
            state_machine.transition(loan, LoanState.PAID_OFF, "Final payment received")
        elif loan.state == LoanState.DEFAULTED and payment_amount >= payment_breakdown.minimum_payment:
            # Payment cures default
            state_machine.transition(loan, LoanState.ACTIVE, "Default cured by payment")
        
        # Create payment record
        payment_record = LoanPayment(
            id=str(uuid.uuid4()),
            loan_id=loan.id,
            payment_amount=payment_amount,
            principal_payment=payment_breakdown.principal_amount,
            interest_payment=payment_breakdown.interest_amount,
            late_fee=late_fee_amount if is_late else Money(Decimal('0'), payment_amount.currency),
            payment_date=payment_date,
            days_late=days_late,
            new_balance=payment_result.new_balance,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        storage.save("loan_payments", payment_record.id, payment_record.to_dict())
        
        # Send payment confirmation
        notification_engine.send_notification(
            customer_id=loan.customer_id,
            template="loan_payment_received",
            data={
                "loan_id": loan.id,
                "payment_amount": str(payment_amount.amount),
                "principal_payment": str(payment_breakdown.principal_amount.amount),
                "interest_payment": str(payment_breakdown.interest_amount.amount),
                "new_balance": str(payment_result.new_balance.amount),
                "next_payment_date": loan_manager.get_next_payment_date(loan.id).isoformat()
            }
        )
        
        return payment_record
```

### Early Payoff Handling

```python
def calculate_payoff_amount(loan_id, payoff_date=None):
    """Calculate amount needed to pay off loan completely"""
    
    if payoff_date is None:
        payoff_date = date.today()
    
    loan = loan_manager.get_loan(loan_id)
    
    # Current principal balance
    principal_balance = loan.current_balance
    
    # Calculate accrued interest up to payoff date
    last_interest_date = loan_manager.get_last_interest_accrual_date(loan_id)
    days_since_interest = (payoff_date - last_interest_date).days
    
    if days_since_interest > 0:
        daily_interest_rate = loan.terms.annual_interest_rate / Decimal('365')
        accrued_interest = principal_balance.amount * daily_interest_rate * Decimal(str(days_since_interest))
        accrued_interest = Money(accrued_interest.quantize(Decimal('0.01')), principal_balance.currency)
    else:
        accrued_interest = Money(Decimal('0'), principal_balance.currency)
    
    # Calculate prepayment penalty if applicable
    prepayment_penalty = Money(Decimal('0'), principal_balance.currency)
    if loan.terms.prepayment_penalty_rate and not loan.terms.allow_prepayment:
        penalty_rate = loan.terms.prepayment_penalty_rate
        prepayment_penalty = Money(
            (principal_balance.amount * penalty_rate).quantize(Decimal('0.01')),
            principal_balance.currency
        )
    
    # Total payoff amount
    total_payoff = principal_balance + accrued_interest + prepayment_penalty
    
    return PayoffCalculation(
        payoff_date=payoff_date,
        principal_balance=principal_balance,
        accrued_interest=accrued_interest,
        prepayment_penalty=prepayment_penalty,
        total_payoff_amount=total_payoff,
        good_through_date=payoff_date + timedelta(days=10)  # Quote valid for 10 days
    )

def process_loan_payoff(loan_id, source_account_id, payoff_date=None):
    """Process complete loan payoff"""
    
    payoff_calc = calculate_payoff_amount(loan_id, payoff_date)
    
    with storage.atomic():
        # Process payoff payment
        payoff_payment = process_loan_payment(
            loan_id=loan_id,
            payment_amount=payoff_calc.total_payoff_amount,
            payment_date=payoff_calc.payoff_date
        )
        
        # Verify loan is completely paid off
        loan = loan_manager.get_loan(loan_id)
        if not loan.current_balance.is_zero():
            raise ValueError("Loan payoff calculation error - balance remaining")
        
        # Generate payoff letter
        payoff_letter = generate_payoff_letter(loan, payoff_calc, payoff_payment)
        
        # Send confirmation
        notification_engine.send_notification(
            customer_id=loan.customer_id,
            template="loan_paid_off_confirmation",
            data={
                "loan_id": loan.id,
                "payoff_amount": str(payoff_calc.total_payoff_amount.amount),
                "payoff_date": payoff_calc.payoff_date.isoformat(),
                "payoff_letter_url": payoff_letter.document_url
            }
        )
        
        return payoff_payment
```

---

## Credit Line Management

### Statement Generation and Billing Cycles

```python
class CreditLineStatementGenerator:
    """Generates monthly statements for credit lines"""
    
    def __init__(self, credit_manager, transaction_processor, storage):
        self.credit_manager = credit_manager
        self.transaction_processor = transaction_processor
        self.storage = storage
    
    def generate_monthly_statement(self, account_id, statement_date):
        """Generate statement for a specific billing cycle"""
        
        # Get previous statement to determine billing period
        previous_statement = self._get_previous_statement(account_id)
        
        if previous_statement:
            period_start = previous_statement.statement_date + timedelta(days=1)
        else:
            # First statement - start from account opening
            account = account_manager.get_account(account_id)
            period_start = account.created_at.date()
        
        period_end = statement_date
        
        # Get all transactions in billing period
        transactions = self._get_billing_period_transactions(
            account_id, period_start, period_end
        )
        
        # Categorize transactions
        purchases = [t for t in transactions if t.category == TransactionCategory.PURCHASE]
        cash_advances = [t for t in transactions if t.category == TransactionCategory.CASH_ADVANCE]
        payments = [t for t in transactions if t.category == TransactionCategory.PAYMENT]
        fees = [t for t in transactions if t.category == TransactionCategory.FEE]
        interest = [t for t in transactions if t.category == TransactionCategory.INTEREST]
        
        # Calculate statement amounts
        new_purchases = sum(t.amount for t in purchases)
        new_cash_advances = sum(t.amount for t in cash_advances)
        payments_credits = sum(t.amount for t in payments)
        fees_charged = sum(t.amount for t in fees)
        interest_charged = sum(t.amount for t in interest)
        
        # Calculate balances
        if previous_statement:
            previous_balance = previous_statement.current_balance
        else:
            previous_balance = Money(Decimal('0'), Currency.USD)
        
        current_balance = (previous_balance + new_purchases + new_cash_advances + 
                          fees_charged + interest_charged - payments_credits)
        
        # Get account info
        account = account_manager.get_account(account_id)
        credit_limit = account.credit_limit
        available_credit = credit_limit - current_balance
        
        # Calculate minimum payment
        minimum_payment = self._calculate_minimum_payment(
            current_balance, previous_statement
        )
        
        # Determine grace period status
        grace_period_active = self._is_grace_period_active(
            account_id, previous_statement, payments
        )
        
        # Calculate due date (typically 21 days from statement date)
        due_date = statement_date + timedelta(days=21)
        
        # Create statement
        statement = CreditStatement(
            id=str(uuid.uuid4()),
            account_id=account_id,
            statement_date=statement_date,
            due_date=due_date,
            previous_balance=previous_balance,
            new_charges=new_purchases + new_cash_advances,
            payments_credits=payments_credits,
            interest_charged=interest_charged,
            fees_charged=fees_charged,
            current_balance=current_balance,
            minimum_payment_due=minimum_payment,
            available_credit=available_credit,
            credit_limit=credit_limit,
            grace_period_active=grace_period_active,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        # Save statement
        self.storage.save("credit_statements", statement.id, statement.to_dict())
        
        # Update transaction statement assignments
        for transaction in transactions:
            transaction.statement_id = statement.id
            self.storage.save("credit_transactions", transaction.id, transaction.to_dict())
        
        # Generate and send statement document
        self._generate_statement_document(statement)
        
        return statement
    
    def _calculate_minimum_payment(self, current_balance, previous_statement):
        """Calculate minimum payment due"""
        if current_balance.is_zero():
            return Money(Decimal('0'), current_balance.currency)
        
        # Typical minimum payment calculation:
        # 1% of balance + any overlimit amount + past due amounts
        
        percentage_payment = current_balance.amount * Decimal('0.01')  # 1%
        minimum_dollar_amount = Decimal('25.00')  # Never less than $25
        
        base_payment = max(percentage_payment, minimum_dollar_amount)
        
        # Add past due amounts from previous statement
        past_due = Money(Decimal('0'), current_balance.currency)
        if previous_statement and previous_statement.is_overdue:
            past_due = previous_statement.minimum_payment_due - previous_statement.paid_amount
        
        return Money(base_payment, current_balance.currency) + past_due
    
    def _is_grace_period_active(self, account_id, previous_statement, payments):
        """Determine if grace period applies to new purchases"""
        
        # Grace period applies if previous statement was paid in full by due date
        if not previous_statement:
            return True  # First statement gets grace period
        
        if previous_statement.is_paid_full and not previous_statement.is_overdue:
            return True
        
        return False
```

### Interest Calculation for Credit Lines

```python
class CreditLineInterestCalculator:
    """Calculates interest for credit lines using average daily balance method"""
    
    def calculate_interest(self, account_id, calculation_date):
        """Calculate interest for a billing period"""
        
        # Get current statement period
        current_statement = self._get_current_statement(account_id)
        if not current_statement:
            return  # No statement yet
        
        # Calculate interest for different transaction types
        purchase_interest = self._calculate_purchase_interest(
            account_id, current_statement, calculation_date
        )
        
        cash_advance_interest = self._calculate_cash_advance_interest(
            account_id, current_statement, calculation_date
        )
        
        total_interest = purchase_interest + cash_advance_interest
        
        if total_interest.is_positive():
            # Create interest charge transaction
            interest_transaction = transaction_processor.process_transaction(
                TransactionRequest(
                    transaction_type=TransactionType.INTEREST_DEBIT,
                    to_account_id=account_id,
                    amount=total_interest,
                    description=f"Interest charge - {calculation_date}",
                    reference=f"INT_{account_id}_{calculation_date}",
                    metadata={
                        "purchase_interest": str(purchase_interest.amount),
                        "cash_advance_interest": str(cash_advance_interest.amount),
                        "calculation_method": "average_daily_balance"
                    }
                )
            )
            
            return interest_transaction
        
        return None
    
    def _calculate_purchase_interest(self, account_id, statement, calculation_date):
        """Calculate interest on purchases (may have grace period)"""
        
        # If grace period is active, no interest on purchases
        if statement.grace_period_active:
            return Money(Decimal('0'), statement.current_balance.currency)
        
        # Get daily balances for purchase transactions
        daily_balances = self._get_daily_balances(
            account_id, TransactionCategory.PURCHASE,
            statement.statement_date, calculation_date
        )
        
        # Calculate average daily balance
        total_balance = sum(balance.amount for balance in daily_balances)
        average_daily_balance = total_balance / Decimal(len(daily_balances))
        
        # Apply annual percentage rate
        account = account_manager.get_account(account_id)
        annual_rate = account.interest_rate
        daily_rate = annual_rate / Decimal('365')
        
        days = len(daily_balances)
        interest_amount = average_daily_balance * daily_rate * Decimal(days)
        
        return Money(
            interest_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            statement.current_balance.currency
        )
    
    def _calculate_cash_advance_interest(self, account_id, statement, calculation_date):
        """Calculate interest on cash advances (no grace period)"""
        
        # Cash advances always accrue interest from transaction date
        cash_advance_transactions = transaction_processor.find_transactions(
            filters={
                "account_id": account_id,
                "transaction_type": TransactionType.CASH_ADVANCE,
                "transaction_date_gte": statement.statement_date,
                "transaction_date_lte": calculation_date
            }
        )
        
        total_interest = Money(Decimal('0'), statement.current_balance.currency)
        
        for transaction in cash_advance_transactions:
            days_accruing = (calculation_date - transaction.transaction_date).days
            if days_accruing > 0:
                # Cash advance rate is typically higher than purchase rate
                account = account_manager.get_account(account_id)
                cash_advance_rate = account.interest_rate + Decimal('0.05')  # +5% premium
                
                daily_rate = cash_advance_rate / Decimal('365')
                interest = transaction.amount.amount * daily_rate * Decimal(days_accruing)
                
                transaction_interest = Money(
                    interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                    transaction.amount.currency
                )
                
                total_interest += transaction_interest
        
        return total_interest
```

---

## Collection Workflow

### Automated Collection Process

```python
class CollectionWorkflow:
    """Manages the collection process for overdue loans and credit lines"""
    
    # Collection stages with escalation timeline
    COLLECTION_STAGES = [
        {"stage": "early_reminder", "days_past_due": 5, "priority": "low"},
        {"stage": "first_notice", "days_past_due": 15, "priority": "medium"},
        {"stage": "second_notice", "days_past_due": 30, "priority": "high"},
        {"stage": "final_notice", "days_past_due": 60, "priority": "critical"},
        {"stage": "legal_referral", "days_past_due": 90, "priority": "critical"},
    ]
    
    def process_daily_collections(self):
        """Daily batch job to identify and escalate collection cases"""
        
        # Find all overdue accounts
        overdue_loans = self._find_overdue_loans()
        overdue_credit_lines = self._find_overdue_credit_lines()
        
        for loan in overdue_loans:
            self._process_loan_collection(loan)
        
        for credit_line in overdue_credit_lines:
            self._process_credit_line_collection(credit_line)
    
    def _process_loan_collection(self, loan):
        """Process collection actions for an overdue loan"""
        
        days_past_due = loan.days_past_due
        
        # Find current collection case
        existing_case = collections_manager.get_active_case(
            loan_id=loan.id
        )
        
        # Determine appropriate collection stage
        current_stage = None
        for stage_info in reversed(self.COLLECTION_STAGES):
            if days_past_due >= stage_info["days_past_due"]:
                current_stage = stage_info
                break
        
        if not current_stage:
            return  # Not past due enough for collection action
        
        if existing_case:
            # Escalate existing case if needed
            if existing_case.stage != current_stage["stage"]:
                self._escalate_collection_case(existing_case, current_stage)
        else:
            # Create new collection case
            self._create_collection_case(loan, current_stage)
    
    def _create_collection_case(self, loan, stage_info):
        """Create a new collection case"""
        
        case = CollectionCase(
            id=str(uuid.uuid4()),
            loan_id=loan.id,
            credit_line_id=None,
            customer_id=loan.customer_id,
            case_type="overdue_loan",
            stage=stage_info["stage"],
            priority=stage_info["priority"],
            days_past_due=loan.days_past_due,
            outstanding_balance=loan.current_balance,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status="open"
        )
        
        # Assign to appropriate collector based on balance and priority
        collector = self._assign_collector(case)
        if collector:
            case.assigned_collector_id = collector.id
        
        # Save case
        collections_manager.save_case(case)
        
        # Execute collection actions for this stage
        self._execute_collection_actions(case)
        
        # Log collection case creation
        audit_trail.log_event(
            event_type=AuditEventType.COLLECTION_CASE_CREATED,
            entity_type="collection_case",
            entity_id=case.id,
            metadata={
                "loan_id": loan.id,
                "customer_id": loan.customer_id,
                "stage": stage_info["stage"],
                "days_past_due": loan.days_past_due,
                "outstanding_balance": str(loan.current_balance.amount)
            }
        )
        
        return case
    
    def _execute_collection_actions(self, case):
        """Execute appropriate collection actions based on stage"""
        
        customer = customer_manager.get_customer(case.customer_id)
        
        if case.stage == "early_reminder":
            # Send friendly reminder via preferred contact method
            notification_engine.send_notification(
                customer_id=case.customer_id,
                template="loan_payment_reminder",
                channels=["email", "sms"],
                data={
                    "customer_name": customer.full_name,
                    "days_past_due": case.days_past_due,
                    "outstanding_balance": str(case.outstanding_balance.amount),
                    "payment_url": f"https://portal.yourbank.com/pay/{case.loan_id}"
                }
            )
            
        elif case.stage == "first_notice":
            # Send formal first notice
            notification_engine.send_notification(
                customer_id=case.customer_id,
                template="collection_first_notice",
                channels=["email", "postal_mail"],
                data={
                    "customer_name": customer.full_name,
                    "account_number": case.loan_id,
                    "days_past_due": case.days_past_due,
                    "outstanding_balance": str(case.outstanding_balance.amount),
                    "minimum_payment": str(case.minimum_payment_due.amount),
                    "late_fees": str(case.late_fees.amount)
                }
            )
            
        elif case.stage == "second_notice":
            # Send second notice + phone call task
            notification_engine.send_notification(
                customer_id=case.customer_id,
                template="collection_second_notice",
                channels=["email", "postal_mail", "phone"]
            )
            
            # Create phone call task for collector
            self._create_collection_task(
                case_id=case.id,
                task_type="phone_call",
                due_date=date.today() + timedelta(days=2),
                notes="Attempt to contact customer regarding overdue account"
            )
            
        elif case.stage == "final_notice":
            # Send final notice before legal action
            notification_engine.send_notification(
                customer_id=case.customer_id,
                template="collection_final_notice",
                channels=["email", "postal_mail", "phone"],
                data={
                    "legal_action_date": (date.today() + timedelta(days=30)).isoformat(),
                    "settlement_offer": str(case.outstanding_balance.amount * Decimal('0.9'))
                }
            )
            
        elif case.stage == "legal_referral":
            # Refer to legal department/external agency
            self._refer_to_legal(case)
    
    def _assign_collector(self, case):
        """Assign case to appropriate collector based on business rules"""
        
        # Get available collectors
        collectors = rbac_manager.get_users_with_role("collector")
        
        if not collectors:
            return None
        
        # Assignment logic based on balance and experience
        if case.outstanding_balance.amount > Decimal('50000'):
            # High balance cases go to senior collectors
            senior_collectors = [c for c in collectors 
                               if c.metadata.get("experience_level") == "senior"]
            if senior_collectors:
                # Assign to collector with lowest current caseload
                return min(senior_collectors, 
                          key=lambda c: collections_manager.get_active_case_count(c.id))
        
        # Regular assignment - round robin or lowest caseload
        return min(collectors, 
                  key=lambda c: collections_manager.get_active_case_count(c.id))
    
    def _create_collection_task(self, case_id, task_type, due_date, notes=None):
        """Create a task for collector to complete"""
        
        task = CollectionTask(
            id=str(uuid.uuid4()),
            case_id=case_id,
            task_type=task_type,
            status="pending",
            due_date=due_date,
            notes=notes,
            created_at=datetime.now(timezone.utc)
        )
        
        collections_manager.save_task(task)
        return task
```

### Payment Plan Management

```python
class PaymentPlanManager:
    """Manages payment plans for customers in collections"""
    
    def create_payment_plan(self, case_id, monthly_payment, duration_months, 
                           start_date=None):
        """Create a payment plan for a collection case"""
        
        if start_date is None:
            start_date = date.today().replace(day=1) + timedelta(days=32)
            start_date = start_date.replace(day=1)  # First of next month
        
        case = collections_manager.get_case(case_id)
        loan = loan_manager.get_loan(case.loan_id) if case.loan_id else None
        
        # Validate payment plan parameters
        total_planned_payments = monthly_payment.amount * Decimal(str(duration_months))
        
        if total_planned_payments < case.outstanding_balance.amount:
            raise ValueError("Payment plan does not cover outstanding balance")
        
        # Create payment plan
        payment_plan = PaymentPlan(
            id=str(uuid.uuid4()),
            case_id=case_id,
            customer_id=case.customer_id,
            loan_id=case.loan_id,
            credit_line_id=case.credit_line_id,
            monthly_payment=monthly_payment,
            duration_months=duration_months,
            start_date=start_date,
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        # Generate payment schedule
        payment_schedule = []
        current_date = start_date
        
        for i in range(duration_months):
            scheduled_payment = ScheduledPayment(
                payment_plan_id=payment_plan.id,
                payment_number=i + 1,
                due_date=current_date,
                amount=monthly_payment,
                status="scheduled"
            )
            payment_schedule.append(scheduled_payment)
            
            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        payment_plan.payment_schedule = payment_schedule
        
        # Save payment plan
        collections_manager.save_payment_plan(payment_plan)
        
        # Update case status
        case.status = "payment_plan"
        case.payment_plan_id = payment_plan.id
        collections_manager.save_case(case)
        
        # Send payment plan confirmation to customer
        notification_engine.send_notification(
            customer_id=case.customer_id,
            template="payment_plan_confirmation",
            data={
                "monthly_payment": str(monthly_payment.amount),
                "duration_months": duration_months,
                "start_date": start_date.isoformat(),
                "total_amount": str(total_planned_payments),
                "first_payment_date": payment_schedule[0].due_date.isoformat()
            }
        )
        
        return payment_plan
    
    def process_payment_plan_payment(self, payment_plan_id, payment_amount, 
                                   payment_date=None):
        """Process a payment against a payment plan"""
        
        if payment_date is None:
            payment_date = date.today()
        
        payment_plan = collections_manager.get_payment_plan(payment_plan_id)
        if payment_plan.status != "active":
            raise ValueError("Payment plan is not active")
        
        # Find the next scheduled payment
        next_scheduled = None
        for scheduled_payment in payment_plan.payment_schedule:
            if scheduled_payment.status == "scheduled":
                next_scheduled = scheduled_payment
                break
        
        if not next_scheduled:
            raise ValueError("No scheduled payments remaining")
        
        with storage.atomic():
            # Process payment to the underlying loan or credit line
            if payment_plan.loan_id:
                loan_payment = process_loan_payment(
                    payment_plan.loan_id, payment_amount, payment_date
                )
            elif payment_plan.credit_line_id:
                credit_payment = process_credit_line_payment(
                    payment_plan.credit_line_id, payment_amount, payment_date
                )
            
            # Mark scheduled payment as paid
            next_scheduled.status = "paid"
            next_scheduled.paid_amount = payment_amount
            next_scheduled.paid_date = payment_date
            
            # Check if payment plan is complete
            remaining_scheduled = [p for p in payment_plan.payment_schedule 
                                 if p.status == "scheduled"]
            
            if not remaining_scheduled:
                # Payment plan complete
                payment_plan.status = "completed"
                payment_plan.completed_date = payment_date
                
                # Update collection case
                case = collections_manager.get_case(payment_plan.case_id)
                case.status = "resolved"
                case.resolution_method = "payment_plan_completed"
                case.resolved_date = payment_date
                collections_manager.save_case(case)
                
                # Send completion notification
                notification_engine.send_notification(
                    customer_id=payment_plan.customer_id,
                    template="payment_plan_completed",
                    data={
                        "completion_date": payment_date.isoformat()
                    }
                )
            
            # Save updated payment plan
            collections_manager.save_payment_plan(payment_plan)
            
            return {
                "scheduled_payment": next_scheduled,
                "payment_plan_status": payment_plan.status,
                "remaining_payments": len(remaining_scheduled)
            }
```

---

## Event-Driven Architecture

### Observer Pattern Implementation

Nexum uses an event-driven architecture where domain events are published and handled by multiple subscribers:

```python
# Example: Transaction processing triggers multiple events
def process_deposit_with_events(account_id, amount, description):
    """Process deposit and publish relevant events"""
    
    with storage.atomic():
        # Process the transaction
        transaction = transaction_processor.process_transaction(
            TransactionRequest(
                transaction_type=TransactionType.DEPOSIT,
                to_account_id=account_id,
                amount=amount,
                description=description
            )
        )
        
        # Publish domain event
        event_dispatcher.publish(
            DomainEvent.TRANSACTION_POSTED,
            EventPayload(
                event_type=DomainEvent.TRANSACTION_POSTED,
                entity_type="transaction",
                entity_id=transaction.id,
                data={
                    "account_id": account_id,
                    "transaction_type": "deposit",
                    "amount": str(amount.amount),
                    "currency": amount.currency.code,
                    "description": description,
                    "new_balance": str(transaction.new_balance.amount)
                }
            )
        )
        
        return transaction

# Event handlers for transaction posted
@event_dispatcher.subscribe(DomainEvent.TRANSACTION_POSTED)
def update_account_metrics(event_payload):
    """Update account activity metrics"""
    account_id = event_payload.data["account_id"]
    amount = Decimal(event_payload.data["amount"])
    
    # Update daily transaction count and volume
    metrics.increment("account_transactions", tags={
        "account_id": account_id,
        "transaction_type": event_payload.data["transaction_type"]
    })
    
    metrics.histogram("transaction_amount", amount, tags={
        "currency": event_payload.data["currency"]
    })

@event_dispatcher.subscribe(DomainEvent.TRANSACTION_POSTED)
def send_transaction_notification(event_payload):
    """Send transaction confirmation to customer"""
    account_id = event_payload.data["account_id"]
    
    # Get customer info
    account = account_manager.get_account(account_id)
    customer = customer_manager.get_customer(account.customer_id)
    
    # Send notification
    notification_engine.send_notification(
        customer_id=customer.id,
        template="transaction_confirmation",
        channels=["email", "push"],
        data=event_payload.data
    )

@event_dispatcher.subscribe(DomainEvent.TRANSACTION_POSTED)
def check_compliance_thresholds(event_payload):
    """Check if transaction triggers compliance reporting"""
    amount = Decimal(event_payload.data["amount"])
    
    # Check for large transaction reporting (CTR)
    if amount > Decimal('10000.00'):
        compliance_engine.create_ctr_report(
            transaction_id=event_payload.entity_id,
            amount=amount,
            customer_id=event_payload.data.get("customer_id")
        )
    
    # Check for suspicious activity patterns
    compliance_engine.analyze_transaction_patterns(
        account_id=event_payload.data["account_id"],
        transaction_id=event_payload.entity_id
    )

@event_dispatcher.subscribe(DomainEvent.TRANSACTION_POSTED)
def update_credit_score_factors(event_payload):
    """Update factors used in credit scoring"""
    if event_payload.data["transaction_type"] in ["loan_payment", "credit_payment"]:
        account_id = event_payload.data["account_id"]
        
        # Update payment history
        credit_scoring.update_payment_history(
            account_id=account_id,
            payment_amount=Decimal(event_payload.data["amount"]),
            payment_date=datetime.fromisoformat(event_payload.timestamp)
        )
```

### Integration with External Systems

```python
class KafkaEventPublisher:
    """Publishes domain events to Kafka for external system integration"""
    
    def __init__(self, kafka_config):
        from kafka import KafkaProducer
        import json
        
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_config.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',  # Wait for all replicas to acknowledge
            retries=3,
            batch_size=16384,
            linger_ms=10
        )
        self.topic_prefix = kafka_config.topic_prefix
    
    @event_dispatcher.subscribe(DomainEvent.TRANSACTION_POSTED)
    def publish_transaction_event(self, event_payload):
        """Publish transaction events to Kafka"""
        
        topic = f"{self.topic_prefix}.transactions.posted"
        key = event_payload.entity_id  # Partition by transaction ID
        
        kafka_message = {
            "event_id": event_payload.event_id,
            "event_type": event_payload.event_type.value,
            "timestamp": event_payload.timestamp.isoformat(),
            "entity_type": event_payload.entity_type,
            "entity_id": event_payload.entity_id,
            "data": event_payload.data,
            "source": "nexum-core-banking",
            "version": "1.0"
        }
        
        try:
            future = self.producer.send(topic, key=key, value=kafka_message)
            # Block for up to 60 seconds to ensure message is sent
            future.get(timeout=60)
        except Exception as e:
            logger.error(f"Failed to publish event to Kafka: {e}")
            # Consider dead letter queue or retry mechanism
    
    @event_dispatcher.subscribe(DomainEvent.CUSTOMER_CREATED)
    def publish_customer_event(self, event_payload):
        """Publish customer events for CRM integration"""
        
        topic = f"{self.topic_prefix}.customers.created"
        
        # Enrich with additional customer data
        customer = customer_manager.get_customer(event_payload.entity_id)
        
        enriched_data = event_payload.data.copy()
        enriched_data.update({
            "kyc_status": customer.kyc_status.value,
            "kyc_tier": customer.kyc_tier.value,
            "created_at": customer.created_at.isoformat()
        })
        
        kafka_message = {
            "event_id": event_payload.event_id,
            "event_type": "customer.created",
            "customer_id": event_payload.entity_id,
            "data": enriched_data,
            "source": "nexum-core-banking"
        }
        
        self.producer.send(topic, key=customer.id, value=kafka_message)
```

### Webhook Integration

```python
class WebhookDispatcher:
    """Sends domain events to registered webhook endpoints"""
    
    def __init__(self, webhook_config):
        self.webhooks = {}  # endpoint_url -> config
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    def register_webhook(self, endpoint_url, events, secret=None, headers=None):
        """Register webhook endpoint for specific events"""
        self.webhooks[endpoint_url] = {
            "events": events,
            "secret": secret,
            "headers": headers or {}
        }
    
    def _create_signature(self, payload, secret):
        """Create HMAC signature for webhook security"""
        import hmac
        import hashlib
        
        if not secret:
            return None
        
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    async def dispatch_event(self, event_payload):
        """Dispatch event to all registered webhooks"""
        
        webhook_payload = {
            "id": event_payload.event_id,
            "type": event_payload.event_type.value,
            "timestamp": event_payload.timestamp.isoformat(),
            "data": {
                "entity_type": event_payload.entity_type,
                "entity_id": event_payload.entity_id,
                **event_payload.data
            }
        }
        
        payload_json = json.dumps(webhook_payload, default=str)
        
        for endpoint_url, config in self.webhooks.items():
            if event_payload.event_type in config["events"]:
                await self._send_webhook(endpoint_url, config, payload_json)
    
    async def _send_webhook(self, endpoint_url, config, payload):
        """Send webhook HTTP request"""
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Nexum-Webhook/1.0",
            **config["headers"]
        }
        
        if config["secret"]:
            signature = self._create_signature(payload, config["secret"])
            headers["X-Nexum-Signature"] = signature
        
        try:
            response = await self.http_client.post(
                endpoint_url,
                data=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook delivered successfully to {endpoint_url}")
            else:
                logger.warning(f"Webhook delivery failed to {endpoint_url}: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Webhook delivery error to {endpoint_url}: {e}")
            # Consider retry mechanism or dead letter queue

# Register webhook handlers for events
@event_dispatcher.subscribe(DomainEvent.TRANSACTION_POSTED)
async def send_transaction_webhook(event_payload):
    await webhook_dispatcher.dispatch_event(event_payload)

@event_dispatcher.subscribe(DomainEvent.LOAN_PAYMENT)
async def send_loan_webhook(event_payload):
    await webhook_dispatcher.dispatch_event(event_payload)
```

---

## Notification Templates

### Template-Based Notification System

```python
class NotificationTemplate:
    """Template for notifications with multiple channel support"""
    
    def __init__(self, name, channels, subject_template, body_template, 
                 metadata=None):
        self.name = name
        self.channels = channels  # email, sms, push, postal_mail
        self.subject_template = subject_template
        self.body_template = body_template
        self.metadata = metadata or {}
    
    def render(self, data):
        """Render template with provided data"""
        from jinja2 import Template
        
        subject = Template(self.subject_template).render(**data)
        body = Template(self.body_template).render(**data)
        
        return {
            "subject": subject,
            "body": body,
            "channels": self.channels
        }

# Notification template library
NOTIFICATION_TEMPLATES = {
    "transaction_confirmation": NotificationTemplate(
        name="Transaction Confirmation",
        channels=["email", "push"],
        subject_template="Transaction Confirmation - {{transaction_type|title}} ${{amount}}",
        body_template="""
Dear {{customer_name}},

Your {{transaction_type}} of ${{amount}} has been successfully processed.

Transaction Details:
- Amount: ${{amount}} {{currency}}
- Account: {{account_name}}
- Date: {{transaction_date}}
- Reference: {{reference}}
- New Balance: ${{new_balance}}

Thank you for banking with us.

Best regards,
{{bank_name}}
        """.strip()
    ),
    
    "loan_payment_confirmation": NotificationTemplate(
        name="Loan Payment Confirmation",
        channels=["email", "sms"],
        subject_template="Loan Payment Received - ${{payment_amount}}",
        body_template="""
Dear {{customer_name}},

We have received your loan payment of ${{payment_amount}}.

Payment Breakdown:
- Principal: ${{principal_payment}}
- Interest: ${{interest_payment}}
- Remaining Balance: ${{remaining_balance}}
- Next Payment Due: {{next_payment_date}}

Payment Reference: {{payment_reference}}

Thank you for your payment.

{{bank_name}}
        """.strip()
    ),
    
    "account_low_balance": NotificationTemplate(
        name="Low Balance Alert",
        channels=["email", "sms", "push"],
        subject_template="Low Balance Alert - {{account_name}}",
        body_template="""
Dear {{customer_name}},

Your account {{account_name}} has a low balance.

Current Balance: ${{current_balance}}
Available Balance: ${{available_balance}}
Minimum Balance Required: ${{minimum_balance}}

{% if minimum_balance_fee %}
To avoid a ${{minimum_balance_fee}} fee, please deposit at least ${{deposit_needed}} by {{fee_assessment_date}}.
{% endif %}

You can make a deposit at any of our branches, ATMs, or through online banking.

{{bank_name}}
        """.strip()
    ),
    
    "kyc_verification_required": NotificationTemplate(
        name="KYC Verification Required",
        channels=["email"],
        subject_template="Action Required: Complete Account Verification",
        body_template="""
Dear {{customer_name}},

To continue using your {{account_type}} account, please complete the identity verification process.

Required Documents:
{% for document in required_documents %}
- {{document|title|replace("_", " ")}}
{% endfor %}

Upload documents online: {{verification_url}}

If you have questions, contact us at {{support_phone}} or {{support_email}}.

{{bank_name}} Compliance Team
        """.strip()
    ),
    
    "loan_approval": NotificationTemplate(
        name="Loan Approved",
        channels=["email", "postal_mail"],
        subject_template="Congratulations! Your loan has been approved",
        body_template="""
Dear {{customer_name}},

Congratulations! Your loan application has been approved.

Loan Details:
- Loan Amount: ${{loan_amount}}
- Interest Rate: {{interest_rate}}%
- Term: {{term_months}} months
- Monthly Payment: ${{monthly_payment}}
- First Payment Due: {{first_payment_date}}

Next Steps:
1. Review and sign your loan documents: {{document_signing_url}}
2. Funds will be disbursed within 1-2 business days after signing

If you have any questions, please contact your loan officer {{loan_officer_name}} at {{loan_officer_phone}}.

Thank you for choosing {{bank_name}}.

Best regards,
Lending Team
        """.strip()
    ),
    
    "payment_plan_confirmation": NotificationTemplate(
        name="Payment Plan Agreement",
        channels=["email", "postal_mail"],
        subject_template="Payment Plan Confirmation - Account {{account_number}}",
        body_template="""
Dear {{customer_name}},

This confirms your payment plan agreement for account {{account_number}}.

Payment Plan Details:
- Monthly Payment: ${{monthly_payment}}
- Payment Date: {{payment_day}} of each month
- Duration: {{duration_months}} months
- Total Amount: ${{total_amount}}
- First Payment Due: {{first_payment_date}}

Payment Methods:
- Online: {{payment_url}}
- Phone: {{payment_phone}}
- Mail: {{payment_address}}

Please ensure payments are received by the due date each month. Missing a payment may void this agreement.

Thank you for working with us to resolve your account.

Collections Department
{{bank_name}}
        """.strip()
    ),
    
    "credit_statement_available": NotificationTemplate(
        name="Credit Statement Available",
        channels=["email"],
        subject_template="Your credit statement is ready - Due {{due_date}}",
        body_template="""
Dear {{customer_name}},

Your credit statement for {{statement_period}} is now available.

Statement Summary:
- Previous Balance: ${{previous_balance}}
- New Charges: ${{new_charges}}
- Payments: ${{payments}}
- Current Balance: ${{current_balance}}
- Minimum Payment Due: ${{minimum_payment}}
- Payment Due Date: {{due_date}}
- Available Credit: ${{available_credit}}

{% if grace_period_active %}
Pay your full balance by {{due_date}} to avoid interest charges on new purchases.
{% endif %}

View your statement: {{statement_url}}
Make a payment: {{payment_url}}

Auto-pay is available to ensure you never miss a payment. Enroll online or call {{customer_service_phone}}.

{{bank_name}}
        """.strip()
    )
}

# Usage example
def send_transaction_notification(transaction, customer):
    template = NOTIFICATION_TEMPLATES["transaction_confirmation"]
    
    data = {
        "customer_name": customer.full_name,
        "transaction_type": transaction.transaction_type.value,
        "amount": str(transaction.amount.amount),
        "currency": transaction.currency.code,
        "account_name": transaction.account.name,
        "transaction_date": transaction.created_at.strftime("%B %d, %Y at %I:%M %p"),
        "reference": transaction.reference,
        "new_balance": str(transaction.new_balance.amount),
        "bank_name": "Your Bank Name"
    }
    
    rendered = template.render(data)
    
    # Send via multiple channels
    for channel in template.channels:
        notification_engine.send(
            recipient_id=customer.id,
            channel=channel,
            subject=rendered["subject"],
            body=rendered["body"]
        )
```

### Multi-Channel Notification Engine

```python
class NotificationEngine:
    """Manages notification delivery across multiple channels"""
    
    def __init__(self, config):
        self.email_provider = self._setup_email_provider(config)
        self.sms_provider = self._setup_sms_provider(config)
        self.push_provider = self._setup_push_provider(config)
        self.postal_provider = self._setup_postal_provider(config)
    
    def send_notification(self, customer_id, template_name, data=None, 
                         channels=None, priority="normal"):
        """Send notification using specified template"""
        
        data = data or {}
        customer = customer_manager.get_customer(customer_id)
        
        # Add customer data to template context
        data.update({
            "customer_name": customer.full_name,
            "customer_id": customer.id,
            "bank_name": "Your Bank Name",  # From config
            "support_phone": "(555) 123-4567",
            "support_email": "support@yourbank.com"
        })
        
        template = NOTIFICATION_TEMPLATES.get(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")
        
        rendered = template.render(data)
        
        # Use specified channels or template defaults
        channels_to_use = channels or template.channels
        
        results = {}
        for channel in channels_to_use:
            try:
                if channel == "email" and customer.email:
                    result = self._send_email(customer.email, rendered["subject"], 
                                            rendered["body"], priority)
                    results[channel] = result
                    
                elif channel == "sms" and customer.phone:
                    # SMS messages need to be shorter
                    sms_body = self._truncate_for_sms(rendered["body"])
                    result = self._send_sms(customer.phone, sms_body, priority)
                    results[channel] = result
                    
                elif channel == "push":
                    result = self._send_push_notification(customer.id, 
                                                        rendered["subject"],
                                                        rendered["body"], 
                                                        priority)
                    results[channel] = result
                    
                elif channel == "postal_mail" and customer.address:
                    result = self._send_postal_mail(customer, rendered["subject"],
                                                  rendered["body"])
                    results[channel] = result
                    
            except Exception as e:
                logger.error(f"Failed to send {channel} notification: {e}")
                results[channel] = {"status": "failed", "error": str(e)}
        
        # Log notification attempt
        self._log_notification(customer_id, template_name, channels_to_use, results)
        
        return results
    
    def _send_email(self, email_address, subject, body, priority):
        """Send email notification"""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        msg = MIMEMultipart()
        msg['From'] = self.email_config['from_address']
        msg['To'] = email_address
        msg['Subject'] = subject
        
        # Add priority header for urgent notifications
        if priority == "urgent":
            msg['X-Priority'] = '1'
            msg['X-MSMail-Priority'] = 'High'
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(self.email_config['smtp_host'], 
                         self.email_config['smtp_port']) as server:
            server.starttls()
            server.login(self.email_config['username'], 
                        self.email_config['password'])
            server.send_message(msg)
        
        return {"status": "sent", "message_id": msg['Message-ID']}
    
    def _send_sms(self, phone_number, message, priority):
        """Send SMS notification via Twilio"""
        from twilio.rest import Client
        
        client = Client(self.sms_config['account_sid'], 
                       self.sms_config['auth_token'])
        
        message = client.messages.create(
            body=message,
            from_=self.sms_config['from_number'],
            to=phone_number
        )
        
        return {"status": "sent", "message_sid": message.sid}
    
    def _truncate_for_sms(self, message, max_length=160):
        """Truncate message for SMS length limits"""
        if len(message) <= max_length:
            return message
        
        truncated = message[:max_length - 3] + "..."
        return truncated
```

---

## Multi-Tenant Deployment Patterns

### Tenant-Aware Database Access

```python
class TenantRoutingMiddleware:
    """Routes database operations to appropriate tenant context"""
    
    def __init__(self, storage_manager, isolation_strategy):
        self.storage_manager = storage_manager
        self.isolation_strategy = isolation_strategy
        
    async def __call__(self, request, call_next):
        tenant_id = await self._extract_tenant_id(request)
        
        if tenant_id:
            # Set tenant context for this request
            with tenant_context(tenant_id):
                # Apply tenant-specific storage configuration
                if self.isolation_strategy == TenantIsolationStrategy.SCHEMA_PER_TENANT:
                    self._set_database_schema(tenant_id)
                elif self.isolation_strategy == TenantIsolationStrategy.DATABASE_PER_TENANT:
                    self._set_database_connection(tenant_id)
                
                response = await call_next(request)
                return response
        else:
            # No tenant context - admin/super-user access
            response = await call_next(request)
            return response
    
    async def _extract_tenant_id(self, request):
        """Extract tenant ID from request"""
        # Method 1: HTTP Header
        tenant_id = request.headers.get('X-Tenant-ID')
        if tenant_id:
            return tenant_id
        
        # Method 2: Subdomain
        host = request.url.hostname
        if host and '.' in host:
            subdomain = host.split('.')[0]
            tenant = tenant_manager.get_tenant_by_code(subdomain.upper())
            if tenant:
                return tenant.id
        
        # Method 3: JWT claim
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
                return payload.get('tenant_id')
            except jwt.InvalidTokenError:
                pass
        
        return None
    
    def _set_database_schema(self, tenant_id):
        """Set PostgreSQL schema for tenant"""
        tenant = tenant_manager.get_tenant(tenant_id)
        if tenant and tenant.database_schema:
            # Switch to tenant-specific schema
            storage_manager.execute(f"SET search_path TO {tenant.database_schema}")
    
    def _set_database_connection(self, tenant_id):
        """Switch to tenant-specific database"""
        tenant = tenant_manager.get_tenant(tenant_id)
        if tenant and tenant.database_url:
            # Use tenant-specific connection
            storage_manager.set_connection(tenant.database_url)
```

### Tenant Resource Quotas

```python
class TenantQuotaManager:
    """Manages resource quotas and usage tracking per tenant"""
    
    def __init__(self, storage, redis_client=None):
        self.storage = storage
        self.redis = redis_client  # For real-time quota tracking
        
    def check_quota(self, tenant_id, resource_type, requested_amount=1):
        """Check if tenant can allocate requested resources"""
        tenant = tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return False
        
        quota_limits = {
            "users": tenant.max_users,
            "accounts": tenant.max_accounts,
            "transactions_per_day": tenant.max_daily_transactions,
            "api_calls_per_hour": tenant.max_api_calls_per_hour
        }
        
        limit = quota_limits.get(resource_type)
        if limit is None:
            return True  # No limit set
        
        current_usage = self._get_current_usage(tenant_id, resource_type)
        
        return current_usage + requested_amount <= limit
    
    def _get_current_usage(self, tenant_id, resource_type):
        """Get current resource usage for tenant"""
        if resource_type == "users":
            return self.storage.count_with_filters("users", {"tenant_id": tenant_id})
        
        elif resource_type == "accounts":
            return self.storage.count_with_filters("accounts", {"tenant_id": tenant_id})
        
        elif resource_type == "transactions_per_day":
            today = date.today()
            return self.storage.count_with_filters("transactions", {
                "tenant_id": tenant_id,
                "created_date": today
            })
        
        elif resource_type == "api_calls_per_hour":
            if self.redis:
                # Use Redis for real-time API call tracking
                hour_key = f"api_calls:{tenant_id}:{datetime.now().hour}"
                return int(self.redis.get(hour_key) or 0)
            else:
                # Fall back to database (less efficient)
                hour_ago = datetime.now() - timedelta(hours=1)
                return self.storage.count_with_filters("api_calls", {
                    "tenant_id": tenant_id,
                    "created_at_gte": hour_ago
                })
        
        return 0
    
    def increment_usage(self, tenant_id, resource_type, amount=1):
        """Increment resource usage counter"""
        if resource_type == "api_calls_per_hour" and self.redis:
            hour_key = f"api_calls:{tenant_id}:{datetime.now().hour}"
            self.redis.incr(hour_key, amount)
            self.redis.expire(hour_key, 3600)  # Expire after 1 hour
        
        # Log usage for billing/reporting
        usage_record = {
            "tenant_id": tenant_id,
            "resource_type": resource_type,
            "amount": amount,
            "timestamp": datetime.now()
        }
        self.storage.save("resource_usage", str(uuid.uuid4()), usage_record)

# Usage in API endpoints
@app.post("/accounts")
async def create_account(request: CreateAccountRequest, tenant_id: str = Depends(get_tenant_id)):
    
    # Check quota before creating account
    if not quota_manager.check_quota(tenant_id, "accounts", 1):
        raise HTTPException(
            status_code=429,
            detail="Account quota exceeded for this tenant"
        )
    
    # Proceed with account creation
    account = account_manager.create_account(request)
    
    # Increment usage counter
    quota_manager.increment_usage(tenant_id, "accounts", 1)
    
    return account
```

### Tenant Configuration Override

```python
class TenantConfigurationManager:
    """Manages tenant-specific configuration overrides"""
    
    def __init__(self, global_config, storage):
        self.global_config = global_config
        self.storage = storage
        self._config_cache = {}
    
    def get_tenant_config(self, tenant_id):
        """Get configuration for specific tenant with overrides"""
        
        # Check cache first
        if tenant_id in self._config_cache:
            return self._config_cache[tenant_id]
        
        # Start with global configuration
        tenant_config = self.global_config.copy()
        
        # Get tenant-specific overrides
        tenant = tenant_manager.get_tenant(tenant_id)
        if tenant and tenant.settings:
            # Apply tenant overrides
            tenant_config.update(tenant.settings)
        
        # Cache the configuration
        self._config_cache[tenant_id] = tenant_config
        
        return tenant_config
    
    def get_business_rule_config(self, tenant_id):
        """Get tenant-specific business rules"""
        config = self.get_tenant_config(tenant_id)
        
        return {
            "max_daily_transaction_limit": Money(
                Decimal(config.get("max_daily_transaction_limit", "10000.00")),
                Currency[config.get("default_currency", "USD")]
            ),
            "min_account_balance": Money(
                Decimal(config.get("min_account_balance", "0.00")),
                Currency[config.get("default_currency", "USD")]
            ),
            "allow_overdrafts": config.get("allow_overdrafts", False),
            "overdraft_limit": Money(
                Decimal(config.get("overdraft_limit", "0.00")),
                Currency[config.get("default_currency", "USD")]
            ),
            "overdraft_fee": Money(
                Decimal(config.get("overdraft_fee", "35.00")),
                Currency[config.get("default_currency", "USD")]
            ),
            "interest_calculation_method": config.get("interest_calculation_method", "daily_balance"),
            "grace_period_days": int(config.get("grace_period_days", "21")),
            "kyc_tier_required_for_accounts": KYCTier[config.get("kyc_tier_required", "TIER_1")]
        }

# Example tenant configurations
TENANT_CONFIGS = {
    "community_bank_portland": {
        "max_daily_transaction_limit": "5000.00",
        "min_account_balance": "25.00", 
        "allow_overdrafts": True,
        "overdraft_limit": "500.00",
        "overdraft_fee": "25.00",
        "default_currency": "USD",
        "interest_calculation_method": "average_balance",
        "kyc_tier_required": "TIER_2"
    },
    "microfinance_org": {
        "max_daily_transaction_limit": "1000.00",
        "min_account_balance": "10.00",
        "allow_overdrafts": False,
        "default_currency": "USD",
        "interest_calculation_method": "daily_balance",
        "kyc_tier_required": "TIER_1",
        "loan_default_grace_period": 7,  # 7 days instead of default 10
        "collection_escalation_days": 30  # Start collections after 30 days
    },
    "credit_union": {
        "max_daily_transaction_limit": "2500.00",
        "min_account_balance": "5.00",  # Member share account
        "allow_overdrafts": True,
        "overdraft_limit": "1000.00",
        "overdraft_fee": "20.00",  # Lower fee for members
        "default_currency": "USD",
        "member_benefits_active": True,
        "dividend_rate": "0.05",  # 5% dividends instead of interest
        "kyc_tier_required": "TIER_2"
    }
}
```

---

## Performance Tuning

### Database Optimization

```python
# Connection pooling configuration
DATABASE_POOL_CONFIG = {
    "min_connections": 5,
    "max_connections": 20,
    "max_inactive_connection_lifetime": 300,  # 5 minutes
    "max_connection_lifetime": 3600,  # 1 hour
    "connection_timeout": 30,  # 30 seconds
    "query_timeout": 60  # 1 minute
}

# Index optimization
RECOMMENDED_INDEXES = [
    # Customer indexes
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_customers_email ON customers(email)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_customers_phone ON customers(phone)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_customers_kyc_status ON customers(kyc_status, kyc_tier)",
    
    # Account indexes
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_accounts_customer_id ON accounts(customer_id)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_accounts_account_number ON accounts(account_number)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_accounts_status_type ON accounts(status, product_type)",
    
    # Transaction indexes
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_account_id_date ON transactions(account_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_type_status ON transactions(transaction_type, status)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_reference ON transactions(reference)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_idempotency ON transactions(idempotency_key)",
    
    # Journal entry indexes
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_journal_entries_reference ON journal_entries(reference)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_journal_entries_state_date ON journal_entries(state, created_at DESC)",
    
    # Loan indexes
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_loans_customer_id ON loans(customer_id)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_loans_state_due_date ON loans(state, next_payment_date)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_loans_days_past_due ON loans(days_past_due) WHERE days_past_due > 0",
    
    # Audit indexes
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_events_entity ON audit_events(entity_type, entity_id)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_events_type_date ON audit_events(event_type, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_events_user_date ON audit_events(user_id, created_at DESC)",
]

def optimize_database_performance():
    """Apply performance optimizations to database"""
    
    # Create recommended indexes
    for index_sql in RECOMMENDED_INDEXES:
        try:
            storage.execute(index_sql)
            print(f"Created index: {index_sql}")
        except Exception as e:
            print(f"Index creation failed: {e}")
    
    # Update table statistics
    storage.execute("ANALYZE;")
    
    # Configure PostgreSQL settings
    performance_settings = [
        "SET shared_buffers = '256MB'",  # Adjust based on available RAM
        "SET effective_cache_size = '1GB'",
        "SET maintenance_work_mem = '64MB'",
        "SET checkpoint_completion_target = 0.7",
        "SET wal_buffers = '16MB'",
        "SET default_statistics_target = 100"
    ]
    
    for setting in performance_settings:
        storage.execute(setting)
```

### Caching Strategy

```python
class PerformanceCache:
    """Multi-level caching for frequent operations"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.local_cache = {}  # In-memory cache
        self.cache_stats = {"hits": 0, "misses": 0}
    
    def get_account_balance(self, account_id, use_cache=True):
        """Get account balance with caching"""
        if not use_cache:
            return self._calculate_balance_from_ledger(account_id)
        
        # Check local cache first (fastest)
        cache_key = f"balance:{account_id}"
        
        if cache_key in self.local_cache:
            cached_data = self.local_cache[cache_key]
            if datetime.now() - cached_data["timestamp"] < timedelta(seconds=30):
                self.cache_stats["hits"] += 1
                return cached_data["balance"]
        
        # Check Redis cache (fast)
        if self.redis:
            cached_balance = self.redis.get(cache_key)
            if cached_balance:
                balance = Money.from_string(cached_balance.decode())
                # Update local cache
                self.local_cache[cache_key] = {
                    "balance": balance,
                    "timestamp": datetime.now()
                }
                self.cache_stats["hits"] += 1
                return balance
        
        # Cache miss - calculate from ledger
        self.cache_stats["misses"] += 1
        balance = self._calculate_balance_from_ledger(account_id)
        
        # Update caches
        if self.redis:
            self.redis.setex(cache_key, 300, str(balance))  # 5 minute TTL
        
        self.local_cache[cache_key] = {
            "balance": balance,
            "timestamp": datetime.now()
        }
        
        return balance
    
    def invalidate_account_cache(self, account_id):
        """Invalidate cached data when account is updated"""
        cache_key = f"balance:{account_id}"
        
        # Remove from local cache
        self.local_cache.pop(cache_key, None)
        
        # Remove from Redis
        if self.redis:
            self.redis.delete(cache_key)
    
    def get_customer_profile(self, customer_id):
        """Get customer profile with caching"""
        cache_key = f"customer:{customer_id}"
        
        if self.redis:
            cached_data = self.redis.get(cache_key)
            if cached_data:
                return json.loads(cached_data.decode())
        
        # Load from database
        customer = customer_manager.get_customer(customer_id)
        if customer:
            customer_data = customer.to_dict()
            
            # Cache for 10 minutes
            if self.redis:
                self.redis.setex(cache_key, 600, json.dumps(customer_data, default=str))
            
            return customer_data
        
        return None
```

### Query Optimization

```python
class OptimizedQueries:
    """Optimized database queries for common operations"""
    
    def get_account_transaction_summary(self, account_id, days=30):
        """Get transaction summary using optimized query"""
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Single query with aggregation instead of multiple queries
        query = """
        SELECT 
            transaction_type,
            COUNT(*) as transaction_count,
            SUM(CASE WHEN transaction_type IN ('deposit', 'credit') THEN amount ELSE 0 END) as total_credits,
            SUM(CASE WHEN transaction_type IN ('withdrawal', 'debit') THEN amount ELSE 0 END) as total_debits,
            AVG(amount) as avg_amount,
            MAX(amount) as max_amount,
            MIN(amount) as min_amount
        FROM transactions 
        WHERE account_id = %s 
          AND created_at >= %s
          AND status = 'completed'
        GROUP BY transaction_type
        ORDER BY transaction_count DESC
        """
        
        result = storage.execute(query, (account_id, cutoff_date))
        return result.fetchall()
    
    def get_overdue_loans_batch(self, limit=1000):
        """Get overdue loans efficiently for batch processing"""
        
        # Use window functions to avoid N+1 queries
        query = """
        SELECT 
            l.*,
            c.first_name,
            c.last_name,
            c.email,
            c.phone,
            ROW_NUMBER() OVER (ORDER BY l.days_past_due DESC, l.current_balance DESC) as priority_rank
        FROM loans l
        JOIN customers c ON l.customer_id = c.id
        WHERE l.days_past_due > 0
          AND l.state = 'active'
        ORDER BY l.days_past_due DESC, l.current_balance DESC
        LIMIT %s
        """
        
        return storage.execute(query, (limit,)).fetchall()
    
    def get_monthly_account_statements(self, account_ids, month, year):
        """Generate monthly statements efficiently"""
        
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)
        
        # Single query to get all transaction data needed for statements
        query = """
        SELECT 
            t.account_id,
            t.transaction_type,
            t.amount,
            t.description,
            t.created_at,
            a.name as account_name,
            a.product_type,
            c.first_name,
            c.last_name,
            c.address
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        JOIN customers c ON a.customer_id = c.id
        WHERE t.account_id = ANY(%s)
          AND t.created_at >= %s
          AND t.created_at < %s
          AND t.status = 'completed'
        ORDER BY t.account_id, t.created_at
        """
        
        return storage.execute(query, (account_ids, start_date, end_date)).fetchall()
```

### Async Processing for Heavy Operations

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class AsyncTaskManager:
    """Manages heavy operations asynchronously"""
    
    def __init__(self, max_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.background_tasks = set()
    
    async def process_bulk_transactions(self, transactions):
        """Process multiple transactions in parallel"""
        
        # Split into chunks for parallel processing
        chunk_size = 50
        chunks = [transactions[i:i+chunk_size] for i in range(0, len(transactions), chunk_size)]
        
        # Process chunks in parallel
        tasks = []
        for chunk in chunks:
            task = asyncio.create_task(self._process_transaction_chunk(chunk))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    async def _process_transaction_chunk(self, transactions):
        """Process a chunk of transactions"""
        
        def process_chunk():
            results = []
            with storage.atomic():
                for transaction_data in transactions:
                    try:
                        result = transaction_processor.process_transaction(transaction_data)
                        results.append({"status": "success", "transaction_id": result.id})
                    except Exception as e:
                        results.append({"status": "error", "error": str(e)})
            return results
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, process_chunk)
    
    def schedule_background_task(self, coro):
        """Schedule a background task"""
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        return task
    
    async def generate_monthly_statements_async(self, month, year):
        """Generate monthly statements asynchronously"""
        
        def generate_statements():
            # Get all active accounts
            active_accounts = account_manager.get_active_accounts()
            
            statement_results = []
            for account in active_accounts:
                try:
                    if account.product_type == ProductType.CREDIT_LINE:
                        statement = credit_manager.generate_statement(account.id, month, year)
                        statement_results.append({"account_id": account.id, "statement": statement})
                except Exception as e:
                    logger.error(f"Failed to generate statement for account {account.id}: {e}")
                    statement_results.append({"account_id": account.id, "error": str(e)})
            
            return statement_results
        
        # Run in background thread
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, generate_statements)

# Usage in FastAPI endpoint
@app.post("/transactions/bulk")
async def process_bulk_transactions(transactions: List[CreateTransactionRequest]):
    task_manager = AsyncTaskManager()
    
    # Process transactions asynchronously
    results = await task_manager.process_bulk_transactions(transactions)
    
    return {
        "processed_count": len(results),
        "results": results
    }
```

This comprehensive best practices guide covers the essential patterns and techniques for building and operating a production-grade core banking system with Nexum, following industry standards and regulatory requirements.