"""
Test suite for transactions module

Tests all transaction types, reversals, idempotency, and compliance integration.
Validates proper double-entry bookkeeping and journal entry creation.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.ledger import GeneralLedger, AccountType
from core_banking.accounts import AccountManager, ProductType
from core_banking.customers import CustomerManager, KYCStatus, KYCTier
from core_banking.compliance import ComplianceEngine, ComplianceAction
from core_banking.transactions import (
    TransactionProcessor, Transaction, TransactionType, 
    TransactionState, TransactionChannel
)


class TestTransactionProcessor:
    """Test transaction processing functionality"""
    
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
        
        # Create test customer and accounts
        self.customer = self.customer_manager.create_customer(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com"
        )
        
        # Update customer to verified KYC for higher limits
        self.customer_manager.update_kyc_status(
            self.customer.id,
            KYCStatus.VERIFIED,
            KYCTier.TIER_2
        )
        
        self.savings_account = self.account_manager.create_account(
            customer_id=self.customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Test Savings Account"
        )
        
        self.checking_account = self.account_manager.create_account(
            customer_id=self.customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Test Checking Account"
        )
    
    def test_create_deposit_transaction(self):
        """Test creating a deposit transaction"""
        transaction = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.DEPOSIT,
            amount=Money(Decimal('1000.00'), Currency.USD),
            description="Initial deposit",
            channel=TransactionChannel.BRANCH,
            to_account_id=self.savings_account.id,
            reference="DEP001"
        )
        
        assert transaction.transaction_type == TransactionType.DEPOSIT
        assert transaction.amount == Money(Decimal('1000.00'), Currency.USD)
        assert transaction.to_account_id == self.savings_account.id
        assert transaction.from_account_id is None
        assert transaction.state == TransactionState.PENDING
        assert transaction.reference == "DEP001"
        assert transaction.idempotency_key is not None
    
    def test_create_withdrawal_transaction(self):
        """Test creating a withdrawal transaction"""
        transaction = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.WITHDRAWAL,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="ATM withdrawal",
            channel=TransactionChannel.ATM,
            from_account_id=self.checking_account.id,
            reference="WITH001"
        )
        
        assert transaction.transaction_type == TransactionType.WITHDRAWAL
        assert transaction.amount == Money(Decimal('500.00'), Currency.USD)
        assert transaction.from_account_id == self.checking_account.id
        assert transaction.to_account_id is None
        assert transaction.state == TransactionState.PENDING
    
    def test_create_transfer_transaction(self):
        """Test creating an internal transfer transaction"""
        transaction = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.TRANSFER_INTERNAL,
            amount=Money(Decimal('250.00'), Currency.USD),
            description="Transfer between accounts",
            channel=TransactionChannel.ONLINE,
            from_account_id=self.savings_account.id,
            to_account_id=self.checking_account.id,
            reference="XFER001"
        )
        
        assert transaction.transaction_type == TransactionType.TRANSFER_INTERNAL
        assert transaction.amount == Money(Decimal('250.00'), Currency.USD)
        assert transaction.from_account_id == self.savings_account.id
        assert transaction.to_account_id == self.checking_account.id
        assert transaction.state == TransactionState.PENDING
    
    def test_idempotency_key_prevents_duplicate(self):
        """Test that idempotency key prevents duplicate transactions"""
        idempotency_key = "UNIQUE_KEY_001"
        
        # Create first transaction
        transaction1 = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.DEPOSIT,
            amount=Money(Decimal('100.00'), Currency.USD),
            description="Test deposit",
            channel=TransactionChannel.ONLINE,
            to_account_id=self.savings_account.id,
            idempotency_key=idempotency_key
        )
        
        # Create second transaction with same idempotency key
        transaction2 = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.DEPOSIT,
            amount=Money(Decimal('200.00'), Currency.USD),  # Different amount
            description="Different deposit",
            channel=TransactionChannel.ONLINE,
            to_account_id=self.savings_account.id,
            idempotency_key=idempotency_key  # Same key
        )
        
        # Should return the same transaction
        assert transaction1.id == transaction2.id
        assert transaction2.amount == Money(Decimal('100.00'), Currency.USD)  # Original amount
    
    def test_process_deposit_transaction(self):
        """Test processing a deposit transaction"""
        # Create deposit
        transaction = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('1500.00'), Currency.USD),
            description="Paycheck deposit",
            channel=TransactionChannel.ONLINE
        )
        
        # Process transaction
        processed = self.transaction_processor.process_transaction(transaction.id)
        
        assert processed.state == TransactionState.COMPLETED
        assert processed.processed_at is not None
        assert processed.journal_entry_id is not None
        
        # Check account balance
        balance = self.account_manager.get_book_balance(self.savings_account.id)
        assert balance == Money(Decimal('1500.00'), Currency.USD)
        
        # Check journal entry was created and posted
        journal_entry = self.ledger.get_journal_entry(processed.journal_entry_id)
        assert journal_entry is not None
        assert len(journal_entry.lines) == 2
        
        # Verify double-entry bookkeeping
        total_debits = sum(line.debit_amount.amount for line in journal_entry.lines)
        total_credits = sum(line.credit_amount.amount for line in journal_entry.lines)
        assert total_debits == total_credits == Decimal('1500.00')
    
    def test_process_withdrawal_with_insufficient_funds(self):
        """Test withdrawal with insufficient funds"""
        # Try to withdraw from empty account
        transaction = self.transaction_processor.withdraw(
            account_id=self.checking_account.id,
            amount=Money(Decimal('100.00'), Currency.USD),
            description="ATM withdrawal",
            channel=TransactionChannel.ATM
        )
        
        # Processing should fail due to insufficient funds
        with pytest.raises(ValueError, match="Insufficient funds"):
            self.transaction_processor.process_transaction(transaction.id)
        
        # Transaction should be marked as failed
        failed_txn = self.transaction_processor.get_transaction(transaction.id)
        assert failed_txn.state == TransactionState.FAILED
        assert failed_txn.error_message is not None
    
    def test_process_withdrawal_with_sufficient_funds(self):
        """Test withdrawal with sufficient funds"""
        # First deposit money
        deposit = self.transaction_processor.deposit(
            account_id=self.checking_account.id,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="Initial deposit",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        # Now withdraw some money
        withdrawal = self.transaction_processor.withdraw(
            account_id=self.checking_account.id,
            amount=Money(Decimal('200.00'), Currency.USD),
            description="Cash withdrawal",
            channel=TransactionChannel.ATM
        )
        
        processed = self.transaction_processor.process_transaction(withdrawal.id)
        assert processed.state == TransactionState.COMPLETED
        
        # Check final balance
        balance = self.account_manager.get_book_balance(self.checking_account.id)
        assert balance == Money(Decimal('300.00'), Currency.USD)
    
    def test_process_internal_transfer(self):
        """Test internal transfer between accounts"""
        # Setup: Deposit money in savings
        deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('1000.00'), Currency.USD),
            description="Initial deposit",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        # Transfer from savings to checking
        transfer = self.transaction_processor.transfer(
            from_account_id=self.savings_account.id,
            to_account_id=self.checking_account.id,
            amount=Money(Decimal('400.00'), Currency.USD),
            description="Transfer to checking",
            channel=TransactionChannel.ONLINE
        )
        
        processed = self.transaction_processor.process_transaction(transfer.id)
        assert processed.state == TransactionState.COMPLETED
        
        # Check balances
        savings_balance = self.account_manager.get_book_balance(self.savings_account.id)
        checking_balance = self.account_manager.get_book_balance(self.checking_account.id)
        
        assert savings_balance == Money(Decimal('600.00'), Currency.USD)
        assert checking_balance == Money(Decimal('400.00'), Currency.USD)
        
        # Verify journal entry
        journal_entry = self.ledger.get_journal_entry(processed.journal_entry_id)
        assert len(journal_entry.lines) == 2
        
        # Find debit and credit lines
        debit_line = next(line for line in journal_entry.lines if line.is_debit)
        credit_line = next(line for line in journal_entry.lines if line.is_credit)
        
        assert debit_line.account_id == self.checking_account.id  # To account gets debited
        assert credit_line.account_id == self.savings_account.id  # From account gets credited
    
    def test_transaction_reversal(self):
        """Test reversing a completed transaction"""
        # Create and process a deposit
        deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('750.00'), Currency.USD),
            description="Deposit to reverse",
            channel=TransactionChannel.BRANCH
        )
        processed_deposit = self.transaction_processor.process_transaction(deposit.id)
        
        # Verify initial balance
        initial_balance = self.account_manager.get_book_balance(self.savings_account.id)
        assert initial_balance == Money(Decimal('750.00'), Currency.USD)
        
        # Reverse the transaction
        reversal = self.transaction_processor.reverse_transaction(
            processed_deposit.id,
            "Customer dispute - unauthorized transaction"
        )
        
        assert reversal.transaction_type == TransactionType.REVERSAL
        assert reversal.state == TransactionState.COMPLETED
        assert reversal.original_transaction_id == processed_deposit.id
        
        # Check that original transaction is marked as reversed
        updated_original = self.transaction_processor.get_transaction(processed_deposit.id)
        assert updated_original.state == TransactionState.REVERSED
        assert updated_original.reversal_transaction_id == reversal.id
        
        # Check final balance (should be zero)
        final_balance = self.account_manager.get_book_balance(self.savings_account.id)
        assert final_balance == Money(Decimal('0.00'), Currency.USD)
    
    def test_compliance_blocking_transaction(self):
        """Test that compliance engine can block transactions"""
        # Create customer with low KYC tier
        low_tier_customer = self.customer_manager.create_customer(
            first_name="Jane",
            last_name="Smith",
            email="jane.smith@example.com"
        )
        # Customer starts with TIER_0 (very low limits)
        
        low_tier_account = self.account_manager.create_account(
            customer_id=low_tier_customer.id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Low Tier Account"
        )
        
        # Try to deposit large amount that exceeds limits
        large_deposit = self.transaction_processor.deposit(
            account_id=low_tier_account.id,
            amount=Money(Decimal('5000.00'), Currency.USD),  # Exceeds TIER_0 limits
            description="Large deposit",
            channel=TransactionChannel.BRANCH
        )
        
        # Process should fail due to compliance
        with pytest.raises(ValueError, match="Blocked by compliance"):
            self.transaction_processor.process_transaction(large_deposit.id)
        
        failed_txn = self.transaction_processor.get_transaction(large_deposit.id)
        assert failed_txn.state == TransactionState.FAILED
        assert failed_txn.compliance_action == ComplianceAction.BLOCK
    
    def test_get_account_transactions(self):
        """Test retrieving transaction history for account"""
        # Create multiple transactions
        transactions = []
        
        # Deposit
        deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('1000.00'), Currency.USD),
            description="Deposit 1",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        transactions.append(deposit)
        
        # Another deposit
        deposit2 = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="Deposit 2",
            channel=TransactionChannel.ONLINE
        )
        self.transaction_processor.process_transaction(deposit2.id)
        transactions.append(deposit2)
        
        # Withdrawal
        withdrawal = self.transaction_processor.withdraw(
            account_id=self.savings_account.id,
            amount=Money(Decimal('200.00'), Currency.USD),
            description="Withdrawal 1",
            channel=TransactionChannel.ATM
        )
        self.transaction_processor.process_transaction(withdrawal.id)
        transactions.append(withdrawal)
        
        # Get transaction history
        history = self.transaction_processor.get_account_transactions(self.savings_account.id)
        
        assert len(history) == 3
        # Should be ordered by creation time (most recent first)
        assert history[0].id == withdrawal.id
        assert history[1].id == deposit2.id
        assert history[2].id == deposit.id
    
    def test_get_account_transactions_with_filters(self):
        """Test getting account transactions with filters"""
        # Create transactions
        deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('300.00'), Currency.USD),
            description="Test deposit",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        withdrawal = self.transaction_processor.withdraw(
            account_id=self.savings_account.id,
            amount=Money(Decimal('100.00'), Currency.USD),
            description="Test withdrawal",
            channel=TransactionChannel.ATM
        )
        self.transaction_processor.process_transaction(withdrawal.id)
        
        # Test type filter
        deposits_only = self.transaction_processor.get_account_transactions(
            account_id=self.savings_account.id,
            transaction_types=[TransactionType.DEPOSIT]
        )
        assert len(deposits_only) == 1
        assert deposits_only[0].transaction_type == TransactionType.DEPOSIT
        
        # Test limit
        limited = self.transaction_processor.get_account_transactions(
            account_id=self.savings_account.id,
            limit=1
        )
        assert len(limited) == 1
    
    def test_transaction_validation_errors(self):
        """Test transaction validation errors"""
        # Test missing accounts
        with pytest.raises(ValueError, match="must have at least one account"):
            self.transaction_processor.create_transaction(
                transaction_type=TransactionType.TRANSFER_INTERNAL,
                amount=Money(Decimal('100.00'), Currency.USD),
                description="Invalid transfer",
                channel=TransactionChannel.ONLINE
                # No from_account_id or to_account_id
            )
        
        # Test negative amount
        with pytest.raises(ValueError, match="must be positive"):
            self.transaction_processor.create_transaction(
                transaction_type=TransactionType.DEPOSIT,
                amount=Money(Decimal('-100.00'), Currency.USD),
                description="Negative deposit",
                channel=TransactionChannel.ONLINE,
                to_account_id=self.savings_account.id
            )
        
        # Test currency mismatch
        with pytest.raises(ValueError, match="currency must match"):
            Transaction(
                id="TEST001",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                transaction_type=TransactionType.DEPOSIT,
                from_account_id=None,
                to_account_id=self.savings_account.id,
                amount=Money(Decimal('100.00'), Currency.USD),
                currency=Currency.EUR,  # Mismatch!
                description="Test",
                reference="TEST",
                idempotency_key="TEST_KEY",
                channel=TransactionChannel.ONLINE
            )
    
    def test_transaction_convenience_methods(self):
        """Test convenience methods for common transaction types"""
        # Test deposit convenience method
        deposit = self.transaction_processor.deposit(
            account_id=self.savings_account.id,
            amount=Money(Decimal('100.00'), Currency.USD),
            description="Convenience deposit",
            channel=TransactionChannel.BRANCH,
            reference="CONV_DEP"
        )
        
        assert deposit.transaction_type == TransactionType.DEPOSIT
        assert deposit.to_account_id == self.savings_account.id
        assert deposit.from_account_id is None
        assert deposit.reference == "CONV_DEP"
        
        # Process to give account balance
        self.transaction_processor.process_transaction(deposit.id)
        
        # Test withdrawal convenience method
        withdrawal = self.transaction_processor.withdraw(
            account_id=self.savings_account.id,
            amount=Money(Decimal('30.00'), Currency.USD),
            description="Convenience withdrawal",
            channel=TransactionChannel.ATM,
            reference="CONV_WITH"
        )
        
        assert withdrawal.transaction_type == TransactionType.WITHDRAWAL
        assert withdrawal.from_account_id == self.savings_account.id
        assert withdrawal.to_account_id is None
        assert withdrawal.reference == "CONV_WITH"
        
        # Test transfer convenience method
        transfer = self.transaction_processor.transfer(
            from_account_id=self.savings_account.id,
            to_account_id=self.checking_account.id,
            amount=Money(Decimal('50.00'), Currency.USD),
            description="Convenience transfer",
            channel=TransactionChannel.ONLINE,
            reference="CONV_XFER"
        )
        
        assert transfer.transaction_type == TransactionType.TRANSFER_INTERNAL
        assert transfer.from_account_id == self.savings_account.id
        assert transfer.to_account_id == self.checking_account.id
        assert transfer.reference == "CONV_XFER"
    
    def test_transaction_with_holds(self):
        """Test transaction processing with account holds"""
        # Deposit money
        deposit = self.transaction_processor.deposit(
            account_id=self.checking_account.id,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="Initial deposit",
            channel=TransactionChannel.BRANCH
        )
        self.transaction_processor.process_transaction(deposit.id)
        
        # Place hold
        hold = self.account_manager.place_hold(
            account_id=self.checking_account.id,
            amount=Money(Decimal('300.00'), Currency.USD),
            reason="Authorization hold"
        )
        
        # Try to withdraw more than available balance (considering hold)
        # Available: $500 - $300 hold = $200
        large_withdrawal = self.transaction_processor.withdraw(
            account_id=self.checking_account.id,
            amount=Money(Decimal('250.00'), Currency.USD),
            description="Large withdrawal",
            channel=TransactionChannel.ATM
        )
        
        # Should fail due to hold reducing available balance
        with pytest.raises(ValueError, match="Insufficient funds"):
            self.transaction_processor.process_transaction(large_withdrawal.id)
        
        # Smaller withdrawal should work
        small_withdrawal = self.transaction_processor.withdraw(
            account_id=self.checking_account.id,
            amount=Money(Decimal('150.00'), Currency.USD),
            description="Small withdrawal",
            channel=TransactionChannel.ATM
        )
        
        processed = self.transaction_processor.process_transaction(small_withdrawal.id)
        assert processed.state == TransactionState.COMPLETED
    
    def test_multiple_currency_support(self):
        """Test transactions in multiple currencies"""
        # Create EUR account
        eur_account = self.account_manager.create_account(
            customer_id=self.customer.id,
            product_type=ProductType.SAVINGS,
            currency=Currency.EUR,
            name="EUR Savings"
        )
        
        # Deposit EUR
        eur_deposit = self.transaction_processor.deposit(
            account_id=eur_account.id,
            amount=Money(Decimal('850.00'), Currency.EUR),
            description="EUR deposit",
            channel=TransactionChannel.BRANCH
        )
        
        processed = self.transaction_processor.process_transaction(eur_deposit.id)
        assert processed.state == TransactionState.COMPLETED
        
        # Check EUR balance
        eur_balance = self.account_manager.get_book_balance(eur_account.id)
        assert eur_balance == Money(Decimal('850.00'), Currency.EUR)
        assert eur_balance.currency == Currency.EUR
        
        # Verify journal entry uses correct currency
        journal_entry = self.ledger.get_journal_entry(processed.journal_entry_id)
        for line in journal_entry.lines:
            assert line.currency == Currency.EUR


if __name__ == "__main__":
    pytest.main([__file__])