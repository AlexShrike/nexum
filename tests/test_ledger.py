"""
Test suite for ledger module

Tests double-entry bookkeeping engine, journal entries, and balance calculations.
CRITICAL: Validates that debits always equal credits and balances are correct.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.ledger import (
    GeneralLedger, JournalEntry, JournalEntryLine, 
    JournalEntryState, AccountType
)


class TestJournalEntryLine:
    """Test individual journal entry lines"""
    
    def test_valid_debit_line(self):
        """Test creation of valid debit line"""
        line = JournalEntryLine(
            account_id="ACC001",
            description="Test debit",
            debit_amount=Money(Decimal('100.00'), Currency.USD),
            credit_amount=Money(Decimal('0.00'), Currency.USD)
        )
        
        assert line.account_id == "ACC001"
        assert line.debit_amount == Money(Decimal('100.00'), Currency.USD)
        assert line.credit_amount == Money(Decimal('0.00'), Currency.USD)
        assert line.is_debit
        assert not line.is_credit
        assert line.amount == Money(Decimal('100.00'), Currency.USD)
        assert line.currency == Currency.USD
    
    def test_valid_credit_line(self):
        """Test creation of valid credit line"""
        line = JournalEntryLine(
            account_id="ACC002",
            description="Test credit",
            debit_amount=Money(Decimal('0.00'), Currency.USD),
            credit_amount=Money(Decimal('50.00'), Currency.USD)
        )
        
        assert line.account_id == "ACC002"
        assert line.debit_amount == Money(Decimal('0.00'), Currency.USD)
        assert line.credit_amount == Money(Decimal('50.00'), Currency.USD)
        assert not line.is_debit
        assert line.is_credit
        assert line.amount == Money(Decimal('50.00'), Currency.USD)
        assert line.currency == Currency.USD
    
    def test_invalid_zero_amounts(self):
        """Test that line with both amounts zero raises error"""
        with pytest.raises(ValueError, match="must have either debit or credit amount"):
            JournalEntryLine(
                account_id="ACC001",
                description="Invalid line",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            )
    
    def test_invalid_both_amounts(self):
        """Test that line with both amounts non-zero raises error"""
        with pytest.raises(ValueError, match="cannot have both debit and credit amounts"):
            JournalEntryLine(
                account_id="ACC001",
                description="Invalid line",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('50.00'), Currency.USD)
            )
    
    def test_currency_mismatch(self):
        """Test that mismatched currencies raise error"""
        with pytest.raises(ValueError, match="must use same currency"):
            JournalEntryLine(
                account_id="ACC001",
                description="Invalid line",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.EUR)
            )


class TestJournalEntry:
    """Test journal entry validation and operations"""
    
    def test_valid_balanced_entry(self):
        """Test creation of balanced journal entry"""
        lines = [
            JournalEntryLine(
                account_id="ACC001",
                description="Debit cash",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="ACC002", 
                description="Credit revenue",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('100.00'), Currency.USD)
            )
        ]
        
        entry = JournalEntry(
            id="JE001",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            reference="TEST001",
            description="Test balanced entry",
            lines=lines,
            state=JournalEntryState.PENDING
        )
        
        assert len(entry.lines) == 2
        assert entry.state == JournalEntryState.PENDING
        assert entry.get_affected_accounts() == {"ACC001", "ACC002"}
        assert entry.get_currencies() == {Currency.USD}
        assert entry.get_total_amount(Currency.USD) == Money(Decimal('100.00'), Currency.USD)
    
    def test_unbalanced_entry_single_currency(self):
        """Test that unbalanced entry raises error"""
        lines = [
            JournalEntryLine(
                account_id="ACC001",
                description="Debit cash",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="ACC002",
                description="Credit revenue - wrong amount",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('75.00'), Currency.USD)  # Unbalanced!
            )
        ]
        
        with pytest.raises(ValueError, match="Journal entry not balanced"):
            JournalEntry(
                id="JE002",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                reference="TEST002",
                description="Test unbalanced entry",
                lines=lines,
                state=JournalEntryState.PENDING
            )
    
    def test_multi_currency_balanced_entry(self):
        """Test balanced entry with multiple currencies"""
        lines = [
            JournalEntryLine(
                account_id="ACC001",
                description="Debit USD cash",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="ACC002",
                description="Credit USD revenue",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('100.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="ACC003",
                description="Debit EUR cash",
                debit_amount=Money(Decimal('50.00'), Currency.EUR),
                credit_amount=Money(Decimal('0.00'), Currency.EUR)
            ),
            JournalEntryLine(
                account_id="ACC004",
                description="Credit EUR revenue", 
                debit_amount=Money(Decimal('0.00'), Currency.EUR),
                credit_amount=Money(Decimal('50.00'), Currency.EUR)
            )
        ]
        
        entry = JournalEntry(
            id="JE003",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            reference="TEST003",
            description="Multi-currency balanced entry",
            lines=lines,
            state=JournalEntryState.PENDING
        )
        
        assert entry.get_currencies() == {Currency.USD, Currency.EUR}
        assert entry.get_total_amount(Currency.USD) == Money(Decimal('100.00'), Currency.USD)
        assert entry.get_total_amount(Currency.EUR) == Money(Decimal('50.00'), Currency.EUR)
    
    def test_multi_currency_unbalanced_entry(self):
        """Test that unbalanced multi-currency entry raises error"""
        lines = [
            JournalEntryLine(
                account_id="ACC001",
                description="Debit USD cash",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="ACC002",
                description="Credit EUR revenue - wrong currency!",
                debit_amount=Money(Decimal('0.00'), Currency.EUR),
                credit_amount=Money(Decimal('100.00'), Currency.EUR)  # Different currency!
            )
        ]
        
        with pytest.raises(ValueError, match="Journal entry not balanced"):
            JournalEntry(
                id="JE004",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                reference="TEST004",
                description="Unbalanced multi-currency entry",
                lines=lines,
                state=JournalEntryState.PENDING
            )
    
    def test_empty_lines_error(self):
        """Test that entry with no lines raises error"""
        with pytest.raises(ValueError, match="must have at least one line"):
            JournalEntry(
                id="JE005",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                reference="TEST005",
                description="Empty entry",
                lines=[],
                state=JournalEntryState.PENDING
            )
    
    def test_entry_state_management(self):
        """Test journal entry state transitions"""
        lines = [
            JournalEntryLine(
                account_id="ACC001",
                description="Debit",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="ACC002",
                description="Credit",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('100.00'), Currency.USD)
            )
        ]
        
        entry = JournalEntry(
            id="JE006",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            reference="TEST006",
            description="State test entry",
            lines=lines,
            state=JournalEntryState.PENDING
        )
        
        # Initially PENDING and can be modified
        assert entry.state == JournalEntryState.PENDING
        assert entry.can_be_modified()
        
        # Post the entry
        entry.post()
        assert entry.state == JournalEntryState.POSTED
        assert not entry.can_be_modified()
        assert entry.posted_at is not None
        
        # Try to post again - should fail
        with pytest.raises(ValueError, match="Cannot post journal entry in posted state"):
            entry.post()
        
        # Try to reverse
        entry.reverse("REV001")
        assert entry.state == JournalEntryState.REVERSED
        assert entry.reversed_by == "REV001"
        
        # Try to reverse again - should fail
        with pytest.raises(ValueError, match="Cannot reverse journal entry in reversed state"):
            entry.reverse("REV002")


class TestGeneralLedger:
    """Test general ledger operations"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.storage = InMemoryStorage()
        self.audit_trail = AuditTrail(self.storage)
        self.ledger = GeneralLedger(self.storage, self.audit_trail)
    
    def test_create_journal_entry(self):
        """Test creating a journal entry through the ledger"""
        lines = [
            JournalEntryLine(
                account_id="CASH001",
                description="Cash deposit",
                debit_amount=Money(Decimal('1000.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="REVENUE001",
                description="Deposit revenue",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('1000.00'), Currency.USD)
            )
        ]
        
        entry = self.ledger.create_journal_entry(
            reference="DEP001",
            description="Customer deposit",
            lines=lines
        )
        
        assert entry.reference == "DEP001"
        assert entry.state == JournalEntryState.PENDING
        assert len(entry.lines) == 2
        
        # Verify it's saved in storage
        retrieved = self.ledger.get_journal_entry(entry.id)
        assert retrieved is not None
        assert retrieved.reference == "DEP001"
    
    def test_post_journal_entry(self):
        """Test posting a journal entry"""
        lines = [
            JournalEntryLine(
                account_id="CASH001", 
                description="Cash withdrawal",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('500.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="CUSTOMER001",
                description="Customer account debit",
                debit_amount=Money(Decimal('500.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            )
        ]
        
        # Create entry
        entry = self.ledger.create_journal_entry(
            reference="WITH001",
            description="Customer withdrawal",
            lines=lines
        )
        
        assert entry.state == JournalEntryState.PENDING
        
        # Post entry
        posted_entry = self.ledger.post_journal_entry(entry.id)
        
        assert posted_entry.state == JournalEntryState.POSTED
        assert posted_entry.posted_at is not None
        
        # Try to post again - should fail
        with pytest.raises(ValueError, match="Cannot post journal entry in posted state"):
            self.ledger.post_journal_entry(entry.id)
    
    def test_reverse_journal_entry(self):
        """Test reversing a posted journal entry"""
        lines = [
            JournalEntryLine(
                account_id="CASH001",
                description="Cash deposit",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="CUSTOMER001",
                description="Customer credit",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('100.00'), Currency.USD)
            )
        ]
        
        # Create and post original entry
        original = self.ledger.create_journal_entry(
            reference="ORIG001",
            description="Original transaction",
            lines=lines
        )
        posted_original = self.ledger.post_journal_entry(original.id)
        
        # Reverse the entry
        reversal = self.ledger.reverse_journal_entry(
            posted_original.id,
            "Customer requested reversal"
        )
        
        # Check reversal entry
        assert reversal.state == JournalEntryState.POSTED
        assert reversal.reference == "REV-ORIG001"
        assert reversal.reverses == posted_original.id
        assert len(reversal.lines) == 2
        
        # Check reversal lines are opposite of original
        assert reversal.lines[0].account_id == "CASH001"
        assert reversal.lines[0].is_credit  # Original was debit
        assert reversal.lines[0].credit_amount == Money(Decimal('100.00'), Currency.USD)
        
        assert reversal.lines[1].account_id == "CUSTOMER001"
        assert reversal.lines[1].is_debit  # Original was credit
        assert reversal.lines[1].debit_amount == Money(Decimal('100.00'), Currency.USD)
        
        # Check original is marked as reversed
        updated_original = self.ledger.get_journal_entry(posted_original.id)
        assert updated_original.state == JournalEntryState.REVERSED
        assert updated_original.reversed_by == reversal.id
    
    def test_calculate_account_balance_asset_account(self):
        """Test balance calculation for asset account (debit normal)"""
        # Create multiple entries affecting the same account
        
        # Entry 1: Debit $1000
        lines1 = [
            JournalEntryLine(
                account_id="CASH001",
                description="Initial deposit",
                debit_amount=Money(Decimal('1000.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="REVENUE001",
                description="Revenue recognition",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('1000.00'), Currency.USD)
            )
        ]
        
        entry1 = self.ledger.create_journal_entry("ENT001", "Entry 1", lines1)
        self.ledger.post_journal_entry(entry1.id)
        
        # Entry 2: Credit $300
        lines2 = [
            JournalEntryLine(
                account_id="CASH001",
                description="Withdrawal", 
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('300.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="CUSTOMER001",
                description="Customer account",
                debit_amount=Money(Decimal('300.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            )
        ]
        
        entry2 = self.ledger.create_journal_entry("ENT002", "Entry 2", lines2)
        self.ledger.post_journal_entry(entry2.id)
        
        # Entry 3: Debit $200
        lines3 = [
            JournalEntryLine(
                account_id="CASH001",
                description="Another deposit",
                debit_amount=Money(Decimal('200.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="REVENUE001",
                description="More revenue",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('200.00'), Currency.USD)
            )
        ]
        
        entry3 = self.ledger.create_journal_entry("ENT003", "Entry 3", lines3)
        self.ledger.post_journal_entry(entry3.id)
        
        # Calculate balance for CASH001 (asset account)
        # Total debits: $1000 + $200 = $1200
        # Total credits: $300
        # Asset balance = Debits - Credits = $1200 - $300 = $900
        balance = self.ledger.calculate_account_balance(
            "CASH001",
            AccountType.ASSET,
            Currency.USD
        )
        
        assert balance == Money(Decimal('900.00'), Currency.USD)
    
    def test_calculate_account_balance_liability_account(self):
        """Test balance calculation for liability account (credit normal)"""
        # Entry 1: Credit $500 (customer deposit)
        lines1 = [
            JournalEntryLine(
                account_id="CASH001",
                description="Cash received",
                debit_amount=Money(Decimal('500.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="CUSTOMER_DEPOSITS",
                description="Customer deposit liability",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('500.00'), Currency.USD)
            )
        ]
        
        entry1 = self.ledger.create_journal_entry("LIA001", "Customer deposit", lines1)
        self.ledger.post_journal_entry(entry1.id)
        
        # Entry 2: Debit $100 (partial withdrawal)
        lines2 = [
            JournalEntryLine(
                account_id="CUSTOMER_DEPOSITS",
                description="Withdrawal reduces liability",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="CASH001",
                description="Cash paid out",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('100.00'), Currency.USD)
            )
        ]
        
        entry2 = self.ledger.create_journal_entry("LIA002", "Partial withdrawal", lines2)
        self.ledger.post_journal_entry(entry2.id)
        
        # Calculate balance for CUSTOMER_DEPOSITS (liability account)
        # Total credits: $500
        # Total debits: $100  
        # Liability balance = Credits - Debits = $500 - $100 = $400
        balance = self.ledger.calculate_account_balance(
            "CUSTOMER_DEPOSITS",
            AccountType.LIABILITY,
            Currency.USD
        )
        
        assert balance == Money(Decimal('400.00'), Currency.USD)
    
    def test_get_entries_for_account(self):
        """Test getting all journal entries for a specific account"""
        # Create entries affecting CASH001
        lines1 = [
            JournalEntryLine(
                account_id="CASH001",
                description="Deposit",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="REV001",
                description="Revenue",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('100.00'), Currency.USD)
            )
        ]
        
        lines2 = [
            JournalEntryLine(
                account_id="CASH001",
                description="Withdrawal",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('50.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="CUST001",
                description="Customer account",
                debit_amount=Money(Decimal('50.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            )
        ]
        
        # Entry that doesn't affect CASH001
        lines3 = [
            JournalEntryLine(
                account_id="OTHER001",
                description="Other debit",
                debit_amount=Money(Decimal('25.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="OTHER002",
                description="Other credit",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('25.00'), Currency.USD)
            )
        ]
        
        entry1 = self.ledger.create_journal_entry("GET001", "Get test 1", lines1)
        entry2 = self.ledger.create_journal_entry("GET002", "Get test 2", lines2)
        entry3 = self.ledger.create_journal_entry("GET003", "Get test 3", lines3)
        
        # Post all entries
        self.ledger.post_journal_entry(entry1.id)
        self.ledger.post_journal_entry(entry2.id)
        self.ledger.post_journal_entry(entry3.id)
        
        # Get entries for CASH001
        cash_entries = self.ledger.get_entries_for_account("CASH001")
        
        # Should return entry1 and entry2, but not entry3
        assert len(cash_entries) == 2
        entry_ids = {entry.id for entry in cash_entries}
        assert entry1.id in entry_ids
        assert entry2.id in entry_ids
        assert entry3.id not in entry_ids
        
        # Entries should be sorted by creation time
        assert cash_entries[0].created_at <= cash_entries[1].created_at
    
    def test_get_entries_for_account_with_filters(self):
        """Test getting entries with date and state filters"""
        import time
        
        lines = [
            JournalEntryLine(
                account_id="TEST001",
                description="Test entry",
                debit_amount=Money(Decimal('100.00'), Currency.USD),
                credit_amount=Money(Decimal('0.00'), Currency.USD)
            ),
            JournalEntryLine(
                account_id="TEST002",
                description="Test entry",
                debit_amount=Money(Decimal('0.00'), Currency.USD),
                credit_amount=Money(Decimal('100.00'), Currency.USD)
            )
        ]
        
        # Create entry and post it
        entry1 = self.ledger.create_journal_entry("FILT001", "Filter test 1", lines)
        posted_entry = self.ledger.post_journal_entry(entry1.id)
        
        time.sleep(0.01)  # Small delay
        
        # Create another entry but don't post it
        entry2 = self.ledger.create_journal_entry("FILT002", "Filter test 2", lines)
        
        # Get entries with POSTED state filter
        posted_entries = self.ledger.get_entries_for_account(
            "TEST001", 
            state_filter=JournalEntryState.POSTED
        )
        assert len(posted_entries) == 1
        assert posted_entries[0].id == posted_entry.id
        
        # Get entries with PENDING state filter
        pending_entries = self.ledger.get_entries_for_account(
            "TEST001",
            state_filter=JournalEntryState.PENDING
        )
        assert len(pending_entries) == 1
        assert pending_entries[0].id == entry2.id
        
        # Test date filter
        start_date = datetime.now(timezone.utc)
        all_entries = self.ledger.get_entries_for_account(
            "TEST001",
            start_date=start_date
        )
        # No entries should be after current time
        assert len(all_entries) == 0
    
    def test_trial_balance(self):
        """Test generating trial balance"""
        # Create a set of balanced transactions
        
        # Transaction 1: Customer deposits $1000
        lines1 = [
            JournalEntryLine("CASH", "Cash received", 
                           Money(Decimal('1000'), Currency.USD), Money(Decimal('0'), Currency.USD)),
            JournalEntryLine("CUSTOMER_DEPOSITS", "Customer deposit",
                           Money(Decimal('0'), Currency.USD), Money(Decimal('1000'), Currency.USD))
        ]
        
        # Transaction 2: Loan disbursement of $500
        lines2 = [
            JournalEntryLine("CUSTOMER_CHECKING", "Loan disbursement",
                           Money(Decimal('500'), Currency.USD), Money(Decimal('0'), Currency.USD)),
            JournalEntryLine("LOANS_PAYABLE", "Loan liability",
                           Money(Decimal('0'), Currency.USD), Money(Decimal('500'), Currency.USD))
        ]
        
        # Transaction 3: Interest income $50
        lines3 = [
            JournalEntryLine("CASH", "Interest collected",
                           Money(Decimal('50'), Currency.USD), Money(Decimal('0'), Currency.USD)),
            JournalEntryLine("INTEREST_INCOME", "Interest earned",
                           Money(Decimal('0'), Currency.USD), Money(Decimal('50'), Currency.USD))
        ]
        
        # Post all entries
        for i, lines in enumerate([lines1, lines2, lines3], 1):
            entry = self.ledger.create_journal_entry(f"TB00{i}", f"Trial balance test {i}", lines)
            self.ledger.post_journal_entry(entry.id)
        
        # Define account types for trial balance
        account_types = {
            "CASH": AccountType.ASSET,
            "CUSTOMER_CHECKING": AccountType.ASSET,
            "CUSTOMER_DEPOSITS": AccountType.LIABILITY,
            "LOANS_PAYABLE": AccountType.LIABILITY,
            "INTEREST_INCOME": AccountType.REVENUE
        }
        
        # Generate trial balance
        trial_balance = self.ledger.get_trial_balance(account_types, Currency.USD)
        
        # Verify balances
        assert trial_balance["CASH"] == Money(Decimal('1050'), Currency.USD)  # 1000 + 50
        assert trial_balance["CUSTOMER_CHECKING"] == Money(Decimal('500'), Currency.USD)
        assert trial_balance["CUSTOMER_DEPOSITS"] == Money(Decimal('1000'), Currency.USD)
        assert trial_balance["LOANS_PAYABLE"] == Money(Decimal('500'), Currency.USD)
        assert trial_balance["INTEREST_INCOME"] == Money(Decimal('50'), Currency.USD)
        
        # Verify trial balance balances (Assets = Liabilities + Equity + Revenue)
        total_assets = trial_balance["CASH"] + trial_balance["CUSTOMER_CHECKING"]
        total_liabilities = trial_balance["CUSTOMER_DEPOSITS"] + trial_balance["LOANS_PAYABLE"]
        total_revenue = trial_balance["INTEREST_INCOME"]
        
        assert total_assets == total_liabilities + total_revenue  # Should balance
    
    def test_balance_calculation_with_pending_entries(self):
        """Test that pending entries don't affect balance calculations"""
        # Create and post an entry
        lines_posted = [
            JournalEntryLine("TEST_ACCOUNT", "Posted entry",
                           Money(Decimal('100'), Currency.USD), Money(Decimal('0'), Currency.USD)),
            JournalEntryLine("OTHER_ACCOUNT", "Posted entry",
                           Money(Decimal('0'), Currency.USD), Money(Decimal('100'), Currency.USD))
        ]
        
        entry_posted = self.ledger.create_journal_entry("POST001", "Posted entry", lines_posted)
        self.ledger.post_journal_entry(entry_posted.id)
        
        # Create but don't post an entry
        lines_pending = [
            JournalEntryLine("TEST_ACCOUNT", "Pending entry",
                           Money(Decimal('50'), Currency.USD), Money(Decimal('0'), Currency.USD)),
            JournalEntryLine("OTHER_ACCOUNT", "Pending entry", 
                           Money(Decimal('0'), Currency.USD), Money(Decimal('50'), Currency.USD))
        ]
        
        entry_pending = self.ledger.create_journal_entry("PEND001", "Pending entry", lines_pending)
        
        # Balance should only include posted entries
        balance = self.ledger.calculate_account_balance("TEST_ACCOUNT", AccountType.ASSET, Currency.USD)
        assert balance == Money(Decimal('100'), Currency.USD)  # Only the posted entry


if __name__ == "__main__":
    pytest.main([__file__])