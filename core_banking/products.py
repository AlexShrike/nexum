"""
Product Engine Module

Configurable product template system that enables defining loan and deposit
products through configuration instead of code changes. Inspired by Oradian's
"Loan and Deposit Product Engines."
"""

from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
import uuid

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType
from .accounts import ProductType, AccountManager, Account


class ProductStatus(Enum):
    """Product lifecycle status"""
    DRAFT = "draft"         # Being configured, not available for accounts
    ACTIVE = "active"       # Available for new accounts
    SUSPENDED = "suspended" # Temporarily unavailable for new accounts
    RETIRED = "retired"     # Permanently unavailable for new accounts


class InterestCalculation(Enum):
    """Interest calculation methods"""
    SIMPLE = "simple"                    # Simple interest
    DAILY_COMPOUND = "daily_compound"    # Compound daily
    MONTHLY_COMPOUND = "monthly_compound" # Compound monthly
    DAILY_ON_BALANCE = "daily_on_balance" # Daily on outstanding balance
    FLAT = "flat"                        # Flat rate (for loans)


class InterestPosting(Enum):
    """Interest posting frequencies"""
    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"
    AT_MATURITY = "at_maturity"


class DayCountConvention(Enum):
    """Day count conventions for interest calculations"""
    ACTUAL_365 = "actual_365"  # Actual days / 365
    ACTUAL_360 = "actual_360"  # Actual days / 360
    THIRTY_360 = "thirty_360"  # 30 days per month / 360


class AccrualStart(Enum):
    """When interest accrual begins"""
    FROM_DISBURSEMENT = "from_disbursement"   # From loan disbursement
    FROM_FIRST_PAYMENT = "from_first_payment" # From first payment date
    FROM_TRANSACTION = "from_transaction"     # From each transaction


class FeeType(Enum):
    """Fee calculation types"""
    FIXED = "fixed"         # Fixed amount
    PERCENTAGE = "percentage" # Percentage of amount
    TIERED = "tiered"       # Tiered based on balance/amount


class FeeFrequency(Enum):
    """Fee charging frequencies"""
    ONE_TIME = "one_time"           # Charged once
    MONTHLY = "monthly"             # Charged monthly
    ANNUALLY = "annually"           # Charged annually
    PER_OCCURRENCE = "per_occurrence" # Charged each time condition is met


class FeeCondition(Enum):
    """Conditions for fee application"""
    ALWAYS = "always"                     # Always applied
    PAYMENT_LATE = "payment_late"         # Applied when payment is late
    OVER_LIMIT = "over_limit"             # Applied when over limit
    CLOSED_EARLY = "closed_early"         # Applied when closed early
    BALANCE_BELOW = "balance_below"       # Applied when balance below threshold
    CLOSED_WITHIN_DAYS = "closed_within_days" # Applied when closed within X days


class FeeAmountType(Enum):
    """How fee amount is specified"""
    FIXED_AMOUNT = "fixed_amount"    # Fixed money amount
    PERCENTAGE = "percentage"        # Percentage of transaction/balance


class GracePeriodType(Enum):
    """Types of grace periods for credit products"""
    PURCHASES_ONLY = "purchases_only"     # Grace only for purchases
    ALL_TRANSACTIONS = "all_transactions" # Grace for all transactions
    NONE = "none"                         # No grace period


class MinPaymentType(Enum):
    """Minimum payment calculation types"""
    FIXED_AMOUNT = "fixed_amount"           # Fixed minimum amount
    PERCENTAGE = "percentage"               # Percentage of balance
    PERCENTAGE_OR_FIXED = "percentage_or_fixed" # Higher of percentage or fixed


class AmortizationMethod(Enum):
    """Loan amortization methods"""
    EQUAL_INSTALLMENT = "equal_installment"   # Equal monthly payments
    EQUAL_PRINCIPAL = "equal_principal"       # Equal principal payments
    INTEREST_ONLY = "interest_only"           # Interest only payments
    BULLET = "bullet"                         # Principal due at maturity


@dataclass
class FeeTier:
    """Tiered fee structure"""
    min_amount: Money
    max_amount: Optional[Money]
    fee_amount: Money
    
    def applies_to(self, amount: Money) -> bool:
        """Check if this tier applies to the given amount"""
        if amount.currency != self.min_amount.currency:
            return False
        if amount < self.min_amount:
            return False
        if self.max_amount and amount > self.max_amount:
            return False
        return True


@dataclass
class FeeConfig(StorageRecord):
    """Fee configuration"""
    name: str
    fee_type: FeeType
    frequency: FeeFrequency
    condition: FeeCondition = FeeCondition.ALWAYS
    
    # Fixed amount fee
    amount: Optional[Money] = None
    
    # Percentage fee
    percentage: Optional[Decimal] = None
    
    # Tiered fees
    tiers: List[FeeTier] = field(default_factory=list)
    
    # Conditional parameters
    condition_value: Optional[int] = None  # e.g., days for CLOSED_WITHIN_DAYS
    waive_if_balance_above: Optional[Money] = None
    
    # Tax and other settings
    tax_applicable: bool = False
    
    def calculate_fee(self, amount: Money, context: Dict = None) -> Money:
        """Calculate fee amount based on configuration"""
        context = context or {}
        
        # Check waive condition
        if (self.waive_if_balance_above and 
            context.get('balance') and 
            context['balance'] >= self.waive_if_balance_above):
            return Money(Decimal('0'), amount.currency)
        
        if self.fee_type == FeeType.FIXED:
            if not self.amount:
                raise ValueError("Fixed fee must have amount specified")
            if self.amount.currency != amount.currency:
                raise ValueError("Fee currency must match amount currency")
            return self.amount
        
        elif self.fee_type == FeeType.PERCENTAGE:
            if not self.percentage:
                raise ValueError("Percentage fee must have percentage specified")
            return amount * self.percentage
        
        elif self.fee_type == FeeType.TIERED:
            for tier in self.tiers:
                if tier.applies_to(amount):
                    return tier.fee_amount
            # No tier found - no fee
            return Money(Decimal('0'), amount.currency)
        
        return Money(Decimal('0'), amount.currency)


@dataclass
class InterestConfig:
    """Interest configuration for products"""
    # Rate configuration
    rate: Optional[Decimal] = None  # Fixed rate
    rate_range: Optional[Tuple[Decimal, Decimal]] = None  # Min/max for risk-based pricing
    
    # Calculation settings
    calculation_method: InterestCalculation = InterestCalculation.SIMPLE
    day_count_convention: DayCountConvention = DayCountConvention.ACTUAL_365
    posting_frequency: InterestPosting = InterestPosting.MONTHLY
    accrual_start: AccrualStart = AccrualStart.FROM_DISBURSEMENT
    
    def get_rate(self, risk_score: Optional[Decimal] = None) -> Decimal:
        """Get interest rate, optionally adjusted for risk"""
        if self.rate:
            return self.rate
        
        if self.rate_range:
            if risk_score is None:
                # Return minimum rate if no risk score provided
                return self.rate_range[0]
            
            # Risk score should be 0-1, map to rate range
            min_rate, max_rate = self.rate_range
            rate_spread = max_rate - min_rate
            return min_rate + (rate_spread * risk_score)
        
        raise ValueError("Interest configuration must have either rate or rate_range")


@dataclass
class LimitConfig:
    """Transaction and balance limits configuration"""
    min_opening_balance: Optional[Money] = None
    min_balance: Optional[Money] = None
    max_balance: Optional[Money] = None
    min_transaction: Optional[Money] = None
    max_transaction: Optional[Money] = None
    daily_withdrawal_limit: Optional[Money] = None
    daily_withdrawal_count: Optional[int] = None
    monthly_withdrawal_limit: Optional[Money] = None


@dataclass
class TermConfig:
    """Term/maturity configuration for loans and time deposits"""
    min_term_months: Optional[int] = None
    max_term_months: Optional[int] = None
    min_amount: Optional[Money] = None
    max_amount: Optional[Money] = None
    prepayment_allowed: bool = True
    prepayment_penalty_rate: Optional[Decimal] = None
    grace_period_days: int = 0
    amortization_methods: List[AmortizationMethod] = field(default_factory=list)
    payment_frequencies: List[int] = field(default_factory=lambda: [1])  # Monthly = 1


@dataclass
class CreditConfig:
    """Credit-specific configuration for credit lines"""
    credit_limit_range: Optional[Tuple[Money, Money]] = None
    grace_period_days: int = 0
    grace_period_type: GracePeriodType = GracePeriodType.NONE
    statement_cycle_days: int = 30
    payment_due_days: int = 22
    minimum_payment_type: MinPaymentType = MinPaymentType.PERCENTAGE
    minimum_payment_percentage: Decimal = Decimal('0.05')  # 5%
    minimum_payment_fixed: Optional[Money] = None
    overlimit_allowed: bool = False
    overlimit_tolerance_percentage: Decimal = Decimal('0')  # 0%


@dataclass
class WithdrawalLimits:
    """Withdrawal limits for savings products"""
    max_per_day: Optional[int] = None
    max_amount_per_day: Optional[Money] = None
    max_per_month: Optional[int] = None
    max_amount_per_month: Optional[Money] = None


@dataclass
class Product(StorageRecord):
    """Product template/definition"""
    name: str
    description: str
    product_type: ProductType
    product_code: str  # Unique identifier
    currency: Currency
    status: ProductStatus = ProductStatus.DRAFT
    version: int = 1
    effective_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    # Configuration components
    interest_config: Optional[InterestConfig] = None
    fees: List[FeeConfig] = field(default_factory=list)
    limit_config: Optional[LimitConfig] = None
    term_config: Optional[TermConfig] = None  # For loans and time deposits
    credit_config: Optional[CreditConfig] = None  # For credit lines
    
    # Product-specific settings
    dormancy_days: Optional[int] = None  # Days before account becomes dormant
    withdrawal_limits: Optional[WithdrawalLimits] = None  # For savings
    
    def __post_init__(self):
        # Validate product type specific configurations
        if self.product_type == ProductType.CREDIT_LINE and not self.credit_config:
            self.credit_config = CreditConfig()
        
        if self.product_type == ProductType.LOAN and not self.term_config:
            self.term_config = TermConfig()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage, handling enums properly"""
        result = super().to_dict()
        
        # Convert enums to their string values
        if hasattr(self, 'product_type') and self.product_type:
            result['product_type'] = self.product_type.value
        if hasattr(self, 'status') and self.status:
            result['status'] = self.status.value
        if hasattr(self, 'currency') and self.currency:
            result['currency'] = self.currency.code
            
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Product':
        """Create instance from dictionary, handling enum conversions"""
        # Convert string values back to enums
        if 'product_type' in data and isinstance(data['product_type'], str):
            data['product_type'] = ProductType(data['product_type'])
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = ProductStatus(data['status'])
        if 'currency' in data and isinstance(data['currency'], str):
            from .currency import Currency
            # Find currency by code
            for curr in Currency:
                if curr.code == data['currency']:
                    data['currency'] = curr
                    break
        
        return super().from_dict(data)
    
    def is_available_for_accounts(self) -> bool:
        """Check if product is available for creating new accounts"""
        if self.status != ProductStatus.ACTIVE:
            return False
        
        now = datetime.now(timezone.utc)
        if self.effective_date and now < self.effective_date:
            return False
        
        if self.end_date and now > self.end_date:
            return False
        
        return True
    
    def get_interest_rate(self, risk_score: Optional[Decimal] = None) -> Optional[Decimal]:
        """Get interest rate for this product"""
        if not self.interest_config:
            return None
        return self.interest_config.get_rate(risk_score)
    
    def calculate_fees(self, fee_name: str, amount: Money, context: Dict = None) -> Money:
        """Calculate fee amount for specific fee type"""
        for fee in self.fees:
            if fee.name == fee_name:
                return fee.calculate_fee(amount, context)
        return Money(Decimal('0'), amount.currency)
    
    def validate_account_parameters(self, 
                                  opening_balance: Money,
                                  credit_limit: Optional[Money] = None) -> List[str]:
        """Validate account parameters against product configuration"""
        errors = []
        
        # Currency validation
        if opening_balance.currency != self.currency:
            errors.append(f"Opening balance currency {opening_balance.currency.code} "
                         f"does not match product currency {self.currency.code}")
        else:
            # Balance limits (only check if currencies match)
            if self.limit_config:
                if (self.limit_config.min_opening_balance and 
                    opening_balance < self.limit_config.min_opening_balance):
                    errors.append(f"Opening balance {opening_balance.to_string()} is below "
                                 f"minimum {self.limit_config.min_opening_balance.to_string()}")
                
                if (self.limit_config.max_balance and 
                    opening_balance > self.limit_config.max_balance):
                    errors.append(f"Opening balance {opening_balance.to_string()} exceeds "
                                 f"maximum {self.limit_config.max_balance.to_string()}")
        
        # Credit limit validation for credit products
        if self.product_type == ProductType.CREDIT_LINE:
            if credit_limit and self.credit_config and self.credit_config.credit_limit_range:
                min_limit, max_limit = self.credit_config.credit_limit_range
                if credit_limit < min_limit or credit_limit > max_limit:
                    errors.append(f"Credit limit {credit_limit.to_string()} is outside "
                                 f"allowed range {min_limit.to_string()} - {max_limit.to_string()}")
        
        return errors


class ProductEngine:
    """Manager class for product definitions and operations"""
    
    def __init__(self, storage: StorageInterface, audit_trail: AuditTrail):
        self.storage = storage
        self.audit_trail = audit_trail
        self.table_name = "products"
    
    def create_product(self,
                      name: str,
                      product_type: ProductType,
                      currency: Currency,
                      product_code: Optional[str] = None,
                      description: str = "",
                      **kwargs) -> Product:
        """Create a new product definition"""
        
        # Generate product code if not provided
        if not product_code:
            product_code = f"{product_type.value.upper()}_{uuid.uuid4().hex[:8]}"
        
        # Check for unique product code
        existing = self.get_product_by_code(product_code)
        if existing:
            raise ValueError(f"Product code {product_code} already exists")
        
        now = datetime.now(timezone.utc)
        product_id = str(uuid.uuid4())
        
        # Create product with all provided parameters
        product = Product(
            id=product_id,
            created_at=now,
            updated_at=now,
            name=name,
            description=description,
            product_type=product_type,
            product_code=product_code,
            currency=currency,
            **kwargs
        )
        
        # Save to storage
        self.storage.save(self.table_name, product_id, product.to_dict())
        
        # Audit trail
        self.audit_trail.log_event(
            event_type=AuditEventType.PRODUCT_CREATED,
            entity_type="product",
            entity_id=product_id,
            metadata={
                "product_code": product_code,
                "name": name,
                "product_type": product_type.value
            }
        )
        
        return product
    
    def update_product(self, product_id: str, **kwargs) -> Product:
        """Update product (creates new version)"""
        current_product = self.get_product(product_id)
        if not current_product:
            raise ValueError(f"Product {product_id} not found")
        
        # Create new version
        now = datetime.now(timezone.utc)
        new_version = current_product.version + 1
        
        # Update fields
        updated_data = current_product.to_dict()
        updated_data.update(kwargs)
        updated_data.update({
            'version': new_version,
            'updated_at': now.isoformat()
        })
        
        product = Product.from_dict(updated_data)
        
        # Save updated product
        self.storage.save(self.table_name, product_id, product.to_dict())
        
        # Audit trail
        self.audit_trail.log_event(
            event_type=AuditEventType.PRODUCT_UPDATED,
            entity_type="product", 
            entity_id=product_id,
            metadata={
                "old_version": current_product.version,
                "new_version": new_version,
                "changes": kwargs
            }
        )
        
        return product
    
    def get_product(self, product_id: str) -> Optional[Product]:
        """Get product by ID"""
        data = self.storage.load(self.table_name, product_id)
        if data:
            return Product.from_dict(data)
        return None
    
    def get_product_by_code(self, product_code: str) -> Optional[Product]:
        """Get product by unique code"""
        products = self.storage.find(self.table_name, {"product_code": product_code})
        if products:
            return Product.from_dict(products[0])
        return None
    
    def list_products(self, 
                     product_type: Optional[ProductType] = None,
                     status: Optional[ProductStatus] = None) -> List[Product]:
        """List products with optional filters"""
        filters = {}
        if product_type:
            filters["product_type"] = product_type.value
        if status:
            filters["status"] = status.value
        
        products_data = self.storage.find(self.table_name, filters)
        return [Product.from_dict(data) for data in products_data]
    
    def activate_product(self, product_id: str) -> Product:
        """Activate a product"""
        return self.update_product(product_id, 
                                 status=ProductStatus.ACTIVE,
                                 effective_date=datetime.now(timezone.utc))
    
    def suspend_product(self, product_id: str) -> Product:
        """Suspend a product"""
        product = self.update_product(product_id, status=ProductStatus.SUSPENDED)
        
        self.audit_trail.log_event(
            event_type=AuditEventType.PRODUCT_SUSPENDED,
            entity_type="product",
            entity_id=product_id,
            metadata={"product_code": product.product_code}
        )
        
        return product
    
    def retire_product(self, product_id: str) -> Product:
        """Retire a product"""
        product = self.update_product(product_id, 
                                    status=ProductStatus.RETIRED,
                                    end_date=datetime.now(timezone.utc))
        
        self.audit_trail.log_event(
            event_type=AuditEventType.PRODUCT_RETIRED,
            entity_type="product",
            entity_id=product_id,
            metadata={"product_code": product.product_code}
        )
        
        return product
    
    def validate_account_against_product(self, 
                                       account: Account, 
                                       product: Product) -> List[str]:
        """Validate account against product configuration"""
        errors = []
        
        # Basic validations
        if account.currency != product.currency:
            errors.append("Account currency does not match product currency")
        
        if account.product_type != product.product_type:
            errors.append("Account product type does not match product product type")
        
        # Additional validations would check limits, fees, etc.
        return errors
    
    def create_account_from_product(self,
                                  product_id: str,
                                  customer_id: str,
                                  account_manager: AccountManager,
                                  opening_balance: Money,
                                  **overrides) -> Account:
        """Create account using product template with defaults"""
        product = self.get_product(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")
        
        if not product.is_available_for_accounts():
            raise ValueError(f"Product {product.product_code} is not available for new accounts")
        
        # Validate parameters against product
        validation_errors = product.validate_account_parameters(opening_balance)
        if validation_errors:
            raise ValueError(f"Account validation failed: {'; '.join(validation_errors)}")
        
        # Build account parameters from product
        account_params = {
            "customer_id": customer_id,
            "product_type": product.product_type,
            "currency": product.currency,
            "name": f"{product.name} - {customer_id}",
            "state": "active"
        }
        
        # Add product-specific defaults
        if product.interest_config:
            account_params["interest_rate"] = product.get_interest_rate()
        
        if product.limit_config:
            if product.limit_config.min_balance:
                account_params["minimum_balance"] = product.limit_config.min_balance
            if product.limit_config.daily_withdrawal_limit:
                account_params["daily_transaction_limit"] = product.limit_config.daily_withdrawal_limit
        
        if product.credit_config and product.credit_config.credit_limit_range:
            # Use minimum credit limit as default
            min_limit, _ = product.credit_config.credit_limit_range
            account_params["credit_limit"] = min_limit
        
        # Apply any overrides
        account_params.update(overrides)
        
        # Create account using account manager
        account = account_manager.create_account(**account_params)
        
        # Audit trail
        self.audit_trail.log_event(
            event_type=AuditEventType.ACCOUNT_CREATED,
            entity_type="account",
            entity_id=account.id,
            metadata={
                "product_id": product_id,
                "product_code": product.product_code,
                "customer_id": customer_id,
                "opening_balance": opening_balance.to_string()
            }
        )
        
        return account
    
    def calculate_fees(self, 
                      product: Product, 
                      fee_name: str,
                      amount: Money,
                      context: Dict = None) -> Money:
        """Calculate applicable fees for a product"""
        return product.calculate_fees(fee_name, amount, context)
    
    def get_interest_rate(self, 
                         product: Product, 
                         risk_score: Optional[Decimal] = None) -> Optional[Decimal]:
        """Get interest rate for product, possibly risk-adjusted"""
        return product.get_interest_rate(risk_score)