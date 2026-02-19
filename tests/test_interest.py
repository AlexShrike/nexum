"""
Test suite for interest module

Tests daily interest accrual, compound interest calculations, grace periods,
and proper interest posting. All calculations must be mathematically precise.
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, date, timedelta

from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.ledger import GeneralLedger, JournalEntryLine, AccountType
from core_banking.accounts import AccountManager, ProductType
from core_banking.customers import CustomerManager, KYCStatus, KYCTier
from core_banking.compliance import ComplianceEngine
from core_banking.transactions import TransactionProcessor, TransactionChannel
from core_banking.interest import (
    InterestEngine, InterestRateConfig, InterestAccrual, GracePeriodTracker,
    InterestType, CompoundingFrequency, InterestCalculationMethod
)


class TestInterestRateConfig:
    """Test interest rate configuration"""
    
    def test_valid_config(self):
        """Test creating valid interest rate configuration"""
        now = datetime.now(timezone.utc)
        
        config = InterestRateConfig(
            id="RATE001",
            created_at=now,
            updated_at=now,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            annual_rate=Decimal('0.025'),  # 2.5% APY
            interest_type=InterestType.COMPOUND,
            compounding_frequency=CompoundingFrequency.DAILY,
            calculation_method=InterestCalculationMethod.ACTUAL_365,
            minimum_balance=Money(Decimal('100.00'), Currency.USD)
        )
        
        assert config.product_type == ProductType.SAVINGS
        assert config.annual_rate == Decimal('0.025')
        assert config.interest_type == InterestType.COMPOUND
        assert config.compounding_frequency == CompoundingFrequency.DAILY
        assert config.minimum_balance == Money(Decimal('100.00'), Currency.USD)
    
    def test_invalid_rate(self):
        """Test that invalid interest rates are rejected"""
        now = datetime.now(timezone.utc)
        
        # Negative rate
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            InterestRateConfig(
                id="RATE002",
                created_at=now,
                updated_at=now,
                product_type=ProductType.SAVINGS,
                currency=Currency.USD,
                annual_rate=Decimal('-0.01')  # Negative rate
            )
        
        # Rate over 100%
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            InterestRateConfig(
                id="RATE003",
                created_at=now,
                updated_at=now,
                product_type=ProductType.SAVINGS,
                currency=Currency.USD,
                annual_rate=Decimal('1.5')  # 150% rate
            )
    
    def test_currency_consistency(self):
        """Test currency consistency in config"""
        now = datetime.now(timezone.utc)
        
        with pytest.raises(ValueError, match="currency must match"):
            InterestRateConfig(
                id="RATE004",
                created_at=now,
                updated_at=now,
                product_type=ProductType.SAVINGS,
                currency=Currency.USD,
                annual_rate=Decimal('0.02'),
                minimum_balance=Money(Decimal('100.00'), Currency.EUR)  # Wrong currency
            )


class TestInterestAccrual:
    """Test interest accrual calculations"""
    
    def test_valid_accrual(self):
        """Test creating valid interest accrual"""
        now = datetime.now(timezone.utc)
        today = date.today()
        
        accrual = InterestAccrual(
            id="ACCR001",
            created_at=now,
            updated_at=now,
            account_id="ACC001",
            accrual_date=today,
            principal_balance=Money(Decimal('1000.00'), Currency.USD),
            daily_rate=Decimal('0.000068493'),  # ~2.5% / 365 days
            accrued_amount=Money(Decimal('0.07'), Currency.USD),
            cumulative_accrued=Money(Decimal('0.07'), Currency.USD),
            calculation_method=InterestCalculationMethod.ACTUAL_365,
            rate_config_id="RATE001"
        )
        
        assert accrual.account_id == "ACC001"
        assert accrual.accrual_date == today
        assert accrual.principal_balance == Money(Decimal('1000.00'), Currency.USD)
        assert accrual.accrued_amount == Money(Decimal('0.07'), Currency.USD)
        assert not accrual.posted
    
    def test_currency_consistency(self):
        """Test that all amounts use same currency"""
        now = datetime.now(timezone.utc)
        
        with pytest.raises(ValueError, match="must use the same currency"):
            InterestAccrual(
                id="ACCR002",
                created_at=now,
                updated_at=now,
                account_id="ACC001",
                accrual_date=date.today(),
                principal_balance=Money(Decimal('1000.00'), Currency.USD),
                daily_rate=Decimal('0.0001'),
                accrued_amount=Money(Decimal('0.10'), Currency.EUR),  # Wrong currency
                cumulative_accrued=Money(Decimal('0.10'), Currency.USD),
                calculation_method=InterestCalculationMethod.ACTUAL_365,
                rate_config_id="RATE001"
            )


class TestGracePeriodTracker:
    """Test grace period tracking for credit products"""
    
    def test_valid_grace_period(self):
        """Test creating valid grace period tracker"""
        now = datetime.now(timezone.utc)
        today = date.today()
        
        tracker = GracePeriodTracker(
            id="GRACE001",
            created_at=now,
            updated_at=now,
            account_id="CREDIT001",
            statement_date=today,
            statement_balance=Money(Decimal('500.00'), Currency.USD),
            due_date=today + timedelta(days=25)
        )
        
        assert tracker.account_id == "CREDIT001"
        assert tracker.statement_balance == Money(Decimal('500.00'), Currency.USD)
        assert tracker.grace_period_active
        assert not tracker.full_payment_received
        assert tracker.is_grace_period_valid
        assert tracker.days_until_due == 25
    
    def test_grace_period_expiration(self):
        """Test grace period expiration"""
        now = datetime.now(timezone.utc)
        past_date = date.today() - timedelta(days=5)
        
        tracker = GracePeriodTracker(
            id="GRACE002",
            created_at=now,
            updated_at=now,
            account_id="CREDIT001",
            statement_date=past_date,
            statement_balance=Money(Decimal('300.00'), Currency.USD),
            due_date=past_date,  # Already expired
            grace_period_lost_date=past_date
        )
        
        assert not tracker.is_grace_period_valid
        assert tracker.days_until_due < 0


class TestInterestEngine:
    """Test interest engine functionality"""
    
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
        self.interest_engine = InterestEngine(
            self.storage, self.ledger, self.account_manager,
            self.transaction_processor, self.audit_trail
        )
        
        # Create test customer and accounts
        self.customer = self.customer_manager.create_customer(
            first_name="Alice",
            last_name="Johnson",
            email="alice@example.com"
        )
        
        # Upgrade customer to avoid compliance limits
        self.customer_manager.update_kyc_status(
            self.customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
        )
        
        self.savings_account = self.account_manager.create_account(
            customer_id=self.customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Interest Test Savings",
            interest_rate=Decimal('0.02'),  # 2% APY
            minimum_balance=Money(Decimal('100.00'), Currency.USD)  # $100 minimum
        )
        
        self.credit_account = self.account_manager.create_account(
            customer_id=self.customer.id,
            product_type=ProductType.CREDIT_LINE,
            currency=Currency.USD,
            name="Interest Test Credit Line",
            credit_limit=Money(Decimal('2000.00'), Currency.USD),
            interest_rate=Decimal('0.18')  # 18% APR
        )
    
    def test_daily_interest_calculation_method_actual_365(self):
        """Test daily rate calculation using ACTUAL/365 method"""
        annual_rate = Decimal('0.02')  # 2% APY
        calculation_date = date(2024, 6, 15)  # Mid-year date
        
        daily_rate = self.interest_engine._calculate_daily_rate(
            annual_rate, InterestCalculationMethod.ACTUAL_365, calculation_date
        )
        
        expected_rate = annual_rate / Decimal('365')
        assert abs(daily_rate - expected_rate) < Decimal('0.0000001')
    
    def test_daily_interest_calculation_method_actual_360(self):
        """Test daily rate calculation using ACTUAL/360 method"""
        annual_rate = Decimal('0.075')  # 7.5% APR
        calculation_date = date(2024, 3, 20)
        
        daily_rate = self.interest_engine._calculate_daily_rate(
            annual_rate, InterestCalculationMethod.ACTUAL_360, calculation_date
        )
        
        expected_rate = annual_rate / Decimal('360')
        assert abs(daily_rate - expected_rate) < Decimal('0.0000001')
    
    def test_daily_accrual_savings_account(self):
        """Test daily interest accrual for savings account"""
        # Give savings account a balance
        deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('1000.00'), Currency.USD),
            description="Initial deposit",
            channel=TransactionChannel.ONLINE
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        # Run daily accrual
        accrual_date = date.today()
        results = self.interest_engine.run_daily_accrual(accrual_date)
        
        # Should have processed 1 savings account
        assert results[ProductType.SAVINGS.value] == 1
        
        # Check that accrual was created
        accruals = self.interest_engine._get_unposted_accruals(self.savings_account.id)
        assert len(accruals) == 1
        
        accrual = accruals[0]
        assert accrual.account_id == self.savings_account.id
        assert accrual.principal_balance == Money(Decimal('1000.00'), Currency.USD)
        assert accrual.accrued_amount.is_positive()
        assert not accrual.posted
        
        # Verify mathematical accuracy
        # Daily rate for 2% APY ≈ 0.000054794 (compound daily)
        # Interest ≈ $1000 * 0.000054794 ≈ $0.055
        expected_daily_interest = Money(Decimal('0.05'), Currency.USD)  # Approximately
        assert abs(accrual.accrued_amount.amount - expected_daily_interest.amount) < Decimal('0.01')
    
    def test_daily_accrual_credit_line_with_balance(self):
        """Test daily interest accrual for credit line with outstanding balance"""
        # Create outstanding balance on credit line (customer owes money)
        # This is represented as a credit balance in the liability account
        purchase = JournalEntryLine(
            account_id="MERCHANT001",
            description="Purchase",
            debit_amount=Money(Decimal('500.00'), Currency.USD),
            credit_amount=Money(Decimal('0.00'), Currency.USD)
        )
        credit_line = JournalEntryLine(
            account_id=self.credit_account.id,
            description="Credit line charge",
            debit_amount=Money(Decimal('0.00'), Currency.USD),
            credit_amount=Money(Decimal('500.00'), Currency.USD)
        )
        
        entry = self.ledger.create_journal_entry("PURCH001", "Credit purchase", [purchase, credit_line])
        self.ledger.post_journal_entry(entry.id)
        
        # Run daily accrual
        results = self.interest_engine.run_daily_accrual()
        
        # Should have processed 1 credit line account
        assert results[ProductType.CREDIT_LINE.value] == 1
        
        # Check accrual
        accruals = self.interest_engine._get_unposted_accruals(self.credit_account.id)
        assert len(accruals) == 1
        
        accrual = accruals[0]
        assert accrual.principal_balance == Money(Decimal('500.00'), Currency.USD)
        assert accrual.accrued_amount.is_positive()
        
        # Verify daily interest calculation for 18% APR
        # Daily rate ≈ 0.18 / 365 ≈ 0.000493
        # Interest ≈ $500 * 0.000493 ≈ $0.25
        expected_daily_interest = Decimal('0.25')
        assert abs(accrual.accrued_amount.amount - expected_daily_interest) <= Decimal('0.02')  # Allow for rounding differences
    
    def test_no_accrual_below_minimum_balance(self):
        """Test that no interest accrues below minimum balance"""
        # Give savings account balance below minimum
        deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('50.00'), Currency.USD),  # Below typical $100 minimum
            description="Small deposit",
            channel=TransactionChannel.ONLINE
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        # Run daily accrual
        results = self.interest_engine.run_daily_accrual()
        
        # Should not process any accounts if below minimum
        assert results[ProductType.SAVINGS.value] == 0
        
        # No accruals should be created
        accruals = self.interest_engine._get_unposted_accruals(self.savings_account.id)
        assert len(accruals) == 0
    
    def test_monthly_interest_posting(self):
        """Test monthly interest posting process"""
        # Setup: Create interest accruals
        deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('2000.00'), Currency.USD),
            description="Large deposit",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        # Run daily accrual for several days
        for i in range(5):
            accrual_date = date.today() - timedelta(days=i)
            self.interest_engine.run_daily_accrual(accrual_date)
        
        # Post monthly interest
        current_month = date.today().month
        current_year = date.today().year
        results = self.interest_engine.post_monthly_interest(current_month, current_year)
        
        # Should have posted interest for savings account
        assert len(results[ProductType.SAVINGS.value]) == 1
        
        # Check that transaction was created
        transaction_id = results[ProductType.SAVINGS.value][0]
        assert transaction_id is not None
        
        # Verify transaction was processed
        from core_banking.transactions import TransactionState
        posted_txn = self.transaction_processor.get_transaction(transaction_id)
        assert posted_txn.state == TransactionState.COMPLETED
        
        # Check account balance increased
        final_balance = self.account_manager.get_book_balance(self.savings_account.id)
        assert final_balance > Money(Decimal('2000.00'), Currency.USD)  # Should be more due to interest
        
        # Verify accruals are marked as posted
        accruals = self.storage.find(self.interest_engine.accruals_table, {
            "account_id": self.savings_account.id,
            "posted": True
        })
        assert len(accruals) == 5  # All 5 days should be posted
    
    def test_grace_period_prevents_interest(self):
        """Test that grace period prevents interest accrual on credit lines"""
        # Create outstanding balance
        purchase = JournalEntryLine(
            account_id="MERCHANT001",
            description="Purchase",
            debit_amount=Money(Decimal('300.00'), Currency.USD),
            credit_amount=Money(Decimal('0.00'), Currency.USD)
        )
        credit_line = JournalEntryLine(
            account_id=self.credit_account.id,
            description="Credit line charge",
            debit_amount=Money(Decimal('0.00'), Currency.USD),
            credit_amount=Money(Decimal('300.00'), Currency.USD)
        )
        
        entry = self.ledger.create_journal_entry("GRACE_TEST", "Grace period test", [purchase, credit_line])
        self.ledger.post_journal_entry(entry.id)
        
        # Create active grace period
        statement_date = date.today() - timedelta(days=10)
        due_date = date.today() + timedelta(days=15)
        
        grace_tracker = self.interest_engine.create_grace_period(
            account_id=self.credit_account.id,
            statement_date=statement_date,
            statement_balance=Money(Decimal('300.00'), Currency.USD),
            due_date=due_date
        )
        
        # Run daily accrual
        results = self.interest_engine.run_daily_accrual()
        
        # Should not accrue interest due to active grace period
        assert results[ProductType.CREDIT_LINE.value] == 0
        
        accruals = self.interest_engine._get_unposted_accruals(self.credit_account.id)
        assert len(accruals) == 0
    
    def test_grace_period_update_on_payment(self):
        """Test grace period status update when payment is made"""
        # Create grace period tracker
        statement_date = date.today() - timedelta(days=5)
        due_date = date.today() + timedelta(days=20)
        statement_balance = Money(Decimal('400.00'), Currency.USD)
        
        tracker = self.interest_engine.create_grace_period(
            account_id=self.credit_account.id,
            statement_date=statement_date,
            statement_balance=statement_balance,
            due_date=due_date
        )
        
        assert tracker.grace_period_active
        assert not tracker.full_payment_received
        
        # Make full payment
        self.interest_engine.update_grace_period_status(
            account_id=self.credit_account.id,
            payment_amount=statement_balance,  # Full payment
            payment_date=date.today()
        )
        
        # Grace period should remain active and full payment should be marked
        updated_tracker = self.interest_engine._get_current_grace_period(self.credit_account.id)
        assert updated_tracker.grace_period_active
        assert updated_tracker.full_payment_received
        
        # Make partial payment after due date - should lose grace period
        late_date = due_date + timedelta(days=5)
        partial_payment = Money(Decimal('100.00'), Currency.USD)
        
        self.interest_engine.update_grace_period_status(
            account_id=self.credit_account.id,
            payment_amount=partial_payment,
            payment_date=late_date
        )
        
        updated_tracker = self.interest_engine._get_current_grace_period(self.credit_account.id)
        assert not updated_tracker.grace_period_active
        assert updated_tracker.grace_period_lost_date == late_date
    
    def test_compound_interest_accuracy(self):
        """Test compound interest calculation accuracy"""
        # Test with known values to verify mathematical precision
        principal = Money(Decimal('10000.00'), Currency.USD)
        annual_rate = Decimal('0.05')  # 5% APY
        
        # Deposit principal
        deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=principal,
            description="Principal deposit",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        # Run daily accrual for 365 days (1 year)
        start_date = date(2024, 1, 1)
        for day_num in range(365):
            accrual_date = start_date + timedelta(days=day_num)
            self.interest_engine.run_daily_accrual(accrual_date)
        
        # Post interest monthly throughout the year
        for month in range(1, 13):
            self.interest_engine.post_monthly_interest(month, 2024)
        
        # Final balance should be approximately $10,500 (with compounding)
        final_balance = self.account_manager.get_book_balance(self.savings_account.id)
        
        # With daily compounding, 5% APY should yield approximately $512.67 interest
        expected_balance = Money(Decimal('10512.67'), Currency.USD)
        
        # Allow small tolerance for rounding differences (monthly posting rounds each month)
        tolerance = Money(Decimal('2.00'), Currency.USD)
        assert abs(final_balance.amount - expected_balance.amount) <= tolerance.amount
    
    def test_interest_calculation_methods(self):
        """Test different interest calculation methods"""
        annual_rate = Decimal('0.06')  # 6% rate
        test_date = date(2024, 7, 15)
        
        # Test ACTUAL/365
        daily_rate_365 = self.interest_engine._calculate_daily_rate(
            annual_rate, InterestCalculationMethod.ACTUAL_365, test_date
        )
        expected_365 = annual_rate / Decimal('365')
        assert abs(daily_rate_365 - expected_365) < Decimal('0.0000001')
        
        # Test ACTUAL/360
        daily_rate_360 = self.interest_engine._calculate_daily_rate(
            annual_rate, InterestCalculationMethod.ACTUAL_360, test_date
        )
        expected_360 = annual_rate / Decimal('360')
        assert abs(daily_rate_360 - expected_360) < Decimal('0.0000001')
        
        # 360-day method should yield slightly higher daily rate
        assert daily_rate_360 > daily_rate_365
    
    def test_no_interest_on_zero_balance(self):
        """Test that no interest accrues on zero balance accounts"""
        # Account starts with zero balance
        balance = self.account_manager.get_book_balance(self.savings_account.id)
        assert balance.is_zero()
        
        # Run daily accrual
        results = self.interest_engine.run_daily_accrual()
        
        # Should not process account with zero balance
        assert results[ProductType.SAVINGS.value] == 0
        
        accruals = self.interest_engine._get_unposted_accruals(self.savings_account.id)
        assert len(accruals) == 0
    
    def test_interest_posting_minimum_threshold(self):
        """Test that very small interest amounts are not posted"""
        # Create tiny balance that would generate negligible interest
        tiny_deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('0.50'), Currency.USD),  # 50 cents
            description="Tiny deposit",
            channel=TransactionChannel.ONLINE
        )
        self.transaction_processor.process_transaction(tiny_deposit.id)
        
        # Run accrual for one day
        self.interest_engine.run_daily_accrual()
        
        # Try to post interest
        results = self.interest_engine.post_monthly_interest()
        
        # Should not post interest if amount is negligible (< 1 cent)
        assert len(results[ProductType.SAVINGS.value]) == 0


if __name__ == "__main__":
    pytest.main([__file__])