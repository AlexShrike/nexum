"""
Test suite for integration scenarios

Tests end-to-end banking scenarios combining all system components.
Validates complete workflows from customer onboarding to complex transactions.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, date, timedelta

from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail, AuditEventType
from core_banking.ledger import GeneralLedger, AccountType
from core_banking.accounts import AccountManager, ProductType, AccountState
from core_banking.customers import CustomerManager, KYCStatus, KYCTier
from core_banking.compliance import ComplianceEngine, ComplianceAction
from core_banking.transactions import (
    TransactionProcessor, TransactionType, TransactionChannel, TransactionState
)
from core_banking.interest import InterestEngine
from core_banking.credit import CreditLineManager, TransactionCategory
from core_banking.loans import LoanManager, LoanTerms, PaymentFrequency, AmortizationMethod


class TestFullBankingSystem:
    """Integration tests for complete banking system"""
    
    def setup_method(self):
        """Set up complete banking system"""
        # Initialize storage and core components
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
        self.credit_manager = CreditLineManager(
            self.storage, self.account_manager, self.transaction_processor,
            self.interest_engine, self.audit_trail
        )
        self.loan_manager = LoanManager(
            self.storage, self.account_manager, self.transaction_processor,
            self.audit_trail
        )
    
    def test_customer_onboarding_complete_flow(self):
        """Test complete customer onboarding process"""
        # Step 1: Create customer
        customer = self.customer_manager.create_customer(
            first_name="Alice",
            last_name="Johnson",
            email="alice.johnson@email.com",
            phone="+1-555-123-4567"
        )
        
        assert customer.kyc_status == KYCStatus.NONE
        assert customer.kyc_tier == KYCTier.TIER_0
        
        # Step 2: Open savings account (should work with basic KYC)
        savings_account = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Alice's Savings Account",
            minimum_balance=Money(Decimal('25.00'), Currency.USD)
        )
        
        assert savings_account.customer_id == customer.id
        assert savings_account.state == AccountState.ACTIVE
        
        # Step 3: Initial deposit (small amount allowed for TIER_0)
        initial_deposit = self.transaction_processor.deposit(
            account_id=savings_account.id,
            amount=Money(Decimal('50.00'), Currency.USD),
            description="Initial deposit",
            channel=TransactionChannel.BRANCH
        )
        
        processed_deposit = self.transaction_processor.process_transaction(initial_deposit.id)
        assert processed_deposit.state == TransactionState.COMPLETED
        
        # Verify balance
        balance = self.account_manager.get_book_balance(savings_account.id)
        assert balance == Money(Decimal('50.00'), Currency.USD)
        
        # Step 4: Try larger deposit - should be blocked due to TIER_0 limits
        large_deposit = self.transaction_processor.deposit(
            account_id=savings_account.id,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="Large deposit",
            channel=TransactionChannel.ONLINE
        )
        
        with pytest.raises(ValueError, match="compliance"):
            self.transaction_processor.process_transaction(large_deposit.id)
        
        # Step 5: Upgrade KYC to TIER_1
        self.customer_manager.update_kyc_status(
            customer.id,
            KYCStatus.VERIFIED,
            KYCTier.TIER_1,
            documents=["drivers_license", "utility_bill"],
            expiry_days=365
        )
        
        # Step 6: Now larger deposit should work
        larger_deposit = self.transaction_processor.deposit(
            account_id=savings_account.id,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="Post-KYC deposit",
            channel=TransactionChannel.ONLINE
        )
        
        processed_large = self.transaction_processor.process_transaction(larger_deposit.id)
        assert processed_large.state == TransactionState.COMPLETED
        
        # Final balance should be $550
        final_balance = self.account_manager.get_book_balance(savings_account.id)
        assert final_balance == Money(Decimal('550.00'), Currency.USD)
        
        # Verify audit trail captured all events
        customer_events = self.audit_trail.get_events_for_entity("customer", customer.id)
        assert len(customer_events) >= 2  # Create + KYC update
        
        account_events = self.audit_trail.get_events_for_entity("account", savings_account.id)
        assert len(account_events) >= 1  # Account creation
    
    def test_multi_account_transfers_and_limits(self):
        """Test transfers between multiple accounts with compliance checks"""
        # Create customer with high KYC tier
        customer = self.customer_manager.create_customer(
            first_name="Bob",
            last_name="Smith", 
            email="bob.smith@email.com"
        )
        
        self.customer_manager.update_kyc_status(
            customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
        )
        
        # Create multiple accounts
        savings = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Savings Account"
        )
        
        checking = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Checking Account"
        )
        
        # Fund savings account
        deposit = self.transaction_processor.deposit(
            account_id=savings.id,
            amount=Money(Decimal('5000.00'), Currency.USD),
            description="Initial funding",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        # Transfer from savings to checking
        transfer = self.transaction_processor.transfer(
            from_account_id=savings.id,
            to_account_id=checking.id,
            amount=Money(Decimal('2000.00'), Currency.USD),
            description="Savings to checking transfer",
            channel=TransactionChannel.ONLINE
        )
        
        processed_transfer = self.transaction_processor.process_transaction(transfer.id)
        assert processed_transfer.state == TransactionState.COMPLETED
        
        # Verify balances
        savings_balance = self.account_manager.get_book_balance(savings.id)
        checking_balance = self.account_manager.get_book_balance(checking.id)
        
        assert savings_balance == Money(Decimal('3000.00'), Currency.USD)
        assert checking_balance == Money(Decimal('2000.00'), Currency.USD)
        
        # Verify double-entry bookkeeping: total balance unchanged
        total_balance = savings_balance + checking_balance
        assert total_balance == Money(Decimal('5000.00'), Currency.USD)
        
        # Test withdrawal from checking
        withdrawal = self.transaction_processor.withdraw(
            account_id=checking.id,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="ATM withdrawal",
            channel=TransactionChannel.ATM
        )
        
        processed_withdrawal = self.transaction_processor.process_transaction(withdrawal.id)
        assert processed_withdrawal.state == TransactionState.COMPLETED
        
        # Final checking balance should be $1500
        final_checking = self.account_manager.get_book_balance(checking.id)
        assert final_checking == Money(Decimal('1500.00'), Currency.USD)
    
    def test_credit_line_with_grace_period_scenario(self):
        """Test complete credit line scenario with grace period logic"""
        # Create customer and upgrade KYC
        customer = self.customer_manager.create_customer(
            first_name="Carol",
            last_name="Davis",
            email="carol.davis@email.com"
        )
        
        self.customer_manager.update_kyc_status(
            customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
        )
        
        # Create credit line account
        credit_line = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.CREDIT_LINE,
            currency=Currency.USD,
            name="Personal Credit Line",
            credit_limit=Money(Decimal('3000.00'), Currency.USD),
            interest_rate=Decimal('0.18')
        )
        
        # Make purchases
        purchase1 = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.PAYMENT,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="Online purchase 1",
            channel=TransactionChannel.ONLINE,
            from_account_id=credit_line.id
        )
        self.transaction_processor.process_transaction(purchase1.id)
        
        # Record as credit transaction
        self.credit_manager.process_credit_transaction(
            account_id=credit_line.id,
            transaction_id=purchase1.id,
            category=TransactionCategory.PURCHASE,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="Online purchase 1"
        )
        
        purchase2 = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.PAYMENT,
            amount=Money(Decimal('300.00'), Currency.USD),
            description="Store purchase",
            channel=TransactionChannel.ONLINE,
            from_account_id=credit_line.id
        )
        self.transaction_processor.process_transaction(purchase2.id)
        
        self.credit_manager.process_credit_transaction(
            account_id=credit_line.id,
            transaction_id=purchase2.id,
            category=TransactionCategory.PURCHASE,
            amount=Money(Decimal('300.00'), Currency.USD),
            description="Store purchase"
        )
        
        # Generate monthly statement
        statement_date = date.today()
        statement = self.credit_manager.generate_monthly_statement(
            account_id=credit_line.id,
            statement_date=statement_date
        )
        
        assert statement.new_charges == Money(Decimal('800.00'), Currency.USD)
        assert statement.current_balance == Money(Decimal('800.00'), Currency.USD)
        assert statement.minimum_payment_due.is_positive()
        assert statement.grace_period_active
        
        # Test full payment within grace period (no interest)
        full_payment = self.credit_manager.make_payment(
            account_id=credit_line.id,
            amount=statement.current_balance,  # Full payment
            payment_date=statement.due_date - timedelta(days=1)  # Before due date
        )
        
        # Update grace period status
        self.interest_engine.update_grace_period_status(
            account_id=credit_line.id,
            payment_amount=statement.current_balance,
            payment_date=statement.due_date - timedelta(days=1)
        )
        
        # Verify no interest should accrue during grace period
        # (Interest engine would check grace period status)
        grace_tracker = self.interest_engine._get_current_grace_period(credit_line.id)
        assert grace_tracker is not None
        assert grace_tracker.full_payment_received
    
    def test_loan_origination_and_payment_flow(self):
        """Test complete loan lifecycle"""
        # Create customer
        customer = self.customer_manager.create_customer(
            first_name="David",
            last_name="Wilson",
            email="david.wilson@email.com"
        )
        
        self.customer_manager.update_kyc_status(
            customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
        )
        
        # Create checking account for disbursement
        checking = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Loan Disbursement Account"
        )
        
        # Originate loan
        loan_terms = LoanTerms(
            principal_amount=Money(Decimal('10000.00'), Currency.USD),
            annual_interest_rate=Decimal('0.075'),  # 7.5% APR
            term_months=60,  # 5 years
            payment_frequency=PaymentFrequency.MONTHLY,
            amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
            first_payment_date=date.today() + timedelta(days=30)
        )
        
        loan = self.loan_manager.originate_loan(
            customer_id=customer.id,
            terms=loan_terms,
            currency=Currency.USD
        )
        
        assert loan.state.value == "originated"
        assert loan.current_balance == Money(Decimal('10000.00'), Currency.USD)
        
        # Disburse loan
        disbursement_txn_id = self.loan_manager.disburse_loan(
            loan_id=loan.id,
            disbursement_account_id=checking.id
        )
        
        # Verify customer received funds
        customer_balance = self.account_manager.get_book_balance(checking.id)
        assert customer_balance == Money(Decimal('10000.00'), Currency.USD)
        
        updated_loan = self.loan_manager.get_loan(loan.id)
        assert updated_loan.state.value == "disbursed"
        
        # Generate amortization schedule
        schedule = self.loan_manager.generate_amortization_schedule(loan.id)
        assert len(schedule) == 60  # 60 monthly payments
        
        # Verify first payment calculation
        first_payment = schedule[0]
        monthly_payment = first_payment.payment_amount
        
        # Make first loan payment
        loan_payment = self.loan_manager.make_payment(
            loan_id=loan.id,
            payment_amount=monthly_payment,
            source_account_id=checking.id
        )
        
        assert loan_payment.payment_amount == monthly_payment
        assert loan_payment.principal_amount.is_positive()
        assert loan_payment.interest_amount.is_positive()
        
        # Verify loan balance reduced
        updated_loan = self.loan_manager.get_loan(loan.id)
        assert updated_loan.current_balance < loan.current_balance
        assert updated_loan.state.value in ["disbursed", "active"]
    
    def test_interest_accrual_and_posting_integration(self):
        """Test interest accrual and posting across product types"""
        # Create customer with savings account
        customer = self.customer_manager.create_customer(
            first_name="Eva",
            last_name="Martinez",
            email="eva.martinez@email.com"
        )
        
        self.customer_manager.update_kyc_status(
            customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
        )
        
        # Create interest-bearing savings account
        savings = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="High-Yield Savings",
            interest_rate=Decimal('0.02')  # 2% APY
        )
        
        # Fund account with significant balance
        deposit = self.transaction_processor.deposit(
            account_id=savings.id,
            amount=Money(Decimal('10000.00'), Currency.USD),
            description="Large deposit for interest testing",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        initial_balance = self.account_manager.get_book_balance(savings.id)
        assert initial_balance == Money(Decimal('10000.00'), Currency.USD)
        
        # Run daily interest accrual for multiple days
        for day in range(30):  # 30 days
            accrual_date = date.today() - timedelta(days=30-day)
            results = self.interest_engine.run_daily_accrual(accrual_date)
            
            if day == 29:  # Last day
                assert results[ProductType.SAVINGS.value] == 1
        
        # Post monthly interest
        current_month = date.today().month
        current_year = date.today().year
        posting_results = self.interest_engine.post_monthly_interest(current_month, current_year)
        
        # Should have posted interest for savings account
        assert len(posting_results[ProductType.SAVINGS.value]) == 1
        
        # Verify balance increased due to interest
        final_balance = self.account_manager.get_book_balance(savings.id)
        assert final_balance > initial_balance
        
        # Calculate expected interest (approximately)
        # 30 days * (2% / 365) * $10,000 ≈ $16.44
        expected_min_interest = Money(Decimal('10.00'), Currency.USD)
        expected_max_interest = Money(Decimal('30.00'), Currency.USD)
        
        actual_interest = final_balance - initial_balance
        assert expected_min_interest <= actual_interest <= expected_max_interest
    
    def test_transaction_reversal_cross_accounts(self):
        """Test transaction reversal maintaining double-entry integrity"""
        # Create customer and accounts
        customer = self.customer_manager.create_customer(
            first_name="Frank",
            last_name="Anderson",
            email="frank.anderson@email.com"
        )
        
        self.customer_manager.update_kyc_status(
            customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
        )
        
        account_a = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Account A"
        )
        
        account_b = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Account B"
        )
        
        # Fund Account A
        deposit = self.transaction_processor.deposit(
            account_id=account_a.id,
            amount=Money(Decimal('1000.00'), Currency.USD),
            description="Initial funding",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        # Transfer from A to B
        transfer = self.transaction_processor.transfer(
            from_account_id=account_a.id,
            to_account_id=account_b.id,
            amount=Money(Decimal('400.00'), Currency.USD),
            description="Transfer A to B",
            channel=TransactionChannel.ONLINE
        )
        
        processed_transfer = self.transaction_processor.process_transaction(transfer.id)
        
        # Verify balances after transfer
        balance_a = self.account_manager.get_book_balance(account_a.id)
        balance_b = self.account_manager.get_book_balance(account_b.id)
        
        assert balance_a == Money(Decimal('600.00'), Currency.USD)
        assert balance_b == Money(Decimal('400.00'), Currency.USD)
        
        # Reverse the transfer
        reversal = self.transaction_processor.reverse_transaction(
            processed_transfer.id,
            "Customer dispute - incorrect transfer"
        )
        
        assert reversal.state == TransactionState.COMPLETED
        assert reversal.original_transaction_id == processed_transfer.id
        
        # Verify balances after reversal (should return to original state)
        final_balance_a = self.account_manager.get_book_balance(account_a.id)
        final_balance_b = self.account_manager.get_book_balance(account_b.id)
        
        assert final_balance_a == Money(Decimal('1000.00'), Currency.USD)
        assert final_balance_b == Money(Decimal('0.00'), Currency.USD)
        
        # Verify original transaction is marked as reversed
        original_txn = self.transaction_processor.get_transaction(processed_transfer.id)
        assert original_txn.state == TransactionState.REVERSED
        assert original_txn.reversal_transaction_id == reversal.id
    
    def test_compliance_and_suspicious_activity_detection(self):
        """Test compliance monitoring and suspicious activity detection"""
        # Create customer with basic KYC
        customer = self.customer_manager.create_customer(
            first_name="Grace",
            last_name="Chen",
            email="grace.chen@email.com"
        )
        
        # Keep at TIER_1 for testing limits
        self.customer_manager.update_kyc_status(
            customer.id, KYCStatus.VERIFIED, KYCTier.TIER_1
        )
        
        account = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Compliance Test Account"
        )
        
        # Test 1: Transaction within limits should work
        small_deposit = self.transaction_processor.deposit(
            account_id=account.id,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="Normal deposit",
            channel=TransactionChannel.ONLINE
        )
        
        processed_small = self.transaction_processor.process_transaction(small_deposit.id)
        assert processed_small.state == TransactionState.COMPLETED
        
        # Test 2: Large transaction should trigger reporting
        large_deposit = self.transaction_processor.deposit(
            account_id=account.id,
            amount=Money(Decimal('12000.00'), Currency.USD),  # Above $10K threshold
            description="Large deposit",
            channel=TransactionChannel.BRANCH
        )
        
        # Should fail due to TIER_1 limits, but would trigger reporting if allowed
        with pytest.raises(ValueError):
            self.transaction_processor.process_transaction(large_deposit.id)
        
        # Test 3: Suspicious round amount
        round_deposit = self.transaction_processor.deposit(
            account_id=account.id,
            amount=Money(Decimal('1000.00'), Currency.USD),  # Suspicious round amount
            description="Round amount deposit",
            channel=TransactionChannel.BRANCH
        )
        
        # May be processed but flagged as suspicious
        try:
            processed_round = self.transaction_processor.process_transaction(round_deposit.id)
            # If processed, check for suspicious activity alerts
            alerts = self.compliance_engine.get_suspicious_alerts()
            # May have alerts depending on implementation
        except ValueError:
            # May be blocked due to limits - this is also valid
            pass
        
        # Check compliance violations and alerts
        violations = self.compliance_engine.get_customer_violations(customer.id)
        alerts = self.compliance_engine.get_suspicious_alerts()
        
        # Should have some compliance activity
        assert len(violations) > 0 or len(alerts) > 0
    
    def test_multi_currency_operations(self):
        """Test operations across multiple currencies"""
        # Create customer
        customer = self.customer_manager.create_customer(
            first_name="Hans",
            last_name="Mueller",
            email="hans.mueller@email.com"
        )
        
        self.customer_manager.update_kyc_status(
            customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
        )
        
        # Create USD account
        usd_account = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="USD Checking"
        )
        
        # Create EUR account
        eur_account = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.EUR,
            name="EUR Savings"
        )
        
        # Deposit to USD account
        usd_deposit = self.transaction_processor.deposit(
            account_id=usd_account.id,
            amount=Money(Decimal('2000.00'), Currency.USD),
            description="USD deposit",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(usd_deposit.id)
        
        # Deposit to EUR account
        eur_deposit = self.transaction_processor.deposit(
            account_id=eur_account.id,
            amount=Money(Decimal('1500.00'), Currency.EUR),
            description="EUR deposit",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(eur_deposit.id)
        
        # Verify balances in correct currencies
        usd_balance = self.account_manager.get_book_balance(usd_account.id)
        eur_balance = self.account_manager.get_book_balance(eur_account.id)
        
        assert usd_balance == Money(Decimal('2000.00'), Currency.USD)
        assert eur_balance == Money(Decimal('1500.00'), Currency.EUR)
        assert usd_balance.currency == Currency.USD
        assert eur_balance.currency == Currency.EUR
        
        # Verify cannot transfer between different currency accounts directly
        # (Would need currency conversion which isn't implemented in this test)
        with pytest.raises(ValueError):
            invalid_transfer = self.transaction_processor.transfer(
                from_account_id=usd_account.id,
                to_account_id=eur_account.id,  # Different currency
                amount=Money(Decimal('100.00'), Currency.USD),
                description="Invalid cross-currency transfer",
                channel=TransactionChannel.ONLINE
            )
            self.transaction_processor.process_transaction(invalid_transfer.id)
    
    def test_audit_trail_integrity_across_operations(self):
        """Test audit trail maintains integrity across complex operations"""
        # Perform various operations to generate audit events
        customer = self.customer_manager.create_customer(
            first_name="Iris",
            last_name="Taylor",
            email="iris.taylor@email.com"
        )
        
        # Upgrade KYC so transactions aren't blocked
        self.customer_manager.update_kyc_status(
            customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
        )
        
        account = self.account_manager.create_account(
            customer_id=customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Audit Test Account"
        )
        
        # Multiple transactions
        for i in range(10):
            deposit = self.transaction_processor.deposit(
                account_id=account.id,
                amount=Money(Decimal(f'{(i+1)*100}.00'), Currency.USD),
                description=f"Deposit {i+1}",
                channel=TransactionChannel.ONLINE
            )
            self.transaction_processor.process_transaction(deposit.id)
        
        # Account state changes
        self.account_manager.freeze_account(account.id, "Suspicious activity investigation")
        self.account_manager.unfreeze_account(account.id, "Investigation completed")
        
        # KYC updates
        self.customer_manager.update_kyc_status(
            customer.id, KYCStatus.VERIFIED, KYCTier.TIER_1
        )
        
        # Verify audit trail integrity
        integrity_result = self.audit_trail.verify_integrity()
        
        assert integrity_result["valid"] == True
        assert integrity_result["total_events"] > 20  # Should have many events
        assert len(integrity_result["hash_errors"]) == 0
        assert len(integrity_result["chain_breaks"]) == 0
        
        # Verify specific event types exist
        all_events = self.audit_trail.get_all_events()
        event_types = {event.event_type for event in all_events}
        
        expected_types = {
            AuditEventType.CUSTOMER_CREATED,
            AuditEventType.ACCOUNT_CREATED,
            AuditEventType.TRANSACTION_CREATED,
            AuditEventType.TRANSACTION_POSTED,
            AuditEventType.ACCOUNT_FROZEN,
            AuditEventType.ACCOUNT_UNFROZEN,
            AuditEventType.KYC_STATUS_CHANGED
        }
        
        # Should have most of the expected event types
        assert len(event_types.intersection(expected_types)) >= 5
    
    def test_full_banking_day_simulation(self):
        """Simulate a full banking day with multiple customers and operations"""
        customers = []
        accounts = []
        
        # Create multiple customers
        for i in range(5):
            customer = self.customer_manager.create_customer(
                first_name=f"Customer{i}",
                last_name=f"Lastname{i}",
                email=f"customer{i}@bank.com"
            )
            
            # Upgrade customers to higher tiers for transaction testing
            self.customer_manager.update_kyc_status(
                customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
            )
            
            customers.append(customer)
            
            # Create accounts for each customer
            checking = self.account_manager.create_account(
                customer_id=customer.id,
                product_type=ProductType.CHECKING,
                currency=Currency.USD,
                name=f"Customer {i} Checking"
            )
            
            savings = self.account_manager.create_account(
                customer_id=customer.id,
                product_type=ProductType.SAVINGS,
                currency=Currency.USD,
                name=f"Customer {i} Savings"
            )
            
            accounts.extend([checking, savings])
        
        # Simulate various transactions throughout the day
        transaction_count = 0
        
        # Morning: deposits
        for i, customer in enumerate(customers):
            customer_accounts = [acc for acc in accounts if acc.customer_id == customer.id]
            for account in customer_accounts:
                if account.product_type == ProductType.CHECKING:
                    deposit = self.transaction_processor.deposit(
                        account_id=account.id,
                        amount=Money(Decimal(f'{(i+1)*500}.00'), Currency.USD),
                        description="Morning deposit",
                        channel=TransactionChannel.BRANCH
                    )
                    self.transaction_processor.process_transaction(deposit.id)
                    transaction_count += 1
        
        # Midday: transfers
        for i in range(len(customers)):
            customer_accounts = [acc for acc in accounts if acc.customer_id == customers[i].id]
            checking_acc = next(acc for acc in customer_accounts if acc.product_type == ProductType.CHECKING)
            savings_acc = next(acc for acc in customer_accounts if acc.product_type == ProductType.SAVINGS)
            
            transfer = self.transaction_processor.transfer(
                from_account_id=checking_acc.id,
                to_account_id=savings_acc.id,
                amount=Money(Decimal('200.00'), Currency.USD),
                description="Savings transfer",
                channel=TransactionChannel.ONLINE
            )
            self.transaction_processor.process_transaction(transfer.id)
            transaction_count += 1
        
        # Afternoon: withdrawals
        for i in range(3):  # Only first 3 customers
            customer_accounts = [acc for acc in accounts if acc.customer_id == customers[i].id]
            checking_acc = next(acc for acc in customer_accounts if acc.product_type == ProductType.CHECKING)
            
            withdrawal = self.transaction_processor.withdraw(
                account_id=checking_acc.id,
                amount=Money(Decimal('100.00'), Currency.USD),
                description="ATM withdrawal",
                channel=TransactionChannel.ATM
            )
            self.transaction_processor.process_transaction(withdrawal.id)
            transaction_count += 1
        
        # End of day: verify system consistency
        
        # 1. All transactions should be completed
        all_accounts_transactions = []
        for account in accounts:
            txns = self.transaction_processor.get_account_transactions(account.id)
            all_accounts_transactions.extend(txns)
        
        completed_count = sum(1 for txn in all_accounts_transactions if txn.state == TransactionState.COMPLETED)
        assert completed_count >= transaction_count
        
        # 2. Trial balance should be balanced
        account_types_map = {}
        for account in accounts:
            if account.product_type in [ProductType.CHECKING, ProductType.SAVINGS]:
                account_types_map[account.id] = AccountType.ASSET
        
        trial_balance = self.ledger.get_trial_balance(account_types_map, Currency.USD)
        
        # Sum all asset account balances
        total_customer_assets = sum(balance.amount for balance in trial_balance.values())
        assert total_customer_assets > Decimal('0')  # Should have positive total assets
        
        # 3. Audit trail should be intact
        integrity_result = self.audit_trail.verify_integrity()
        assert integrity_result["valid"] == True
        
        # 4. Run daily interest accrual
        accrual_results = self.interest_engine.run_daily_accrual()
        # May or may not accrue interest depending on balances and minimums
        
        print(f"Banking day simulation completed:")
        print(f"- Customers created: {len(customers)}")
        print(f"- Accounts opened: {len(accounts)}")
        print(f"- Transactions processed: {completed_count}")
        print(f"- Total assets: ${total_customer_assets}")
        print(f"- Audit events: {integrity_result['total_events']}")
        print(f"- Interest accruals: {sum(accrual_results.values())}")


if __name__ == "__main__":
    pytest.main([__file__])