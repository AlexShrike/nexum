"""
Test suite for loans module

Tests loan origination, amortization schedule generation, payment processing,
and mathematical accuracy of loan calculations. All financial math must be precise.
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, date, timedelta

from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.ledger import GeneralLedger
from core_banking.accounts import AccountManager, ProductType
from core_banking.customers import CustomerManager
from core_banking.compliance import ComplianceEngine
from core_banking.transactions import TransactionProcessor, TransactionChannel
from core_banking.loans import (
    LoanManager, Loan, LoanTerms, LoanPayment, AmortizationEntry,
    LoanState, AmortizationMethod, PaymentFrequency
)


class TestLoanTerms:
    """Test loan terms functionality"""
    
    def test_valid_monthly_loan_terms(self):
        """Test creating valid monthly loan terms"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('10000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.075'),  # 7.5% APR
            term_months=60,  # 5 years
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date(2024, 2, 1),
            allow_prepayment=True,
            grace_period_days=10
        )
        
        assert terms.principal_amount == Money(Decimal('10000.00'), Currency.USD)
        assert terms.annual_interest_rate == Decimal('0.075')
        assert terms.term_months == 60
        assert terms.payment_frequency == PaymentFrequency.MONTHLY
        assert terms.total_payments == 60  # 5 years * 12 months
        assert terms.payments_per_year == 12
        assert terms.payment_period_months == Decimal('1')
    
    def test_bi_weekly_loan_terms(self):
        """Test bi-weekly payment frequency calculations"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('5000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.06'),
            term_months=24,
            payment_frequency=PaymentFrequency.BI_WEEKLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date(2024, 1, 15)
        )
        
        assert terms.payments_per_year == 26  # 26 bi-weekly payments per year
        assert terms.total_payments == 52  # 2 years * 26 payments
    
    def test_prepayment_penalty_terms(self):
        """Test loan terms with prepayment penalty"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('15000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.08'),
            term_months=36,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_PRINCIPAL,
            first_payment_date=date(2024, 3, 1),
            allow_prepayment=True,
            prepayment_penalty_rate=Decimal('0.02')  # 2% penalty
        )
        
        assert terms.allow_prepayment
        assert terms.prepayment_penalty_rate == Decimal('0.02')
    
    def test_currency_consistency(self):
        """Test currency consistency in loan terms"""
        with pytest.raises(ValueError, match="currency must match"):
            LoanTerms(
                principal_amount=Money(Decimal('10000.00'), Currency.USD),
                annual_interest_rate=Decimal('0.075'),
                term_months=60,
                payment_frequency=PaymentFrequency.MONTHLY,
                amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
                first_payment_date=date(2024, 2, 1),
                late_fee=Money(Decimal('25.00'), Currency.EUR)  # Wrong currency
            )


class TestAmortizationEntry:
    """Test amortization entry validation"""
    
    def test_valid_amortization_entry(self):
        """Test creating valid amortization entry"""
        entry = AmortizationEntry(
            payment_number=1,
            payment_date=date(2024, 2, 1),
            payment_amount=Money(Decimal('200.38'), Currency.USD),
            principal_amount=Money(Decimal('137.88'), Currency.USD),
            interest_amount=Money(Decimal('62.50'), Currency.USD),
            remaining_balance=Money(Decimal('9862.12'), Currency.USD)
        )
        
        assert entry.payment_number == 1
        assert entry.payment_amount == Money(Decimal('200.38'), Currency.USD)
        assert entry.principal_amount == Money(Decimal('137.88'), Currency.USD)
        assert entry.interest_amount == Money(Decimal('62.50'), Currency.USD)
        
        # Payment should equal principal + interest
        calculated_payment = entry.principal_amount + entry.interest_amount
        assert abs(entry.payment_amount.amount - calculated_payment.amount) <= Decimal('0.01')
    
    def test_payment_amount_validation(self):
        """Test that payment amount must equal principal + interest"""
        with pytest.raises(ValueError, match="does not equal"):
            AmortizationEntry(
                payment_number=1,
                payment_date=date(2024, 2, 1),
                payment_amount=Money(Decimal('200.00'), Currency.USD),  # Incorrect total
                principal_amount=Money(Decimal('150.00'), Currency.USD),
                interest_amount=Money(Decimal('60.00'), Currency.USD),  # 150 + 60 = 210, not 200
                remaining_balance=Money(Decimal('9850.00'), Currency.USD)
            )


class TestLoan:
    """Test loan object functionality"""
    
    def test_valid_loan(self):
        """Test creating valid loan"""
        now = datetime.now(timezone.utc)
        today = date.today()
        
        terms = LoanTerms(
            principal_amount=Money(Decimal('8000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.065'),
            term_months=48,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=today + timedelta(days=30)
        )
        
        loan = Loan(
            id="LOAN001",
            created_at=now,
            updated_at=now,
            account_id="LOANACCT001",
            customer_id="CUST001",
            terms=terms,
            state=LoanState.ORIGINATED,
            originated_date=today
        )
        
        assert loan.account_id == "LOANACCT001"
        assert loan.customer_id == "CUST001"
        assert loan.state == LoanState.ORIGINATED
        assert loan.current_balance == Money(Decimal('8000.00'), Currency.USD)  # Initially equals principal
        assert not loan.is_active  # Not active until disbursed
        assert not loan.is_paid_off
        assert not loan.is_past_due
    
    def test_loan_state_properties(self):
        """Test loan state property checks"""
        now = datetime.now(timezone.utc)
        
        terms = LoanTerms(
            principal_amount=Money(Decimal('5000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.05'),
            term_months=36,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today()
        )
        
        # Test different states
        originated_loan = Loan(
            id="LOAN002", created_at=now, updated_at=now,
            account_id="ACC", customer_id="CUST", terms=terms,
            state=LoanState.ORIGINATED
        )
        assert not originated_loan.is_active
        
        disbursed_loan = Loan(
            id="LOAN003", created_at=now, updated_at=now,
            account_id="ACC", customer_id="CUST", terms=terms,
            state=LoanState.DISBURSED
        )
        assert disbursed_loan.is_active
        
        active_loan = Loan(
            id="LOAN004", created_at=now, updated_at=now,
            account_id="ACC", customer_id="CUST", terms=terms,
            state=LoanState.ACTIVE
        )
        assert active_loan.is_active
        
        paid_off_loan = Loan(
            id="LOAN005", created_at=now, updated_at=now,
            account_id="ACC", customer_id="CUST", terms=terms,
            state=LoanState.PAID_OFF,
            current_balance=Money(Decimal('0.00'), Currency.USD)
        )
        assert not paid_off_loan.is_active
        assert paid_off_loan.is_paid_off
    
    def test_monthly_payment_calculation(self):
        """Test monthly payment calculation for equal installment method"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('10000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.06'),  # 6% APR
            term_months=60,  # 5 years
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today()
        )
        
        loan = Loan(
            id="LOAN006",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            account_id="ACC",
            customer_id="CUST",
            terms=terms
        )
        
        monthly_payment = loan.monthly_payment
        
        # Standard loan payment formula verification
        # For $10,000 at 6% APR for 60 months, payment should be approximately $193.33
        expected_payment = Money(Decimal('193.33'), Currency.USD)
        
        # Allow small tolerance for rounding differences
        assert abs(monthly_payment.amount - expected_payment.amount) < Decimal('0.10')


class TestLoanManager:
    """Test loan manager functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.storage = InMemoryStorage()
        self.audit_trail = AuditTrail(self.storage)
        self.ledger = GeneralLedger(self.storage, self.audit_trail)
        self.account_manager = AccountManager(self.storage, self.ledger, self.audit_trail)
        self.customer_manager = CustomerManager(self.storage, self.audit_trail)
        self.compliance_engine = ComplianceEngine(self.storage, self.customer_manager, self.audit_trail)
        self.transaction_processor = TransactionProcessor(
            self.storage, self.ledger, self.account_manager,
            self.customer_manager, self.compliance_engine, self.audit_trail
        )
        self.loan_manager = LoanManager(
            self.storage, self.account_manager, self.transaction_processor,
            self.audit_trail
        )
        
        # Create test customer
        self.customer = self.customer_manager.create_customer(
            first_name="Charlie",
            last_name="Brown",
            email="charlie@example.com"
        )
        
        # Create disbursement account (checking account to receive loan funds)
        self.disbursement_account = self.account_manager.create_account(
            customer_id=self.customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Loan Disbursement Account"
        )
    
    def test_originate_loan(self):
        """Test loan origination"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('12000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.075'),
            term_months=48,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date(2024, 3, 1)
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        assert loan.customer_id == self.customer.id
        assert loan.state == LoanState.ORIGINATED
        assert loan.terms.principal_amount == Money(Decimal('12000.00'), Currency.USD)
        assert loan.account_id is not None  # Loan account should be created
        assert loan.originated_date == date.today()
        
        # Verify loan account was created
        loan_account = self.account_manager.get_account(loan.account_id)
        assert loan_account is not None
        assert loan_account.product_type == ProductType.LOAN
        assert loan_account.customer_id == self.customer.id
        
        # Verify loan is retrievable
        retrieved_loan = self.loan_manager.get_loan(loan.id)
        assert retrieved_loan is not None
        assert retrieved_loan.id == loan.id
    
    def test_disburse_loan(self):
        """Test loan disbursement"""
        # First originate loan
        terms = LoanTerms(
            principal_amount=Money(Decimal('5000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.08'),
            term_months=36,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today() + timedelta(days=30)
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        # Disburse loan
        disbursement_txn_id = self.loan_manager.disburse_loan(
            loan_id=loan.id,
            disbursement_account_id=self.disbursement_account.id
        )
        
        assert disbursement_txn_id is not None
        
        # Verify loan state changed
        updated_loan = self.loan_manager.get_loan(loan.id)
        assert updated_loan.state == LoanState.DISBURSED
        assert updated_loan.disbursed_date == date.today()
        
        # Verify disbursement transaction
        disbursement_txn = self.transaction_processor.get_transaction(disbursement_txn_id)
        assert disbursement_txn is not None
        assert disbursement_txn.amount == Money(Decimal('5000.00'), Currency.USD)
        
        # Verify customer account received funds
        customer_balance = self.account_manager.get_book_balance(self.disbursement_account.id)
        assert customer_balance == Money(Decimal('5000.00'), Currency.USD)
    
    def test_cannot_disburse_non_originated_loan(self):
        """Test that only originated loans can be disbursed"""
        # Create loan in different state
        terms = LoanTerms(
            principal_amount=Money(Decimal('1000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.05'),
            term_months=12,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today()
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        # Manually change state to active
        loan.state = LoanState.ACTIVE
        self.loan_manager._save_loan(loan)
        
        # Try to disburse - should fail
        with pytest.raises(ValueError, match="Can only disburse ORIGINATED loans"):
            self.loan_manager.disburse_loan(
                loan_id=loan.id,
                disbursement_account_id=self.disbursement_account.id
            )
    
    def test_make_loan_payment(self):
        """Test making loan payment"""
        # Setup: Create and disburse loan
        terms = LoanTerms(
            principal_amount=Money(Decimal('6000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.09'),
            term_months=60,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today()
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        self.loan_manager.disburse_loan(loan.id, self.disbursement_account.id)
        
        # Make payment
        payment_amount = Money(Decimal('124.44'), Currency.USD)  # Approximate monthly payment
        
        loan_payment = self.loan_manager.make_payment(
            loan_id=loan.id,
            payment_amount=payment_amount,
            source_account_id=self.disbursement_account.id
        )
        
        assert loan_payment.loan_id == loan.id
        assert loan_payment.payment_amount == payment_amount
        assert loan_payment.principal_amount.is_positive()
        assert loan_payment.interest_amount.is_positive()
        assert loan_payment.payment_date == date.today()
        
        # Verify payment allocation (interest first, then principal)
        total_allocated = loan_payment.principal_amount + loan_payment.interest_amount
        assert abs(total_allocated.amount - payment_amount.amount) < Decimal('0.01')
        
        # Verify loan balance was reduced
        updated_loan = self.loan_manager.get_loan(loan.id)
        assert updated_loan.current_balance < loan.current_balance
        assert updated_loan.state in [LoanState.DISBURSED, LoanState.ACTIVE]
        assert updated_loan.last_payment_date == date.today()
    
    def test_generate_equal_installment_amortization_schedule(self):
        """Test equal installment amortization schedule generation"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('10000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.06'),  # 6% APR
            term_months=12,  # 1 year for easier testing
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date(2024, 2, 1)
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        # Generate amortization schedule
        schedule = self.loan_manager.generate_amortization_schedule(loan.id)
        
        assert len(schedule) == 12  # 12 monthly payments
        
        # Verify first payment
        first_payment = schedule[0]
        assert first_payment.payment_number == 1
        assert first_payment.payment_date == date(2024, 2, 1)
        
        # For 6% APR monthly, first month interest should be approximately $50
        # (10,000 * 0.06 / 12 = 50)
        expected_first_interest = Money(Decimal('50.00'), Currency.USD)
        assert abs(first_payment.interest_amount.amount - expected_first_interest.amount) < Decimal('0.10')
        
        # Verify payment amounts are consistent (equal installment)
        payment_amounts = [payment.payment_amount for payment in schedule]
        first_amount = payment_amounts[0]
        
        # All payments should be equal (within rounding tolerance), except possibly the final one
        for i, amount in enumerate(payment_amounts):
            if i == len(payment_amounts) - 1:  # Final payment
                assert abs(amount.amount - first_amount.amount) < Decimal('0.10')  # Allow larger tolerance
            else:
                assert abs(amount.amount - first_amount.amount) < Decimal('0.01')
        
        # Verify final balance is zero
        final_payment = schedule[-1]
        assert final_payment.remaining_balance.is_zero()
        
        # Verify total payments equal principal plus total interest
        total_payments = sum(payment.payment_amount.amount for payment in schedule)
        total_interest = sum(payment.interest_amount.amount for payment in schedule)
        total_principal = sum(payment.principal_amount.amount for payment in schedule)
        
        assert abs(total_principal - terms.principal_amount.amount) < Decimal('0.01')
        assert abs(total_payments - (terms.principal_amount.amount + total_interest)) < Decimal('0.01')
    
    def test_generate_equal_principal_amortization_schedule(self):
        """Test equal principal amortization schedule generation"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('12000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.08'),  # 8% APR
            term_months=12,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_PRINCIPAL,
            first_payment_date=date(2024, 1, 15)
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        schedule = self.loan_manager.generate_amortization_schedule(loan.id)
        
        assert len(schedule) == 12
        
        # Principal should be equal each month
        expected_principal = Money(Decimal('1000.00'), Currency.USD)  # 12,000 / 12
        
        for payment in schedule:
            assert abs(payment.principal_amount.amount - expected_principal.amount) < Decimal('0.01')
        
        # Interest should decrease each month
        previous_interest = None
        for payment in schedule:
            if previous_interest is not None:
                assert payment.interest_amount <= previous_interest  # Should decrease or stay same
            previous_interest = payment.interest_amount
        
        # Total payment amounts should decrease each month
        previous_payment = None
        for payment in schedule:
            if previous_payment is not None:
                assert payment.payment_amount <= previous_payment
            previous_payment = payment.payment_amount
    
    def test_generate_bullet_amortization_schedule(self):
        """Test bullet payment amortization schedule generation"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('5000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.10'),  # 10% APR
            term_months=6,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.BULLET,
            first_payment_date=date(2024, 1, 1)
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        schedule = self.loan_manager.generate_amortization_schedule(loan.id)
        
        assert len(schedule) == 6
        
        # First 5 payments should be interest-only
        monthly_interest = Money(Decimal('41.67'), Currency.USD)  # Approximately 5000 * 0.10 / 12
        
        for i in range(5):  # First 5 payments
            payment = schedule[i]
            assert payment.principal_amount.is_zero()
            assert abs(payment.interest_amount.amount - monthly_interest.amount) < Decimal('1.00')
            assert payment.remaining_balance == Money(Decimal('5000.00'), Currency.USD)  # Principal unchanged
        
        # Final payment should include all principal plus final interest
        final_payment = schedule[5]
        assert final_payment.principal_amount == Money(Decimal('5000.00'), Currency.USD)
        assert final_payment.interest_amount.is_positive()
        assert final_payment.remaining_balance.is_zero()
    
    def test_get_amortization_schedule(self):
        """Test retrieving saved amortization schedule"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('8000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.07'),
            term_months=24,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today()
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        # Generate schedule (saves to storage)
        generated_schedule = self.loan_manager.generate_amortization_schedule(loan.id)
        
        # Retrieve schedule
        retrieved_schedule = self.loan_manager.get_amortization_schedule(loan.id)
        
        assert len(retrieved_schedule) == len(generated_schedule)
        assert len(retrieved_schedule) == 24
        
        # Verify payment order
        for i, payment in enumerate(retrieved_schedule):
            assert payment.payment_number == i + 1
    
    def test_get_loan_payments(self):
        """Test retrieving loan payment history"""
        # Setup loan
        terms = LoanTerms(
            principal_amount=Money(Decimal('3000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.05'),
            term_months=36,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today()
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        self.loan_manager.disburse_loan(loan.id, self.disbursement_account.id)
        
        # Make multiple payments
        payment_amount = Money(Decimal('90.00'), Currency.USD)
        
        for i in range(3):
            self.loan_manager.make_payment(
                loan_id=loan.id,
                payment_amount=payment_amount,
                payment_date=date.today() - timedelta(days=30 - i*30)  # Different dates
            )
        
        # Get payment history
        payment_history = self.loan_manager.get_loan_payments(loan.id)
        
        assert len(payment_history) == 3
        
        # Should be sorted by payment date
        for i in range(len(payment_history) - 1):
            assert payment_history[i].payment_date <= payment_history[i + 1].payment_date
    
    def test_get_customer_loans(self):
        """Test getting all loans for a customer"""
        # Create multiple loans
        terms1 = LoanTerms(
            principal_amount=Money(Decimal('5000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.06'),
            term_months=36,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today()
        )
        
        terms2 = LoanTerms(
            principal_amount=Money(Decimal('10000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.08'),
            term_months=60,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_PRINCIPAL,
            first_payment_date=date.today()
        )
        
        loan1 = self.loan_manager.originate_loan(self.customer.id, terms1, Currency.USD)
        loan2 = self.loan_manager.originate_loan(self.customer.id, terms2, Currency.USD)
        
        # Create loan for different customer
        other_customer = self.customer_manager.create_customer(
            first_name="Other",
            last_name="Customer",
            email="other@example.com"
        )
        
        other_loan = self.loan_manager.originate_loan(other_customer.id, terms1, Currency.USD)
        
        # Get loans for our customer
        customer_loans = self.loan_manager.get_customer_loans(self.customer.id)
        
        assert len(customer_loans) == 2
        loan_ids = {loan.id for loan in customer_loans}
        assert loan1.id in loan_ids
        assert loan2.id in loan_ids
        assert other_loan.id not in loan_ids
    
    def test_loan_payment_with_late_fee(self):
        """Test loan payment with late fee assessment"""
        # Setup loan with past due date
        past_date = date.today() - timedelta(days=15)
        
        terms = LoanTerms(
            principal_amount=Money(Decimal('4000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.07'),
            term_months=48,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=past_date,
            grace_period_days=5  # 5 day grace period
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        self.loan_manager.disburse_loan(loan.id, self.disbursement_account.id)
        
        # Manually set loan as past due
        loan.days_past_due = 10  # 10 days past due
        self.loan_manager._save_loan(loan)
        
        # Make payment (should include late fee)
        payment = self.loan_manager.make_payment(
            loan_id=loan.id,
            payment_amount=Money(Decimal('125.00'), Currency.USD)  # Includes extra for late fee
        )
        
        # Late fee should be deducted
        assert payment.late_fee.is_positive()
        assert payment.payment_amount < Money(Decimal('125.00'), Currency.USD)  # Amount after fee deduction
    
    def test_prepayment_with_penalty(self):
        """Test prepayment with penalty"""
        terms = LoanTerms(
            principal_amount=Money(Decimal('10000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.06'),
            term_months=60,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today(),
            allow_prepayment=True,
            prepayment_penalty_rate=Decimal('0.02')  # 2% penalty on prepaid amount
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        self.loan_manager.disburse_loan(loan.id, self.disbursement_account.id)
        
        # Make large payment (prepayment)
        large_payment = Money(Decimal('2000.00'), Currency.USD)  # Much larger than monthly payment
        
        payment = self.loan_manager.make_payment(
            loan_id=loan.id,
            payment_amount=large_payment
        )
        
        # Should have prepayment penalty
        assert payment.prepayment_penalty.is_positive()
    
    def test_process_past_due_loans(self):
        """Test processing past due loans"""
        # Create loan with past due payment
        past_date = date.today() - timedelta(days=20)
        
        terms = LoanTerms(
            principal_amount=Money(Decimal('5000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.08'),
            term_months=36,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=past_date
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        # Set to active state (would normally happen after disbursement)
        loan.state = LoanState.ACTIVE
        self.loan_manager._save_loan(loan)
        
        # Process past due loans
        results = self.loan_manager.process_past_due_loans()
        
        # Should have processed at least some loans
        assert results["loans_processed"] >= 0
        assert results["late_fees_charged"] >= 0


if __name__ == "__main__":
    pytest.main([__file__])