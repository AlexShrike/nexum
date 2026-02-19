"""
Double-Entry Ledger Engine

Core bookkeeping engine that ensures every transaction creates balanced
journal entries (debits = credits). Journal entries are immutable once
posted and balances are derived from entries for correctness.
"""

from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import uuid

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType


class JournalEntryState(Enum):
    """States of a journal entry"""
    PENDING = "pending"    # Created but not yet posted
    POSTED = "posted"      # Finalized and immutable
    REVERSED = "reversed"  # Reversed by a subsequent entry


class AccountType(Enum):
    """Standard accounting account types"""
    ASSET = "asset"           # Debit normal balance
    LIABILITY = "liability"   # Credit normal balance
    EQUITY = "equity"        # Credit normal balance
    REVENUE = "revenue"      # Credit normal balance
    EXPENSE = "expense"      # Debit normal balance


@dataclass
class JournalEntryLine:
    """
    Individual line item in a journal entry
    Each line affects one account with either a debit or credit
    """
    account_id: str
    description: str
    debit_amount: Money
    credit_amount: Money
    
    def __post_init__(self):
        """Validate that exactly one of debit or credit is non-zero"""
        debit_zero = self.debit_amount.is_zero()
        credit_zero = self.credit_amount.is_zero()
        
        if debit_zero and credit_zero:
            raise ValueError("Journal entry line must have either debit or credit amount")
        
        if not debit_zero and not credit_zero:
            raise ValueError("Journal entry line cannot have both debit and credit amounts")
        
        # Ensure both amounts use same currency
        if self.debit_amount.currency != self.credit_amount.currency:
            raise ValueError("Debit and credit amounts must use same currency")
    
    @property
    def currency(self) -> Currency:
        """Get the currency for this line"""
        return self.debit_amount.currency
    
    @property
    def amount(self) -> Money:
        """Get the non-zero amount (debit or credit)"""
        if not self.debit_amount.is_zero():
            return self.debit_amount
        return self.credit_amount
    
    @property
    def is_debit(self) -> bool:
        """Check if this is a debit entry"""
        return not self.debit_amount.is_zero()
    
    @property
    def is_credit(self) -> bool:
        """Check if this is a credit entry"""
        return not self.credit_amount.is_zero()


@dataclass
class JournalEntry(StorageRecord):
    """
    Double-entry journal entry with multiple lines that must balance
    Immutable once posted to ensure audit trail integrity
    """
    reference: str  # External reference (transaction ID, etc.)
    description: str
    lines: List[JournalEntryLine]
    state: JournalEntryState
    posted_at: Optional[datetime] = None
    reversed_by: Optional[str] = None  # ID of reversing journal entry
    reverses: Optional[str] = None     # ID of original entry being reversed
    
    def __post_init__(self):
        self.validate_balance()
    
    def validate_balance(self) -> None:
        """
        Validate that total debits equal total credits for each currency
        This is the fundamental rule of double-entry bookkeeping
        """
        if not self.lines:
            raise ValueError("Journal entry must have at least one line")
        
        # Group by currency and sum debits/credits
        currency_totals: Dict[Currency, Dict[str, Money]] = {}
        
        for line in self.lines:
            currency = line.currency
            if currency not in currency_totals:
                zero = Money(Decimal('0'), currency)
                currency_totals[currency] = {'debits': zero, 'credits': zero}
            
            if line.is_debit:
                currency_totals[currency]['debits'] = currency_totals[currency]['debits'] + line.debit_amount
            else:
                currency_totals[currency]['credits'] = currency_totals[currency]['credits'] + line.credit_amount
        
        # Verify balance for each currency
        for currency, totals in currency_totals.items():
            if totals['debits'] != totals['credits']:
                raise ValueError(f"Journal entry not balanced for {currency.code}: "
                               f"debits={totals['debits'].to_string()}, "
                               f"credits={totals['credits'].to_string()}")
    
    def get_affected_accounts(self) -> Set[str]:
        """Get set of account IDs affected by this entry"""
        return {line.account_id for line in self.lines}
    
    def get_total_amount(self, currency: Currency) -> Money:
        """Get total amount (debit side) for a specific currency"""
        zero = Money(Decimal('0'), currency)
        total = zero
        
        for line in self.lines:
            if line.currency == currency and line.is_debit:
                total = total + line.debit_amount
        
        return total
    
    def get_currencies(self) -> Set[Currency]:
        """Get all currencies used in this journal entry"""
        return {line.currency for line in self.lines}
    
    def can_be_modified(self) -> bool:
        """Check if this entry can be modified (only PENDING entries)"""
        return self.state == JournalEntryState.PENDING
    
    def post(self) -> None:
        """
        Post the journal entry (make it immutable)
        Can only be done once and only for PENDING entries
        """
        if self.state != JournalEntryState.PENDING:
            raise ValueError(f"Cannot post journal entry in {self.state.value} state")
        
        self.state = JournalEntryState.POSTED
        self.posted_at = datetime.now(timezone.utc)
        self.updated_at = self.posted_at
    
    def reverse(self, reversal_entry_id: str) -> None:
        """
        Mark this entry as reversed by another entry
        Can only be done for POSTED entries
        """
        if self.state != JournalEntryState.POSTED:
            raise ValueError(f"Cannot reverse journal entry in {self.state.value} state")
        
        self.state = JournalEntryState.REVERSED
        self.reversed_by = reversal_entry_id
        self.updated_at = datetime.now(timezone.utc)


class GeneralLedger:
    """
    General ledger that manages journal entries and calculates account balances
    Balances are derived from journal entries, never stored separately
    """
    
    def __init__(self, storage: StorageInterface, audit_trail: AuditTrail):
        self.storage = storage
        self.audit_trail = audit_trail
        self.table_name = "journal_entries"
    
    def create_journal_entry(
        self,
        reference: str,
        description: str,
        lines: List[JournalEntryLine]
    ) -> JournalEntry:
        """
        Create a new journal entry in PENDING state
        
        Args:
            reference: External reference (transaction ID, etc.)
            description: Human-readable description
            lines: List of journal entry lines that must balance
            
        Returns:
            Created JournalEntry in PENDING state
            
        Raises:
            ValueError: If lines don't balance
        """
        now = datetime.now(timezone.utc)
        entry_id = str(uuid.uuid4())
        
        entry = JournalEntry(
            id=entry_id,
            created_at=now,
            updated_at=now,
            reference=reference,
            description=description,
            lines=lines,
            state=JournalEntryState.PENDING
        )
        
        # Save to storage
        self._save_entry(entry)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.JOURNAL_ENTRY_CREATED,
            entity_type="journal_entry",
            entity_id=entry.id,
            metadata={
                "reference": reference,
                "description": description,
                "line_count": len(lines),
                "accounts": list(entry.get_affected_accounts()),
                "currencies": [c.code for c in entry.get_currencies()]
            }
        )
        
        return entry
    
    def post_journal_entry(self, entry_id: str) -> JournalEntry:
        """
        Post a journal entry (make it immutable)
        
        Args:
            entry_id: ID of the journal entry to post
            
        Returns:
            Posted JournalEntry
            
        Raises:
            ValueError: If entry doesn't exist or cannot be posted
        """
        entry = self._load_entry(entry_id)
        if not entry:
            raise ValueError(f"Journal entry {entry_id} not found")
        
        # Use atomic transaction to ensure all journal lines are posted together
        with self.storage.atomic():
            entry.post()
            self._save_entry(entry)
            
            # Log audit event
            self.audit_trail.log_event(
                event_type=AuditEventType.JOURNAL_ENTRY_POSTED,
                entity_type="journal_entry",
                entity_id=entry.id,
                metadata={
                    "reference": entry.reference,
                    "posted_at": entry.posted_at.isoformat()
                }
            )
        
        return entry
    
    def reverse_journal_entry(
        self,
        entry_id: str,
        reversal_reason: str
    ) -> JournalEntry:
        """
        Reverse a posted journal entry by creating counter-entries
        
        Args:
            entry_id: ID of the journal entry to reverse
            reversal_reason: Reason for the reversal
            
        Returns:
            New reversing JournalEntry
            
        Raises:
            ValueError: If entry doesn't exist or cannot be reversed
        """
        original_entry = self._load_entry(entry_id)
        if not original_entry:
            raise ValueError(f"Journal entry {entry_id} not found")
        
        if original_entry.state != JournalEntryState.POSTED:
            raise ValueError(f"Can only reverse POSTED journal entries")
        
        # Create reversing lines (flip debits and credits)
        reversing_lines = []
        for line in original_entry.lines:
            if line.is_debit:
                # Original was debit, reversal is credit
                reversing_line = JournalEntryLine(
                    account_id=line.account_id,
                    description=f"REVERSAL: {line.description}",
                    debit_amount=Money(Decimal('0'), line.currency),
                    credit_amount=line.debit_amount
                )
            else:
                # Original was credit, reversal is debit
                reversing_line = JournalEntryLine(
                    account_id=line.account_id,
                    description=f"REVERSAL: {line.description}",
                    debit_amount=line.credit_amount,
                    credit_amount=Money(Decimal('0'), line.currency)
                )
            reversing_lines.append(reversing_line)
        
        # Create reversing entry
        reversing_entry = self.create_journal_entry(
            reference=f"REV-{original_entry.reference}",
            description=f"REVERSAL: {reversal_reason}",
            lines=reversing_lines
        )
        
        # Mark as reversal
        reversing_entry.reverses = entry_id
        self._save_entry(reversing_entry)
        
        # Post the reversing entry
        posted_reversing_entry = self.post_journal_entry(reversing_entry.id)
        
        # Mark original as reversed
        original_entry.reverse(posted_reversing_entry.id)
        self._save_entry(original_entry)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.JOURNAL_ENTRY_REVERSED,
            entity_type="journal_entry",
            entity_id=original_entry.id,
            metadata={
                "original_reference": original_entry.reference,
                "reversing_entry_id": posted_reversing_entry.id,
                "reversal_reason": reversal_reason
            }
        )
        
        return posted_reversing_entry
    
    def get_journal_entry(self, entry_id: str) -> Optional[JournalEntry]:
        """Get a journal entry by ID"""
        return self._load_entry(entry_id)
    
    def get_entries_for_account(
        self,
        account_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        state_filter: Optional[JournalEntryState] = None
    ) -> List[JournalEntry]:
        """
        Get all journal entries affecting a specific account
        
        Args:
            account_id: Account to get entries for
            start_date: Optional start date filter
            end_date: Optional end date filter
            state_filter: Optional state filter
            
        Returns:
            List of JournalEntry objects affecting the account
        """
        all_entries = self.storage.load_all(self.table_name)
        entries = [self._entry_from_dict(data) for data in all_entries]
        
        # Filter by account
        filtered_entries = []
        for entry in entries:
            if account_id in entry.get_affected_accounts():
                filtered_entries.append(entry)
        
        # Apply additional filters
        if start_date:
            filtered_entries = [e for e in filtered_entries 
                              if e.created_at >= start_date]
        
        if end_date:
            filtered_entries = [e for e in filtered_entries 
                              if e.created_at <= end_date]
        
        if state_filter:
            filtered_entries = [e for e in filtered_entries 
                              if e.state == state_filter]
        
        # Sort by creation time
        filtered_entries.sort(key=lambda x: x.created_at)
        return filtered_entries
    
    def calculate_account_balance(
        self,
        account_id: str,
        account_type: AccountType,
        currency: Currency,
        as_of_date: Optional[datetime] = None
    ) -> Money:
        """
        Calculate account balance from journal entries
        
        This is the source of truth for account balances - never store
        balances separately as they can become inconsistent.
        
        Args:
            account_id: Account to calculate balance for
            account_type: Type of account (affects debit/credit normal balance)
            currency: Currency for the balance
            as_of_date: Calculate balance as of this date (inclusive)
            
        Returns:
            Current balance as Money object
        """
        entries = self.get_entries_for_account(
            account_id=account_id,
            end_date=as_of_date,
            state_filter=JournalEntryState.POSTED  # Only posted entries count
        )
        
        zero_balance = Money(Decimal('0'), currency)
        running_balance = zero_balance
        
        for entry in entries:
            for line in entry.lines:
                if line.account_id == account_id and line.currency == currency:
                    if line.is_debit:
                        running_balance = running_balance + line.debit_amount
                    else:
                        running_balance = running_balance - line.credit_amount
        
        # Adjust for account type normal balance
        # Assets and Expenses have debit normal balance
        # Liabilities, Equity, and Revenue have credit normal balance
        if account_type in [AccountType.LIABILITY, AccountType.EQUITY, AccountType.REVENUE]:
            running_balance = -running_balance
        
        return running_balance
    
    def get_trial_balance(
        self,
        account_types_and_ids: Dict[str, AccountType],
        currency: Currency,
        as_of_date: Optional[datetime] = None
    ) -> Dict[str, Money]:
        """
        Generate trial balance for given accounts
        
        Args:
            account_types_and_ids: Map of account_id -> AccountType
            currency: Currency for balances
            as_of_date: Date for trial balance
            
        Returns:
            Dictionary of account_id -> balance
        """
        balances = {}
        
        for account_id, account_type in account_types_and_ids.items():
            balance = self.calculate_account_balance(
                account_id=account_id,
                account_type=account_type,
                currency=currency,
                as_of_date=as_of_date
            )
            balances[account_id] = balance
        
        return balances
    
    def _save_entry(self, entry: JournalEntry) -> None:
        """Save journal entry to storage"""
        entry_dict = self._entry_to_dict(entry)
        self.storage.save(self.table_name, entry.id, entry_dict)
    
    def _load_entry(self, entry_id: str) -> Optional[JournalEntry]:
        """Load journal entry from storage"""
        entry_dict = self.storage.load(self.table_name, entry_id)
        if entry_dict:
            return self._entry_from_dict(entry_dict)
        return None
    
    def _entry_to_dict(self, entry: JournalEntry) -> Dict:
        """Convert JournalEntry to dictionary for storage"""
        result = entry.to_dict()
        
        # Convert lines to serializable format
        lines_data = []
        for line in entry.lines:
            line_data = {
                'account_id': line.account_id,
                'description': line.description,
                'debit_amount': str(line.debit_amount.amount),
                'debit_currency': line.debit_amount.currency.code,
                'credit_amount': str(line.credit_amount.amount),
                'credit_currency': line.credit_amount.currency.code
            }
            lines_data.append(line_data)
        
        result['lines'] = lines_data
        result['state'] = entry.state.value
        
        if entry.posted_at:
            result['posted_at'] = entry.posted_at.isoformat()
        
        return result
    
    def _entry_from_dict(self, data: Dict) -> JournalEntry:
        """Convert dictionary to JournalEntry"""
        # Convert lines back to objects
        lines = []
        for line_data in data['lines']:
            debit_currency = Currency[line_data['debit_currency']]
            credit_currency = Currency[line_data['credit_currency']]
            
            line = JournalEntryLine(
                account_id=line_data['account_id'],
                description=line_data['description'],
                debit_amount=Money(Decimal(line_data['debit_amount']), debit_currency),
                credit_amount=Money(Decimal(line_data['credit_amount']), credit_currency)
            )
            lines.append(line)
        
        # Convert timestamps
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        posted_at = None
        if data.get('posted_at'):
            posted_at = datetime.fromisoformat(data['posted_at'])
        
        return JournalEntry(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            reference=data['reference'],
            description=data['description'],
            lines=lines,
            state=JournalEntryState(data['state']),
            posted_at=posted_at,
            reversed_by=data.get('reversed_by'),
            reverses=data.get('reverses')
        )