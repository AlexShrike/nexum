"""
Loan Module

Handles loan origination, disbursement, amortization schedule generation,
payment processing, prepayment handling, and loan lifecycle management.
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta, date
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import uuid
import calendar

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType
from .accounts import AccountManager, Account, ProductType
from .transactions import TransactionProcessor, TransactionType, TransactionChannel


class LoanState(Enum):
    """Loan lifecycle states"""
    ORIGINATED = "originated"      # Loan approved and created
    DISBURSED = "disbursed"       # Loan funds disbursed to customer
    ACTIVE = "active"             # Loan is active with regular payments
    PAID_OFF = "paid_off"         # Loan fully paid
    DEFAULTED = "defaulted"       # Loan in default
    WRITTEN_OFF = "written_off"   # Loan written off as uncollectible
    CLOSED = "closed"             # Loan account closed


class AmortizationMethod(Enum):
    """Methods for loan amortization"""
    EQUAL_INSTALLMENT = "equal_installment"  # French method - equal payments
    EQUAL_PRINCIPAL = "equal_principal"      # Equal principal + declining interest
    BULLET = "bullet"                        # Interest only, principal at end
    CUSTOM = "custom"                        # Custom payment schedule


class PaymentFrequency(Enum):
    """Payment frequency options"""
    WEEKLY = "weekly"          # 52 payments per year
    BI_WEEKLY = "bi_weekly"    # 26 payments per year
    MONTHLY = "monthly"        # 12 payments per year
    QUARTERLY = "quarterly"    # 4 payments per year
    SEMI_ANNUALLY = "semi_annually"  # 2 payments per year
    ANNUALLY = "annually"      # 1 payment per year


@dataclass
class LoanTerms:
    """Loan terms and conditions"""
    principal_amount: Money
    annual_interest_rate: Decimal       # e.g., 0.075 for 7.5%
    term_months: int                    # Total loan term in months
    payment_frequency: PaymentFrequency
    amortization_method: AmortizationMethod
    first_payment_date: date
    allow_prepayment: bool = True
    prepayment_penalty_rate: Optional[Decimal] = None  # e.g., 0.02 for 2% penalty
    grace_period_days: int = 10        # Days before late fee
    late_fee: Money = None             # Late payment fee
    
    def __post_init__(self):
        if not self.late_fee:
            self.late_fee = Money(Decimal('25'), self.principal_amount.currency)
        
        # Validate currency consistency
        if self.late_fee.currency != self.principal_amount.currency:
            raise ValueError("Late fee currency must match principal currency")
    
    @property
    def total_payments(self) -> int:
        """Calculate total number of payments"""
        payments_per_year = {
            PaymentFrequency.WEEKLY: 52,
            PaymentFrequency.BI_WEEKLY: 26,
            PaymentFrequency.MONTHLY: 12,
            PaymentFrequency.QUARTERLY: 4,
            PaymentFrequency.SEMI_ANNUALLY: 2,
            PaymentFrequency.ANNUALLY: 1
        }
        
        return int((self.term_months / 12) * payments_per_year[self.payment_frequency])
    
    @property
    def payment_period_months(self) -> Decimal:
        """Get months between payments"""
        return Decimal('12') / Decimal(str(self.payments_per_year))
    
    @property
    def payments_per_year(self) -> int:
        """Get number of payments per year"""
        return {
            PaymentFrequency.WEEKLY: 52,
            PaymentFrequency.BI_WEEKLY: 26,
            PaymentFrequency.MONTHLY: 12,
            PaymentFrequency.QUARTERLY: 4,
            PaymentFrequency.SEMI_ANNUALLY: 2,
            PaymentFrequency.ANNUALLY: 1
        }[self.payment_frequency]


@dataclass
class AmortizationEntry:
    """Single entry in amortization schedule"""
    payment_number: int
    payment_date: date
    payment_amount: Money
    principal_amount: Money
    interest_amount: Money
    remaining_balance: Money
    
    def __post_init__(self):
        # Validate that payment equals principal + interest
        calculated_payment = self.principal_amount + self.interest_amount
        if abs(calculated_payment.amount - self.payment_amount.amount) > Decimal('0.01'):
            raise ValueError(f"Payment amount {self.payment_amount.to_string()} does not equal "
                           f"principal {self.principal_amount.to_string()} + "
                           f"interest {self.interest_amount.to_string()}")


@dataclass
class Loan(StorageRecord):
    """Loan account with terms and current status"""
    account_id: str                     # Associated loan account
    customer_id: str                    # Borrower
    terms: LoanTerms
    state: LoanState = LoanState.ORIGINATED
    
    # Current loan status
    current_balance: Money = None       # Remaining principal balance
    total_paid: Money = None           # Total amount paid to date
    interest_paid: Money = None        # Total interest paid
    principal_paid: Money = None       # Total principal paid
    
    # Dates
    originated_date: Optional[date] = None
    disbursed_date: Optional[date] = None
    first_payment_date: Optional[date] = None
    last_payment_date: Optional[date] = None
    maturity_date: Optional[date] = None
    
    # Default tracking
    days_past_due: int = 0
    last_late_fee_date: Optional[date] = None
    
    def __post_init__(self):
        
        # Initialize amounts if None
        if not self.current_balance:
            self.current_balance = self.terms.principal_amount
        
        zero_amount = Money(Decimal('0'), self.terms.principal_amount.currency)
        if not self.total_paid:
            self.total_paid = zero_amount
        if not self.interest_paid:
            self.interest_paid = zero_amount
        if not self.principal_paid:
            self.principal_paid = zero_amount
    
    @property
    def is_active(self) -> bool:
        """Check if loan is in active repayment"""
        return self.state in [LoanState.DISBURSED, LoanState.ACTIVE]
    
    @property
    def is_paid_off(self) -> bool:
        """Check if loan is fully paid"""
        return self.current_balance.is_zero() or self.state == LoanState.PAID_OFF
    
    @property
    def is_past_due(self) -> bool:
        """Check if loan has past due payments"""
        return self.days_past_due > 0
    
    @property
    def monthly_payment(self) -> Money:
        """Get scheduled monthly payment amount"""
        # This would typically come from the amortization schedule
        # For now, return a calculated amount based on terms
        return self._calculate_payment_amount()
    
    def _calculate_payment_amount(self) -> Money:
        """Calculate payment amount for equal installment method"""
        if self.terms.amortization_method != AmortizationMethod.EQUAL_INSTALLMENT:
            raise ValueError("Payment calculation only implemented for equal installment method")
        
        # Standard loan payment formula: P * [c(1+c)^n] / [(1+c)^n - 1]
        # Where P = principal, c = periodic interest rate, n = number of payments
        
        principal = self.terms.principal_amount.amount
        annual_rate = self.terms.annual_interest_rate
        periods_per_year = Decimal(str(self.terms.payments_per_year))
        periodic_rate = annual_rate / periods_per_year
        num_payments = Decimal(str(self.terms.total_payments))
        
        if periodic_rate == Decimal('0'):
            # No interest - simple division
            payment_amount = principal / num_payments
        else:
            # Standard formula
            factor = (Decimal('1') + periodic_rate) ** num_payments
            payment_amount = principal * (periodic_rate * factor) / (factor - Decimal('1'))
        
        return Money(payment_amount, self.terms.principal_amount.currency)


@dataclass
class LoanPayment(StorageRecord):
    """Record of a loan payment"""
    loan_id: str
    transaction_id: str                 # Reference to transaction
    payment_date: date
    payment_amount: Money
    principal_amount: Money
    interest_amount: Money
    late_fee: Money = None
    prepayment_penalty: Money = None
    scheduled_payment_number: Optional[int] = None  # Which scheduled payment this covers
    
    def __post_init__(self):
        
        # Initialize fees if None
        zero_amount = Money(Decimal('0'), self.payment_amount.currency)
        if not self.late_fee:
            self.late_fee = zero_amount
        if not self.prepayment_penalty:
            self.prepayment_penalty = zero_amount


class LoanManager:
    """
    Manages loan lifecycle from origination through payoff
    """
    
    def __init__(
        self,
        storage: StorageInterface,
        account_manager: AccountManager,
        transaction_processor: TransactionProcessor,
        audit_trail: AuditTrail
    ):
        self.storage = storage
        self.account_manager = account_manager
        self.transaction_processor = transaction_processor
        self.audit_trail = audit_trail
        
        self.loans_table = "loans"
        self.payments_table = "loan_payments"
        self.amortization_table = "amortization_schedules"
    
    def originate_loan(
        self,
        customer_id: str,
        terms: LoanTerms,
        currency: Currency
    ) -> Loan:
        """
        Originate a new loan
        
        Args:
            customer_id: Borrower customer ID
            terms: Loan terms and conditions
            currency: Loan currency
            
        Returns:
            Created Loan object
        """
        now = datetime.now(timezone.utc)
        today = now.date()
        
        # Create loan account
        loan_account = self.account_manager.create_account(
            customer_id=customer_id,
            product_type=ProductType.LOAN,
            currency=currency,
            name=f"Loan Account - {terms.principal_amount.to_string()}",
            minimum_balance=Money(Decimal('0'), currency)
        )
        
        # Calculate maturity date
        maturity_date = terms.first_payment_date + timedelta(days=terms.term_months * 30)
        
        # Create loan record
        loan = Loan(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            account_id=loan_account.id,
            customer_id=customer_id,
            terms=terms,
            state=LoanState.ORIGINATED,
            originated_date=today,
            first_payment_date=terms.first_payment_date,
            maturity_date=maturity_date
        )
        
        # Save loan
        self._save_loan(loan)
        
        # Generate amortization schedule
        self.generate_amortization_schedule(loan.id)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.LOAN_ORIGINATED,
            entity_type="loan",
            entity_id=loan.id,
            metadata={
                "customer_id": customer_id,
                "principal_amount": terms.principal_amount.to_string(),
                "annual_rate": str(terms.annual_interest_rate),
                "term_months": terms.term_months,
                "payment_frequency": terms.payment_frequency.value,
                "first_payment_date": terms.first_payment_date.isoformat()
            }
        )
        
        return loan
    
    def disburse_loan(
        self,
        loan_id: str,
        disbursement_account_id: str
    ) -> Loan:
        """
        Disburse loan funds to customer account
        
        Args:
            loan_id: Loan ID to disburse
            disbursement_account_id: Customer account to receive funds
            
        Returns:
            Updated Loan object
        """
        loan = self.get_loan(loan_id)
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")
        
        if loan.state != LoanState.ORIGINATED:
            raise ValueError(f"Can only disburse ORIGINATED loans, loan is {loan.state.value}")
        
        # Create disbursement transaction (credit customer account, debit loan account)
        disbursement = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.TRANSFER_INTERNAL,
            amount=loan.terms.principal_amount,
            description=f"Loan disbursement",
            channel=TransactionChannel.SYSTEM,
            from_account_id=loan.account_id,  # Loan account (liability) is debited
            to_account_id=disbursement_account_id,  # Customer account is credited
            reference=f"LOAN-DISB-{loan_id[:8]}"
        )
        
        # Process transaction
        processed_disbursement = self.transaction_processor.process_transaction(disbursement.id)
        
        # Update loan state
        loan.state = LoanState.DISBURSED
        loan.disbursed_date = date.today()
        loan.updated_at = datetime.now(timezone.utc)
        self._save_loan(loan)
        
        # Also update the current balance to reflect the disbursement (negative balance = liability)
        loan.current_balance = -loan.terms.principal_amount
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.LOAN_DISBURSED,
            entity_type="loan",
            entity_id=loan.id,
            metadata={
                "transaction_id": processed_disbursement.id,
                "disbursement_account": disbursement_account_id,
                "amount": loan.terms.principal_amount.to_string(),
                "disbursed_date": loan.disbursed_date.isoformat()
            }
        )
        
        return processed_disbursement.id
    
    def make_payment(
        self,
        loan_id: str,
        payment_amount: Money,
        payment_date: Optional[date] = None,
        source_account_id: Optional[str] = None
    ) -> LoanPayment:
        """
        Process a loan payment
        
        Args:
            loan_id: Loan ID
            payment_amount: Payment amount
            payment_date: Date of payment (defaults to today)
            source_account_id: Source account for payment
            
        Returns:
            LoanPayment record
        """
        if not payment_date:
            payment_date = date.today()
        
        loan = self.get_loan(loan_id)
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")
        
        if not loan.is_active:
            # Debug information
            print(f"DEBUG: Loan state={loan.state}, is_active={loan.is_active}, days_past_due={loan.days_past_due}")
            print(f"DEBUG: States that should be active: {[LoanState.DISBURSED, LoanState.ACTIVE]}")
            raise ValueError(f"Loan {loan_id} is not active for payments")
        
        # Calculate payment allocation (interest first, then principal)
        interest_due, principal_due = self._calculate_payment_allocation(loan, payment_amount)
        
        # Check for late fees
        late_fee = Money(Decimal('0'), payment_amount.currency)
        if loan.is_past_due:
            late_fee = loan.terms.late_fee
            payment_amount = payment_amount - late_fee  # Deduct late fee from payment
        
        # Check for prepayment penalty
        prepayment_penalty = Money(Decimal('0'), payment_amount.currency)
        if self._is_prepayment(loan, payment_amount) and loan.terms.prepayment_penalty_rate:
            # Prepayment amount is the excess over the scheduled monthly payment
            prepayment_amount = payment_amount - loan.monthly_payment
            penalty_rate = loan.terms.prepayment_penalty_rate
            if prepayment_amount.is_positive():
                prepayment_penalty = prepayment_amount * penalty_rate
        
        # Use atomic transaction for payment processing
        with self.storage.atomic():
            # Create payment transaction
            payment_transaction = self.transaction_processor.create_transaction(
                transaction_type=TransactionType.PAYMENT,
                amount=payment_amount + late_fee + prepayment_penalty,
                description=f"Loan payment",
                channel=TransactionChannel.SYSTEM,
                from_account_id=source_account_id,
                to_account_id=loan.account_id,  # Payment credits the loan account (reduces liability)
                reference=f"LOAN-PMT-{loan_id[:8]}"
            )
            
            # Process transaction
            processed_payment = self.transaction_processor.process_transaction(payment_transaction.id)
            
            # Create payment record
            loan_payment = LoanPayment(
                id=str(uuid.uuid4()),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                loan_id=loan.id,
                transaction_id=processed_payment.id,
                payment_date=payment_date,
                payment_amount=payment_amount,
                principal_amount=min(principal_due, payment_amount),
                interest_amount=min(interest_due, payment_amount),
                late_fee=late_fee,
                prepayment_penalty=prepayment_penalty
            )
            
            # Save payment
            self._save_payment(loan_payment)
            
            # Update loan balances
            self._update_loan_after_payment(loan, loan_payment)
            
            # Log audit event
            self.audit_trail.log_event(
                event_type=AuditEventType.LOAN_PAYMENT_MADE,
                entity_type="loan",
                entity_id=loan.id,
                metadata={
                    "payment_id": loan_payment.id,
                    "transaction_id": processed_payment.id,
                    "payment_amount": payment_amount.to_string(),
                    "principal_amount": loan_payment.principal_amount.to_string(),
                    "interest_amount": loan_payment.interest_amount.to_string(),
                    "remaining_balance": loan.current_balance.to_string()
                }
            )
        
        return loan_payment
    
    def generate_amortization_schedule(self, loan_id: str) -> List[AmortizationEntry]:
        """
        Generate amortization schedule for loan
        
        Args:
            loan_id: Loan ID
            
        Returns:
            List of AmortizationEntry objects
        """
        loan = self.get_loan(loan_id)
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")
        
        schedule = []
        
        if loan.terms.amortization_method == AmortizationMethod.EQUAL_INSTALLMENT:
            schedule = self._generate_equal_installment_schedule(loan)
        elif loan.terms.amortization_method == AmortizationMethod.EQUAL_PRINCIPAL:
            schedule = self._generate_equal_principal_schedule(loan)
        elif loan.terms.amortization_method == AmortizationMethod.BULLET:
            schedule = self._generate_bullet_schedule(loan)
        else:
            raise ValueError(f"Unsupported amortization method: {loan.terms.amortization_method}")
        
        # Save schedule entries
        for entry in schedule:
            entry_dict = self._amortization_entry_to_dict(entry, loan_id)
            entry_id = f"{loan_id}_{entry.payment_number}"
            self.storage.save(self.amortization_table, entry_id, entry_dict)
        
        return schedule
    
    def get_loan(self, loan_id: str) -> Optional[Loan]:
        """Get loan by ID"""
        loan_dict = self.storage.load(self.loans_table, loan_id)
        if loan_dict:
            return self._loan_from_dict(loan_dict)
        return None
    
    def get_customer_loans(self, customer_id: str) -> List[Loan]:
        """Get all loans for a customer"""
        loans_data = self.storage.find(self.loans_table, {"customer_id": customer_id})
        return [self._loan_from_dict(data) for data in loans_data]
    
    def get_loan_payments(self, loan_id: str) -> List[LoanPayment]:
        """Get payment history for loan"""
        payments_data = self.storage.find(self.payments_table, {"loan_id": loan_id})
        payments = [self._payment_from_dict(data) for data in payments_data]
        
        # Sort by payment date
        payments.sort(key=lambda x: x.payment_date)
        return payments
    
    def get_amortization_schedule(self, loan_id: str) -> List[AmortizationEntry]:
        """Get amortization schedule for loan"""
        # Find all schedule entries for this loan
        all_entries = self.storage.load_all(self.amortization_table)
        loan_entries = [data for data in all_entries if data.get('loan_id') == loan_id]
        
        # Convert to objects and sort by payment number
        schedule = [self._amortization_entry_from_dict(data) for data in loan_entries]
        schedule.sort(key=lambda x: x.payment_number)
        
        return schedule
    
    def process_past_due_loans(self) -> Dict[str, int]:
        """Process past due loans and charge late fees"""
        results = {"late_fees_charged": 0, "loans_processed": 0}
        
        # Get all active loans
        all_loans_data = self.storage.find(
            self.loans_table,
            {"state": LoanState.ACTIVE.value}
        )
        loans = [self._loan_from_dict(data) for data in all_loans_data]
        
        today = date.today()
        
        for loan in loans:
            try:
                # Check if loan is past due
                days_past_due = self._calculate_days_past_due(loan, today)
                
                if days_past_due > loan.terms.grace_period_days:
                    # Charge late fee if not already charged this month
                    should_charge_fee = (
                        not loan.last_late_fee_date or
                        loan.last_late_fee_date.month != today.month or
                        loan.last_late_fee_date.year != today.year
                    )
                    
                    if should_charge_fee:
                        self._charge_late_fee(loan)
                        results["late_fees_charged"] += 1
                    
                    # Update past due days
                    loan.days_past_due = days_past_due
                    loan.updated_at = datetime.now(timezone.utc)
                    self._save_loan(loan)
                    
                    results["loans_processed"] += 1
            
            except Exception as e:
                # Log error but continue with other loans
                self.audit_trail.log_event(
                    event_type=AuditEventType.SYSTEM_START,  # Generic error
                    entity_type="loan",
                    entity_id=loan.id,
                    metadata={
                        "error": "Past due processing failed",
                        "message": str(e)
                    }
                )
        
        return results
    
    def _generate_equal_installment_schedule(self, loan: Loan) -> List[AmortizationEntry]:
        """Generate equal installment amortization schedule"""
        schedule = []
        
        # Calculate payment amount
        payment_amount = loan._calculate_payment_amount()
        
        remaining_balance = loan.terms.principal_amount
        payment_date = loan.terms.first_payment_date
        annual_rate = loan.terms.annual_interest_rate
        periods_per_year = Decimal(str(loan.terms.payments_per_year))
        periodic_rate = annual_rate / periods_per_year
        
        for payment_num in range(1, loan.terms.total_payments + 1):
            # Calculate interest on remaining balance
            interest_amount = remaining_balance * periodic_rate
            
            # Principal is payment minus interest
            principal_amount = payment_amount - interest_amount
            
            # Ensure we don't overpay on final payment
            if principal_amount > remaining_balance:
                principal_amount = remaining_balance
                payment_amount = principal_amount + interest_amount
            
            # For final payment, ensure we pay off the exact remaining balance
            if payment_num == loan.terms.total_payments:
                principal_amount = remaining_balance  # Pay exactly what's left
                payment_amount = principal_amount + interest_amount
                remaining_balance = Money(Decimal('0'), remaining_balance.currency)
            else:
                # Update remaining balance
                remaining_balance = remaining_balance - principal_amount
            
            # Create schedule entry
            entry = AmortizationEntry(
                payment_number=payment_num,
                payment_date=payment_date,
                payment_amount=payment_amount,
                principal_amount=principal_amount,
                interest_amount=interest_amount,
                remaining_balance=remaining_balance
            )
            schedule.append(entry)
            
            # Move to next payment date
            if loan.terms.payment_frequency == PaymentFrequency.MONTHLY:
                payment_date = self._add_months(payment_date, 1)
            elif loan.terms.payment_frequency == PaymentFrequency.WEEKLY:
                payment_date = payment_date + timedelta(days=7)
            elif loan.terms.payment_frequency == PaymentFrequency.BI_WEEKLY:
                payment_date = payment_date + timedelta(days=14)
            elif loan.terms.payment_frequency == PaymentFrequency.QUARTERLY:
                payment_date = self._add_months(payment_date, 3)
            elif loan.terms.payment_frequency == PaymentFrequency.SEMI_ANNUALLY:
                payment_date = self._add_months(payment_date, 6)
            elif loan.terms.payment_frequency == PaymentFrequency.ANNUALLY:
                payment_date = self._add_months(payment_date, 12)
            
            # Break if balance is paid off
            if remaining_balance.is_zero():
                break
        
        return schedule
    
    def _generate_equal_principal_schedule(self, loan: Loan) -> List[AmortizationEntry]:
        """Generate equal principal amortization schedule"""
        schedule = []
        
        principal_per_payment = loan.terms.principal_amount / Decimal(str(loan.terms.total_payments))
        remaining_balance = loan.terms.principal_amount
        payment_date = loan.terms.first_payment_date
        annual_rate = loan.terms.annual_interest_rate
        periods_per_year = Decimal(str(loan.terms.payments_per_year))
        periodic_rate = annual_rate / periods_per_year
        
        for payment_num in range(1, loan.terms.total_payments + 1):
            # Interest on remaining balance
            interest_amount = remaining_balance * periodic_rate
            
            # Principal amount is fixed
            principal_amount = principal_per_payment
            if principal_amount > remaining_balance:
                principal_amount = remaining_balance
            
            # Total payment is principal + interest
            payment_amount = principal_amount + interest_amount
            
            # Update remaining balance
            remaining_balance = remaining_balance - principal_amount
            
            # Create schedule entry
            entry = AmortizationEntry(
                payment_number=payment_num,
                payment_date=payment_date,
                payment_amount=payment_amount,
                principal_amount=principal_amount,
                interest_amount=interest_amount,
                remaining_balance=remaining_balance
            )
            schedule.append(entry)
            
            # Move to next payment date (same logic as equal installment)
            payment_date = self._calculate_next_payment_date(payment_date, loan.terms.payment_frequency)
            
            if remaining_balance.is_zero():
                break
        
        return schedule
    
    def _generate_bullet_schedule(self, loan: Loan) -> List[AmortizationEntry]:
        """Generate bullet payment schedule (interest only, principal at end)"""
        schedule = []
        
        remaining_balance = loan.terms.principal_amount
        payment_date = loan.terms.first_payment_date
        annual_rate = loan.terms.annual_interest_rate
        periods_per_year = Decimal(str(loan.terms.payments_per_year))
        periodic_rate = annual_rate / periods_per_year
        
        # Interest-only payments for all but last payment
        interest_payment = remaining_balance * periodic_rate
        
        for payment_num in range(1, loan.terms.total_payments):
            entry = AmortizationEntry(
                payment_number=payment_num,
                payment_date=payment_date,
                payment_amount=interest_payment,
                principal_amount=Money(Decimal('0'), loan.terms.principal_amount.currency),
                interest_amount=interest_payment,
                remaining_balance=remaining_balance
            )
            schedule.append(entry)
            
            payment_date = self._calculate_next_payment_date(payment_date, loan.terms.payment_frequency)
        
        # Final payment includes all principal plus final interest
        final_payment = remaining_balance + interest_payment
        
        final_entry = AmortizationEntry(
            payment_number=loan.terms.total_payments,
            payment_date=payment_date,
            payment_amount=final_payment,
            principal_amount=remaining_balance,
            interest_amount=interest_payment,
            remaining_balance=Money(Decimal('0'), loan.terms.principal_amount.currency)
        )
        schedule.append(final_entry)
        
        return schedule
    
    def _calculate_payment_allocation(self, loan: Loan, payment_amount: Money) -> Tuple[Money, Money]:
        """Calculate how payment should be allocated between interest and principal"""
        # Simple allocation: interest first, then principal
        # In practice, this would be more sophisticated based on amortization schedule
        
        # Calculate current interest due (simplified)
        annual_rate = loan.terms.annual_interest_rate
        periods_per_year = Decimal(str(loan.terms.payments_per_year))
        periodic_rate = annual_rate / periods_per_year
        
        interest_due = loan.current_balance * periodic_rate
        principal_due = payment_amount - interest_due
        
        # Ensure non-negative amounts
        if principal_due.is_negative():
            principal_due = Money(Decimal('0'), payment_amount.currency)
            interest_due = payment_amount
        
        return interest_due, principal_due
    
    def _is_prepayment(self, loan: Loan, payment_amount: Money) -> bool:
        """Check if payment is a prepayment (exceeds scheduled amount)"""
        scheduled_payment = loan.monthly_payment
        return payment_amount > scheduled_payment
    
    def _update_loan_after_payment(self, loan: Loan, payment: LoanPayment) -> None:
        """Update loan balances and status after payment"""
        loan.current_balance = loan.current_balance - payment.principal_amount
        loan.total_paid = loan.total_paid + payment.payment_amount
        loan.principal_paid = loan.principal_paid + payment.principal_amount
        loan.interest_paid = loan.interest_paid + payment.interest_amount
        loan.last_payment_date = payment.payment_date
        
        # Check if loan is paid off
        if loan.current_balance.is_zero() or loan.current_balance.is_negative():
            loan.current_balance = Money(Decimal('0'), loan.current_balance.currency)
            loan.state = LoanState.PAID_OFF
        else:
            loan.state = LoanState.ACTIVE
        
        # Reset past due status if payment brings loan current
        loan.days_past_due = max(0, loan.days_past_due - 30)  # Simplified
        
        loan.updated_at = datetime.now(timezone.utc)
        self._save_loan(loan)
    
    def _calculate_days_past_due(self, loan: Loan, as_of_date: date) -> int:
        """Calculate days past due for loan"""
        # Simplified calculation - would need actual payment schedule
        if not loan.first_payment_date:
            return 0
        
        # Check if any payment is overdue
        days_since_first_payment = (as_of_date - loan.first_payment_date).days
        
        if loan.terms.payment_frequency == PaymentFrequency.MONTHLY:
            months_elapsed = days_since_first_payment // 30
            expected_payments = months_elapsed
        else:
            # Simplified for other frequencies
            expected_payments = days_since_first_payment // 30
        
        # This would need actual payment tracking in production
        return max(0, days_since_first_payment - (expected_payments * 30))
    
    def _charge_late_fee(self, loan: Loan) -> None:
        """Charge late fee to loan"""
        fee_transaction = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.FEE,
            amount=loan.terms.late_fee,
            description="Late payment fee",
            channel=TransactionChannel.SYSTEM,
            from_account_id=loan.account_id,
            reference=f"LATE-FEE-{loan.id[:8]}"
        )
        
        self.transaction_processor.process_transaction(fee_transaction.id)
        
        loan.last_late_fee_date = date.today()
        loan.updated_at = datetime.now(timezone.utc)
        self._save_loan(loan)
    
    def _calculate_next_payment_date(self, current_date: date, frequency: PaymentFrequency) -> date:
        """Calculate next payment date based on frequency"""
        if frequency == PaymentFrequency.WEEKLY:
            return current_date + timedelta(days=7)
        elif frequency == PaymentFrequency.BI_WEEKLY:
            return current_date + timedelta(days=14)
        elif frequency == PaymentFrequency.MONTHLY:
            return self._add_months(current_date, 1)
        elif frequency == PaymentFrequency.QUARTERLY:
            return self._add_months(current_date, 3)
        elif frequency == PaymentFrequency.SEMI_ANNUALLY:
            return self._add_months(current_date, 6)
        elif frequency == PaymentFrequency.ANNUALLY:
            return self._add_months(current_date, 12)
        else:
            raise ValueError(f"Unsupported payment frequency: {frequency}")
    
    def _add_months(self, start_date: date, months: int) -> date:
        """Add months to a date, handling month-end edge cases"""
        month = start_date.month - 1 + months
        year = start_date.year + month // 12
        month = month % 12 + 1
        day = min(start_date.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    
    def _save_loan(self, loan: Loan) -> None:
        """Save loan to storage (merge with existing to preserve state changes from other operations)"""
        loan_dict = self._loan_to_dict(loan)
        existing = self.storage.load(self.loans_table, loan.id)
        if existing:
            # Merge: existing fields are base, new fields override
            # But preserve the more advanced state (e.g., DISBURSED > ORIGINATED)
            state_order = {
                'originated': 0, 'disbursed': 1, 'active': 2,
                'paid_off': 3, 'defaulted': 4, 'written_off': 5
            }
            existing_state = existing.get('state', 'originated')
            new_state = loan_dict.get('state', 'originated')
            if state_order.get(existing_state, 0) > state_order.get(new_state, 0):
                loan_dict['state'] = existing_state
            # Also preserve disbursed_date if it was set
            if existing.get('disbursed_date') and not loan_dict.get('disbursed_date'):
                loan_dict['disbursed_date'] = existing['disbursed_date']
            existing.update(loan_dict)
            loan_dict = existing
        self.storage.save(self.loans_table, loan.id, loan_dict)
    
    def _save_payment(self, payment: LoanPayment) -> None:
        """Save loan payment to storage"""
        payment_dict = self._payment_to_dict(payment)
        self.storage.save(self.payments_table, payment.id, payment_dict)
    
    def _loan_to_dict(self, loan: Loan) -> Dict:
        """Convert loan to dictionary"""
        result = loan.to_dict()
        result['state'] = loan.state.value
        
        # Convert terms
        terms_dict = {
            'principal_amount': str(loan.terms.principal_amount.amount),
            'principal_currency': loan.terms.principal_amount.currency.code,
            'annual_interest_rate': str(loan.terms.annual_interest_rate),
            'term_months': loan.terms.term_months,
            'payment_frequency': loan.terms.payment_frequency.value,
            'amortization_method': loan.terms.amortization_method.value,
            'first_payment_date': loan.terms.first_payment_date.isoformat(),
            'allow_prepayment': loan.terms.allow_prepayment,
            'grace_period_days': loan.terms.grace_period_days,
            'late_fee': str(loan.terms.late_fee.amount),
            'late_fee_currency': loan.terms.late_fee.currency.code
        }
        
        if loan.terms.prepayment_penalty_rate:
            terms_dict['prepayment_penalty_rate'] = str(loan.terms.prepayment_penalty_rate)
        
        result['terms'] = terms_dict
        
        # Convert money amounts
        for field in ['current_balance', 'total_paid', 'interest_paid', 'principal_paid']:
            amount = getattr(loan, field)
            result[f'{field}_amount'] = str(amount.amount)
            result[f'{field}_currency'] = amount.currency.code
        
        # Convert dates
        for field in ['originated_date', 'disbursed_date', 'first_payment_date', 
                      'last_payment_date', 'maturity_date', 'last_late_fee_date']:
            date_value = getattr(loan, field)
            if date_value:
                result[field] = date_value.isoformat()
        
        return result
    
    def _loan_from_dict(self, data: Dict) -> Loan:
        """Convert dictionary to loan"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        # Reconstruct terms
        terms_data = data['terms']
        
        prepayment_penalty_rate = None
        if terms_data.get('prepayment_penalty_rate'):
            prepayment_penalty_rate = Decimal(terms_data['prepayment_penalty_rate'])
        
        terms = LoanTerms(
            principal_amount=Money(
                Decimal(terms_data['principal_amount']),
                Currency[terms_data['principal_currency']]
            ),
            annual_interest_rate=Decimal(terms_data['annual_interest_rate']),
            term_months=terms_data['term_months'],
            payment_frequency=PaymentFrequency(terms_data['payment_frequency']),
            amortization_method=AmortizationMethod(terms_data['amortization_method']),
            first_payment_date=date.fromisoformat(terms_data['first_payment_date']),
            allow_prepayment=terms_data['allow_prepayment'],
            prepayment_penalty_rate=prepayment_penalty_rate,
            grace_period_days=terms_data['grace_period_days'],
            late_fee=Money(
                Decimal(terms_data['late_fee']),
                Currency[terms_data['late_fee_currency']]
            )
        )
        
        # Reconstruct money amounts
        def get_money(field_prefix: str) -> Money:
            return Money(
                Decimal(data[f'{field_prefix}_amount']),
                Currency[data[f'{field_prefix}_currency']]
            )
        
        # Reconstruct dates
        def get_date(field: str) -> Optional[date]:
            if data.get(field):
                return date.fromisoformat(data[field])
            return None
        
        return Loan(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            account_id=data['account_id'],
            customer_id=data['customer_id'],
            terms=terms,
            state=LoanState(data['state']),
            current_balance=get_money('current_balance'),
            total_paid=get_money('total_paid'),
            interest_paid=get_money('interest_paid'),
            principal_paid=get_money('principal_paid'),
            originated_date=get_date('originated_date'),
            disbursed_date=get_date('disbursed_date'),
            first_payment_date=get_date('first_payment_date'),
            last_payment_date=get_date('last_payment_date'),
            maturity_date=get_date('maturity_date'),
            days_past_due=data.get('days_past_due', 0),
            last_late_fee_date=get_date('last_late_fee_date')
        )
    
    def _payment_to_dict(self, payment: LoanPayment) -> Dict:
        """Convert payment to dictionary"""
        result = payment.to_dict()
        result['payment_date'] = payment.payment_date.isoformat()
        
        # Convert money amounts
        for field in ['payment_amount', 'principal_amount', 'interest_amount', 'late_fee', 'prepayment_penalty']:
            amount = getattr(payment, field)
            result[f'{field}_amount'] = str(amount.amount)
            result[f'{field}_currency'] = amount.currency.code
        
        return result
    
    def _payment_from_dict(self, data: Dict) -> LoanPayment:
        """Convert dictionary to payment"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        payment_date = date.fromisoformat(data['payment_date'])
        
        def get_money(field_prefix: str) -> Money:
            return Money(
                Decimal(data[f'{field_prefix}_amount']),
                Currency[data[f'{field_prefix}_currency']]
            )
        
        return LoanPayment(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            loan_id=data['loan_id'],
            transaction_id=data['transaction_id'],
            payment_date=payment_date,
            payment_amount=get_money('payment_amount'),
            principal_amount=get_money('principal_amount'),
            interest_amount=get_money('interest_amount'),
            late_fee=get_money('late_fee'),
            prepayment_penalty=get_money('prepayment_penalty'),
            scheduled_payment_number=data.get('scheduled_payment_number')
        )
    
    def _amortization_entry_to_dict(self, entry: AmortizationEntry, loan_id: str) -> Dict:
        """Convert amortization entry to dictionary"""
        return {
            'loan_id': loan_id,
            'payment_number': entry.payment_number,
            'payment_date': entry.payment_date.isoformat(),
            'payment_amount': str(entry.payment_amount.amount),
            'payment_currency': entry.payment_amount.currency.code,
            'principal_amount': str(entry.principal_amount.amount),
            'principal_currency': entry.principal_amount.currency.code,
            'interest_amount': str(entry.interest_amount.amount),
            'interest_currency': entry.interest_amount.currency.code,
            'remaining_balance': str(entry.remaining_balance.amount),
            'remaining_currency': entry.remaining_balance.currency.code
        }
    
    def _amortization_entry_from_dict(self, data: Dict) -> AmortizationEntry:
        """Convert dictionary to amortization entry"""
        return AmortizationEntry(
            payment_number=data['payment_number'],
            payment_date=date.fromisoformat(data['payment_date']),
            payment_amount=Money(Decimal(data['payment_amount']), Currency[data['payment_currency']]),
            principal_amount=Money(Decimal(data['principal_amount']), Currency[data['principal_currency']]),
            interest_amount=Money(Decimal(data['interest_amount']), Currency[data['interest_currency']]),
            remaining_balance=Money(Decimal(data['remaining_balance']), Currency[data['remaining_currency']])
        )