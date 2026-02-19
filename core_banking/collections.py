"""
Collections Management Module

Handles delinquent loans and credit lines, collection activities, promises to pay,
and automated collection strategies.
"""

from decimal import Decimal
from datetime import datetime, timezone, date, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import uuid

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType
from .loans import LoanManager, Loan, LoanState
from .credit import CreditLineManager
from .accounts import AccountManager


class DelinquencyStatus(Enum):
    """Delinquency status categories"""
    CURRENT = "current"                 # 0 days past due
    EARLY = "early"                     # 1-30 days past due
    LATE = "late"                       # 31-60 days past due  
    SERIOUS = "serious"                 # 61-90 days past due
    DEFAULT = "default"                 # 90+ days past due
    WRITTEN_OFF = "written_off"         # Written off as uncollectible


class CollectionAction(Enum):
    """Types of collection actions"""
    REMINDER_SMS = "reminder_sms"
    REMINDER_EMAIL = "reminder_email"
    REMINDER_CALL = "reminder_call"
    DEMAND_LETTER = "demand_letter"
    FIELD_VISIT = "field_visit"
    LEGAL_NOTICE = "legal_notice"
    WRITE_OFF = "write_off"


class ActionResult(Enum):
    """Results of collection actions"""
    SUCCESSFUL = "successful"           # Contact made, positive response
    NO_ANSWER = "no_answer"            # Unable to contact
    PROMISED = "promised"              # Customer made payment promise
    REFUSED = "refused"                # Customer refused to cooperate
    ESCALATED = "escalated"            # Escalated to next level


class PromiseStatus(Enum):
    """Status of payment promises"""
    PENDING = "pending"                # Promise not yet due
    KEPT = "kept"                      # Promise fulfilled
    BROKEN = "broken"                  # Promise not fulfilled


class CaseResolution(Enum):
    """Ways collection cases can be resolved"""
    PAID = "paid"                      # Account brought current
    RESTRUCTURED = "restructured"      # Payment plan agreed
    WRITTEN_OFF = "written_off"        # Written off as bad debt


@dataclass
class CollectionActionRecord(StorageRecord):
    """Record of a collection action taken"""
    case_id: str
    action_type: CollectionAction
    performed_at: datetime
    performed_by: str
    notes: str
    result: ActionResult
    next_follow_up_date: Optional[date] = None


@dataclass
class PaymentPromise(StorageRecord):
    """Record of a customer payment promise"""
    case_id: str
    promised_amount: Money
    promised_date: date
    status: PromiseStatus = PromiseStatus.PENDING
    actual_payment_date: Optional[date] = None
    actual_amount: Optional[Money] = None
    
    def __post_init__(self):
        # Initialize actual amount if None
        if not self.actual_amount:
            self.actual_amount = Money(Decimal('0'), self.promised_amount.currency)


@dataclass  
class CollectionCase(StorageRecord):
    """Collection case for a delinquent loan or credit line"""
    loan_id: Optional[str] = None
    credit_line_id: Optional[str] = None
    customer_id: str = ""
    account_id: str = ""
    status: DelinquencyStatus = DelinquencyStatus.CURRENT
    days_past_due: int = 0
    amount_overdue: Money = None
    total_outstanding: Money = None
    last_payment_date: Optional[date] = None
    next_action_date: Optional[date] = None
    assigned_collector: Optional[str] = None
    priority: int = 1  # 1-5, where 5 is highest priority
    actions_taken: List[CollectionActionRecord] = field(default_factory=list)
    promises_to_pay: List[PaymentPromise] = field(default_factory=list)
    resolved_at: Optional[datetime] = None
    resolution: Optional[CaseResolution] = None
    
    def __post_init__(self):
        # Ensure either loan_id or credit_line_id is set
        if not self.loan_id and not self.credit_line_id:
            raise ValueError("CollectionCase must have either loan_id or credit_line_id")
        
        # Initialize money amounts if None (will be set properly when creating case)
        if not self.amount_overdue:
            self.amount_overdue = Money(Decimal('0'), Currency.USD)
        if not self.total_outstanding:
            self.total_outstanding = Money(Decimal('0'), Currency.USD)
    
    @property
    def is_resolved(self) -> bool:
        """Check if case is resolved"""
        return self.resolved_at is not None
    
    @property
    def is_high_priority(self) -> bool:
        """Check if case is high priority (4 or 5)"""
        return self.priority >= 4
    
    def get_delinquency_status(self, days_past_due: int) -> DelinquencyStatus:
        """Determine delinquency status based on days past due"""
        if days_past_due == 0:
            return DelinquencyStatus.CURRENT
        elif days_past_due <= 30:
            return DelinquencyStatus.EARLY
        elif days_past_due <= 60:
            return DelinquencyStatus.LATE
        elif days_past_due <= 90:
            return DelinquencyStatus.SERIOUS
        else:
            return DelinquencyStatus.DEFAULT


@dataclass
class CollectionStrategy(StorageRecord):
    """Collection strategy configuration"""
    product_id: Optional[str] = None  # None means default strategy
    escalation_rules: List[Tuple[int, CollectionAction, bool]] = field(default_factory=list)
    auto_write_off_days: Optional[int] = None
    promise_tolerance_days: int = 3  # Grace days after broken promise before escalation
    
    def __post_init__(self):
        # Set default escalation rules if none provided
        if not self.escalation_rules:
            self.escalation_rules = [
                (1, CollectionAction.REMINDER_SMS, True),
                (7, CollectionAction.REMINDER_EMAIL, True),
                (15, CollectionAction.REMINDER_CALL, False),
                (30, CollectionAction.DEMAND_LETTER, True),
                (60, CollectionAction.FIELD_VISIT, False),
                (90, CollectionAction.LEGAL_NOTICE, True)
            ]
        
        # Set default write-off period if not specified
        if self.auto_write_off_days is None:
            self.auto_write_off_days = 365


class CollectionsManager:
    """Manager for collection cases and activities"""
    
    def __init__(
        self,
        storage: StorageInterface,
        account_manager: AccountManager,
        loan_manager: Optional[LoanManager] = None,
        credit_manager: Optional[CreditLineManager] = None
    ):
        self.storage = storage
        self.account_manager = account_manager
        self.loan_manager = loan_manager
        self.credit_manager = credit_manager
        
        self.cases_table = "collection_cases"
        self.actions_table = "collection_actions"  
        self.promises_table = "payment_promises"
        self.strategies_table = "collection_strategies"
        
        # Initialize default strategy
        self._initialize_default_strategy()
    
    def _initialize_default_strategy(self):
        """Initialize default collection strategy"""
        default_strategy = CollectionStrategy(
            id="default",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        # Only save if not already exists
        existing = self.storage.load(self.strategies_table, "default")
        if not existing:
            strategy_dict = self._strategy_to_dict(default_strategy)
            self.storage.save(self.strategies_table, "default", strategy_dict)
    
    def scan_delinquencies(self) -> Dict[str, int]:
        """Scan all loans and credit lines for delinquencies, create/update cases"""
        results = {
            "cases_created": 0,
            "cases_updated": 0, 
            "total_amount_overdue": Decimal('0')
        }
        
        today = date.today()
        
        # Scan loans if loan manager available
        if self.loan_manager:
            # Get all active loans
            all_loans_data = self.storage.find(
                self.loan_manager.loans_table,
                {"state": LoanState.ACTIVE.value}
            ) + self.storage.find(
                self.loan_manager.loans_table, 
                {"state": LoanState.DISBURSED.value}
            )
            
            for loan_data in all_loans_data:
                loan = self.loan_manager._loan_from_dict(loan_data)
                
                # Calculate days past due
                days_past_due = self._calculate_days_past_due_loan(loan, today)
                
                if days_past_due > 0:
                    # Check if case already exists
                    existing_case = self._get_case_by_loan_id(loan.id)
                    
                    if existing_case:
                        # Update existing case
                        self._update_case_for_loan(existing_case, loan, days_past_due)
                        results["cases_updated"] += 1
                    else:
                        # Create new case
                        new_case = self._create_case_for_loan(loan, days_past_due)
                        results["cases_created"] += 1
                    
                    results["total_amount_overdue"] += self._calculate_overdue_amount_loan(loan)
        
        # Scan credit lines if credit manager available
        if self.credit_manager:
            # Get all credit line accounts from account manager
            from .accounts import ProductType
            all_accounts_data = self.storage.find(
                "accounts",
                {"product_type": ProductType.CREDIT_LINE.value}
            )
            
            for account_data in all_accounts_data:
                account = self.account_manager._account_from_dict(account_data)
                
                if account.is_active:
                    days_past_due = self._calculate_days_past_due_credit_account(account, today)
                    
                    if days_past_due > 0:
                        existing_case = self._get_case_by_credit_line_id(account.id)
                        
                        if existing_case:
                            self._update_case_for_credit_account(existing_case, account, days_past_due)
                            results["cases_updated"] += 1
                        else:
                            new_case = self._create_case_for_credit_account(account, days_past_due)
                            results["cases_created"] += 1
                        
                        results["total_amount_overdue"] += self._calculate_overdue_amount_credit_account(account)
        
        return results
    
    def get_case(self, case_id: str) -> Optional[CollectionCase]:
        """Get collection case by ID"""
        case_dict = self.storage.load(self.cases_table, case_id)
        if case_dict:
            return self._case_from_dict(case_dict)
        return None
    
    def get_cases(
        self,
        status: Optional[DelinquencyStatus] = None,
        priority: Optional[int] = None,
        collector: Optional[str] = None
    ) -> List[CollectionCase]:
        """Get collection cases with optional filters"""
        filters = {}
        
        if status:
            filters["status"] = status.value
        if priority:
            filters["priority"] = priority  
        if collector:
            filters["assigned_collector"] = collector
        
        cases_data = self.storage.find(self.cases_table, filters)
        cases = [self._case_from_dict(data) for data in cases_data]
        
        # Sort by priority (highest first), then by days past due
        cases.sort(key=lambda x: (-x.priority, -x.days_past_due))
        
        return cases
    
    def get_cases_by_customer(self, customer_id: str) -> List[CollectionCase]:
        """Get all collection cases for a customer"""
        cases_data = self.storage.find(self.cases_table, {"customer_id": customer_id})
        return [self._case_from_dict(data) for data in cases_data]
    
    def assign_collector(self, case_id: str, collector_id: str) -> CollectionCase:
        """Assign collector to a case"""
        case = self.get_case(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found")
        
        case.assigned_collector = collector_id
        case.updated_at = datetime.now(timezone.utc)
        
        self._save_case(case)
        return case
    
    def record_action(
        self,
        case_id: str,
        action_type: CollectionAction,
        performed_by: str,
        notes: str,
        result: ActionResult,
        next_follow_up: Optional[date] = None
    ) -> CollectionActionRecord:
        """Record a collection action"""
        case = self.get_case(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found")
        
        now = datetime.now(timezone.utc)
        action_id = str(uuid.uuid4())
        
        action = CollectionActionRecord(
            id=action_id,
            created_at=now,
            updated_at=now,
            case_id=case_id,
            action_type=action_type,
            performed_at=now,
            performed_by=performed_by,
            notes=notes,
            result=result,
            next_follow_up_date=next_follow_up
        )
        
        # Save action record
        action_dict = self._action_to_dict(action)
        self.storage.save(self.actions_table, action_id, action_dict)
        
        # Update case with next action date
        if next_follow_up:
            case.next_action_date = next_follow_up
            case.updated_at = now
            self._save_case(case)
        
        return action
    
    def record_promise(
        self,
        case_id: str,
        promised_amount: Money,
        promised_date: date
    ) -> PaymentPromise:
        """Record a payment promise from customer"""
        case = self.get_case(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found")
        
        now = datetime.now(timezone.utc)
        promise_id = str(uuid.uuid4())
        
        promise = PaymentPromise(
            id=promise_id,
            created_at=now,
            updated_at=now,
            case_id=case_id,
            promised_amount=promised_amount,
            promised_date=promised_date
        )
        
        # Save promise
        promise_dict = self._promise_to_dict(promise)
        self.storage.save(self.promises_table, promise_id, promise_dict)
        
        return promise
    
    def check_promises(self) -> Dict[str, int]:
        """Check for broken payment promises"""
        results = {"promises_checked": 0, "promises_broken": 0}
        
        today = date.today()
        
        # Get all pending promises
        all_promises_data = self.storage.find(
            self.promises_table,
            {"status": PromiseStatus.PENDING.value}
        )
        
        for promise_data in all_promises_data:
            promise = self._promise_from_dict(promise_data)
            results["promises_checked"] += 1
            
            # Check if promise is overdue (with tolerance)
            strategy = self.get_strategy()  # Get default strategy
            tolerance_date = promise.promised_date + timedelta(days=strategy.promise_tolerance_days)
            
            if today > tolerance_date:
                # Mark promise as broken
                promise.status = PromiseStatus.BROKEN
                promise.updated_at = datetime.now(timezone.utc)
                
                promise_dict = self._promise_to_dict(promise)
                self.storage.save(self.promises_table, promise.id, promise_dict)
                
                results["promises_broken"] += 1
        
        return results
    
    def get_collection_summary(self) -> Dict:
        """Get portfolio-level collection statistics"""
        summary = {
            "total_cases": 0,
            "cases_by_status": {},
            "total_overdue_amount": Decimal('0'),
            "cases_by_priority": {},
            "assigned_cases": 0,
            "unassigned_cases": 0
        }
        
        # Get all unresolved cases
        all_cases_data = self.storage.load_all(self.cases_table)
        cases = [self._case_from_dict(data) for data in all_cases_data if not data.get('resolved_at')]
        
        summary["total_cases"] = len(cases)
        
        # Initialize counters
        for status in DelinquencyStatus:
            summary["cases_by_status"][status.value] = 0
        
        for priority in range(1, 6):
            summary["cases_by_priority"][priority] = 0
        
        # Count cases
        for case in cases:
            # Count by status
            summary["cases_by_status"][case.status.value] += 1
            
            # Count by priority
            summary["cases_by_priority"][case.priority] += 1
            
            # Sum overdue amounts
            summary["total_overdue_amount"] += case.amount_overdue.amount
            
            # Count assignment
            if case.assigned_collector:
                summary["assigned_cases"] += 1
            else:
                summary["unassigned_cases"] += 1
        
        return summary
    
    def set_strategy(self, strategy: CollectionStrategy) -> None:
        """Set collection strategy"""
        strategy_dict = self._strategy_to_dict(strategy)
        strategy_id = strategy.product_id or "default"
        self.storage.save(self.strategies_table, strategy_id, strategy_dict)
    
    def get_strategy(self, product_id: Optional[str] = None) -> CollectionStrategy:
        """Get collection strategy for product (or default)"""
        strategy_id = product_id or "default"
        strategy_dict = self.storage.load(self.strategies_table, strategy_id)
        
        if strategy_dict:
            return self._strategy_from_dict(strategy_dict)
        
        # Return default strategy if specific product strategy not found
        if product_id:
            return self.get_strategy()
        
        # Should not happen if _initialize_default_strategy worked
        raise ValueError("Default collection strategy not found")
    
    def run_auto_actions(self) -> Dict[str, int]:
        """Execute automatic collection actions based on strategy"""
        results = {"actions_executed": 0, "cases_processed": 0}
        
        today = date.today()
        
        # Get all unresolved cases
        cases = self.get_cases()
        
        for case in cases:
            if case.is_resolved:
                continue
            
            results["cases_processed"] += 1
            
            # Get strategy (use product-specific if available)
            strategy = self.get_strategy()
            
            # Check escalation rules
            for days_threshold, action, auto_execute in strategy.escalation_rules:
                if (case.days_past_due >= days_threshold and 
                    auto_execute and 
                    not self._action_recently_taken(case, action)):
                    
                    # Execute automatic action
                    self.record_action(
                        case_id=case.id,
                        action_type=action,
                        performed_by="SYSTEM",
                        notes=f"Automatic action: {case.days_past_due} days past due",
                        result=ActionResult.SUCCESSFUL  # Assume success for auto actions
                    )
                    
                    results["actions_executed"] += 1
            
            # Check for auto write-off
            if (strategy.auto_write_off_days and 
                case.days_past_due >= strategy.auto_write_off_days and
                case.status != DelinquencyStatus.WRITTEN_OFF):
                
                # Auto write-off
                self.resolve_case(case.id, CaseResolution.WRITTEN_OFF)
                results["actions_executed"] += 1
        
        return results
    
    def resolve_case(
        self,
        case_id: str,
        resolution: CaseResolution
    ) -> CollectionCase:
        """Resolve a collection case"""
        case = self.get_case(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found")
        
        now = datetime.now(timezone.utc)
        case.resolution = resolution
        case.resolved_at = now
        case.updated_at = now
        
        # Update status based on resolution
        if resolution == CaseResolution.WRITTEN_OFF:
            case.status = DelinquencyStatus.WRITTEN_OFF
        elif resolution in [CaseResolution.PAID, CaseResolution.RESTRUCTURED]:
            case.status = DelinquencyStatus.CURRENT
        
        self._save_case(case)
        return case
    
    def get_recovery_rate(
        self,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None
    ) -> Dict[str, Decimal]:
        """Calculate recovery rate for resolved cases"""
        # Filter resolved cases by date range
        all_cases_data = self.storage.load_all(self.cases_table)
        resolved_cases = []
        
        for case_data in all_cases_data:
            case = self._case_from_dict(case_data)
            if not case.is_resolved:
                continue
            
            if period_start and case.resolved_at.date() < period_start:
                continue
            if period_end and case.resolved_at.date() > period_end:
                continue
            
            resolved_cases.append(case)
        
        if not resolved_cases:
            return {
                "total_cases": 0,
                "total_overdue_amount": Decimal('0'),
                "total_recovered_amount": Decimal('0'),
                "recovery_rate": Decimal('0'),
                "cases_paid": 0,
                "cases_restructured": 0,
                "cases_written_off": 0
            }
        
        total_overdue = Decimal('0')
        recovered_amount = Decimal('0')
        cases_paid = 0
        cases_restructured = 0
        cases_written_off = 0
        
        for case in resolved_cases:
            total_overdue += case.amount_overdue.amount
            
            if case.resolution == CaseResolution.PAID:
                recovered_amount += case.amount_overdue.amount
                cases_paid += 1
            elif case.resolution == CaseResolution.RESTRUCTURED:
                # Assume partial recovery for restructured cases (50%)
                recovered_amount += case.amount_overdue.amount * Decimal('0.5')
                cases_restructured += 1
            elif case.resolution == CaseResolution.WRITTEN_OFF:
                cases_written_off += 1
                # No recovery for written-off cases
        
        recovery_rate = Decimal('0')
        if total_overdue > 0:
            recovery_rate = recovered_amount / total_overdue
        
        return {
            "total_cases": len(resolved_cases),
            "total_overdue_amount": total_overdue,
            "total_recovered_amount": recovered_amount,
            "recovery_rate": recovery_rate,
            "cases_paid": cases_paid,
            "cases_restructured": cases_restructured,
            "cases_written_off": cases_written_off
        }
    
    # Private helper methods
    
    def _get_case_by_loan_id(self, loan_id: str) -> Optional[CollectionCase]:
        """Get collection case by loan ID"""
        cases_data = self.storage.find(self.cases_table, {"loan_id": loan_id})
        if cases_data:
            # Return the first unresolved case
            for case_data in cases_data:
                case = self._case_from_dict(case_data)
                if not case.is_resolved:
                    return case
        return None
    
    def _get_case_by_credit_line_id(self, credit_line_id: str) -> Optional[CollectionCase]:
        """Get collection case by credit line ID"""
        cases_data = self.storage.find(self.cases_table, {"credit_line_id": credit_line_id})
        if cases_data:
            for case_data in cases_data:
                case = self._case_from_dict(case_data)
                if not case.is_resolved:
                    return case
        return None
    
    def _create_case_for_loan(self, loan: Loan, days_past_due: int) -> CollectionCase:
        """Create new collection case for loan"""
        now = datetime.now(timezone.utc)
        case_id = str(uuid.uuid4())
        
        # Calculate priority based on amount and days past due
        priority = self._calculate_priority(loan.current_balance, days_past_due)
        
        # Determine delinquency status
        temp_case = CollectionCase(
            id="temp", 
            created_at=now, 
            updated_at=now, 
            loan_id="temp_loan"
        )
        status = temp_case.get_delinquency_status(days_past_due)
        
        case = CollectionCase(
            id=case_id,
            created_at=now,
            updated_at=now,
            loan_id=loan.id,
            customer_id=loan.customer_id,
            account_id=loan.account_id,
            status=status,
            days_past_due=days_past_due,
            amount_overdue=self._calculate_overdue_amount_loan_money(loan),
            total_outstanding=loan.current_balance,
            last_payment_date=loan.last_payment_date,
            priority=priority
        )
        
        self._save_case(case)
        return case
    
    def _create_case_for_credit_account(self, account, days_past_due: int) -> CollectionCase:
        """Create new collection case for credit account"""
        now = datetime.now(timezone.utc)
        case_id = str(uuid.uuid4())
        
        balance = self.account_manager.get_book_balance(account.id)
        priority = self._calculate_priority(balance, days_past_due)
        
        temp_case = CollectionCase(
            id="temp", 
            created_at=now, 
            updated_at=now, 
            credit_line_id="temp_credit"
        )
        status = temp_case.get_delinquency_status(days_past_due)
        
        case = CollectionCase(
            id=case_id,
            created_at=now,
            updated_at=now,
            credit_line_id=account.id,
            customer_id=account.customer_id,
            account_id=account.id,
            status=status,
            days_past_due=days_past_due,
            amount_overdue=self._calculate_overdue_amount_credit_account_money(account),
            total_outstanding=balance,
            last_payment_date=self._get_last_payment_date_credit(account),
            priority=priority
        )
        
        self._save_case(case)
        return case
    
    def _update_case_for_loan(self, case: CollectionCase, loan: Loan, days_past_due: int) -> None:
        """Update existing case with current loan data"""
        temp_case = CollectionCase(
            id="temp", 
            created_at=datetime.now(timezone.utc), 
            updated_at=datetime.now(timezone.utc), 
            loan_id="temp_loan"
        )
        case.status = temp_case.get_delinquency_status(days_past_due)
        case.days_past_due = days_past_due
        case.amount_overdue = self._calculate_overdue_amount_loan_money(loan)
        case.total_outstanding = loan.current_balance
        case.last_payment_date = loan.last_payment_date
        case.priority = self._calculate_priority(loan.current_balance, days_past_due)
        case.updated_at = datetime.now(timezone.utc)
        
        self._save_case(case)
    
    def _update_case_for_credit_account(self, case: CollectionCase, account, days_past_due: int) -> None:
        """Update existing case with current credit account data"""
        temp_case = CollectionCase(
            id="temp", 
            created_at=datetime.now(timezone.utc), 
            updated_at=datetime.now(timezone.utc), 
            credit_line_id="temp_credit"
        )
        balance = self.account_manager.get_book_balance(account.id)
        
        case.status = temp_case.get_delinquency_status(days_past_due)
        case.days_past_due = days_past_due
        case.amount_overdue = self._calculate_overdue_amount_credit_account_money(account)
        case.total_outstanding = balance
        case.last_payment_date = self._get_last_payment_date_credit(account)
        case.priority = self._calculate_priority(balance, days_past_due)
        case.updated_at = datetime.now(timezone.utc)
        
        self._save_case(case)
    
    def _calculate_days_past_due_loan(self, loan: Loan, as_of_date: date) -> int:
        """Calculate days past due for loan"""
        # Use the loan's built-in days_past_due calculation or derive from payment schedule
        if hasattr(loan, 'days_past_due'):
            return max(0, loan.days_past_due)
        
        # Fallback calculation
        if not loan.first_payment_date:
            return 0
        
        # Simple calculation - in production would check actual payment schedule
        if loan.first_payment_date <= as_of_date:
            return (as_of_date - loan.first_payment_date).days
        
        return 0
    
    def _calculate_days_past_due_credit_account(self, account, as_of_date: date) -> int:
        """Calculate days past due for credit account"""
        # Get current statement to check due date
        current_statement = None
        if self.credit_manager:
            current_statement = self.credit_manager.get_current_statement(account.id)
        
        if current_statement and current_statement.due_date:
            if as_of_date > current_statement.due_date and current_statement.remaining_balance().is_positive():
                return (as_of_date - current_statement.due_date).days
        
        return 0
    
    def _calculate_overdue_amount_loan(self, loan: Loan) -> Decimal:
        """Calculate overdue amount for loan"""
        # Simplified - in production would calculate based on missed payments
        if loan.days_past_due > 0:
            return loan.monthly_payment.amount
        return Decimal('0')
    
    def _calculate_overdue_amount_loan_money(self, loan: Loan) -> Money:
        """Calculate overdue amount for loan as Money"""
        amount = self._calculate_overdue_amount_loan(loan)
        return Money(amount, loan.current_balance.currency)
    
    def _calculate_overdue_amount_credit_account(self, account) -> Decimal:
        """Calculate overdue amount for credit account"""
        # Get current statement to determine minimum payment due
        if self.credit_manager:
            current_statement = self.credit_manager.get_current_statement(account.id)
            if current_statement and current_statement.is_overdue():
                return current_statement.minimum_payment_due.amount
        
        # Fallback - assume 5% minimum payment on outstanding balance
        balance = self.account_manager.get_book_balance(account.id)
        if balance.is_positive():
            return balance.amount * Decimal('0.05')
        
        return Decimal('0')
    
    def _calculate_overdue_amount_credit_account_money(self, account) -> Money:
        """Calculate overdue amount for credit account as Money"""
        amount = self._calculate_overdue_amount_credit_account(account)
        balance = self.account_manager.get_book_balance(account.id)
        return Money(amount, balance.currency)
    
    def _get_last_payment_date_credit(self, account) -> Optional[date]:
        """Get last payment date for credit account"""
        # Get current statement which tracks payments
        if self.credit_manager:
            current_statement = self.credit_manager.get_current_statement(account.id)
            if current_statement and current_statement.paid_date:
                return current_statement.paid_date
        
        return None
    
    def _calculate_priority(self, outstanding_balance: Money, days_past_due: int) -> int:
        """Calculate case priority (1-5) based on balance and delinquency"""
        priority = 1
        
        # Increase priority based on outstanding balance
        if outstanding_balance.amount >= Decimal('100000'):  # $100K+
            priority += 2
        elif outstanding_balance.amount >= Decimal('50000'):  # $50K+
            priority += 1
        
        # Increase priority based on days past due
        if days_past_due >= 90:  # Default
            priority += 2
        elif days_past_due >= 60:  # Serious
            priority += 1
        
        return min(priority, 5)  # Cap at 5
    
    def _action_recently_taken(self, case: CollectionCase, action: CollectionAction) -> bool:
        """Check if action was recently taken (within last 7 days)"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
        
        # Check recent actions for this case
        actions_data = self.storage.find(
            self.actions_table,
            {"case_id": case.id, "action_type": action.value}
        )
        
        for action_data in actions_data:
            action_record = self._action_from_dict(action_data)
            if action_record.performed_at > cutoff_date:
                return True
        
        return False
    
    def _save_case(self, case: CollectionCase) -> None:
        """Save case to storage"""
        case_dict = self._case_to_dict(case)
        self.storage.save(self.cases_table, case.id, case_dict)
    
    # Serialization methods
    
    def _case_to_dict(self, case: CollectionCase) -> Dict:
        """Convert case to dictionary"""
        result = case.to_dict()
        result['status'] = case.status.value
        
        # Convert money amounts
        result['amount_overdue'] = str(case.amount_overdue.amount)
        result['amount_overdue_currency'] = case.amount_overdue.currency.code
        result['total_outstanding'] = str(case.total_outstanding.amount)
        result['total_outstanding_currency'] = case.total_outstanding.currency.code
        
        # Convert dates
        if case.last_payment_date:
            result['last_payment_date'] = case.last_payment_date.isoformat()
        if case.next_action_date:
            result['next_action_date'] = case.next_action_date.isoformat()
        if case.resolved_at:
            result['resolved_at'] = case.resolved_at.isoformat()
        if case.resolution:
            result['resolution'] = case.resolution.value
        
        return result
    
    def _case_from_dict(self, data: Dict) -> CollectionCase:
        """Convert dictionary to case"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        # Parse dates
        last_payment_date = None
        if data.get('last_payment_date'):
            last_payment_date = date.fromisoformat(data['last_payment_date'])
        
        next_action_date = None
        if data.get('next_action_date'):
            next_action_date = date.fromisoformat(data['next_action_date'])
        
        resolved_at = None
        if data.get('resolved_at'):
            resolved_at = datetime.fromisoformat(data['resolved_at'])
        
        resolution = None
        if data.get('resolution'):
            resolution = CaseResolution(data['resolution'])
        
        return CollectionCase(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            loan_id=data.get('loan_id'),
            credit_line_id=data.get('credit_line_id'),
            customer_id=data['customer_id'],
            account_id=data['account_id'],
            status=DelinquencyStatus(data['status']),
            days_past_due=data['days_past_due'],
            amount_overdue=Money(
                Decimal(data['amount_overdue']),
                Currency[data['amount_overdue_currency']]
            ),
            total_outstanding=Money(
                Decimal(data['total_outstanding']),
                Currency[data['total_outstanding_currency']]
            ),
            last_payment_date=last_payment_date,
            next_action_date=next_action_date,
            assigned_collector=data.get('assigned_collector'),
            priority=data['priority'],
            resolved_at=resolved_at,
            resolution=resolution
        )
    
    def _action_to_dict(self, action: CollectionActionRecord) -> Dict:
        """Convert action to dictionary"""
        result = action.to_dict()
        result['action_type'] = action.action_type.value
        result['performed_at'] = action.performed_at.isoformat()
        result['result'] = action.result.value
        
        if action.next_follow_up_date:
            result['next_follow_up_date'] = action.next_follow_up_date.isoformat()
        
        return result
    
    def _action_from_dict(self, data: Dict) -> CollectionActionRecord:
        """Convert dictionary to action"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        performed_at = datetime.fromisoformat(data['performed_at'])
        
        next_follow_up_date = None
        if data.get('next_follow_up_date'):
            next_follow_up_date = date.fromisoformat(data['next_follow_up_date'])
        
        return CollectionActionRecord(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            case_id=data['case_id'],
            action_type=CollectionAction(data['action_type']),
            performed_at=performed_at,
            performed_by=data['performed_by'],
            notes=data['notes'],
            result=ActionResult(data['result']),
            next_follow_up_date=next_follow_up_date
        )
    
    def _promise_to_dict(self, promise: PaymentPromise) -> Dict:
        """Convert promise to dictionary"""
        result = promise.to_dict()
        result['promised_amount'] = str(promise.promised_amount.amount)
        result['promised_currency'] = promise.promised_amount.currency.code
        result['promised_date'] = promise.promised_date.isoformat()
        result['status'] = promise.status.value
        
        if promise.actual_payment_date:
            result['actual_payment_date'] = promise.actual_payment_date.isoformat()
        if promise.actual_amount:
            result['actual_amount'] = str(promise.actual_amount.amount)
            result['actual_currency'] = promise.actual_amount.currency.code
        
        return result
    
    def _promise_from_dict(self, data: Dict) -> PaymentPromise:
        """Convert dictionary to promise"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        promised_date = date.fromisoformat(data['promised_date'])
        
        actual_payment_date = None
        if data.get('actual_payment_date'):
            actual_payment_date = date.fromisoformat(data['actual_payment_date'])
        
        actual_amount = None
        if data.get('actual_amount'):
            actual_amount = Money(
                Decimal(data['actual_amount']),
                Currency[data['actual_currency']]
            )
        
        return PaymentPromise(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            case_id=data['case_id'],
            promised_amount=Money(
                Decimal(data['promised_amount']),
                Currency[data['promised_currency']]
            ),
            promised_date=promised_date,
            status=PromiseStatus(data['status']),
            actual_payment_date=actual_payment_date,
            actual_amount=actual_amount
        )
    
    def _strategy_to_dict(self, strategy: CollectionStrategy) -> Dict:
        """Convert strategy to dictionary"""
        result = strategy.to_dict()
        
        # Convert escalation rules
        result['escalation_rules'] = [
            {
                "days_past_due": days,
                "action": action.value,
                "auto_execute": auto_execute
            }
            for days, action, auto_execute in strategy.escalation_rules
        ]
        
        return result
    
    def _strategy_from_dict(self, data: Dict) -> CollectionStrategy:
        """Convert dictionary to strategy"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        # Convert escalation rules
        escalation_rules = [
            (
                rule['days_past_due'],
                CollectionAction(rule['action']),
                rule['auto_execute']
            )
            for rule in data.get('escalation_rules', [])
        ]
        
        return CollectionStrategy(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            product_id=data.get('product_id'),
            escalation_rules=escalation_rules,
            auto_write_off_days=data.get('auto_write_off_days'),
            promise_tolerance_days=data.get('promise_tolerance_days', 3)
        )