"""
Test suite for accounts module

Tests account lifecycle, balance calculations, holds, and product types.
Validates proper integration with ledger for balance derivation.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.ledger import GeneralLedger, JournalEntryLine, AccountType
from core_banking.accounts import (
    AccountManager, Account, ProductType, AccountState, AccountHold
)


class TestAccount:
    """Test Account class functionality"""
    
    def test_valid_savings_account(self):
        """Test creating a valid savings account"""
        now = datetime.now(timezone.utc)
        
        account = Account(
            id="ACC001",
            created_at=now,
            updated_at=now,
            account_number="SAV123456",
            customer_id="CUST001",
            product_type=ProductType.SAVINGS,
            account_type=AccountType.ASSET,
            currency=Currency.USD,
            name="Primary Savings",
            interest_rate=Decimal('0.02'),
            minimum_balance=Money(Decimal('100.00'), Currency.USD)
        )
        
        assert account.account_number == "SAV123456"
        assert account.product_type == ProductType.SAVINGS
        assert account.account_type == AccountType.ASSET
        assert account.currency == Currency.USD
        assert account.is_asset_account
        assert not account.is_liability_account
        assert account.is_deposit_product
        assert not account.is_credit_product
        assert account.can_transact()
        assert account.can_credit()
        assert account.can_debit()
    
    def test_valid_credit_line_account(self):
        """Test creating a valid credit line account"""
        now = datetime.now(timezone.utc)
        
        account = Account(
            id="ACC002",
            created_at=now,
            updated_at=now,
            account_number="CRD789012",
            customer_id="CUST002",
            product_type=ProductType.CREDIT_LINE,
            account_type=AccountType.LIABILITY,
            currency=Currency.USD,
            name="Personal Credit Line",
            credit_limit=Money(Decimal('5000.00'), Currency.USD),
            interest_rate=Decimal('0.1899')
        )
        
        assert account.product_type == ProductType.CREDIT_LINE
        assert account.account_type == AccountType.LIABILITY
        assert account.is_liability_account
        assert not account.is_asset_account
        assert account.is_credit_product
        assert not account.is_deposit_product
        assert account.supports_overdraft
        assert account.credit_limit == Money(Decimal('5000.00'), Currency.USD)
    
    def test_currency_consistency_validation(self):
        """Test that currency inconsistencies are caught"""
        now = datetime.now(timezone.utc)
        
        # Test credit limit currency mismatch
        with pytest.raises(ValueError, match="Credit limit currency must match account currency"):
            Account(
                id="ACC003",
                created_at=now,
                updated_at=now,
                account_number="TEST001",
                customer_id="CUST001",
                product_type=ProductType.CREDIT_LINE,
                account_type=AccountType.LIABILITY,
                currency=Currency.USD,
                name="Test Account",
                credit_limit=Money(Decimal('1000.00'), Currency.EUR)  # Wrong currency!
            )
        
        # Test minimum balance currency mismatch
        with pytest.raises(ValueError, match="Minimum balance currency must match account currency"):
            Account(
                id="ACC004",
                created_at=now,
                updated_at=now,
                account_number="TEST002",
                customer_id="CUST001",
                product_type=ProductType.SAVINGS,
                account_type=AccountType.ASSET,
                currency=Currency.USD,
                name="Test Savings",
                minimum_balance=Money(Decimal('100.00'), Currency.EUR)  # Wrong currency!
            )
    
    def test_account_state_permissions(self):
        """Test account state permissions"""
        now = datetime.now(timezone.utc)
        
        # Active account - all permissions
        active_account = Account(
            id="ACC005",
            created_at=now,
            updated_at=now,
            account_number="ACTIVE001",
            customer_id="CUST001",
            product_type=ProductType.CHECKING,
            account_type=AccountType.ASSET,
            currency=Currency.USD,
            name="Active Account",
            state=AccountState.ACTIVE
        )
        
        assert active_account.can_transact()
        assert active_account.can_credit()
        assert active_account.can_debit()
        
        # Frozen account - can credit but not debit
        frozen_account = Account(
            id="ACC006",
            created_at=now,
            updated_at=now,
            account_number="FROZEN001",
            customer_id="CUST001",
            product_type=ProductType.CHECKING,
            account_type=AccountType.ASSET,
            currency=Currency.USD,
            name="Frozen Account",
            state=AccountState.FROZEN
        )
        
        assert not frozen_account.can_transact()
        assert frozen_account.can_credit()
        assert not frozen_account.can_debit()
        
        # Dormant account - can credit but not debit
        dormant_account = Account(
            id="ACC007",
            created_at=now,
            updated_at=now,
            account_number="DORMANT001",
            customer_id="CUST001",
            product_type=ProductType.SAVINGS,
            account_type=AccountType.ASSET,
            currency=Currency.USD,
            name="Dormant Account",
            state=AccountState.DORMANT
        )
        
        assert not dormant_account.can_transact()
        assert dormant_account.can_credit()
        assert not dormant_account.can_debit()
        
        # Closed account - cannot do anything
        closed_account = Account(
            id="ACC008",
            created_at=now,
            updated_at=now,
            account_number="CLOSED001",
            customer_id="CUST001",
            product_type=ProductType.CHECKING,
            account_type=AccountType.ASSET,
            currency=Currency.USD,
            name="Closed Account",
            state=AccountState.CLOSED
        )
        
        assert not closed_account.can_transact()
        assert not closed_account.can_credit()
        assert not closed_account.can_debit()


class TestAccountHold:
    """Test AccountHold functionality"""
    
    def test_valid_hold(self):
        """Test creating a valid account hold"""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=24)
        
        hold = AccountHold(
            id="HOLD001",
            created_at=now,
            updated_at=now,
            account_id="ACC001",
            amount=Money(Decimal('100.00'), Currency.USD),
            reason="Pending transaction verification",
            expires_at=expires_at
        )
        
        assert hold.account_id == "ACC001"
        assert hold.amount == Money(Decimal('100.00'), Currency.USD)
        assert hold.reason == "Pending transaction verification"
        assert hold.expires_at == expires_at
        assert hold.is_active  # Not released and not expired
    
    def test_hold_expiration(self):
        """Test hold expiration logic"""
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        
        hold = AccountHold(
            id="HOLD002",
            created_at=past_time,
            updated_at=past_time,
            account_id="ACC001",
            amount=Money(Decimal('50.00'), Currency.USD),
            reason="Test hold",
            expires_at=past_time  # Already expired
        )
        
        assert not hold.is_active  # Should be inactive due to expiration
    
    def test_hold_release(self):
        """Test hold release"""
        now = datetime.now(timezone.utc)
        
        hold = AccountHold(
            id="HOLD003",
            created_at=now,
            updated_at=now,
            account_id="ACC001",
            amount=Money(Decimal('75.00'), Currency.USD),
            reason="Test hold"
        )
        
        assert hold.is_active
        
        # Release the hold
        hold.released_at = now
        assert not hold.is_active


class TestAccountManager:
    """Test AccountManager functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.storage = InMemoryStorage()
        self.audit_trail = AuditTrail(self.storage)
        self.ledger = GeneralLedger(self.storage, self.audit_trail)
        self.account_manager = AccountManager(self.storage, self.ledger, self.audit_trail)
    
    def test_create_savings_account(self):
        """Test creating a savings account"""
        account = self.account_manager.create_account(
            customer_id="CUST001",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Primary Savings Account",
            interest_rate=Decimal('0.025'),
            minimum_balance=Money(Decimal('100.00'), Currency.USD),
            daily_transaction_limit=Money(Decimal('1000.00'), Currency.USD)
        )
        
        assert account.customer_id == "CUST001"
        assert account.product_type == ProductType.SAVINGS
        assert account.account_type == AccountType.ASSET  # Should be auto-assigned
        assert account.currency == Currency.USD
        assert account.name == "Primary Savings Account"
        assert account.interest_rate == Decimal('0.025')
        assert account.minimum_balance == Money(Decimal('100.00'), Currency.USD)
        assert account.account_number.startswith("SAV")  # Should have SAV prefix
        assert account.state == AccountState.ACTIVE
        
        # Should be retrievable
        retrieved = self.account_manager.get_account(account.id)
        assert retrieved is not None
        assert retrieved.customer_id == "CUST001"
    
    def test_create_credit_line_account(self):
        """Test creating a credit line account"""
        account = self.account_manager.create_account(
            customer_id="CUST002",
            product_type=ProductType.CREDIT_LINE,
            currency=Currency.USD,
            name="Personal Credit Line",
            credit_limit=Money(Decimal('5000.00'), Currency.USD),
            interest_rate=Decimal('0.1899')
        )
        
        assert account.product_type == ProductType.CREDIT_LINE
        assert account.account_type == AccountType.LIABILITY  # Should be auto-assigned
        assert account.credit_limit == Money(Decimal('5000.00'), Currency.USD)
        assert account.account_number.startswith("CRD")  # Should have CRD prefix
        assert account.supports_overdraft
    
    def test_get_account_by_number(self):
        """Test retrieving account by account number"""
        # Create account
        account = self.account_manager.create_account(
            customer_id="CUST003",
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Test Checking"
        )
        
        # Retrieve by account number
        retrieved = self.account_manager.get_account_by_number(account.account_number)
        assert retrieved is not None
        assert retrieved.id == account.id
        assert retrieved.account_number == account.account_number
        
        # Test non-existent account number
        non_existent = self.account_manager.get_account_by_number("NONEXISTENT123")
        assert non_existent is None
    
    def test_get_customer_accounts(self):
        """Test getting all accounts for a customer"""
        customer_id = "CUST004"
        
        # Create multiple accounts for the customer
        savings = self.account_manager.create_account(
            customer_id=customer_id,
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Savings Account"
        )
        
        checking = self.account_manager.create_account(
            customer_id=customer_id,
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Checking Account"
        )
        
        credit = self.account_manager.create_account(
            customer_id=customer_id,
            product_type=ProductType.CREDIT_LINE,
            currency=Currency.USD,
            name="Credit Line",
            credit_limit=Money(Decimal('3000.00'), Currency.USD)
        )
        
        # Create account for different customer
        other_customer = self.account_manager.create_account(
            customer_id="OTHER_CUSTOMER",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Other Account"
        )
        
        # Get accounts for our customer
        customer_accounts = self.account_manager.get_customer_accounts(customer_id)
        
        assert len(customer_accounts) == 3
        account_ids = {acc.id for acc in customer_accounts}
        assert savings.id in account_ids
        assert checking.id in account_ids
        assert credit.id in account_ids
        assert other_customer.id not in account_ids
    
    def test_account_state_management(self):
        """Test account state changes"""
        account = self.account_manager.create_account(
            customer_id="CUST005",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="State Test Account"
        )
        
        assert account.state == AccountState.ACTIVE
        
        # Freeze account
        frozen_account = self.account_manager.freeze_account(account.id, "Suspicious activity")
        assert frozen_account.state == AccountState.FROZEN
        
        # Unfreeze account
        unfrozen_account = self.account_manager.unfreeze_account(account.id, "Investigation completed")
        assert unfrozen_account.state == AccountState.ACTIVE
        
        # Close account (will fail if there's a balance)
        closed_account = self.account_manager.close_account(account.id, "Customer request")
        assert closed_account.state == AccountState.CLOSED
    
    def test_close_account_with_balance(self):
        """Test that account with non-zero balance cannot be closed"""
        account = self.account_manager.create_account(
            customer_id="CUST006",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Balance Test Account"
        )
        
        # Create a journal entry to give the account a balance
        lines = [
            JournalEntryLine(
                account_id=account.id,
                description="Test deposit",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="REVENUE001",
                description="Test revenue",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('100.00'), Currency.USD)
            )
        ]
        
        entry = self.ledger.create_journal_entry("TEST001", "Test deposit", lines)
        self.ledger.post_journal_entry(entry.id)
        
        # Try to close account with balance - should fail
        with pytest.raises(ValueError, match="Cannot close account with non-zero balance"):
            self.account_manager.close_account(account.id, "Should fail")
    
    def test_place_and_release_hold(self):
        """Test placing and releasing account holds"""
        account = self.account_manager.create_account(
            customer_id="CUST007",
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Hold Test Account"
        )
        
        # Place a hold
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        hold = self.account_manager.place_hold(
            account_id=account.id,
            amount=Money(Decimal('250.00'), Currency.USD),
            reason="Pending transaction verification",
            expires_at=expires_at
        )
        
        assert hold.account_id == account.id
        assert hold.amount == Money(Decimal('250.00'), Currency.USD)
        assert hold.is_active
        
        # Get active holds
        active_holds = self.account_manager.get_active_holds(account.id)
        assert len(active_holds) == 1
        assert active_holds[0].id == hold.id
        
        # Release hold
        released_hold = self.account_manager.release_hold(hold.id, "Transaction completed")
        assert not released_hold.is_active
        
        # Active holds should now be empty
        active_holds = self.account_manager.get_active_holds(account.id)
        assert len(active_holds) == 0
    
    def test_hold_currency_validation(self):
        """Test hold currency must match account currency"""
        account = self.account_manager.create_account(
            customer_id="CUST008",
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Currency Test Account"
        )
        
        # Try to place hold in different currency
        with pytest.raises(ValueError, match="Hold amount currency must match account currency"):
            self.account_manager.place_hold(
                account_id=account.id,
                amount=Money(Decimal('100.00'), Currency.EUR),  # Wrong currency!
                reason="Test hold"
            )
    
    def test_hold_amount_validation(self):
        """Test hold amount must be positive"""
        account = self.account_manager.create_account(
            customer_id="CUST009",
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Amount Test Account"
        )
        
        # Try to place negative hold
        with pytest.raises(ValueError, match="Hold amount must be positive"):
            self.account_manager.place_hold(
                account_id=account.id,
                amount=Money(Decimal('-50.00'), Currency.USD),
                reason="Negative hold test"
            )
        
        # Try to place zero hold
        with pytest.raises(ValueError, match="Hold amount must be positive"):
            self.account_manager.place_hold(
                account_id=account.id,
                amount=Money(Decimal('0.00'), Currency.USD),
                reason="Zero hold test"
            )
    
    def test_book_balance_calculation(self):
        """Test book balance calculation from ledger"""
        account = self.account_manager.create_account(
            customer_id="CUST010",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Balance Test Account"
        )
        
        # Initially zero balance
        balance = self.account_manager.get_book_balance(account.id)
        assert balance == Money(Decimal('0.00'), Currency.USD)
        
        # Create deposit entry
        lines1 = [
            JournalEntryLine(
                account_id=account.id,
                description="Deposit",
                debit_amount=Money(Decimal('500.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="CASH001",
                description="Cash received",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('500.00'), Currency.USD)
            )
        ]
        
        entry1 = self.ledger.create_journal_entry("BAL001", "Deposit", lines1)
        self.ledger.post_journal_entry(entry1.id)
        
        # Balance should now be $500
        balance = self.account_manager.get_book_balance(account.id)
        assert balance == Money(Decimal('500.00'), Currency.USD)
        
        # Create withdrawal entry
        lines2 = [
            JournalEntryLine(
                account_id=account.id,
                description="Withdrawal",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('150.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="CASH001",
                description="Cash paid",
                debit_amount=Money(Decimal('150.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            )
        ]
        
        entry2 = self.ledger.create_journal_entry("BAL002", "Withdrawal", lines2)
        self.ledger.post_journal_entry(entry2.id)
        
        # Balance should now be $350 ($500 - $150)
        balance = self.account_manager.get_book_balance(account.id)
        assert balance == Money(Decimal('350.00'), Currency.USD)
    
    def test_available_balance_with_holds(self):
        """Test available balance calculation including holds"""
        account = self.account_manager.create_account(
            customer_id="CUST011",
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            name="Available Balance Test"
        )
        
        # Create deposit to give account a balance
        lines = [
            JournalEntryLine(
                account_id=account.id,
                description="Initial deposit",
                debit_amount=Money(Decimal('1000.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="CASH001",
                description="Cash received",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('1000.00'), Currency.USD)
            )
        ]
        
        entry = self.ledger.create_journal_entry("AVAIL001", "Initial deposit", lines)
        self.ledger.post_journal_entry(entry.id)
        
        # Book balance and available balance should be equal initially
        book_balance = self.account_manager.get_book_balance(account.id)
        available_balance = self.account_manager.get_available_balance(account.id)
        
        assert book_balance == Money(Decimal('1000.00'), Currency.USD)
        assert available_balance == Money(Decimal('1000.00'), Currency.USD)
        
        # Place holds
        hold1 = self.account_manager.place_hold(
            account_id=account.id,
            amount=Money(Decimal('200.00'), Currency.USD),
            reason="Hold 1"
        )
        
        hold2 = self.account_manager.place_hold(
            account_id=account.id,
            amount=Money(Decimal('300.00'), Currency.USD),
            reason="Hold 2"
        )
        
        # Available balance should be reduced by holds
        available_balance = self.account_manager.get_available_balance(account.id)
        assert available_balance == Money(Decimal('500.00'), Currency.USD)  # 1000 - 200 - 300
        
        # Book balance should be unchanged
        book_balance = self.account_manager.get_book_balance(account.id)
        assert book_balance == Money(Decimal('1000.00'), Currency.USD)
        
        # Release one hold
        self.account_manager.release_hold(hold1.id, "Released")
        
        # Available balance should increase
        available_balance = self.account_manager.get_available_balance(account.id)
        assert available_balance == Money(Decimal('700.00'), Currency.USD)  # 1000 - 300
    
    def test_credit_available_for_credit_line(self):
        """Test available credit calculation for credit line account"""
        account = self.account_manager.create_account(
            customer_id="CUST012",
            product_type=ProductType.CREDIT_LINE,
            currency=Currency.USD,
            name="Credit Line Test",
            credit_limit=Money(Decimal('2000.00'), Currency.USD)
        )
        
        # Initially, full credit should be available
        available_credit = self.account_manager.get_credit_available(account.id)
        assert available_credit == Money(Decimal('2000.00'), Currency.USD)
        
        # Create a charge (increases liability balance)
        lines = [
            JournalEntryLine(
                account_id="MERCHANT001",
                description="Purchase",
                debit_amount=Money(Decimal('500.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id=account.id,
                description="Credit line charge",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('500.00'), Currency.USD)
            )
        ]
        
        entry = self.ledger.create_journal_entry("CRED001", "Credit purchase", lines)
        self.ledger.post_journal_entry(entry.id)
        
        # Available credit should be reduced
        available_credit = self.account_manager.get_credit_available(account.id)
        assert available_credit == Money(Decimal('1500.00'), Currency.USD)  # 2000 - 500
        
        # Book balance should show negative (customer owes money)
        book_balance = self.account_manager.get_book_balance(account.id)
        assert book_balance == Money(Decimal('-500.00'), Currency.USD)
        
        # Place a hold on credit line
        hold = self.account_manager.place_hold(
            account_id=account.id,
            amount=Money(Decimal('300.00'), Currency.USD),
            reason="Authorization hold"
        )
        
        # Available credit should be further reduced
        available_credit = self.account_manager.get_credit_available(account.id)
        assert available_credit == Money(Decimal('1200.00'), Currency.USD)  # 2000 - 500 - 300
    
    def test_credit_available_non_credit_account(self):
        """Test that get_credit_available fails for non-credit accounts"""
        account = self.account_manager.create_account(
            customer_id="CUST013",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            name="Not Credit Line"
        )
        
        with pytest.raises(ValueError, match="Account is not a credit product"):
            self.account_manager.get_credit_available(account.id)


if __name__ == "__main__":
    pytest.main([__file__])