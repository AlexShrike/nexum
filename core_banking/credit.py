"""
Credit Line Module

Manages revolving credit lines with proper grace period logic, statement
generation, minimum payment calculations, and late payment handling.
Similar to Salmon's credit management but with full banking integration.
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta, date
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import uuid
import calendar

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType
from .accounts import AccountManager, Account, ProductType
from .transactions import TransactionProcessor, TransactionType, TransactionChannel
from .interest import InterestEngine, GracePeriodTracker


class StatementStatus(Enum):
    """Credit statement status"""
    CURRENT = "current"          # Current unpaid statement
    PAID_FULL = "paid_full"      # Paid in full by due date
    PAID_MINIMUM = "paid_minimum"  # Minimum payment made
    OVERDUE = "overdue"          # Past due date with balance
    CLOSED = "closed"            # Account closed


class TransactionCategory(Enum):
    """Categories for credit line transactions"""
    PURCHASE = "purchase"        # Regular purchases (eligible for grace period)
    CASH_ADVANCE = "cash_advance"  # Cash advances (no grace period)
    BALANCE_TRANSFER = "balance_transfer"  # Balance transfer
    FEE = "fee"                 # Fees (late fee, overlimit, etc.)
    PAYMENT = "payment"         # Payment toward balance
    INTEREST = "interest"       # Interest charges
    REVERSAL = "reversal"       # Transaction reversal


@dataclass
class CreditStatement(StorageRecord):
    """Monthly credit line statement"""
    account_id: str
    statement_date: date
    due_date: date
    
    # Balance information
    previous_balance: Money
    new_charges: Money
    payments_credits: Money
    interest_charged: Money
    fees_charged: Money
    current_balance: Money
    
    # Payment information
    minimum_payment_due: Money
    available_credit: Money
    credit_limit: Money
    
    # Grace period information
    grace_period_active: bool = True
    
    # Status tracking
    status: StatementStatus = StatementStatus.CURRENT
    paid_amount: Money = None
    paid_date: Optional[date] = None
    
    def __post_init__(self):
        
        # Initialize paid_amount if None
        if self.paid_amount is None:
            self.paid_amount = Money(Decimal('0'), self.current_balance.currency)
        
        # Validate currency consistency
        amounts = [
            self.previous_balance, self.new_charges, self.payments_credits,
            self.interest_charged, self.fees_charged, self.current_balance,
            self.minimum_payment_due, self.available_credit, self.credit_limit,
            self.paid_amount
        ]
        currencies = {amount.currency for amount in amounts}
        if len(currencies) > 1:
            raise ValueError("All statement amounts must use the same currency")
    
    @property
    def is_overdue(self) -> bool:
        """Check if statement is overdue"""
        return date.today() > self.due_date and not self.current_balance.is_zero()
    
    @property
    def days_overdue(self) -> int:
        """Get number of days overdue"""
        if not self.is_overdue:
            return 0
        return (date.today() - self.due_date).days
    
    @property
    def is_minimum_paid(self) -> bool:
        """Check if minimum payment has been made"""
        return self.paid_amount >= self.minimum_payment_due
    
    @property
    def is_paid_full(self) -> bool:
        """Check if statement balance is paid in full"""
        return self.paid_amount >= self.current_balance
    
    @property
    def remaining_balance(self) -> Money:
        """Get remaining balance after payments"""
        return self.current_balance - self.paid_amount


@dataclass
class CreditTransaction(StorageRecord):
    """Transaction specific to credit line with category and grace period info"""
    account_id: str
    transaction_id: str  # Reference to main transaction
    category: TransactionCategory
    amount: Money
    transaction_date: date
    post_date: date
    description: str
    
    # Grace period tracking
    eligible_for_grace: bool = True  # Purchases are eligible, cash advances are not
    grace_period_applies: bool = False  # Set based on previous statement payment
    interest_charged: Money = None
    
    # Statement assignment
    statement_id: Optional[str] = None  # Which statement this transaction appears on
    
    def __post_init__(self):
        
        # Initialize interest_charged if None
        if self.interest_charged is None:
            self.interest_charged = Money(Decimal('0'), self.amount.currency)
        
        # Cash advances and fees are never eligible for grace period
        if self.category in [TransactionCategory.CASH_ADVANCE, TransactionCategory.FEE]:
            self.eligible_for_grace = False
        
        # Ensure currency consistency
        if self.interest_charged.currency != self.amount.currency:
            raise ValueError("Interest charged currency must match transaction amount currency")


class CreditLineManager:
    """
    Manages credit line operations including statement generation,
    grace period logic, minimum payments, and late fees
    """
    
    def __init__(
        self,
        storage: StorageInterface,
        account_manager: AccountManager,
        transaction_processor: TransactionProcessor,
        interest_engine: InterestEngine,
        audit_trail: AuditTrail
    ):
        self.storage = storage
        self.account_manager = account_manager
        self.transaction_processor = transaction_processor
        self.interest_engine = interest_engine
        self.audit_trail = audit_trail
        
        self.statements_table = "credit_statements"
        self.credit_transactions_table = "credit_transactions"
        
        # Credit line parameters
        self.grace_period_days = 25  # Days from statement to due date
        self.minimum_payment_rate = Decimal('0.02')  # 2% of balance
        self.minimum_payment_floor = Money(Decimal('25'), Currency.USD)  # Minimum $25
        self.late_fee = Money(Decimal('35'), Currency.USD)  # $35 late fee
        self.overlimit_fee = Money(Decimal('25'), Currency.USD)  # $25 overlimit fee
    
    def process_credit_transaction(
        self,
        account_id: str,
        transaction_id: str,
        category: TransactionCategory,
        amount: Money,
        description: str,
        transaction_date: Optional[date] = None,
        post_date: Optional[date] = None
    ) -> CreditTransaction:
        """
        Process a credit line transaction and handle grace period logic
        
        Args:
            account_id: Credit line account ID
            transaction_id: Main transaction ID
            category: Transaction category
            amount: Transaction amount
            description: Transaction description
            transaction_date: Date transaction occurred
            post_date: Date transaction posted
            
        Returns:
            CreditTransaction object
        """
        if not transaction_date:
            transaction_date = date.today()
        if not post_date:
            post_date = date.today()
        
        # Validate account is credit line
        account = self.account_manager.get_account(account_id)
        if not account or account.product_type != ProductType.CREDIT_LINE:
            raise ValueError("Account must be a credit line")
        
        # Check for overlimit condition
        if category in [TransactionCategory.PURCHASE, TransactionCategory.CASH_ADVANCE]:
            current_balance = self.account_manager.get_book_balance(account_id)
            available_credit = self.account_manager.get_credit_available(account_id)
            
            if amount > available_credit:
                # Charge overlimit fee
                self._charge_fee(account_id, self.overlimit_fee, "Overlimit fee", TransactionChannel.SYSTEM)
        
        # Create credit transaction record
        credit_txn = CreditTransaction(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            account_id=account_id,
            transaction_id=transaction_id,
            category=category,
            amount=amount,
            transaction_date=transaction_date,
            post_date=post_date,
            description=description
        )
        
        # Determine grace period eligibility
        self._update_grace_period_status(credit_txn)
        
        # Save credit transaction
        self._save_credit_transaction(credit_txn)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.CREDIT_PAYMENT_MADE if category == TransactionCategory.PAYMENT 
                      else AuditEventType.TRANSACTION_CREATED,
            entity_type="credit_account",
            entity_id=account_id,
            metadata={
                "credit_transaction_id": credit_txn.id,
                "transaction_id": transaction_id,
                "category": category.value,
                "amount": amount.to_string(),
                "eligible_for_grace": credit_txn.eligible_for_grace
            }
        )
        
        return credit_txn
    
    def make_payment(
        self,
        account_id: str,
        amount: Money,
        payment_date: Optional[date] = None
    ) -> str:
        """
        Make a payment toward credit line balance
        
        Args:
            account_id: Credit line account ID
            amount: Payment amount
            payment_date: Date of payment
            
        Returns:
            Transaction ID of payment transaction
        """
        if not payment_date:
            payment_date = date.today()
        
        # Use atomic transaction for payment processing
        with self.storage.atomic():
            # Create payment transaction
            payment_transaction = self.transaction_processor.create_transaction(
                transaction_type=TransactionType.PAYMENT,
                amount=amount,
                description=f"Credit line payment",
                channel=TransactionChannel.ONLINE,
                to_account_id=account_id,  # Payment credits the account (reduces liability)
                reference=f"PAY-{account_id}-{payment_date.strftime('%Y%m%d')}"
            )
            
            # Process the transaction
            processed_payment = self.transaction_processor.process_transaction(payment_transaction.id)
            
            # Record as credit transaction
            self.process_credit_transaction(
                account_id=account_id,
                transaction_id=processed_payment.id,
                category=TransactionCategory.PAYMENT,
                amount=amount,
                description="Payment received",
                transaction_date=payment_date,
                post_date=payment_date
            )
            
            # Update grace period status
            self.interest_engine.update_grace_period_status(account_id, amount, payment_date)
            
            # Update statement payment tracking
            self._update_statement_payments(account_id, amount, payment_date)
        
        return processed_payment.id
    
    def generate_monthly_statement(
        self,
        account_id: str,
        statement_date: Optional[date] = None
    ) -> CreditStatement:
        """
        Generate monthly statement for credit line
        
        Args:
            account_id: Credit line account ID
            statement_date: Statement date (defaults to today)
            
        Returns:
            Generated CreditStatement
        """
        if not statement_date:
            statement_date = date.today()
        
        account = self.account_manager.get_account(account_id)
        if not account or account.product_type != ProductType.CREDIT_LINE:
            raise ValueError("Account must be a credit line")
        
        # Get previous statement for balance calculation
        previous_statement = self._get_latest_statement(account_id)
        previous_balance = Money(Decimal('0'), account.currency)
        if previous_statement:
            previous_balance = previous_statement.current_balance
        
        # Get transactions since last statement
        last_statement_date = previous_statement.statement_date if previous_statement else date.min
        transactions = self._get_credit_transactions_since(account_id, last_statement_date)
        
        # Calculate statement components
        new_charges = Money(Decimal('0'), account.currency)
        payments_credits = Money(Decimal('0'), account.currency)
        interest_charged = Money(Decimal('0'), account.currency)
        fees_charged = Money(Decimal('0'), account.currency)
        
        for txn in transactions:
            if txn.category in [TransactionCategory.PURCHASE, TransactionCategory.CASH_ADVANCE, 
                              TransactionCategory.BALANCE_TRANSFER]:
                new_charges = new_charges + txn.amount
            elif txn.category == TransactionCategory.PAYMENT:
                payments_credits = payments_credits + txn.amount
            elif txn.category == TransactionCategory.INTEREST:
                interest_charged = interest_charged + txn.amount
            elif txn.category == TransactionCategory.FEE:
                fees_charged = fees_charged + txn.amount
        
        # Calculate current balance
        current_balance = previous_balance + new_charges + interest_charged + fees_charged - payments_credits
        
        # Calculate minimum payment
        minimum_payment = self._calculate_minimum_payment(current_balance, interest_charged, fees_charged)
        
        # Calculate available credit
        available_credit = account.credit_limit - current_balance
        if available_credit.is_negative():
            available_credit = Money(Decimal('0'), account.currency)
        
        # Set due date
        due_date = statement_date + timedelta(days=self.grace_period_days)
        
        # Create statement
        statement = CreditStatement(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            account_id=account_id,
            statement_date=statement_date,
            due_date=due_date,
            previous_balance=previous_balance,
            new_charges=new_charges,
            payments_credits=payments_credits,
            interest_charged=interest_charged,
            fees_charged=fees_charged,
            current_balance=current_balance,
            minimum_payment_due=minimum_payment,
            available_credit=available_credit,
            credit_limit=account.credit_limit,
            paid_amount=Money(Decimal('0'), account.currency)
        )
        
        # Save statement
        self._save_statement(statement)
        
        # Update transaction statement assignments
        for txn in transactions:
            txn.statement_id = statement.id
            self._save_credit_transaction(txn)
        
        # Create grace period tracker
        if not current_balance.is_zero():
            self.interest_engine.create_grace_period(
                account_id=account_id,
                statement_date=statement_date,
                statement_balance=current_balance,
                due_date=due_date
            )
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.CREDIT_STATEMENT_GENERATED,
            entity_type="credit_account",
            entity_id=account_id,
            metadata={
                "statement_id": statement.id,
                "statement_date": statement_date.isoformat(),
                "due_date": due_date.isoformat(),
                "current_balance": current_balance.to_string(),
                "minimum_payment": minimum_payment.to_string()
            }
        )
        
        return statement
    
    def process_overdue_accounts(self) -> Dict[str, int]:
        """
        Process overdue accounts and charge late fees
        
        Returns:
            Dictionary with counts of accounts processed
        """
        results = {"late_fees_charged": 0, "accounts_processed": 0}
        
        # Get all current statements
        all_statements_data = self.storage.load_all(self.statements_table)
        statements = [self._statement_from_dict(data) for data in all_statements_data]
        
        current_statements = [s for s in statements if s.status == StatementStatus.CURRENT]
        
        for statement in current_statements:
            if statement.is_overdue and not statement.is_minimum_paid:
                # Charge late fee
                try:
                    self._charge_fee(
                        account_id=statement.account_id,
                        fee_amount=self.late_fee,
                        description="Late payment fee",
                        channel=TransactionChannel.SYSTEM
                    )
                    results["late_fees_charged"] += 1
                    
                    # Update statement status
                    statement.status = StatementStatus.OVERDUE
                    statement.updated_at = datetime.now(timezone.utc)
                    self._save_statement(statement)
                    
                except Exception as e:
                    # Log error but continue with other accounts
                    self.audit_trail.log_event(
                        event_type=AuditEventType.SYSTEM_START,  # Generic error
                        entity_type="credit_account",
                        entity_id=statement.account_id,
                        metadata={
                            "error": "Late fee processing failed",
                            "message": str(e),
                            "statement_id": statement.id
                        }
                    )
                
                results["accounts_processed"] += 1
        
        return results
    
    def adjust_credit_limit(
        self,
        account_id: str,
        new_limit: Money,
        reason: str
    ) -> Account:
        """
        Adjust credit limit for account
        
        Args:
            account_id: Account ID
            new_limit: New credit limit
            reason: Reason for adjustment
            
        Returns:
            Updated Account object
        """
        account = self.account_manager.get_account(account_id)
        if not account or account.product_type != ProductType.CREDIT_LINE:
            raise ValueError("Account must be a credit line")
        
        old_limit = account.credit_limit
        account.credit_limit = new_limit
        account.updated_at = datetime.now(timezone.utc)
        
        # Save account
        account_dict = self.account_manager._account_to_dict(account)
        self.storage.save(self.account_manager.accounts_table, account.id, account_dict)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.CREDIT_LINE_LIMIT_CHANGED,
            entity_type="credit_account",
            entity_id=account_id,
            metadata={
                "old_limit": old_limit.to_string() if old_limit else "None",
                "new_limit": new_limit.to_string(),
                "reason": reason
            }
        )
        
        return account
    
    def get_statement(self, statement_id: str) -> Optional[CreditStatement]:
        """Get credit statement by ID"""
        statement_dict = self.storage.load(self.statements_table, statement_id)
        if statement_dict:
            return self._statement_from_dict(statement_dict)
        return None
    
    def get_account_statements(
        self,
        account_id: str,
        limit: Optional[int] = None
    ) -> List[CreditStatement]:
        """Get statements for account"""
        statements_data = self.storage.find(self.statements_table, {"account_id": account_id})
        statements = [self._statement_from_dict(data) for data in statements_data]
        
        # Sort by statement date (most recent first)
        statements.sort(key=lambda x: x.statement_date, reverse=True)
        
        if limit:
            statements = statements[:limit]
        
        return statements
    
    def get_current_statement(self, account_id: str) -> Optional[CreditStatement]:
        """Get current unpaid statement for account"""
        statements_data = self.storage.find(
            self.statements_table,
            {"account_id": account_id, "status": StatementStatus.CURRENT.value}
        )
        
        if statements_data:
            statements = [self._statement_from_dict(data) for data in statements_data]
            # Return most recent current statement
            statements.sort(key=lambda x: x.statement_date, reverse=True)
            return statements[0]
        
        return None
    
    def _update_grace_period_status(self, credit_txn: CreditTransaction) -> None:
        """Update grace period status based on previous statement payment history"""
        # Get previous statement
        previous_statement = self._get_latest_statement(credit_txn.account_id)
        
        if not previous_statement:
            # No previous statement, grace period applies for purchases
            credit_txn.grace_period_applies = credit_txn.eligible_for_grace
            return
        
        # Check if previous statement was paid in full by due date
        if previous_statement.is_paid_full:
            # Previous statement paid in full, grace period applies
            credit_txn.grace_period_applies = credit_txn.eligible_for_grace
        else:
            # Previous statement not paid in full, no grace period
            credit_txn.grace_period_applies = False
    
    def _calculate_minimum_payment(
        self,
        current_balance: Money,
        interest_charged: Money,
        fees_charged: Money
    ) -> Money:
        """Calculate minimum payment due"""
        if current_balance.is_zero() or current_balance.is_negative():
            return Money(Decimal('0'), current_balance.currency)
        
        # Minimum payment is greater of:
        # 1. Percentage of balance (e.g., 2%)
        # 2. Interest + fees + minimum principal payment
        # 3. Floor amount (e.g., $25)
        
        percentage_payment = current_balance * self.minimum_payment_rate
        
        # Ensure minimum covers at least interest and fees
        required_payment = interest_charged + fees_charged
        
        # Add minimum principal payment if balance is large
        if current_balance > Money(Decimal('1000'), current_balance.currency):
            required_payment = required_payment + Money(Decimal('10'), current_balance.currency)
        
        # Take the maximum of percentage and required payment
        minimum_payment = max(percentage_payment, required_payment, key=lambda x: x.amount)
        
        # Apply floor amount
        floor_amount = Money(self.minimum_payment_floor.amount, current_balance.currency)
        minimum_payment = max(minimum_payment, floor_amount, key=lambda x: x.amount)
        
        # Don't exceed current balance
        if minimum_payment > current_balance:
            minimum_payment = current_balance
        
        return minimum_payment
    
    def _charge_fee(
        self,
        account_id: str,
        fee_amount: Money,
        description: str,
        channel: TransactionChannel
    ) -> str:
        """Charge a fee to credit line account"""
        # Create fee transaction
        fee_transaction = self.transaction_processor.create_transaction(
            transaction_type=TransactionType.FEE,
            amount=fee_amount,
            description=description,
            channel=channel,
            from_account_id=account_id,
            reference=f"FEE-{account_id}-{date.today().strftime('%Y%m%d')}"
        )
        
        # Process transaction
        processed_fee = self.transaction_processor.process_transaction(fee_transaction.id)
        
        # Record as credit transaction
        self.process_credit_transaction(
            account_id=account_id,
            transaction_id=processed_fee.id,
            category=TransactionCategory.FEE,
            amount=fee_amount,
            description=description,
            transaction_date=date.today(),
            post_date=date.today()
        )
        
        return processed_fee.id
    
    def _update_statement_payments(self, account_id: str, payment_amount: Money, payment_date: date) -> None:
        """Update statement payment tracking"""
        current_statement = self.get_current_statement(account_id)
        if not current_statement:
            return
        
        # Update payment amount
        current_statement.paid_amount = current_statement.paid_amount + payment_amount
        current_statement.paid_date = payment_date
        current_statement.updated_at = datetime.now(timezone.utc)
        
        # Update status based on payment
        if current_statement.is_paid_full:
            current_statement.status = StatementStatus.PAID_FULL
        elif current_statement.is_minimum_paid:
            current_statement.status = StatementStatus.PAID_MINIMUM
        
        self._save_statement(current_statement)
    
    def _get_latest_statement(self, account_id: str) -> Optional[CreditStatement]:
        """Get the most recent statement for account"""
        statements = self.get_account_statements(account_id, limit=1)
        return statements[0] if statements else None
    
    def _get_credit_transactions_since(self, account_id: str, since_date: date) -> List[CreditTransaction]:
        """Get credit transactions since specified date"""
        transactions_data = self.storage.find(
            self.credit_transactions_table,
            {"account_id": account_id}
        )
        
        transactions = [self._credit_transaction_from_dict(data) for data in transactions_data]
        
        # Filter by date
        filtered = [txn for txn in transactions if txn.post_date > since_date]
        
        # Sort by post date
        filtered.sort(key=lambda x: x.post_date)
        
        return filtered
    
    def _save_statement(self, statement: CreditStatement) -> None:
        """Save credit statement to storage"""
        statement_dict = self._statement_to_dict(statement)
        self.storage.save(self.statements_table, statement.id, statement_dict)
    
    def _save_credit_transaction(self, credit_txn: CreditTransaction) -> None:
        """Save credit transaction to storage"""
        txn_dict = self._credit_transaction_to_dict(credit_txn)
        self.storage.save(self.credit_transactions_table, credit_txn.id, txn_dict)
    
    def _statement_to_dict(self, statement: CreditStatement) -> Dict:
        """Convert statement to dictionary"""
        result = statement.to_dict()
        result['statement_date'] = statement.statement_date.isoformat()
        result['due_date'] = statement.due_date.isoformat()
        result['status'] = statement.status.value
        
        if statement.paid_date:
            result['paid_date'] = statement.paid_date.isoformat()
        
        # Convert money amounts
        money_fields = [
            'previous_balance', 'new_charges', 'payments_credits',
            'interest_charged', 'fees_charged', 'current_balance',
            'minimum_payment_due', 'available_credit', 'credit_limit', 'paid_amount'
        ]
        
        for field in money_fields:
            amount = getattr(statement, field)
            result[f"{field}_amount"] = str(amount.amount)
            result[f"{field}_currency"] = amount.currency.code
        
        return result
    
    def _statement_from_dict(self, data: Dict) -> CreditStatement:
        """Convert dictionary to statement"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        statement_date = date.fromisoformat(data['statement_date'])
        due_date = date.fromisoformat(data['due_date'])
        
        paid_date = None
        if data.get('paid_date'):
            paid_date = date.fromisoformat(data['paid_date'])
        
        # Reconstruct money amounts
        def get_money(field_prefix: str) -> Money:
            return Money(
                Decimal(data[f"{field_prefix}_amount"]),
                Currency[data[f"{field_prefix}_currency"]]
            )
        
        return CreditStatement(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            account_id=data['account_id'],
            statement_date=statement_date,
            due_date=due_date,
            previous_balance=get_money('previous_balance'),
            new_charges=get_money('new_charges'),
            payments_credits=get_money('payments_credits'),
            interest_charged=get_money('interest_charged'),
            fees_charged=get_money('fees_charged'),
            current_balance=get_money('current_balance'),
            minimum_payment_due=get_money('minimum_payment_due'),
            available_credit=get_money('available_credit'),
            credit_limit=get_money('credit_limit'),
            grace_period_active=data.get('grace_period_active', True),
            status=StatementStatus(data['status']),
            paid_amount=get_money('paid_amount'),
            paid_date=paid_date
        )
    
    def _credit_transaction_to_dict(self, credit_txn: CreditTransaction) -> Dict:
        """Convert credit transaction to dictionary"""
        result = credit_txn.to_dict()
        result['category'] = credit_txn.category.value
        result['transaction_date'] = credit_txn.transaction_date.isoformat()
        result['post_date'] = credit_txn.post_date.isoformat()
        result['amount'] = str(credit_txn.amount.amount)
        result['amount_currency'] = credit_txn.amount.currency.code
        result['interest_charged'] = str(credit_txn.interest_charged.amount)
        result['interest_currency'] = credit_txn.interest_charged.currency.code
        return result
    
    def _credit_transaction_from_dict(self, data: Dict) -> CreditTransaction:
        """Convert dictionary to credit transaction"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        transaction_date = date.fromisoformat(data['transaction_date'])
        post_date = date.fromisoformat(data['post_date'])
        
        return CreditTransaction(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            account_id=data['account_id'],
            transaction_id=data['transaction_id'],
            category=TransactionCategory(data['category']),
            amount=Money(Decimal(data['amount']), Currency[data['amount_currency']]),
            transaction_date=transaction_date,
            post_date=post_date,
            description=data['description'],
            eligible_for_grace=data.get('eligible_for_grace', True),
            grace_period_applies=data.get('grace_period_applies', False),
            interest_charged=Money(
                Decimal(data['interest_charged']),
                Currency[data['interest_currency']]
            ),
            statement_id=data.get('statement_id')
        )