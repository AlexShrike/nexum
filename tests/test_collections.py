"""
Test suite for collections module

Tests collection case creation, delinquency status progression, action recording,
promise tracking, collection strategies, and recovery rate calculations.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, date, timedelta

from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.ledger import GeneralLedger
from core_banking.accounts import AccountManager, ProductType
from core_banking.customers import CustomerManager
from core_banking.compliance import ComplianceEngine
from core_banking.transactions import TransactionProcessor
from core_banking.loans import LoanManager, LoanTerms, LoanState, AmortizationMethod, PaymentFrequency
from core_banking.credit import CreditLineManager
from core_banking.interest import InterestEngine
from core_banking.collections import (
    CollectionsManager, CollectionCase, CollectionActionRecord, PaymentPromise,
    CollectionStrategy, DelinquencyStatus, CollectionAction, ActionResult,
    PromiseStatus, CaseResolution
)


class TestDelinquencyStatus:
    """Test delinquency status classification"""
    
    def test_delinquency_status_progression(self):
        """Test that delinquency status correctly classifies days past due"""
        now = datetime.now(timezone.utc)
        temp_case = CollectionCase(
            id="test",
            created_at=now,
            updated_at=now,
            loan_id="test_loan"
        )
        
        assert temp_case.get_delinquency_status(0) == DelinquencyStatus.CURRENT
        assert temp_case.get_delinquency_status(15) == DelinquencyStatus.EARLY
        assert temp_case.get_delinquency_status(30) == DelinquencyStatus.EARLY
        assert temp_case.get_delinquency_status(45) == DelinquencyStatus.LATE
        assert temp_case.get_delinquency_status(60) == DelinquencyStatus.LATE
        assert temp_case.get_delinquency_status(75) == DelinquencyStatus.SERIOUS
        assert temp_case.get_delinquency_status(90) == DelinquencyStatus.SERIOUS
        assert temp_case.get_delinquency_status(120) == DelinquencyStatus.DEFAULT


class TestCollectionCase:
    """Test collection case functionality"""
    
    def test_valid_collection_case_for_loan(self):
        """Test creating valid collection case for loan"""
        now = datetime.now(timezone.utc)
        
        case = CollectionCase(
            id="CASE001",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id="CUST001",
            account_id="ACC001",
            status=DelinquencyStatus.EARLY,
            days_past_due=15,
            amount_overdue=Money(Decimal('500.00'), Currency.USD),
            total_outstanding=Money(Decimal('5000.00'), Currency.USD),
            priority=2
        )
        
        assert case.loan_id == "LOAN001"
        assert case.customer_id == "CUST001"
        assert case.status == DelinquencyStatus.EARLY
        assert case.days_past_due == 15
        assert case.amount_overdue == Money(Decimal('500.00'), Currency.USD)
        assert case.priority == 2
        assert not case.is_resolved
        assert not case.is_high_priority
    
    def test_valid_collection_case_for_credit_line(self):
        """Test creating valid collection case for credit line"""
        now = datetime.now(timezone.utc)
        
        case = CollectionCase(
            id="CASE002",
            created_at=now,
            updated_at=now,
            credit_line_id="CREDIT001",
            customer_id="CUST001",
            account_id="ACC001",
            status=DelinquencyStatus.SERIOUS,
            days_past_due=75,
            amount_overdue=Money(Decimal('250.00'), Currency.USD),
            total_outstanding=Money(Decimal('3000.00'), Currency.USD),
            priority=4
        )
        
        assert case.credit_line_id == "CREDIT001"
        assert case.status == DelinquencyStatus.SERIOUS
        assert case.is_high_priority  # Priority 4 is high priority
    
    def test_case_must_have_loan_or_credit_line_id(self):
        """Test that case must have either loan_id or credit_line_id"""
        now = datetime.now(timezone.utc)
        
        with pytest.raises(ValueError, match="must have either loan_id or credit_line_id"):
            CollectionCase(
                id="CASE003",
                created_at=now,
                updated_at=now,
                customer_id="CUST001",
                account_id="ACC001"
                # Missing both loan_id and credit_line_id
            )
    
    def test_resolved_case_properties(self):
        """Test resolved case properties"""
        now = datetime.now(timezone.utc)
        
        case = CollectionCase(
            id="CASE004",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id="CUST001",
            account_id="ACC001",
            resolved_at=now,
            resolution=CaseResolution.PAID
        )
        
        assert case.is_resolved
        assert case.resolution == CaseResolution.PAID


class TestPaymentPromise:
    """Test payment promise functionality"""
    
    def test_valid_payment_promise(self):
        """Test creating valid payment promise"""
        now = datetime.now(timezone.utc)
        promise_date = date.today() + timedelta(days=7)
        
        promise = PaymentPromise(
            id="PROMISE001",
            created_at=now,
            updated_at=now,
            case_id="CASE001",
            promised_amount=Money(Decimal('500.00'), Currency.USD),
            promised_date=promise_date
        )
        
        assert promise.case_id == "CASE001"
        assert promise.promised_amount == Money(Decimal('500.00'), Currency.USD)
        assert promise.promised_date == promise_date
        assert promise.status == PromiseStatus.PENDING
        assert promise.actual_amount == Money(Decimal('0'), Currency.USD)


class TestCollectionStrategy:
    """Test collection strategy functionality"""
    
    def test_default_collection_strategy(self):
        """Test default collection strategy creation"""
        now = datetime.now(timezone.utc)
        
        strategy = CollectionStrategy(
            id="default",
            created_at=now,
            updated_at=now
        )
        
        # Should have default escalation rules
        assert len(strategy.escalation_rules) == 6
        
        # Check first few escalation rules
        assert strategy.escalation_rules[0] == (1, CollectionAction.REMINDER_SMS, True)
        assert strategy.escalation_rules[1] == (7, CollectionAction.REMINDER_EMAIL, True)
        assert strategy.escalation_rules[2] == (15, CollectionAction.REMINDER_CALL, False)
        
        # Should have default write-off period
        assert strategy.auto_write_off_days == 365
        assert strategy.promise_tolerance_days == 3
    
    def test_custom_collection_strategy(self):
        """Test custom collection strategy"""
        now = datetime.now(timezone.utc)
        
        custom_rules = [
            (5, CollectionAction.REMINDER_EMAIL, True),
            (14, CollectionAction.REMINDER_CALL, False),
            (30, CollectionAction.LEGAL_NOTICE, True)
        ]
        
        strategy = CollectionStrategy(
            id="aggressive",
            created_at=now,
            updated_at=now,
            product_id="PRODUCT001",
            escalation_rules=custom_rules,
            auto_write_off_days=180,
            promise_tolerance_days=1
        )
        
        assert strategy.product_id == "PRODUCT001"
        assert len(strategy.escalation_rules) == 3
        assert strategy.escalation_rules[0] == (5, CollectionAction.REMINDER_EMAIL, True)
        assert strategy.auto_write_off_days == 180
        assert strategy.promise_tolerance_days == 1


class TestCollectionsManager:
    """Test collections manager functionality"""
    
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
        self.interest_engine = InterestEngine(
            self.storage, self.ledger, self.account_manager,
            self.transaction_processor, self.audit_trail
        )
        self.credit_manager = CreditLineManager(
            self.storage, self.account_manager, self.transaction_processor,
            self.interest_engine, self.audit_trail
        )
        self.collections_manager = CollectionsManager(
            self.storage, self.account_manager, self.loan_manager, self.credit_manager
        )
        
        # Create test customer
        self.customer = self.customer_manager.create_customer(
            first_name="John",
            last_name="Debtor",
            email="john.debtor@example.com"
        )
        
        # Create disbursement account
        self.disbursement_account = self.account_manager.create_account(
            customer_id=self.customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Checking Account"
        )
    
    def test_create_collection_case_from_delinquent_loan(self):
        """Test creating collection case from delinquent loan"""
        # Create and disburse loan
        terms = LoanTerms(
            principal_amount=Money(Decimal('10000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.08'),
            term_months=60,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today() - timedelta(days=45)  # 45 days ago
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        self.loan_manager.disburse_loan(loan.id, self.disbursement_account.id)
        
        # Make loan past due
        loan.days_past_due = 45
        loan.state = LoanState.ACTIVE
        self.loan_manager._save_loan(loan)
        
        # Scan for delinquencies
        results = self.collections_manager.scan_delinquencies()
        
        assert results["cases_created"] == 1
        assert results["cases_updated"] == 0
        
        # Get the created case
        cases = self.collections_manager.get_cases()
        assert len(cases) == 1
        
        case = cases[0]
        assert case.loan_id == loan.id
        assert case.customer_id == self.customer.id
        assert case.status == DelinquencyStatus.LATE  # 45 days = LATE
        assert case.days_past_due == 45
        assert case.amount_overdue.is_positive()
        assert case.total_outstanding == loan.current_balance
    
    def test_update_existing_collection_case(self):
        """Test updating existing collection case when loan status changes"""
        # Create loan and case
        terms = LoanTerms(
            principal_amount=Money(Decimal('5000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.07'),
            term_months=36,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today() - timedelta(days=20)
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        self.loan_manager.disburse_loan(loan.id, self.disbursement_account.id)
        
        # Initial delinquency scan
        loan.days_past_due = 20
        loan.state = LoanState.ACTIVE
        self.loan_manager._save_loan(loan)
        
        results1 = self.collections_manager.scan_delinquencies()
        assert results1["cases_created"] == 1
        
        # Loan gets worse
        loan.days_past_due = 70
        self.loan_manager._save_loan(loan)
        
        results2 = self.collections_manager.scan_delinquencies()
        assert results2["cases_created"] == 0
        assert results2["cases_updated"] == 1
        
        # Verify case was updated
        cases = self.collections_manager.get_cases()
        assert len(cases) == 1
        
        case = cases[0]
        assert case.days_past_due == 70
        assert case.status == DelinquencyStatus.SERIOUS  # 70 days = SERIOUS
    
    def test_get_cases_with_filters(self):
        """Test getting cases with status, priority, and collector filters"""
        # Create multiple cases with different properties
        now = datetime.now(timezone.utc)
        
        case1 = CollectionCase(
            id="CASE001",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id=self.customer.id,
            account_id="ACC001",
            status=DelinquencyStatus.EARLY,
            days_past_due=15,
            amount_overdue=Money(Decimal('200.00'), Currency.USD),
            total_outstanding=Money(Decimal('2000.00'), Currency.USD),
            priority=2,
            assigned_collector="COLLECTOR1"
        )
        
        case2 = CollectionCase(
            id="CASE002", 
            created_at=now,
            updated_at=now,
            loan_id="LOAN002",
            customer_id=self.customer.id,
            account_id="ACC002",
            status=DelinquencyStatus.SERIOUS,
            days_past_due=75,
            amount_overdue=Money(Decimal('800.00'), Currency.USD),
            total_outstanding=Money(Decimal('8000.00'), Currency.USD),
            priority=4,
            assigned_collector="COLLECTOR2"
        )
        
        case3 = CollectionCase(
            id="CASE003",
            created_at=now,
            updated_at=now,
            loan_id="LOAN003",
            customer_id=self.customer.id,
            account_id="ACC003",
            status=DelinquencyStatus.LATE,
            days_past_due=45,
            amount_overdue=Money(Decimal('400.00'), Currency.USD),
            total_outstanding=Money(Decimal('4000.00'), Currency.USD),
            priority=4
            # No assigned collector
        )
        
        self.collections_manager._save_case(case1)
        self.collections_manager._save_case(case2)
        self.collections_manager._save_case(case3)
        
        # Test filtering by status
        early_cases = self.collections_manager.get_cases(status=DelinquencyStatus.EARLY)
        assert len(early_cases) == 1
        assert early_cases[0].id == "CASE001"
        
        serious_cases = self.collections_manager.get_cases(status=DelinquencyStatus.SERIOUS)
        assert len(serious_cases) == 1
        assert serious_cases[0].id == "CASE002"
        
        # Test filtering by priority
        priority_4_cases = self.collections_manager.get_cases(priority=4)
        assert len(priority_4_cases) == 2
        case_ids = {case.id for case in priority_4_cases}
        assert "CASE002" in case_ids
        assert "CASE003" in case_ids
        
        # Test filtering by collector
        collector1_cases = self.collections_manager.get_cases(collector="COLLECTOR1")
        assert len(collector1_cases) == 1
        assert collector1_cases[0].id == "CASE001"
        
        # Test getting all cases (sorted by priority then days past due)
        all_cases = self.collections_manager.get_cases()
        assert len(all_cases) == 3
        # Should be sorted by priority desc, then days past due desc
        assert all_cases[0].priority >= all_cases[1].priority
        assert all_cases[1].priority >= all_cases[2].priority
    
    def test_get_cases_by_customer(self):
        """Test getting all cases for a specific customer"""
        # Create another customer
        other_customer = self.customer_manager.create_customer(
            first_name="Jane",
            last_name="Other", 
            email="jane.other@example.com"
        )
        
        now = datetime.now(timezone.utc)
        
        # Create cases for both customers
        case1 = CollectionCase(
            id="CASE001",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id=self.customer.id,
            account_id="ACC001",
            status=DelinquencyStatus.EARLY,
            days_past_due=15,
            amount_overdue=Money(Decimal('200.00'), Currency.USD),
            total_outstanding=Money(Decimal('2000.00'), Currency.USD)
        )
        
        case2 = CollectionCase(
            id="CASE002",
            created_at=now,
            updated_at=now,
            loan_id="LOAN002",
            customer_id=other_customer.id,
            account_id="ACC002",
            status=DelinquencyStatus.LATE,
            days_past_due=45,
            amount_overdue=Money(Decimal('400.00'), Currency.USD),
            total_outstanding=Money(Decimal('4000.00'), Currency.USD)
        )
        
        case3 = CollectionCase(
            id="CASE003",
            created_at=now,
            updated_at=now,
            loan_id="LOAN003",
            customer_id=self.customer.id,
            account_id="ACC003",
            status=DelinquencyStatus.SERIOUS,
            days_past_due=75,
            amount_overdue=Money(Decimal('800.00'), Currency.USD),
            total_outstanding=Money(Decimal('8000.00'), Currency.USD)
        )
        
        self.collections_manager._save_case(case1)
        self.collections_manager._save_case(case2)
        self.collections_manager._save_case(case3)
        
        # Get cases for first customer
        customer_cases = self.collections_manager.get_cases_by_customer(self.customer.id)
        assert len(customer_cases) == 2
        case_ids = {case.id for case in customer_cases}
        assert "CASE001" in case_ids
        assert "CASE003" in case_ids
        
        # Get cases for other customer
        other_customer_cases = self.collections_manager.get_cases_by_customer(other_customer.id)
        assert len(other_customer_cases) == 1
        assert other_customer_cases[0].id == "CASE002"
    
    def test_assign_collector(self):
        """Test assigning collector to case"""
        now = datetime.now(timezone.utc)
        
        case = CollectionCase(
            id="CASE001",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id=self.customer.id,
            account_id="ACC001",
            status=DelinquencyStatus.EARLY,
            days_past_due=15,
            amount_overdue=Money(Decimal('200.00'), Currency.USD),
            total_outstanding=Money(Decimal('2000.00'), Currency.USD)
        )
        
        self.collections_manager._save_case(case)
        
        # Assign collector
        updated_case = self.collections_manager.assign_collector("CASE001", "COLLECTOR_SMITH")
        
        assert updated_case.assigned_collector == "COLLECTOR_SMITH"
        
        # Verify persistence
        retrieved_case = self.collections_manager.get_case("CASE001")
        assert retrieved_case.assigned_collector == "COLLECTOR_SMITH"
    
    def test_record_collection_action(self):
        """Test recording collection action"""
        now = datetime.now(timezone.utc)
        
        case = CollectionCase(
            id="CASE001",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id=self.customer.id,
            account_id="ACC001",
            status=DelinquencyStatus.EARLY,
            days_past_due=15,
            amount_overdue=Money(Decimal('200.00'), Currency.USD),
            total_outstanding=Money(Decimal('2000.00'), Currency.USD)
        )
        
        self.collections_manager._save_case(case)
        
        # Record action
        follow_up_date = date.today() + timedelta(days=7)
        
        action = self.collections_manager.record_action(
            case_id="CASE001",
            action_type=CollectionAction.REMINDER_CALL,
            performed_by="COLLECTOR_SMITH",
            notes="Spoke with customer, promised payment by next week",
            result=ActionResult.PROMISED,
            next_follow_up=follow_up_date
        )
        
        assert action.case_id == "CASE001"
        assert action.action_type == CollectionAction.REMINDER_CALL
        assert action.performed_by == "COLLECTOR_SMITH"
        assert action.result == ActionResult.PROMISED
        assert action.next_follow_up_date == follow_up_date
        
        # Verify case was updated with next action date
        updated_case = self.collections_manager.get_case("CASE001")
        assert updated_case.next_action_date == follow_up_date
    
    def test_record_payment_promise(self):
        """Test recording payment promise"""
        now = datetime.now(timezone.utc)
        
        case = CollectionCase(
            id="CASE001",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id=self.customer.id,
            account_id="ACC001",
            status=DelinquencyStatus.EARLY,
            days_past_due=15,
            amount_overdue=Money(Decimal('200.00'), Currency.USD),
            total_outstanding=Money(Decimal('2000.00'), Currency.USD)
        )
        
        self.collections_manager._save_case(case)
        
        # Record promise
        promise_date = date.today() + timedelta(days=10)
        promise_amount = Money(Decimal('200.00'), Currency.USD)
        
        promise = self.collections_manager.record_promise(
            case_id="CASE001",
            promised_amount=promise_amount,
            promised_date=promise_date
        )
        
        assert promise.case_id == "CASE001"
        assert promise.promised_amount == promise_amount
        assert promise.promised_date == promise_date
        assert promise.status == PromiseStatus.PENDING
    
    def test_check_broken_promises(self):
        """Test checking for broken payment promises"""
        now = datetime.now(timezone.utc)
        
        case = CollectionCase(
            id="CASE001",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id=self.customer.id,
            account_id="ACC001",
            status=DelinquencyStatus.EARLY,
            days_past_due=15,
            amount_overdue=Money(Decimal('200.00'), Currency.USD),
            total_outstanding=Money(Decimal('2000.00'), Currency.USD)
        )
        
        self.collections_manager._save_case(case)
        
        # Create promises with different dates
        overdue_date = date.today() - timedelta(days=10)  # 10 days ago
        future_date = date.today() + timedelta(days=5)   # 5 days from now
        
        # Record overdue promise
        overdue_promise = PaymentPromise(
            id="PROMISE001",
            created_at=now,
            updated_at=now,
            case_id="CASE001",
            promised_amount=Money(Decimal('100.00'), Currency.USD),
            promised_date=overdue_date,
            status=PromiseStatus.PENDING
        )
        
        # Record future promise
        future_promise = PaymentPromise(
            id="PROMISE002",
            created_at=now,
            updated_at=now,
            case_id="CASE001",
            promised_amount=Money(Decimal('100.00'), Currency.USD),
            promised_date=future_date,
            status=PromiseStatus.PENDING
        )
        
        # Save promises manually
        overdue_dict = self.collections_manager._promise_to_dict(overdue_promise)
        future_dict = self.collections_manager._promise_to_dict(future_promise)
        
        self.storage.save(self.collections_manager.promises_table, overdue_promise.id, overdue_dict)
        self.storage.save(self.collections_manager.promises_table, future_promise.id, future_dict)
        
        # Check promises
        results = self.collections_manager.check_promises()
        
        assert results["promises_checked"] == 2
        assert results["promises_broken"] == 1  # Only overdue promise should be broken
        
        # Verify overdue promise was marked as broken
        overdue_dict_updated = self.storage.load(self.collections_manager.promises_table, overdue_promise.id)
        assert overdue_dict_updated["status"] == PromiseStatus.BROKEN.value
        
        # Verify future promise is still pending
        future_dict_updated = self.storage.load(self.collections_manager.promises_table, future_promise.id)
        assert future_dict_updated["status"] == PromiseStatus.PENDING.value
    
    def test_collection_summary_statistics(self):
        """Test collection summary portfolio statistics"""
        now = datetime.now(timezone.utc)
        
        # Create cases in different statuses
        cases = [
            CollectionCase(
                id="CASE001",
                created_at=now,
                updated_at=now,
                loan_id="LOAN001",
                customer_id=self.customer.id,
                account_id="ACC001",
                status=DelinquencyStatus.EARLY,
                days_past_due=15,
                amount_overdue=Money(Decimal('200.00'), Currency.USD),
                total_outstanding=Money(Decimal('2000.00'), Currency.USD),
                priority=2,
                assigned_collector="COLLECTOR1"
            ),
            CollectionCase(
                id="CASE002",
                created_at=now,
                updated_at=now,
                loan_id="LOAN002",
                customer_id=self.customer.id,
                account_id="ACC002",
                status=DelinquencyStatus.SERIOUS,
                days_past_due=75,
                amount_overdue=Money(Decimal('800.00'), Currency.USD),
                total_outstanding=Money(Decimal('8000.00'), Currency.USD),
                priority=5
                # No assigned collector
            ),
            CollectionCase(
                id="CASE003",
                created_at=now,
                updated_at=now,
                loan_id="LOAN003",
                customer_id=self.customer.id,
                account_id="ACC003",
                status=DelinquencyStatus.LATE,
                days_past_due=45,
                amount_overdue=Money(Decimal('400.00'), Currency.USD),
                total_outstanding=Money(Decimal('4000.00'), Currency.USD),
                priority=3,
                assigned_collector="COLLECTOR2"
            ),
            # Resolved case (should not be included)
            CollectionCase(
                id="CASE004",
                created_at=now,
                updated_at=now,
                loan_id="LOAN004",
                customer_id=self.customer.id,
                account_id="ACC004",
                status=DelinquencyStatus.CURRENT,
                days_past_due=0,
                amount_overdue=Money(Decimal('0.00'), Currency.USD),
                total_outstanding=Money(Decimal('1000.00'), Currency.USD),
                priority=1,
                resolved_at=now,
                resolution=CaseResolution.PAID
            )
        ]
        
        for case in cases:
            self.collections_manager._save_case(case)
        
        # Get summary
        summary = self.collections_manager.get_collection_summary()
        
        assert summary["total_cases"] == 3  # Excludes resolved case
        assert summary["total_overdue_amount"] == Decimal('1400.00')  # 200 + 800 + 400
        assert summary["assigned_cases"] == 2  # CASE001 and CASE003
        assert summary["unassigned_cases"] == 1  # CASE002
        
        # Check cases by status
        assert summary["cases_by_status"]["early"] == 1
        assert summary["cases_by_status"]["late"] == 1  
        assert summary["cases_by_status"]["serious"] == 1
        assert summary["cases_by_status"]["current"] == 0
        assert summary["cases_by_status"]["default"] == 0
        
        # Check cases by priority
        assert summary["cases_by_priority"][2] == 1
        assert summary["cases_by_priority"][3] == 1
        assert summary["cases_by_priority"][5] == 1
        assert summary["cases_by_priority"][1] == 0
        assert summary["cases_by_priority"][4] == 0
    
    def test_collection_strategy_configuration(self):
        """Test setting and getting collection strategies"""
        # Test default strategy
        default_strategy = self.collections_manager.get_strategy()
        assert default_strategy.product_id is None
        assert len(default_strategy.escalation_rules) == 6
        assert default_strategy.auto_write_off_days == 365
        
        # Create custom strategy
        custom_rules = [
            (3, CollectionAction.REMINDER_SMS, True),
            (10, CollectionAction.REMINDER_CALL, False),
            (30, CollectionAction.LEGAL_NOTICE, True)
        ]
        
        custom_strategy = CollectionStrategy(
            id="aggressive",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            product_id="PRODUCT001",
            escalation_rules=custom_rules,
            auto_write_off_days=120,
            promise_tolerance_days=1
        )
        
        # Set custom strategy
        self.collections_manager.set_strategy(custom_strategy)
        
        # Retrieve custom strategy
        retrieved_strategy = self.collections_manager.get_strategy("PRODUCT001")
        assert retrieved_strategy.product_id == "PRODUCT001"
        assert len(retrieved_strategy.escalation_rules) == 3
        assert retrieved_strategy.auto_write_off_days == 120
        assert retrieved_strategy.promise_tolerance_days == 1
    
    def test_auto_action_execution(self):
        """Test automatic collection action execution based on days past due"""
        now = datetime.now(timezone.utc)
        
        # Create case eligible for auto actions
        case = CollectionCase(
            id="CASE001",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id=self.customer.id,
            account_id="ACC001",
            status=DelinquencyStatus.LATE,
            days_past_due=35,  # Should trigger multiple auto actions
            amount_overdue=Money(Decimal('500.00'), Currency.USD),
            total_outstanding=Money(Decimal('5000.00'), Currency.USD),
            priority=3
        )
        
        self.collections_manager._save_case(case)
        
        # Run auto actions
        results = self.collections_manager.run_auto_actions()
        
        assert results["cases_processed"] == 1
        assert results["actions_executed"] > 0  # Should execute several actions
        
        # Verify actions were recorded
        actions_data = self.storage.find(
            self.collections_manager.actions_table,
            {"case_id": "CASE001"}
        )
        
        assert len(actions_data) > 0
        
        # Check that auto actions have correct performer
        for action_data in actions_data:
            action = self.collections_manager._action_from_dict(action_data)
            assert action.performed_by == "SYSTEM"
            assert "Automatic action" in action.notes
    
    def test_case_resolution(self):
        """Test resolving collection cases"""
        now = datetime.now(timezone.utc)
        
        case = CollectionCase(
            id="CASE001",
            created_at=now,
            updated_at=now,
            loan_id="LOAN001",
            customer_id=self.customer.id,
            account_id="ACC001",
            status=DelinquencyStatus.SERIOUS,
            days_past_due=75,
            amount_overdue=Money(Decimal('800.00'), Currency.USD),
            total_outstanding=Money(Decimal('8000.00'), Currency.USD),
            priority=4
        )
        
        self.collections_manager._save_case(case)
        
        # Resolve case as paid
        resolved_case = self.collections_manager.resolve_case("CASE001", CaseResolution.PAID)
        
        assert resolved_case.is_resolved
        assert resolved_case.resolution == CaseResolution.PAID
        assert resolved_case.status == DelinquencyStatus.CURRENT
        assert resolved_case.resolved_at is not None
        
        # Verify persistence
        retrieved_case = self.collections_manager.get_case("CASE001")
        assert retrieved_case.is_resolved
        assert retrieved_case.resolution == CaseResolution.PAID
    
    def test_recovery_rate_calculation(self):
        """Test recovery rate calculation for resolved cases"""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        
        # Create resolved cases with different resolutions
        cases = [
            # Paid case
            CollectionCase(
                id="CASE001",
                created_at=yesterday,
                updated_at=now,
                loan_id="LOAN001",
                customer_id=self.customer.id,
                account_id="ACC001",
                status=DelinquencyStatus.CURRENT,
                days_past_due=0,
                amount_overdue=Money(Decimal('500.00'), Currency.USD),
                total_outstanding=Money(Decimal('5000.00'), Currency.USD),
                priority=3,
                resolved_at=now,
                resolution=CaseResolution.PAID
            ),
            # Restructured case
            CollectionCase(
                id="CASE002",
                created_at=yesterday,
                updated_at=now,
                loan_id="LOAN002",
                customer_id=self.customer.id,
                account_id="ACC002",
                status=DelinquencyStatus.CURRENT,
                days_past_due=0,
                amount_overdue=Money(Decimal('1000.00'), Currency.USD),
                total_outstanding=Money(Decimal('10000.00'), Currency.USD),
                priority=4,
                resolved_at=now,
                resolution=CaseResolution.RESTRUCTURED
            ),
            # Written-off case
            CollectionCase(
                id="CASE003",
                created_at=yesterday,
                updated_at=now,
                loan_id="LOAN003",
                customer_id=self.customer.id,
                account_id="ACC003",
                status=DelinquencyStatus.WRITTEN_OFF,
                days_past_due=0,
                amount_overdue=Money(Decimal('300.00'), Currency.USD),
                total_outstanding=Money(Decimal('3000.00'), Currency.USD),
                priority=2,
                resolved_at=now,
                resolution=CaseResolution.WRITTEN_OFF
            )
        ]
        
        for case in cases:
            self.collections_manager._save_case(case)
        
        # Calculate recovery rate
        recovery_stats = self.collections_manager.get_recovery_rate()
        
        assert recovery_stats["total_cases"] == 3
        assert recovery_stats["total_overdue_amount"] == Decimal('1800.00')  # 500 + 1000 + 300
        
        # Expected recovery: 500 (paid) + 500 (50% of restructured) = 1000
        assert recovery_stats["total_recovered_amount"] == Decimal('1000.00')
        
        # Recovery rate should be 1000/1800 = 0.5556...
        expected_rate = Decimal('1000.00') / Decimal('1800.00')
        assert abs(recovery_stats["recovery_rate"] - expected_rate) < Decimal('0.001')
        
        assert recovery_stats["cases_paid"] == 1
        assert recovery_stats["cases_restructured"] == 1
        assert recovery_stats["cases_written_off"] == 1
    
    def test_multiple_cases_per_customer(self):
        """Test handling multiple collection cases for same customer"""
        # Create customer with multiple loans
        terms = LoanTerms(
            principal_amount=Money(Decimal('5000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.08'),
            term_months=36,
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today() - timedelta(days=30)
        )
        
        # Create multiple loans
        loan1 = self.loan_manager.originate_loan(
            customer_id=self.customer.id,
            terms=terms,
            currency=Currency.USD
        )
        
        loan2 = self.loan_manager.originate_loan(
            customer_id=self.customer.id, 
            terms=terms,
            currency=Currency.USD
        )
        
        # Disburse loans
        self.loan_manager.disburse_loan(loan1.id, self.disbursement_account.id)
        self.loan_manager.disburse_loan(loan2.id, self.disbursement_account.id)
        
        # Make both loans delinquent
        loan1.days_past_due = 25
        loan1.state = LoanState.ACTIVE
        self.loan_manager._save_loan(loan1)
        
        loan2.days_past_due = 55
        loan2.state = LoanState.ACTIVE
        self.loan_manager._save_loan(loan2)
        
        # Scan for delinquencies
        results = self.collections_manager.scan_delinquencies()
        
        assert results["cases_created"] == 2
        
        # Get cases for customer
        customer_cases = self.collections_manager.get_cases_by_customer(self.customer.id)
        assert len(customer_cases) == 2
        
        # Verify different statuses
        statuses = {case.status for case in customer_cases}
        assert DelinquencyStatus.EARLY in statuses  # 25 days
        assert DelinquencyStatus.LATE in statuses   # 55 days


if __name__ == "__main__":
    pytest.main([__file__])