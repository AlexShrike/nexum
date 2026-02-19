"""
Account Management Module

Manages the chart of accounts, account states, and balance calculations.
Accounts can be assets, liabilities, equity, revenue, or expenses with
different product types like savings, checking, credit lines, etc.
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
from .ledger import GeneralLedger, AccountType

# Import events for Phase 2 observer pattern (optional)
try:
    from .events import EventDispatcher, DomainEvent, create_account_event
except ImportError:
    EventDispatcher = None
    DomainEvent = None
    create_account_event = None


class ProductType(Enum):
    """Banking product types"""
    SAVINGS = "savings"          # Savings account (Asset)
    CHECKING = "checking"        # Checking account (Asset)  
    CREDIT_LINE = "credit_line"  # Credit line (Liability)
    LOAN = "loan"               # Loan (Liability)
    GL_INTERNAL = "gl_internal" # General ledger internal account


class AccountState(Enum):
    """Account lifecycle states"""
    ACTIVE = "active"      # Normal operation
    FROZEN = "frozen"      # Temporarily suspended
    CLOSED = "closed"      # Permanently closed
    DORMANT = "dormant"    # Inactive but can be reactivated


@dataclass
class AccountHold(StorageRecord):
    """
    Hold placed on account funds
    Reduces available balance but not book balance
    """
    account_id: str
    amount: Money
    reason: str
    expires_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    
    @property
    def is_active(self) -> bool:
        """Check if hold is currently active"""
        if self.released_at:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True


@dataclass  
class Account(StorageRecord):
    """
    Bank account with proper double-entry accounting integration
    """
    account_number: str
    customer_id: str
    product_type: ProductType
    account_type: AccountType
    currency: Currency
    name: str
    state: AccountState = AccountState.ACTIVE
    interest_rate: Optional[Decimal] = None  # Annual interest rate
    credit_limit: Optional[Money] = None     # For credit products
    minimum_balance: Optional[Money] = None
    daily_transaction_limit: Optional[Money] = None
    monthly_transaction_limit: Optional[Money] = None
    
    def __post_init__(self):
        
        # Validate currency consistency
        if self.credit_limit and self.credit_limit.currency != self.currency:
            raise ValueError("Credit limit currency must match account currency")
        
        if self.minimum_balance and self.minimum_balance.currency != self.currency:
            raise ValueError("Minimum balance currency must match account currency")
        
        if self.daily_transaction_limit and self.daily_transaction_limit.currency != self.currency:
            raise ValueError("Daily transaction limit currency must match account currency")
        
        if self.monthly_transaction_limit and self.monthly_transaction_limit.currency != self.currency:
            raise ValueError("Monthly transaction limit currency must match account currency")
    
    @property
    def is_asset_account(self) -> bool:
        """Check if this is an asset account"""
        return self.account_type == AccountType.ASSET
    
    @property
    def is_liability_account(self) -> bool:
        """Check if this is a liability account"""
        return self.account_type == AccountType.LIABILITY
    
    @property
    def supports_overdraft(self) -> bool:
        """Check if account supports overdraft (has credit limit)"""
        return self.credit_limit is not None and not self.credit_limit.is_zero()
    
    @property 
    def is_credit_product(self) -> bool:
        """Check if this is a credit product"""
        return self.product_type == ProductType.CREDIT_LINE
    
    @property
    def is_deposit_product(self) -> bool:
        """Check if this is a deposit product"""
        return self.product_type in [ProductType.SAVINGS, ProductType.CHECKING]
    
    @property
    def is_loan_product(self) -> bool:
        """Check if this is a loan product"""
        return self.product_type == ProductType.LOAN
    
    def can_transact(self) -> bool:
        """Check if account can process transactions"""
        return self.state == AccountState.ACTIVE
    
    def can_credit(self) -> bool:
        """Check if account can receive credits"""
        return self.state in [AccountState.ACTIVE, AccountState.DORMANT, AccountState.FROZEN]
    
    def can_debit(self) -> bool:
        """Check if account can be debited"""
        return self.state == AccountState.ACTIVE


class AccountManager:
    """
    Manages account lifecycle, holds, and balance calculations
    """
    
    def __init__(
        self,
        storage: StorageInterface,
        ledger: GeneralLedger,
        audit_trail: AuditTrail,
        event_dispatcher: Optional['EventDispatcher'] = None
    ):
        self.storage = storage
        self.ledger = ledger  
        self.audit_trail = audit_trail
        self.accounts_table = "accounts"
        self.holds_table = "account_holds"
        
        # Event dispatcher for publishing domain events (Phase 2)
        self._event_dispatcher = event_dispatcher
    
    def _publish_event(self, event_type, account: Account) -> None:
        """Publish a domain event if event dispatcher is available"""
        if self._event_dispatcher and create_account_event and event_type:
            try:
                event = create_account_event(event_type, account)
                self._event_dispatcher.publish(event)
            except Exception as e:
                # Log but don't fail the operation
                pass
    
    def create_account(
        self,
        customer_id: str,
        product_type: ProductType,
        currency: Currency,
        name: str,
        account_number: Optional[str] = None,
        interest_rate: Optional[Decimal] = None,
        credit_limit: Optional[Money] = None,
        minimum_balance: Optional[Money] = None,
        daily_transaction_limit: Optional[Money] = None,
        monthly_transaction_limit: Optional[Money] = None
    ) -> Account:
        """
        Create a new account
        
        Args:
            customer_id: ID of account owner
            product_type: Type of banking product
            currency: Account currency
            name: Account name/description
            account_number: Specific account number (generated if not provided)
            interest_rate: Annual interest rate (if applicable)
            credit_limit: Credit limit for credit products
            minimum_balance: Minimum balance requirement
            daily_transaction_limit: Daily transaction limit
            monthly_transaction_limit: Monthly transaction limit
            
        Returns:
            Created Account object
        """
        now = datetime.now(timezone.utc)
        account_id = str(uuid.uuid4())
        
        # Generate account number if not provided
        if not account_number:
            account_number = self._generate_account_number(product_type)
        
        # Determine account type based on product type
        if product_type in [ProductType.SAVINGS, ProductType.CHECKING]:
            account_type = AccountType.ASSET
        elif product_type in [ProductType.CREDIT_LINE, ProductType.LOAN]:
            account_type = AccountType.LIABILITY
        else:  # GL_INTERNAL
            account_type = AccountType.ASSET  # Default, can be overridden
        
        account = Account(
            id=account_id,
            created_at=now,
            updated_at=now,
            account_number=account_number,
            customer_id=customer_id,
            product_type=product_type,
            account_type=account_type,
            currency=currency,
            name=name,
            interest_rate=interest_rate,
            credit_limit=credit_limit,
            minimum_balance=minimum_balance,
            daily_transaction_limit=daily_transaction_limit,
            monthly_transaction_limit=monthly_transaction_limit
        )
        
        # Save account
        self._save_account(account)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_CREATED,
            entity_type="account",
            entity_id=account.id,
            metadata={
                "account_number": account_number,
                "customer_id": customer_id,
                "product_type": product_type.value,
                "account_type": account_type.value,
                "currency": currency.code,
                "name": name
            }
        )
        
        # Publish domain event (Phase 2)
        if DomainEvent:
            self._publish_event(DomainEvent.ACCOUNT_CREATED, account)
        
        return account
    
    def get_account(self, account_id: str) -> Optional[Account]:
        """Get account by ID"""
        account_dict = self.storage.load(self.accounts_table, account_id)
        if account_dict:
            return self._account_from_dict(account_dict)
        return None
    
    def get_account_by_number(self, account_number: str) -> Optional[Account]:
        """Get account by account number"""
        accounts = self.storage.find(self.accounts_table, {"account_number": account_number})
        if accounts:
            return self._account_from_dict(accounts[0])
        return None
    
    def get_customer_accounts(self, customer_id: str) -> List[Account]:
        """Get all accounts for a customer"""
        accounts_data = self.storage.find(self.accounts_table, {"customer_id": customer_id})
        return [self._account_from_dict(data) for data in accounts_data]
    
    def update_account_state(self, account_id: str, new_state: AccountState, reason: str) -> Account:
        """Update account state with audit trail"""
        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")
        
        old_state = account.state
        account.state = new_state
        account.updated_at = datetime.now(timezone.utc)
        
        self._save_account(account)
        
        # Log specific audit events
        if new_state == AccountState.FROZEN:
            event_type = AuditEventType.ACCOUNT_FROZEN
        elif old_state == AccountState.FROZEN and new_state == AccountState.ACTIVE:
            event_type = AuditEventType.ACCOUNT_UNFROZEN
        elif new_state == AccountState.CLOSED:
            event_type = AuditEventType.ACCOUNT_CLOSED
        else:
            event_type = AuditEventType.ACCOUNT_UPDATED
        
        self.audit_trail.log_event(
            event_type=event_type,
            entity_type="account",
            entity_id=account.id,
            metadata={
                "old_state": old_state.value,
                "new_state": new_state.value,
                "reason": reason
            }
        )
        
        # Publish domain event (Phase 2)
        if DomainEvent:
            event_type_mapping = {
                AccountState.CLOSED: DomainEvent.ACCOUNT_CLOSED,
            }
            domain_event = event_type_mapping.get(new_state, DomainEvent.ACCOUNT_UPDATED)
            self._publish_event(domain_event, account)
        
        return account
    
    def freeze_account(self, account_id: str, reason: str) -> Account:
        """Freeze an account"""
        return self.update_account_state(account_id, AccountState.FROZEN, reason)
    
    def unfreeze_account(self, account_id: str, reason: str) -> Account:
        """Unfreeze an account"""
        return self.update_account_state(account_id, AccountState.ACTIVE, reason)
    
    def close_account(self, account_id: str, reason: str) -> Account:
        """Close an account"""
        # Verify zero balance before closing (for deposit accounts)
        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")
        
        if account.is_deposit_product:
            balance = self.get_book_balance(account_id)
            if not balance.is_zero():
                raise ValueError(f"Cannot close account with non-zero balance: {balance.to_string()}")
        
        return self.update_account_state(account_id, AccountState.CLOSED, reason)
    
    def update_account_interest_rate(self, account_id: str, new_rate: Decimal) -> Account:
        """Update account's interest rate"""
        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")
        
        # Update the rate
        account.interest_rate = new_rate
        account.updated_at = datetime.now(timezone.utc)
        
        # Save to storage
        self._save_account(account)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_STATE_CHANGED,
            entity_type="account",
            entity_id=account.id,
            metadata={
                "new_interest_rate": str(new_rate),
                "updated_by": "system"
            }
        )
        
        return account
    
    def place_hold(
        self,
        account_id: str,
        amount: Money,
        reason: str,
        expires_at: Optional[datetime] = None
    ) -> AccountHold:
        """
        Place a hold on account funds
        
        Args:
            account_id: Account to place hold on
            amount: Amount to hold
            reason: Reason for the hold
            expires_at: Optional expiration time
            
        Returns:
            Created AccountHold object
        """
        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")
        
        if amount.currency != account.currency:
            raise ValueError("Hold amount currency must match account currency")
        
        if not amount.is_positive():
            raise ValueError("Hold amount must be positive")
        
        now = datetime.now(timezone.utc)
        hold_id = str(uuid.uuid4())
        
        hold = AccountHold(
            id=hold_id,
            created_at=now,
            updated_at=now,
            account_id=account_id,
            amount=amount,
            reason=reason,
            expires_at=expires_at
        )
        
        # Save hold
        hold_dict = self._hold_to_dict(hold)
        self.storage.save(self.holds_table, hold.id, hold_dict)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_HOLD_PLACED,
            entity_type="account",
            entity_id=account_id,
            metadata={
                "hold_id": hold_id,
                "amount": amount.to_string(),
                "reason": reason,
                "expires_at": expires_at.isoformat() if expires_at else None
            }
        )
        
        return hold
    
    def release_hold(self, hold_id: str, reason: str) -> AccountHold:
        """Release an account hold"""
        hold_dict = self.storage.load(self.holds_table, hold_id)
        if not hold_dict:
            raise ValueError(f"Hold {hold_id} not found")
        
        hold = self._hold_from_dict(hold_dict)
        
        if hold.released_at:
            raise ValueError(f"Hold {hold_id} already released")
        
        now = datetime.now(timezone.utc)
        hold.released_at = now
        hold.updated_at = now
        
        # Save updated hold
        hold_dict = self._hold_to_dict(hold)
        self.storage.save(self.holds_table, hold.id, hold_dict)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_HOLD_RELEASED,
            entity_type="account",
            entity_id=hold.account_id,
            metadata={
                "hold_id": hold_id,
                "amount": hold.amount.to_string(),
                "reason": reason
            }
        )
        
        return hold
    
    def get_active_holds(self, account_id: str) -> List[AccountHold]:
        """Get all active holds for an account"""
        holds_data = self.storage.find(self.holds_table, {"account_id": account_id})
        holds = [self._hold_from_dict(data) for data in holds_data]
        return [hold for hold in holds if hold.is_active]
    
    def get_book_balance(self, account_id: str) -> Money:
        """
        Get book balance (actual balance from ledger)
        This is the source of truth derived from journal entries
        For customer-facing credit products, returns customer perspective (debt is negative)
        """
        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")
        
        balance = self.ledger.calculate_account_balance(
            account_id=account_id,
            account_type=account.account_type,
            currency=account.currency
        )
        
        # For customer-facing credit products, flip the sign to show customer perspective
        # Traditional accounting: positive balance = customer owes money
        # Customer perspective: negative balance = customer owes money
        if account.is_credit_product:
            balance = -balance
        
        return balance
    
    def get_available_balance(self, account_id: str) -> Money:
        """
        Get available balance (book balance minus holds and plus credit limit)
        """
        book_balance = self.get_book_balance(account_id)
        account = self.get_account(account_id)
        
        if not account:
            raise ValueError(f"Account {account_id} not found")
        
        # Start with book balance
        available = book_balance
        
        # Subtract active holds
        holds = self.get_active_holds(account_id)
        for hold in holds:
            available = available - hold.amount
        
        # Add credit limit for liability accounts (credit products)
        if account.is_liability_account and account.credit_limit:
            available = available + account.credit_limit
        
        return available
    
    def get_credit_available(self, account_id: str) -> Money:
        """Get available credit for credit line accounts"""
        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")
        
        if not account.is_credit_product:
            raise ValueError("Account is not a credit product")
        
        if not account.credit_limit:
            return Money(Decimal('0'), account.currency)
        
        # For credit products, negative balance means customer owes money (customer's perspective)
        book_balance = self.get_book_balance(account_id)
        
        # Available credit = limit - current debt
        # book_balance is negative for customer debt (from customer's perspective)
        used_credit = -book_balance if book_balance.is_negative() else Money(Decimal('0'), account.currency)
        available_credit = account.credit_limit - used_credit
        
        # Subtract holds
        holds = self.get_active_holds(account_id)
        for hold in holds:
            available_credit = available_credit - hold.amount
        
        return available_credit if available_credit.is_positive() else Money(Decimal('0'), account.currency)
    
    def _generate_account_number(self, product_type: ProductType) -> str:
        """Generate a unique account number"""
        # Simple implementation - in production would have more sophisticated numbering
        timestamp = int(datetime.now(timezone.utc).timestamp())
        prefix_map = {
            ProductType.SAVINGS: "SAV",
            ProductType.CHECKING: "CHK", 
            ProductType.CREDIT_LINE: "CRD",
            ProductType.LOAN: "LON",
            ProductType.GL_INTERNAL: "GL"
        }
        prefix = prefix_map.get(product_type, "ACC")
        return f"{prefix}{timestamp}"
    
    def _save_account(self, account: Account) -> None:
        """Save account to storage"""
        account_dict = self._account_to_dict(account)
        self.storage.save(self.accounts_table, account.id, account_dict)
    
    def _account_to_dict(self, account: Account) -> Dict:
        """Convert Account to dictionary for storage"""
        result = account.to_dict()
        result['product_type'] = account.product_type.value
        result['account_type'] = account.account_type.value
        result['currency'] = account.currency.code
        result['state'] = account.state.value
        
        if account.interest_rate:
            result['interest_rate'] = str(account.interest_rate)
        
        if account.credit_limit:
            result['credit_limit_amount'] = str(account.credit_limit.amount)
            result['credit_limit_currency'] = account.credit_limit.currency.code
        
        if account.minimum_balance:
            result['minimum_balance_amount'] = str(account.minimum_balance.amount)
            result['minimum_balance_currency'] = account.minimum_balance.currency.code
        
        if account.daily_transaction_limit:
            result['daily_limit_amount'] = str(account.daily_transaction_limit.amount)
            result['daily_limit_currency'] = account.daily_transaction_limit.currency.code
        
        if account.monthly_transaction_limit:
            result['monthly_limit_amount'] = str(account.monthly_transaction_limit.amount)
            result['monthly_limit_currency'] = account.monthly_transaction_limit.currency.code
        
        return result
    
    def _account_from_dict(self, data: Dict) -> Account:
        """Convert dictionary to Account"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        currency = Currency[data['currency']]
        
        credit_limit = None
        if data.get('credit_limit_amount'):
            credit_limit = Money(
                Decimal(data['credit_limit_amount']),
                Currency[data['credit_limit_currency']]
            )
        
        minimum_balance = None
        if data.get('minimum_balance_amount'):
            minimum_balance = Money(
                Decimal(data['minimum_balance_amount']),
                Currency[data['minimum_balance_currency']]
            )
        
        daily_transaction_limit = None
        if data.get('daily_limit_amount'):
            daily_transaction_limit = Money(
                Decimal(data['daily_limit_amount']),
                Currency[data['daily_limit_currency']]
            )
        
        monthly_transaction_limit = None
        if data.get('monthly_limit_amount'):
            monthly_transaction_limit = Money(
                Decimal(data['monthly_limit_amount']),
                Currency[data['monthly_limit_currency']]
            )
        
        interest_rate = None
        if data.get('interest_rate'):
            interest_rate = Decimal(data['interest_rate'])
        
        return Account(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            account_number=data['account_number'],
            customer_id=data['customer_id'],
            product_type=ProductType(data['product_type']),
            account_type=AccountType(data['account_type']),
            currency=currency,
            name=data['name'],
            state=AccountState(data['state']),
            interest_rate=interest_rate,
            credit_limit=credit_limit,
            minimum_balance=minimum_balance,
            daily_transaction_limit=daily_transaction_limit,
            monthly_transaction_limit=monthly_transaction_limit
        )
    
    def _hold_to_dict(self, hold: AccountHold) -> Dict:
        """Convert AccountHold to dictionary"""
        result = hold.to_dict()
        result['amount'] = str(hold.amount.amount)
        result['currency'] = hold.amount.currency.code
        
        if hold.expires_at:
            result['expires_at'] = hold.expires_at.isoformat()
        
        if hold.released_at:
            result['released_at'] = hold.released_at.isoformat()
        
        return result
    
    def _hold_from_dict(self, data: Dict) -> AccountHold:
        """Convert dictionary to AccountHold"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        expires_at = None
        if data.get('expires_at'):
            expires_at = datetime.fromisoformat(data['expires_at'])
        
        released_at = None
        if data.get('released_at'):
            released_at = datetime.fromisoformat(data['released_at'])
        
        return AccountHold(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            account_id=data['account_id'],
            amount=Money(Decimal(data['amount']), Currency[data['currency']]),
            reason=data['reason'],
            expires_at=expires_at,
            released_at=released_at
        )