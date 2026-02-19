# Collections Module

The collections module manages delinquent accounts and implements automated collection strategies to maximize recovery while maintaining regulatory compliance. It provides comprehensive tools for monitoring delinquency, executing collection actions, and tracking recovery performance.

## Overview

The collections system handles the complete delinquency management lifecycle:

- **Delinquency Detection**: Automated scanning for past-due accounts
- **Strategy Assignment**: Rule-based assignment of collection strategies
- **Action Execution**: Automated and manual collection actions
- **Promise Tracking**: Payment promise management and monitoring
- **Recovery Analytics**: Performance metrics and reporting

## Key Concepts

### Delinquency Buckets
Accounts are categorized by days past due:
- **Current**: 0 days past due
- **1-30 Days**: Early stage delinquency
- **31-60 Days**: Moderate delinquency
- **61-90 Days**: Serious delinquency
- **90+ Days**: Severe delinquency (charge-off consideration)

### Collection Strategies
Rules-based approaches that define:
- Which actions to take at which delinquency stages
- Communication frequency and channels
- Escalation triggers
- Settlement authorization levels

### Auto-Actions
System-driven collection activities that execute automatically based on configured rules and triggers.

## Core Classes

### CollectionCase

Represents a delinquent account under collection management:

```python
from core_banking.collections import CollectionCase, CollectionStatus
from core_banking.currency import Money, Currency
from datetime import date
from decimal import Decimal

@dataclass
class CollectionCase(StorageRecord):
    account_id: str
    customer_id: str
    loan_id: Optional[str] = None
    
    # Delinquency information
    days_past_due: int
    amount_past_due: Money
    total_balance: Money
    last_payment_date: Optional[date]
    
    # Case management
    status: CollectionStatus
    assigned_collector: Optional[str] = None
    strategy_id: Optional[str] = None
    priority_score: int = 0  # 1-100, higher = more urgent
    
    # Contact tracking
    last_contact_date: Optional[date] = None
    contact_attempts: int = 0
    successful_contacts: int = 0
    
    # Promise tracking
    active_promise_id: Optional[str] = None
    promises_made: int = 0
    promises_kept: int = 0
    promises_broken: int = 0
    
    # Resolution tracking
    resolved_date: Optional[date] = None
    resolution_type: Optional[str] = None
    recovery_amount: Money = None
    
    def __post_init__(self):
        if self.recovery_amount is None:
            self.recovery_amount = Money(Decimal('0'), self.amount_past_due.currency)
    
    @property
    def delinquency_bucket(self) -> str:
        """Get delinquency bucket based on days past due"""
        if self.days_past_due <= 30:
            return "1-30"
        elif self.days_past_due <= 60:
            return "31-60"
        elif self.days_past_due <= 90:
            return "61-90"
        else:
            return "90+"
    
    @property
    def contact_rate(self) -> Decimal:
        """Calculate successful contact rate"""
        if self.contact_attempts == 0:
            return Decimal('0')
        return Decimal(self.successful_contacts) / Decimal(self.contact_attempts)
    
    @property
    def promise_keep_rate(self) -> Decimal:
        """Calculate promise keeping rate"""
        if self.promises_made == 0:
            return Decimal('0')
        return Decimal(self.promises_kept) / Decimal(self.promises_made)
```

### CollectionStrategy

Defines the collection approach for different account types:

```python
from core_banking.collections import CollectionStrategy, CollectionAction

@dataclass
class CollectionStrategy(StorageRecord):
    name: str
    description: str
    
    # Targeting criteria
    min_balance: Money
    max_balance: Money
    min_days_past_due: int
    max_days_past_due: int
    account_types: List[str]
    customer_segments: List[str]
    
    # Strategy configuration
    actions: List[CollectionAction]
    auto_assign: bool = True
    requires_supervisor_approval: bool = False
    
    # Performance tracking
    cases_assigned: int = 0
    total_recovery: Money = None
    
    def __post_init__(self):
        if self.total_recovery is None:
            self.total_recovery = Money(Decimal('0'), Currency.USD)

# Example collection strategy
early_stage_strategy = CollectionStrategy(
    name="Early Stage Personal Loans",
    description="Automated outreach for 1-30 day delinquent personal loans",
    min_balance=Money(Decimal("100.00"), Currency.USD),
    max_balance=Money(Decimal("50000.00"), Currency.USD),
    min_days_past_due=1,
    max_days_past_due=30,
    account_types=["personal_loan"],
    customer_segments=["prime", "near_prime"],
    actions=[
        CollectionAction(
            action_type="sms",
            trigger_days=1,
            message_template="payment_reminder_sms",
            frequency_days=3,
            max_attempts=3
        ),
        CollectionAction(
            action_type="email",
            trigger_days=5,
            message_template="payment_reminder_email",
            frequency_days=7,
            max_attempts=2
        ),
        CollectionAction(
            action_type="phone_call",
            trigger_days=10,
            frequency_days=7,
            max_attempts=5,
            requires_human=True
        )
    ],
    auto_assign=True
)
```

### PaymentPromise

Tracks customer payment commitments:

```python
from core_banking.collections import PaymentPromise, PromiseStatus

@dataclass
class PaymentPromise(StorageRecord):
    case_id: str
    customer_id: str
    
    # Promise details
    promised_amount: Money
    promised_date: date
    partial_payment_acceptable: bool = False
    
    # Status tracking
    status: PromiseStatus = PromiseStatus.ACTIVE
    actual_payment_amount: Money = None
    actual_payment_date: Optional[date] = None
    
    # Follow-up
    reminder_sent: bool = False
    reminder_date: Optional[date] = None
    collector_notes: str = ""
    
    def __post_init__(self):
        if self.actual_payment_amount is None:
            self.actual_payment_amount = Money(Decimal('0'), self.promised_amount.currency)
    
    @property
    def is_kept(self) -> bool:
        """Check if promise was kept"""
        if self.status != PromiseStatus.FULFILLED:
            return False
        
        # Promise is kept if payment was made by promised date
        if not self.actual_payment_date or self.actual_payment_date > self.promised_date:
            return False
        
        # Check amount (allow partial if acceptable)
        if self.partial_payment_acceptable:
            return self.actual_payment_amount > Money(Decimal('0'), self.promised_amount.currency)
        else:
            return self.actual_payment_amount >= self.promised_amount
    
    @property
    def days_until_due(self) -> int:
        """Days until promise is due"""
        return (self.promised_date - date.today()).days
```

## Collection Management

### CollectionManager

Main interface for collection operations:

```python
from core_banking.collections import CollectionManager

class CollectionManager:
    def __init__(self, storage: StorageInterface, loan_manager, credit_manager):
        self.storage = storage
        self.loan_manager = loan_manager
        self.credit_manager = credit_manager
    
    def scan_for_delinquent_accounts(self, as_of_date: date) -> List[CollectionCase]:
        """Scan all accounts for delinquency and create collection cases"""
        
        cases = []
        
        # Scan loans
        delinquent_loans = self.loan_manager.get_delinquent_loans(as_of_date)
        for loan in delinquent_loans:
            if not self.has_active_case(loan.account_id):
                case = self.create_collection_case_from_loan(loan, as_of_date)
                cases.append(case)
        
        # Scan credit lines
        delinquent_credit = self.credit_manager.get_delinquent_accounts(as_of_date)
        for account in delinquent_credit:
            if not self.has_active_case(account.id):
                case = self.create_collection_case_from_credit(account, as_of_date)
                cases.append(case)
        
        return cases
    
    def create_collection_case_from_loan(self, loan, as_of_date: date) -> CollectionCase:
        """Create collection case from delinquent loan"""
        
        # Calculate past due amount (missed payments)
        schedule = self.loan_manager.get_payment_schedule(loan.id)
        past_due_amount = self.calculate_past_due_amount(loan, schedule, as_of_date)
        
        case = CollectionCase(
            account_id=loan.account_id,
            customer_id=loan.customer_id,
            loan_id=loan.id,
            days_past_due=loan.days_past_due,
            amount_past_due=past_due_amount,
            total_balance=loan.current_balance,
            last_payment_date=loan.last_payment_date,
            status=CollectionStatus.OPEN,
            priority_score=self.calculate_priority_score(loan, past_due_amount)
        )
        
        # Auto-assign strategy
        strategy = self.find_matching_strategy(case)
        if strategy:
            case.strategy_id = strategy.id
            case.assigned_collector = self.assign_collector(strategy)
        
        self.storage.store(case)
        
        # Log case creation
        self.audit.log_event(
            AuditEventType.COLLECTION_CASE_CREATED,
            entity_id=case.id,
            details={
                "account_id": loan.account_id,
                "days_past_due": loan.days_past_due,
                "amount_past_due": str(past_due_amount.amount)
            }
        )
        
        return case
```

## Collection Actions

### Automated Actions

```python
def execute_auto_actions(case_id: str, execution_date: date) -> List[CollectionActionResult]:
    """Execute automated collection actions for a case"""
    
    case = self.get_case(case_id)
    strategy = self.get_strategy(case.strategy_id) if case.strategy_id else None
    
    if not strategy:
        return []
    
    results = []
    
    for action in strategy.actions:
        # Check if action should be triggered
        if not self.should_trigger_action(case, action, execution_date):
            continue
        
        # Check if action has exceeded max attempts
        if self.get_action_attempt_count(case.id, action.action_type) >= action.max_attempts:
            continue
        
        # Execute the action
        result = self.execute_action(case, action, execution_date)
        results.append(result)
        
        # Log action
        self.log_collection_action(case, action, result)
    
    return results

def execute_action(
    case: CollectionCase, 
    action: CollectionAction, 
    execution_date: date
) -> CollectionActionResult:
    """Execute a specific collection action"""
    
    if action.action_type == "sms":
        return self.send_sms_reminder(case, action.message_template)
    
    elif action.action_type == "email":
        return self.send_email_reminder(case, action.message_template)
    
    elif action.action_type == "phone_call":
        if action.requires_human:
            return self.schedule_collector_call(case)
        else:
            return self.make_automated_call(case, action.message_template)
    
    elif action.action_type == "letter":
        return self.generate_collection_letter(case, action.message_template)
    
    elif action.action_type == "hold_placement":
        return self.place_account_hold(case.account_id, action.hold_type)
    
    elif action.action_type == "escalate":
        return self.escalate_case(case, action.escalation_level)
    
    else:
        raise ValueError(f"Unknown action type: {action.action_type}")
```

### Communication Templates

```python
class MessageTemplates:
    """Collection message templates"""
    
    SMS_TEMPLATES = {
        "payment_reminder_sms": (
            "Reminder: Your payment of ${amount} was due on {due_date}. "
            "Please make your payment today to avoid additional fees. "
            "Call {phone} or visit {website}"
        ),
        "promise_reminder_sms": (
            "Reminder: You promised to pay ${amount} by {date}. "
            "Please make your payment today. Call {phone} with questions."
        ),
        "final_notice_sms": (
            "FINAL NOTICE: Your account is seriously delinquent. "
            "Pay ${amount} immediately or face collection action. Call {phone}"
        )
    }
    
    EMAIL_TEMPLATES = {
        "payment_reminder_email": {
            "subject": "Payment Reminder - Account {account_number}",
            "body": """
Dear {customer_name},

This is a reminder that your payment of ${amount_due} was due on {due_date} 
and has not been received.

Current Account Status:
- Account Number: {account_number}
- Amount Past Due: ${amount_past_due}
- Days Past Due: {days_past_due}
- Total Balance: ${total_balance}

To make a payment or discuss payment options, please:
- Call us at {phone}
- Visit our website at {website}
- Mail payment to {mailing_address}

We're here to help. Please contact us to discuss payment arrangements.

Sincerely,
Collections Department
            """
        }
    }

def send_sms_reminder(case: CollectionCase, template_key: str) -> CollectionActionResult:
    """Send SMS collection reminder"""
    
    customer = self.customer_manager.get_customer(case.customer_id)
    
    if not customer.phone:
        return CollectionActionResult(
            success=False,
            error="No phone number on file"
        )
    
    # Get message template
    template = MessageTemplates.SMS_TEMPLATES.get(template_key)
    if not template:
        raise ValueError(f"Unknown SMS template: {template_key}")
    
    # Substitute variables
    message = template.format(
        amount=str(case.amount_past_due.amount),
        due_date=case.last_payment_date.strftime("%m/%d/%Y") if case.last_payment_date else "N/A",
        phone="1-800-BANK-123",
        website="www.nexumbank.com/payments"
    )
    
    # Send SMS via external service
    result = self.sms_service.send_message(customer.phone, message)
    
    # Update case contact tracking
    case.contact_attempts += 1
    case.last_contact_date = date.today()
    
    if result.delivered:
        case.successful_contacts += 1
    
    self.storage.update(case.id, case)
    
    return CollectionActionResult(
        success=result.delivered,
        action_type="sms",
        contact_method=customer.phone,
        response=result.response_code
    )
```

## Promise Management

```python
def record_payment_promise(
    case_id: str,
    promised_amount: Money,
    promised_date: date,
    collector_notes: str = "",
    partial_acceptable: bool = False
) -> PaymentPromise:
    """Record customer payment promise"""
    
    case = self.get_case(case_id)
    
    # Deactivate any existing active promise
    existing_promise = self.get_active_promise(case_id)
    if existing_promise:
        existing_promise.status = PromiseStatus.SUPERSEDED
        self.storage.update(existing_promise.id, existing_promise)
    
    # Create new promise
    promise = PaymentPromise(
        case_id=case_id,
        customer_id=case.customer_id,
        promised_amount=promised_amount,
        promised_date=promised_date,
        partial_payment_acceptable=partial_acceptable,
        collector_notes=collector_notes
    )
    
    self.storage.store(promise)
    
    # Update case
    case.active_promise_id = promise.id
    case.promises_made += 1
    self.storage.update(case_id, case)
    
    # Schedule reminder
    self.schedule_promise_reminder(promise)
    
    return promise

def check_promise_fulfillment(promise_id: str, check_date: date) -> bool:
    """Check if payment promise was fulfilled"""
    
    promise = self.get_promise(promise_id)
    case = self.get_case(promise.case_id)
    
    # Look for payments made since promise date
    payments = self.get_payments_since_date(case.account_id, promise.promised_date)
    
    total_payments = sum(p.amount for p in payments)
    
    # Check if promise was fulfilled
    if total_payments >= promise.promised_amount:
        promise.status = PromiseStatus.FULFILLED
        promise.actual_payment_amount = total_payments
        promise.actual_payment_date = max(p.payment_date for p in payments)
        
        # Update case
        case.promises_kept += 1
        case.active_promise_id = None
        
        # Consider case for resolution if fully current
        if self.is_account_current(case.account_id):
            self.resolve_case(case.id, "promise_fulfilled", total_payments)
    
    elif check_date > promise.promised_date:
        # Promise is broken
        promise.status = PromiseStatus.BROKEN
        case.promises_broken += 1
        case.active_promise_id = None
        
        # Escalate case for broken promise
        self.escalate_case_for_broken_promise(case)
    
    self.storage.update(promise.id, promise)
    self.storage.update(case.id, case)
    
    return promise.status == PromiseStatus.FULFILLED
```

## Strategy Management

```python
def assign_collection_strategy(case: CollectionCase) -> Optional[CollectionStrategy]:
    """Assign appropriate collection strategy to case"""
    
    strategies = self.get_active_strategies()
    
    for strategy in strategies:
        if self.strategy_matches_case(strategy, case):
            case.strategy_id = strategy.id
            
            # Auto-assign collector if strategy allows
            if strategy.auto_assign:
                collector = self.assign_collector(strategy)
                case.assigned_collector = collector
            
            self.storage.update(case.id, case)
            
            # Update strategy statistics
            strategy.cases_assigned += 1
            self.storage.update(strategy.id, strategy)
            
            return strategy
    
    return None

def strategy_matches_case(strategy: CollectionStrategy, case: CollectionCase) -> bool:
    """Check if strategy criteria match the case"""
    
    # Check balance range
    if (case.total_balance < strategy.min_balance or 
        case.total_balance > strategy.max_balance):
        return False
    
    # Check days past due
    if (case.days_past_due < strategy.min_days_past_due or 
        case.days_past_due > strategy.max_days_past_due):
        return False
    
    # Check account type
    account = self.account_manager.get_account(case.account_id)
    if account.product_type.value not in strategy.account_types:
        return False
    
    # Check customer segment
    customer = self.customer_manager.get_customer(case.customer_id)
    customer_segment = self.get_customer_segment(customer)
    if customer_segment not in strategy.customer_segments:
        return False
    
    return True
```

## Recovery Analytics

```python
def generate_collection_performance_report(
    start_date: date,
    end_date: date
) -> CollectionPerformanceReport:
    """Generate comprehensive collection performance report"""
    
    cases = self.get_cases_in_period(start_date, end_date)
    
    report = CollectionPerformanceReport()
    
    # Overall metrics
    report.total_cases = len(cases)
    report.total_balance_placed = sum(case.total_balance for case in cases)
    report.total_past_due_placed = sum(case.amount_past_due for case in cases)
    
    # Resolution metrics
    resolved_cases = [case for case in cases if case.status == CollectionStatus.RESOLVED]
    report.cases_resolved = len(resolved_cases)
    report.resolution_rate = Decimal(len(resolved_cases)) / Decimal(len(cases)) if cases else Decimal('0')
    
    # Recovery metrics
    report.total_recovered = sum(case.recovery_amount for case in resolved_cases)
    report.recovery_rate = (report.total_recovered / report.total_past_due_placed 
                           if not report.total_past_due_placed.is_zero() else Decimal('0'))
    
    # Contact metrics
    total_attempts = sum(case.contact_attempts for case in cases)
    total_successful = sum(case.successful_contacts for case in cases)
    report.overall_contact_rate = (Decimal(total_successful) / Decimal(total_attempts) 
                                  if total_attempts > 0 else Decimal('0'))
    
    # Promise metrics
    total_promises = sum(case.promises_made for case in cases)
    total_kept = sum(case.promises_kept for case in cases)
    report.promise_keep_rate = (Decimal(total_kept) / Decimal(total_promises) 
                               if total_promises > 0 else Decimal('0'))
    
    # Strategy performance
    report.strategy_performance = self.analyze_strategy_performance(cases)
    
    # Aging analysis
    report.aging_analysis = self.analyze_portfolio_aging(cases)
    
    return report

def calculate_recovery_roi(strategy_id: str, period_months: int = 12) -> Decimal:
    """Calculate return on investment for collection strategy"""
    
    strategy = self.get_strategy(strategy_id)
    end_date = date.today()
    start_date = end_date.replace(month=end_date.month - period_months)
    
    # Get cases assigned to this strategy
    cases = self.get_cases_by_strategy(strategy_id, start_date, end_date)
    
    # Calculate total recovery
    total_recovery = sum(case.recovery_amount for case in cases 
                        if case.status == CollectionStatus.RESOLVED)
    
    # Estimate collection costs (simplified)
    cost_per_case = Decimal('50.00')  # Average cost per case
    total_costs = len(cases) * cost_per_case
    
    # Calculate ROI
    if total_costs > 0:
        roi = ((total_recovery.amount - total_costs) / total_costs) * 100
    else:
        roi = Decimal('0')
    
    return roi
```

## Compliance and Regulation

```python
class ComplianceTracker:
    """Track compliance with collection regulations"""
    
    def validate_collection_action(
        self, 
        case: CollectionCase, 
        action: CollectionAction
    ) -> ComplianceValidationResult:
        """Validate collection action against regulations"""
        
        issues = []
        
        # FDCPA compliance checks
        if action.action_type == "phone_call":
            # No calls before 8 AM or after 9 PM customer's time
            customer = self.customer_manager.get_customer(case.customer_id)
            if not self.is_valid_call_time(customer.timezone):
                issues.append("Call outside permitted hours (8 AM - 9 PM)")
        
        # TCPA compliance for SMS/calls
        if action.action_type in ["sms", "phone_call"]:
            if not self.has_valid_consent(case.customer_id, action.action_type):
                issues.append(f"No valid consent for {action.action_type}")
        
        # Frequency limits
        recent_actions = self.get_recent_actions(case.id, days=7)
        if len(recent_actions) >= 3:  # Max 3 contacts per week
            issues.append("Excessive contact frequency")
        
        # State-specific regulations
        customer = self.customer_manager.get_customer(case.customer_id)
        state_issues = self.check_state_regulations(customer.address.state, action)
        issues.extend(state_issues)
        
        return ComplianceValidationResult(
            is_compliant=len(issues) == 0,
            issues=issues
        )
    
    def is_valid_call_time(self, customer_timezone: str) -> bool:
        """Check if current time is valid for debt collection calls"""
        import pytz
        
        customer_tz = pytz.timezone(customer_timezone)
        customer_time = datetime.now(customer_tz).time()
        
        return time(8, 0) <= customer_time <= time(21, 0)
```

## Testing Collection Strategies

```python
def test_collection_case_creation():
    """Test collection case creation from delinquent loan"""
    
    # Create delinquent loan
    loan = create_test_loan(days_past_due=15)
    
    # Scan for delinquency
    cases = collection_manager.scan_for_delinquent_accounts(date.today())
    
    # Should create case for delinquent loan
    assert len(cases) == 1
    case = cases[0]
    
    assert case.account_id == loan.account_id
    assert case.days_past_due == 15
    assert case.status == CollectionStatus.OPEN
    
def test_payment_promise_tracking():
    """Test payment promise creation and tracking"""
    
    case = create_test_collection_case()
    
    # Record promise
    promise = collection_manager.record_payment_promise(
        case_id=case.id,
        promised_amount=Money(Decimal("500.00"), Currency.USD),
        promised_date=date.today() + timedelta(days=7)
    )
    
    assert promise.status == PromiseStatus.ACTIVE
    assert case.promises_made == 1
    
    # Simulate payment
    make_test_payment(case.account_id, Money(Decimal("500.00"), Currency.USD))
    
    # Check promise fulfillment
    fulfilled = collection_manager.check_promise_fulfillment(promise.id, date.today())
    
    assert fulfilled
    assert promise.status == PromiseStatus.FULFILLED

def test_strategy_assignment():
    """Test automatic strategy assignment"""
    
    # Create case that matches strategy criteria
    case = create_test_case_for_strategy()
    
    # Should auto-assign matching strategy
    strategy = collection_manager.assign_collection_strategy(case)
    
    assert strategy is not None
    assert case.strategy_id == strategy.id
    
    if strategy.auto_assign:
        assert case.assigned_collector is not None
```

The collections module provides comprehensive delinquency management with automated workflows, regulatory compliance, and detailed performance tracking to maximize recovery while maintaining customer relationships.