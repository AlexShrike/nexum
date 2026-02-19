"""
Transaction Processing Module

Handles all types of banking transactions: deposits, withdrawals, transfers,
payments, fees, etc. All transactions create proper double-entry journal
entries and support idempotency, reversals, and state management.
"""

from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import hashlib

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType
from .ledger import GeneralLedger, JournalEntry, JournalEntryLine
from .accounts import ProductType
from .accounts import AccountManager, Account
from .customers import CustomerManager
from .compliance import ComplianceEngine, ComplianceAction
from .logging_config import get_logger, log_action

# Import events for Phase 2 observer pattern (optional)
try:
    from .events import EventDispatcher, DomainEvent, create_transaction_event
except ImportError:
    EventDispatcher = None
    DomainEvent = None
    create_transaction_event = None


class TransactionType(Enum):
    """Types of banking transactions"""
    DEPOSIT = "deposit"                    # Cash/check deposit
    WITHDRAWAL = "withdrawal"              # Cash withdrawal
    TRANSFER_INTERNAL = "transfer_internal"  # Transfer between internal accounts
    TRANSFER_EXTERNAL = "transfer_external"  # Transfer to/from external bank
    PAYMENT = "payment"                    # Bill payment or P2P payment
    FEE = "fee"                           # Service fee
    INTEREST_CREDIT = "interest_credit"    # Interest earned
    INTEREST_DEBIT = "interest_debit"     # Interest charged
    REVERSAL = "reversal"                 # Reversal of previous transaction
    ADJUSTMENT = "adjustment"             # Manual adjustment


class TransactionState(Enum):
    """States of a transaction"""
    PENDING = "pending"        # Created but not yet processed
    PROCESSING = "processing"  # Being processed
    COMPLETED = "completed"    # Successfully completed
    FAILED = "failed"         # Processing failed
    REVERSED = "reversed"     # Reversed by another transaction


class TransactionChannel(Enum):
    """Channels through which transactions can originate"""
    ATM = "atm"
    BRANCH = "branch"
    ONLINE = "online"
    MOBILE = "mobile"
    API = "api"
    SYSTEM = "system"  # System-generated (fees, interest, etc.)


@dataclass
class Transaction(StorageRecord):
    """
    Banking transaction with double-entry bookkeeping integration
    """
    transaction_type: TransactionType
    from_account_id: Optional[str]  # Source account (None for deposits from external)
    to_account_id: Optional[str]    # Destination account (None for withdrawals to external)
    amount: Money
    currency: Currency
    description: str
    reference: str                   # External reference number
    idempotency_key: str            # Prevents duplicate processing
    channel: TransactionChannel
    state: TransactionState = TransactionState.PENDING
    
    # Journal entry tracking
    journal_entry_id: Optional[str] = None
    reversal_transaction_id: Optional[str] = None
    original_transaction_id: Optional[str] = None  # If this is a reversal
    
    # Processing details
    processed_at: Optional[datetime] = None
    processing_node: Optional[str] = None
    error_message: Optional[str] = None
    
    # Compliance and audit
    compliance_checked: bool = False
    compliance_action: Optional[ComplianceAction] = None
    compliance_notes: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        
        # Validate that we have at least one account
        if not self.from_account_id and not self.to_account_id:
            raise ValueError("Transaction must have at least one account (from_account_id or to_account_id)")
        
        # Validate amount is positive
        if not self.amount.is_positive():
            raise ValueError("Transaction amount must be positive")
        
        # Ensure currency consistency
        if self.amount.currency != self.currency:
            raise ValueError("Transaction amount currency must match transaction currency")
    
    @property
    def is_completed(self) -> bool:
        """Check if transaction is completed"""
        return self.state == TransactionState.COMPLETED
    
    @property
    def is_pending(self) -> bool:
        """Check if transaction is pending"""
        return self.state == TransactionState.PENDING
    
    @property
    def is_failed(self) -> bool:
        """Check if transaction failed"""
        return self.state == TransactionState.FAILED
    
    @property
    def is_reversible(self) -> bool:
        """Check if transaction can be reversed"""
        return self.state == TransactionState.COMPLETED and not self.reversal_transaction_id
    
    @property
    def involves_external_account(self) -> bool:
        """Check if transaction involves an external account"""
        return (
            (self.transaction_type == TransactionType.DEPOSIT and not self.from_account_id) or
            (self.transaction_type == TransactionType.WITHDRAWAL and not self.to_account_id) or
            self.transaction_type == TransactionType.TRANSFER_EXTERNAL
        )


class TransactionProcessor:
    """
    Processes banking transactions with double-entry bookkeeping,
    compliance checks, and state management
    """
    
    def __init__(
        self,
        storage: StorageInterface,
        ledger: GeneralLedger,
        account_manager: AccountManager,
        customer_manager: CustomerManager,
        compliance_engine: ComplianceEngine,
        audit_trail: AuditTrail,
        event_dispatcher: Optional['EventDispatcher'] = None
    ):
        self.storage = storage
        self.ledger = ledger
        self.account_manager = account_manager
        self.customer_manager = customer_manager
        self.compliance_engine = compliance_engine
        self.audit_trail = audit_trail
        self.table_name = "transactions"
        self.logger = get_logger("nexum.transactions")
        
        # Event dispatcher for publishing domain events (Phase 2)
        self._event_dispatcher = event_dispatcher
        
        # System accounts for external transactions
        self._system_accounts = {
            "external_deposits": "EXT_DEP_001",  # External deposit source
            "external_withdrawals": "EXT_WITH_001",  # External withdrawal destination
            "fee_income": "FEE_INC_001",  # Fee income account
            "interest_expense": "INT_EXP_001",  # Interest expense account
            "interest_income": "INT_INC_001"  # Interest income account
        }
    
    def _publish_event(self, event_type, transaction: Transaction) -> None:
        """Publish a domain event if event dispatcher is available"""
        if self._event_dispatcher and create_transaction_event and event_type:
            try:
                event = create_transaction_event(event_type, transaction)
                self._event_dispatcher.publish(event)
            except Exception as e:
                self.logger.error(f"Error publishing event {event_type}: {e}")
    
    def create_transaction(
        self,
        transaction_type: TransactionType,
        amount: Money,
        description: str,
        channel: TransactionChannel,
        from_account_id: Optional[str] = None,
        to_account_id: Optional[str] = None,
        reference: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Transaction:
        """
        Create a new transaction
        
        Args:
            transaction_type: Type of transaction
            amount: Transaction amount
            description: Transaction description
            channel: Channel through which transaction originated
            from_account_id: Source account ID
            to_account_id: Destination account ID
            reference: External reference number
            idempotency_key: Key to prevent duplicate processing
            metadata: Additional transaction metadata
            
        Returns:
            Created Transaction object in PENDING state
        """
        now = datetime.now(timezone.utc)
        transaction_id = str(uuid.uuid4())
        
        # Generate reference if not provided
        if not reference:
            reference = f"{transaction_type.value.upper()}-{transaction_id[:8]}"
        
        # Generate idempotency key if not provided
        if not idempotency_key:
            key_data = f"{transaction_type.value}:{from_account_id}:{to_account_id}:{amount.amount}:{amount.currency.code}:{now.isoformat()}"
            idempotency_key = hashlib.sha256(key_data.encode()).hexdigest()[:16]
        
        # Check for duplicate idempotency key
        existing = self._find_by_idempotency_key(idempotency_key)
        if existing:
            return existing
        
        transaction = Transaction(
            id=transaction_id,
            created_at=now,
            updated_at=now,
            transaction_type=transaction_type,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount=amount,
            currency=amount.currency,
            description=description,
            reference=reference,
            idempotency_key=idempotency_key,
            channel=channel,
            metadata=metadata or {}
        )
        
        # Save transaction
        self._save_transaction(transaction)
        
        # Log transaction creation
        log_action(
            self.logger, "info", f"Transaction created: {transaction_type.value}",
            action="create_transaction", resource=f"transaction:{transaction.id}",
            extra={
                "transaction_id": transaction.id,
                "transaction_type": transaction_type.value,
                "amount": amount.to_string(),
                "from_account": from_account_id,
                "to_account": to_account_id,
                "reference": reference,
                "channel": channel.value,
                "idempotency_key": idempotency_key
            }
        )
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.TRANSACTION_CREATED,
            entity_type="transaction",
            entity_id=transaction.id,
            metadata={
                "transaction_type": transaction_type.value,
                "amount": amount.to_string(),
                "from_account": from_account_id,
                "to_account": to_account_id,
                "reference": reference,
                "channel": channel.value
            }
        )
        
        # Publish domain event (Phase 2)
        if DomainEvent:
            self._publish_event(DomainEvent.TRANSACTION_CREATED, transaction)
        
        return transaction
    
    def process_transaction(self, transaction_id: str) -> Transaction:
        """
        Process a pending transaction through completion
        
        Args:
            transaction_id: ID of transaction to process
            
        Returns:
            Processed Transaction object
            
        Raises:
            ValueError: If transaction not found or cannot be processed
        """
        transaction = self.get_transaction(transaction_id)
        if not transaction:
            raise ValueError(f"Transaction {transaction_id} not found")
        
        if not transaction.is_pending:
            raise ValueError(f"Transaction {transaction_id} is not in PENDING state")
        
        # Use atomic transaction to ensure all operations succeed or fail together
        with self.storage.atomic():
            try:
                # Update state to processing
                transaction.state = TransactionState.PROCESSING
                transaction.updated_at = datetime.now(timezone.utc)
                self._save_transaction(transaction)
                
                # Run compliance checks (skip for system transactions and reversals)
                if (not transaction.compliance_checked and 
                    transaction.channel != TransactionChannel.SYSTEM and
                    transaction.transaction_type != TransactionType.REVERSAL):
                    self._run_compliance_checks(transaction)
                elif transaction.channel == TransactionChannel.SYSTEM or transaction.transaction_type == TransactionType.REVERSAL:
                    # System transactions and reversals are automatically allowed
                    transaction.compliance_checked = True
                    transaction.compliance_action = ComplianceAction.ALLOW
                
                # If blocked by compliance, fail the transaction
                if transaction.compliance_action == ComplianceAction.BLOCK:
                    self._fail_transaction(transaction, "Blocked by compliance rules")
                    raise ValueError("Blocked by compliance rules")
                
                # Validate accounts
                self._validate_transaction_accounts(transaction)
                
                # Create journal entry
                journal_entry = self._create_journal_entry(transaction)
                
                # Post journal entry
                posted_entry = self.ledger.post_journal_entry(journal_entry.id)
                
                # Complete transaction
                transaction.journal_entry_id = posted_entry.id
                transaction.state = TransactionState.COMPLETED
                transaction.processed_at = datetime.now(timezone.utc)
                transaction.updated_at = transaction.processed_at
                
                self._save_transaction(transaction)
                
                # Log audit event
                self.audit_trail.log_event(
                    event_type=AuditEventType.TRANSACTION_POSTED,
                    entity_type="transaction",
                    entity_id=transaction.id,
                    metadata={
                        "journal_entry_id": journal_entry.id,
                        "processed_at": transaction.processed_at.isoformat()
                    }
                )
                
                # Publish domain event (Phase 2)
                if DomainEvent:
                    self._publish_event(DomainEvent.TRANSACTION_POSTED, transaction)
                
            except Exception as e:
                # Handle processing failure
                self._fail_transaction(transaction, str(e))
                raise
        
        return transaction
    
    def reverse_transaction(
        self,
        original_transaction_id: str,
        reason: str,
        channel: TransactionChannel = TransactionChannel.SYSTEM
    ) -> Transaction:
        """
        Reverse a completed transaction
        
        Args:
            original_transaction_id: ID of transaction to reverse
            reason: Reason for reversal
            channel: Channel for reversal transaction
            
        Returns:
            Reversal Transaction object
        """
        original_transaction = self.get_transaction(original_transaction_id)
        if not original_transaction:
            raise ValueError(f"Transaction {original_transaction_id} not found")
        
        if not original_transaction.is_reversible:
            raise ValueError(f"Transaction {original_transaction_id} cannot be reversed")
        
        # Create reversal transaction (swap from/to accounts and negate amount)
        reversal = self.create_transaction(
            transaction_type=TransactionType.REVERSAL,
            amount=original_transaction.amount,  # Same amount
            description=f"REVERSAL: {reason}",
            channel=channel,
            from_account_id=original_transaction.to_account_id,  # Swapped
            to_account_id=original_transaction.from_account_id,  # Swapped
            reference=f"REV-{original_transaction.reference}",
            metadata={
                "original_transaction_id": original_transaction_id,
                "reversal_reason": reason
            }
        )
        
        # Mark as reversal
        reversal.original_transaction_id = original_transaction_id
        self._save_transaction(reversal)
        
        # Process reversal
        processed_reversal = self.process_transaction(reversal.id)
        
        # Update original transaction
        original_transaction.state = TransactionState.REVERSED
        original_transaction.reversal_transaction_id = reversal.id
        original_transaction.updated_at = datetime.now(timezone.utc)
        self._save_transaction(original_transaction)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.TRANSACTION_REVERSED,
            entity_type="transaction",
            entity_id=original_transaction_id,
            metadata={
                "reversal_transaction_id": reversal.id,
                "reason": reason
            }
        )
        
        # Publish domain event (Phase 2)
        if DomainEvent:
            self._publish_event(DomainEvent.TRANSACTION_REVERSED, original_transaction)
        
        return processed_reversal
    
    def deposit(
        self,
        account_id: str,
        amount: Money,
        description: str,
        channel: TransactionChannel,
        reference: Optional[str] = None
    ) -> Transaction:
        """Convenience method for deposits"""
        return self.create_transaction(
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            description=description,
            channel=channel,
            to_account_id=account_id,  # Money goes TO the account
            reference=reference
        )
    
    def withdraw(
        self,
        account_id: str,
        amount: Money,
        description: str,
        channel: TransactionChannel,
        reference: Optional[str] = None
    ) -> Transaction:
        """Convenience method for withdrawals"""
        return self.create_transaction(
            transaction_type=TransactionType.WITHDRAWAL,
            amount=amount,
            description=description,
            channel=channel,
            from_account_id=account_id,  # Money comes FROM the account
            reference=reference
        )
    
    def transfer(
        self,
        from_account_id: str,
        to_account_id: str,
        amount: Money,
        description: str,
        channel: TransactionChannel,
        reference: Optional[str] = None
    ) -> Transaction:
        """Convenience method for internal transfers"""
        # Validate currency match for internal transfers
        from_account = self.account_manager.get_account(from_account_id)
        to_account = self.account_manager.get_account(to_account_id)
        if from_account and to_account and from_account.currency != to_account.currency:
            raise ValueError(
                f"Cannot transfer between accounts with different currencies: "
                f"{from_account.currency.value[0]} -> {to_account.currency.value[0]}. "
                f"Use currency conversion instead."
            )
        return self.create_transaction(
            transaction_type=TransactionType.TRANSFER_INTERNAL,
            amount=amount,
            description=description,
            channel=channel,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            reference=reference
        )
    
    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """Get transaction by ID"""
        transaction_dict = self.storage.load(self.table_name, transaction_id)
        if transaction_dict:
            return self._transaction_from_dict(transaction_dict)
        return None
    
    def get_account_transactions(
        self,
        account_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        transaction_types: Optional[List[TransactionType]] = None,
        limit: Optional[int] = None
    ) -> List[Transaction]:
        """
        Get transactions for an account with optional filters
        
        Args:
            account_id: Account ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            transaction_types: Optional transaction type filter
            limit: Optional limit on number of transactions
            
        Returns:
            List of Transaction objects
        """
        all_transactions = self.storage.load_all(self.table_name)
        transactions = [self._transaction_from_dict(data) for data in all_transactions]
        
        # Filter by account
        filtered_transactions = []
        for txn in transactions:
            if txn.from_account_id == account_id or txn.to_account_id == account_id:
                filtered_transactions.append(txn)
        
        # Apply additional filters
        if start_date:
            filtered_transactions = [t for t in filtered_transactions 
                                   if t.created_at >= start_date]
        
        if end_date:
            filtered_transactions = [t for t in filtered_transactions 
                                   if t.created_at <= end_date]
        
        if transaction_types:
            filtered_transactions = [t for t in filtered_transactions 
                                   if t.transaction_type in transaction_types]
        
        # Sort by creation time (most recent first)
        filtered_transactions.sort(key=lambda x: x.created_at, reverse=True)
        
        # Apply limit
        if limit:
            filtered_transactions = filtered_transactions[:limit]
        
        return filtered_transactions
    
    def _run_compliance_checks(self, transaction: Transaction) -> None:
        """Run compliance checks on transaction"""
        # Determine customer ID
        customer_id = None
        account_id = transaction.from_account_id or transaction.to_account_id
        
        if account_id:
            account = self.account_manager.get_account(account_id)
            if account:
                customer_id = account.customer_id
        
        if not customer_id:
            # Cannot check compliance without customer info
            transaction.compliance_checked = True
            transaction.compliance_action = ComplianceAction.ALLOW
            return
        
        # Run compliance check
        action, violations = self.compliance_engine.check_transaction_compliance(
            customer_id=customer_id,
            account_id=account_id,
            transaction_amount=transaction.amount,
            transaction_type=transaction.transaction_type.value,
            transaction_id=transaction.id
        )
        
        transaction.compliance_checked = True
        transaction.compliance_action = action
        if violations:
            transaction.compliance_notes = "; ".join(violations)
        
        self._save_transaction(transaction)
    
    def _validate_transaction_accounts(self, transaction: Transaction) -> None:
        """Validate that accounts exist and can process the transaction"""
        # Validate from_account if present
        if transaction.from_account_id:
            from_account = self.account_manager.get_account(transaction.from_account_id)
            if not from_account:
                raise ValueError(f"From account {transaction.from_account_id} not found")
            
            if not from_account.can_debit():
                raise ValueError(f"From account {transaction.from_account_id} cannot be debited")
            
            # Check available balance for debits (skip for loan accounts during disbursement)
            if transaction.transaction_type in [
                TransactionType.WITHDRAWAL, 
                TransactionType.TRANSFER_INTERNAL,
                TransactionType.TRANSFER_EXTERNAL
            ]:
                # Allow loan account debits up to the loan amount for disbursement
                if from_account.product_type == ProductType.LOAN:
                    # For loan accounts, we allow debits up to a reasonable loan amount
                    # This is typically handled by credit limits, but for simplicity allow larger amounts
                    max_loan_amount = Money(Decimal('1000000'), transaction.amount.currency)  # $1M limit
                    current_balance = self.account_manager.get_book_balance(from_account.id)
                    if abs(current_balance.amount - transaction.amount.amount) > max_loan_amount.amount:
                        raise ValueError(f"Loan amount {transaction.amount.to_string()} exceeds maximum loan limit")
                else:
                    # Regular balance check for non-loan accounts
                    available_balance = self.account_manager.get_available_balance(from_account.id)
                    if available_balance < transaction.amount:
                        raise ValueError(f"Insufficient funds: available {available_balance.to_string()}, requested {transaction.amount.to_string()}")
        
        # Validate to_account if present
        if transaction.to_account_id:
            to_account = self.account_manager.get_account(transaction.to_account_id)
            if not to_account:
                raise ValueError(f"To account {transaction.to_account_id} not found")
            
            if not to_account.can_credit():
                raise ValueError(f"To account {transaction.to_account_id} cannot be credited")
    
    def _create_journal_entry(self, transaction: Transaction) -> JournalEntry:
        """Create journal entry for transaction"""
        lines = []
        
        if transaction.transaction_type == TransactionType.DEPOSIT:
            # Deposit: Debit customer account, Credit external source
            lines.append(JournalEntryLine(
                account_id=transaction.to_account_id,
                description=f"Deposit: {transaction.description}",
                debit_amount=transaction.amount,
                credit_amount=Money(Decimal('0'), transaction.currency)
            ))
            lines.append(JournalEntryLine(
                account_id=self._system_accounts["external_deposits"],
                description=f"Deposit source: {transaction.description}",
                debit_amount=Money(Decimal('0'), transaction.currency),
                credit_amount=transaction.amount
            ))
        
        elif transaction.transaction_type == TransactionType.WITHDRAWAL:
            # Withdrawal: Credit customer account, Debit external destination
            lines.append(JournalEntryLine(
                account_id=transaction.from_account_id,
                description=f"Withdrawal: {transaction.description}",
                debit_amount=Money(Decimal('0'), transaction.currency),
                credit_amount=transaction.amount
            ))
            lines.append(JournalEntryLine(
                account_id=self._system_accounts["external_withdrawals"],
                description=f"Withdrawal destination: {transaction.description}",
                debit_amount=transaction.amount,
                credit_amount=Money(Decimal('0'), transaction.currency)
            ))
        
        elif transaction.transaction_type == TransactionType.TRANSFER_INTERNAL:
            # Internal transfer: Credit from account, Debit to account
            lines.append(JournalEntryLine(
                account_id=transaction.from_account_id,
                description=f"Transfer out: {transaction.description}",
                debit_amount=Money(Decimal('0'), transaction.currency),
                credit_amount=transaction.amount
            ))
            lines.append(JournalEntryLine(
                account_id=transaction.to_account_id,
                description=f"Transfer in: {transaction.description}",
                debit_amount=transaction.amount,
                credit_amount=Money(Decimal('0'), transaction.currency)
            ))
        
        elif transaction.transaction_type == TransactionType.PAYMENT:
            # Payment: Credit customer account (reduce balance), Debit external payee
            lines.append(JournalEntryLine(
                account_id=transaction.from_account_id,
                description=f"Payment: {transaction.description}",
                debit_amount=Money(Decimal('0'), transaction.currency),
                credit_amount=transaction.amount
            ))
            lines.append(JournalEntryLine(
                account_id=self._system_accounts.get("external_payments", "EXTERNAL_PAYMENTS"),
                description=f"Payment to: {transaction.description}",
                debit_amount=transaction.amount,
                credit_amount=Money(Decimal('0'), transaction.currency)
            ))
        
        elif transaction.transaction_type == TransactionType.FEE:
            # Fee: Credit customer account, Debit fee income
            lines.append(JournalEntryLine(
                account_id=transaction.from_account_id,
                description=f"Fee: {transaction.description}",
                debit_amount=Money(Decimal('0'), transaction.currency),
                credit_amount=transaction.amount
            ))
            lines.append(JournalEntryLine(
                account_id=self._system_accounts["fee_income"],
                description=f"Fee income: {transaction.description}",
                debit_amount=transaction.amount,
                credit_amount=Money(Decimal('0'), transaction.currency)
            ))
            
        elif transaction.transaction_type == TransactionType.INTEREST_CREDIT:
            # Interest credit: Debit customer account (asset), Credit interest expense account (bank expense)
            lines.append(JournalEntryLine(
                account_id=transaction.to_account_id,
                description=f"Interest earned: {transaction.description}",
                debit_amount=transaction.amount,
                credit_amount=Money(Decimal('0'), transaction.currency)
            ))
            lines.append(JournalEntryLine(
                account_id=self._system_accounts.get("interest_expense", "INTEREST_EXP_001"),
                description=f"Interest expense: {transaction.description}",
                debit_amount=Money(Decimal('0'), transaction.currency),
                credit_amount=transaction.amount
            ))
            
        elif transaction.transaction_type == TransactionType.INTEREST_DEBIT:
            # Interest debit: Credit customer account (reduces asset/increases liability), Debit interest income account (bank income)
            lines.append(JournalEntryLine(
                account_id=self._system_accounts.get("interest_income", "INTEREST_INC_001"),
                description=f"Interest income: {transaction.description}",
                debit_amount=transaction.amount,
                credit_amount=Money(Decimal('0'), transaction.currency)
            ))
            lines.append(JournalEntryLine(
                account_id=transaction.from_account_id,
                description=f"Interest charged: {transaction.description}",
                debit_amount=Money(Decimal('0'), transaction.currency),
                credit_amount=transaction.amount
            ))
        
        elif transaction.transaction_type == TransactionType.REVERSAL:
            # Reversal: Create opposite entries of original
            if transaction.original_transaction_id:
                # Use the same logic as the original but with swapped accounts
                # This is handled by the calling reverse_transaction method
                # which creates the transaction with swapped accounts
                return self._create_journal_entry_for_reversal(transaction)
            else:
                raise ValueError("Reversal transaction must have original_transaction_id")
        
        else:
            raise ValueError(f"Unsupported transaction type: {transaction.transaction_type}")
        
        # Create and return journal entry
        return self.ledger.create_journal_entry(
            reference=transaction.reference,
            description=transaction.description,
            lines=lines
        )
    
    def _create_journal_entry_for_reversal(self, reversal_transaction: Transaction) -> JournalEntry:
        """Create journal entry for reversal transaction"""
        # For reversal, we need to create the opposite journal entries of the original
        original_txn = self.get_transaction(reversal_transaction.original_transaction_id)
        if not original_txn:
            raise ValueError("Original transaction not found for reversal")
        
        lines = []
        
        if original_txn.transaction_type == TransactionType.DEPOSIT:
            # Original: Debit customer account, Credit external source
            # Reversal: Credit customer account, Debit external source
            lines.append(JournalEntryLine(
                account_id=original_txn.to_account_id,  # Customer account
                description=f"Deposit reversal: {reversal_transaction.description}",
                debit_amount=Money(Decimal('0'), reversal_transaction.currency),
                credit_amount=reversal_transaction.amount
            ))
            lines.append(JournalEntryLine(
                account_id=self._system_accounts["external_deposits"],
                description=f"Deposit reversal source: {reversal_transaction.description}",
                debit_amount=reversal_transaction.amount,
                credit_amount=Money(Decimal('0'), reversal_transaction.currency)
            ))
            
        elif original_txn.transaction_type == TransactionType.WITHDRAWAL:
            # Original: Credit customer account, Debit external destination
            # Reversal: Debit customer account, Credit external destination
            lines.append(JournalEntryLine(
                account_id=original_txn.from_account_id,  # Customer account
                description=f"Withdrawal reversal: {reversal_transaction.description}",
                debit_amount=reversal_transaction.amount,
                credit_amount=Money(Decimal('0'), reversal_transaction.currency)
            ))
            lines.append(JournalEntryLine(
                account_id=self._system_accounts["external_withdrawals"],
                description=f"Withdrawal reversal destination: {reversal_transaction.description}",
                debit_amount=Money(Decimal('0'), reversal_transaction.currency),
                credit_amount=reversal_transaction.amount
            ))
            
        elif original_txn.transaction_type == TransactionType.TRANSFER_INTERNAL:
            # Original: Credit from account, Debit to account
            # Reversal: Debit from account, Credit to account
            lines.append(JournalEntryLine(
                account_id=original_txn.from_account_id,
                description=f"Transfer reversal out: {reversal_transaction.description}",
                debit_amount=reversal_transaction.amount,
                credit_amount=Money(Decimal('0'), reversal_transaction.currency)
            ))
            lines.append(JournalEntryLine(
                account_id=original_txn.to_account_id,
                description=f"Transfer reversal in: {reversal_transaction.description}",
                debit_amount=Money(Decimal('0'), reversal_transaction.currency),
                credit_amount=reversal_transaction.amount
            ))
        else:
            raise ValueError(f"Reversal not supported for transaction type {original_txn.transaction_type}")
        
        # Create journal entry using the ledger
        return self.ledger.create_journal_entry(
            reference=reversal_transaction.reference,
            description=reversal_transaction.description,
            lines=lines
        )
    
    def _fail_transaction(self, transaction: Transaction, error_message: str) -> None:
        """Mark transaction as failed"""
        transaction.state = TransactionState.FAILED
        transaction.error_message = error_message
        transaction.processed_at = datetime.now(timezone.utc)
        transaction.updated_at = transaction.processed_at
        
        self._save_transaction(transaction)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.TRANSACTION_FAILED,
            entity_type="transaction",
            entity_id=transaction.id,
            metadata={
                "error_message": error_message,
                "failed_at": transaction.processed_at.isoformat()
            }
        )
        
        # Publish domain event (Phase 2)
        if DomainEvent:
            self._publish_event(DomainEvent.TRANSACTION_FAILED, transaction)
    
    def _find_by_idempotency_key(self, idempotency_key: str) -> Optional[Transaction]:
        """Find transaction by idempotency key"""
        transactions = self.storage.find(self.table_name, {"idempotency_key": idempotency_key})
        if transactions:
            return self._transaction_from_dict(transactions[0])
        return None
    
    def _save_transaction(self, transaction: Transaction) -> None:
        """Save transaction to storage"""
        transaction_dict = self._transaction_to_dict(transaction)
        self.storage.save(self.table_name, transaction.id, transaction_dict)
    
    def _transaction_to_dict(self, transaction: Transaction) -> Dict:
        """Convert Transaction to dictionary for storage"""
        result = transaction.to_dict()
        result['transaction_type'] = transaction.transaction_type.value
        result['currency'] = transaction.currency.code
        result['amount'] = str(transaction.amount.amount)
        result['channel'] = transaction.channel.value
        result['state'] = transaction.state.value
        
        if transaction.compliance_action:
            result['compliance_action'] = transaction.compliance_action.value
        
        if transaction.processed_at:
            result['processed_at'] = transaction.processed_at.isoformat()
        
        return result
    
    def _transaction_from_dict(self, data: Dict) -> Transaction:
        """Convert dictionary to Transaction"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        processed_at = None
        if data.get('processed_at'):
            processed_at = datetime.fromisoformat(data['processed_at'])
        
        compliance_action = None
        if data.get('compliance_action'):
            compliance_action = ComplianceAction(data['compliance_action'])
        
        return Transaction(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            transaction_type=TransactionType(data['transaction_type']),
            from_account_id=data.get('from_account_id'),
            to_account_id=data.get('to_account_id'),
            amount=Money(Decimal(data['amount']), Currency[data['currency']]),
            currency=Currency[data['currency']],
            description=data['description'],
            reference=data['reference'],
            idempotency_key=data['idempotency_key'],
            channel=TransactionChannel(data['channel']),
            state=TransactionState(data['state']),
            journal_entry_id=data.get('journal_entry_id'),
            reversal_transaction_id=data.get('reversal_transaction_id'),
            original_transaction_id=data.get('original_transaction_id'),
            processed_at=processed_at,
            processing_node=data.get('processing_node'),
            error_message=data.get('error_message'),
            compliance_checked=data.get('compliance_checked', False),
            compliance_action=compliance_action,
            compliance_notes=data.get('compliance_notes'),
            metadata=data.get('metadata', {})
        )