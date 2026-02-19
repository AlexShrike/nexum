# Product Engine

The Product Engine enables defining banking products through configuration rather than code changes. This powerful module allows financial institutions to launch new savings, checking, loan, and credit line products without requiring software deployments.

## Overview

The Product Engine follows a template-based approach where banking products are defined as configurable entities with parameters for interest rates, fees, limits, and business rules. Once configured, products can be used to create customer accounts with consistent behavior.

## Key Concepts

### Product Templates
Products are templates that define:
- Interest calculation methods and rates
- Fee structures and conditions
- Account limits and restrictions
- Business rules and validation logic
- Lifecycle management (draft → active → suspended → retired)

### Configuration-Driven
Instead of hard-coding product rules, the engine uses configuration objects that can be modified without code changes:

```python
from core_banking.products import Product, InterestConfig, FeeConfig
from decimal import Decimal

# Define a high-yield savings product
savings_product = Product(
    name="High Yield Savings",
    product_type=ProductType.SAVINGS,
    currency=Currency.USD,
    interest_config=InterestConfig(
        annual_rate=Decimal("0.045"),  # 4.5% APY
        calculation=InterestCalculation.DAILY_COMPOUND,
        posting=InterestPosting.MONTHLY
    ),
    minimum_balance=Money(Decimal("1000.00"), Currency.USD),
    fees=[
        FeeConfig(
            name="Maintenance Fee",
            fee_type=FeeType.FIXED,
            amount=Money(Decimal("10.00"), Currency.USD),
            frequency=FeeFrequency.MONTHLY,
            condition=FeeCondition.BALANCE_BELOW,
            threshold=Money(Decimal("1000.00"), Currency.USD)
        )
    ]
)
```

## Core Classes

### Product

The main product definition class:

```python
from core_banking.products import Product, ProductStatus
from core_banking.currency import Currency
from core_banking.accounts import ProductType

@dataclass
class Product(StorageRecord):
    name: str
    description: str
    product_type: ProductType
    currency: Currency
    status: ProductStatus
    
    # Interest configuration
    interest_config: Optional[InterestConfig] = None
    
    # Fee configuration
    fees: List[FeeConfig] = field(default_factory=list)
    
    # Account limits
    minimum_balance: Optional[Money] = None
    maximum_balance: Optional[Money] = None
    daily_transaction_limit: Optional[Money] = None
    monthly_transaction_limit: Optional[Money] = None
    
    # Product-specific settings
    settings: Dict[str, Any] = field(default_factory=dict)
```

### InterestConfig

Defines how interest is calculated and posted:

```python
from core_banking.products import InterestConfig, InterestCalculation, InterestPosting

@dataclass
class InterestConfig:
    annual_rate: Decimal
    calculation: InterestCalculation
    posting: InterestPosting
    day_count: DayCountConvention = DayCountConvention.ACTUAL_365
    accrual_start: AccrualStart = AccrualStart.FROM_TRANSACTION
    minimum_balance_for_interest: Optional[Money] = None
    maximum_rate: Optional[Decimal] = None
    variable_rate_margin: Optional[Decimal] = None
```

### FeeConfig

Defines fees and when they apply:

```python
from core_banking.products import FeeConfig, FeeType, FeeFrequency

@dataclass 
class FeeConfig:
    name: str
    description: str
    fee_type: FeeType
    frequency: FeeFrequency
    condition: FeeCondition = FeeCondition.ALWAYS
    
    # Fee amount (for fixed fees)
    amount: Optional[Money] = None
    
    # Percentage (for percentage fees)
    percentage: Optional[Decimal] = None
    
    # Conditions
    threshold: Optional[Money] = None
    days: Optional[int] = None
    
    # Tiered fees
    tiers: List[FeeTier] = field(default_factory=list)
```

## Product Types

### Savings Products

High-yield savings with compound interest:

```python
def create_high_yield_savings() -> Product:
    return Product(
        name="High Yield Savings",
        description="Premium savings account with competitive rates",
        product_type=ProductType.SAVINGS,
        currency=Currency.USD,
        status=ProductStatus.ACTIVE,
        
        interest_config=InterestConfig(
            annual_rate=Decimal("0.045"),  # 4.5% APY
            calculation=InterestCalculation.DAILY_COMPOUND,
            posting=InterestPosting.MONTHLY,
            minimum_balance_for_interest=Money(Decimal("100.00"), Currency.USD)
        ),
        
        minimum_balance=Money(Decimal("100.00"), Currency.USD),
        maximum_balance=Money(Decimal("250000.00"), Currency.USD),
        daily_transaction_limit=Money(Decimal("5000.00"), Currency.USD),
        
        fees=[
            FeeConfig(
                name="Low Balance Fee",
                description="Monthly fee for balances under $1000",
                fee_type=FeeType.FIXED,
                frequency=FeeFrequency.MONTHLY,
                condition=FeeCondition.BALANCE_BELOW,
                amount=Money(Decimal("12.00"), Currency.USD),
                threshold=Money(Decimal("1000.00"), Currency.USD)
            ),
            FeeConfig(
                name="Excessive Transaction Fee",
                description="Fee for withdrawals over 6 per month",
                fee_type=FeeType.FIXED,
                frequency=FeeFrequency.PER_OCCURRENCE,
                amount=Money(Decimal("3.00"), Currency.USD)
            )
        ]
    )
```

### Checking Products

Basic checking with overdraft protection:

```python
def create_premium_checking() -> Product:
    return Product(
        name="Premium Checking",
        description="Full-service checking with overdraft protection",
        product_type=ProductType.CHECKING,
        currency=Currency.USD,
        status=ProductStatus.ACTIVE,
        
        interest_config=InterestConfig(
            annual_rate=Decimal("0.01"),  # 1% APY
            calculation=InterestCalculation.DAILY_ON_BALANCE,
            posting=InterestPosting.MONTHLY,
            minimum_balance_for_interest=Money(Decimal("1500.00"), Currency.USD)
        ),
        
        minimum_balance=Money(Decimal("0.00"), Currency.USD),
        daily_transaction_limit=Money(Decimal("2500.00"), Currency.USD),
        
        fees=[
            FeeConfig(
                name="Monthly Maintenance",
                fee_type=FeeType.FIXED,
                frequency=FeeFrequency.MONTHLY,
                amount=Money(Decimal("15.00"), Currency.USD),
                condition=FeeCondition.BALANCE_BELOW,
                threshold=Money(Decimal("1500.00"), Currency.USD)
            ),
            FeeConfig(
                name="Overdraft Fee",
                fee_type=FeeType.FIXED,
                frequency=FeeFrequency.PER_OCCURRENCE,
                amount=Money(Decimal("35.00"), Currency.USD),
                condition=FeeCondition.ALWAYS
            )
        ],
        
        settings={
            "overdraft_limit": Money(Decimal("500.00"), Currency.USD),
            "overdraft_grace_period_days": 1,
            "daily_overdraft_limit": Money(Decimal("200.00"), Currency.USD)
        }
    )
```

### Loan Products

Personal loan with equal installment payments:

```python
def create_personal_loan() -> Product:
    return Product(
        name="Personal Loan",
        description="Unsecured personal loan with fixed payments",
        product_type=ProductType.LOAN,
        currency=Currency.USD,
        status=ProductStatus.ACTIVE,
        
        interest_config=InterestConfig(
            annual_rate=Decimal("0.089"),  # 8.9% APR
            calculation=InterestCalculation.DAILY_ON_BALANCE,
            posting=InterestPosting.MONTHLY,
            day_count=DayCountConvention.ACTUAL_365,
            accrual_start=AccrualStart.FROM_DISBURSEMENT
        ),
        
        minimum_balance=Money(Decimal("1000.00"), Currency.USD),   # Min loan amount
        maximum_balance=Money(Decimal("50000.00"), Currency.USD),  # Max loan amount
        
        fees=[
            FeeConfig(
                name="Origination Fee",
                description="One-time loan origination fee",
                fee_type=FeeType.PERCENTAGE,
                frequency=FeeFrequency.ONE_TIME,
                percentage=Decimal("0.02"),  # 2%
                condition=FeeCondition.ALWAYS
            ),
            FeeConfig(
                name="Late Payment Fee",
                fee_type=FeeType.FIXED,
                frequency=FeeFrequency.PER_OCCURRENCE,
                condition=FeeCondition.PAYMENT_LATE,
                amount=Money(Decimal("39.00"), Currency.USD)
            )
        ],
        
        settings={
            "min_term_months": 12,
            "max_term_months": 60,
            "default_term_months": 36,
            "grace_period_days": 10,
            "allow_prepayment": True,
            "prepayment_penalty_rate": Decimal("0.00")
        }
    )
```

### Credit Line Products

Revolving credit line with grace periods:

```python
def create_personal_line_of_credit() -> Product:
    return Product(
        name="Personal Line of Credit",
        description="Revolving credit line with flexible payments",
        product_type=ProductType.CREDIT_LINE,
        currency=Currency.USD,
        status=ProductStatus.ACTIVE,
        
        interest_config=InterestConfig(
            annual_rate=Decimal("0.129"),  # 12.9% APR
            calculation=InterestCalculation.DAILY_ON_BALANCE,
            posting=InterestPosting.MONTHLY,
            day_count=DayCountConvention.ACTUAL_365
        ),
        
        maximum_balance=Money(Decimal("25000.00"), Currency.USD),  # Credit limit
        
        fees=[
            FeeConfig(
                name="Annual Fee",
                fee_type=FeeType.FIXED,
                frequency=FeeFrequency.ANNUALLY,
                amount=Money(Decimal("50.00"), Currency.USD)
            ),
            FeeConfig(
                name="Over-Limit Fee",
                fee_type=FeeType.FIXED,
                frequency=FeeFrequency.PER_OCCURRENCE,
                condition=FeeCondition.OVER_LIMIT,
                amount=Money(Decimal("25.00"), Currency.USD)
            ),
            FeeConfig(
                name="Late Payment Fee",
                fee_type=FeeType.TIERED,
                frequency=FeeFrequency.PER_OCCURRENCE,
                condition=FeeCondition.PAYMENT_LATE,
                tiers=[
                    FeeTier(
                        threshold=Money(Decimal("100.00"), Currency.USD),
                        amount=Money(Decimal("15.00"), Currency.USD)
                    ),
                    FeeTier(
                        threshold=Money(Decimal("1000.00"), Currency.USD),
                        amount=Money(Decimal("25.00"), Currency.USD)
                    ),
                    FeeTier(
                        threshold=None,  # No upper limit
                        amount=Money(Decimal("39.00"), Currency.USD)
                    )
                ]
            )
        ],
        
        settings={
            "grace_period_type": GracePeriodType.PURCHASES_ONLY,
            "grace_period_days": 25,
            "minimum_payment_type": MinPaymentType.PERCENTAGE_OR_MINIMUM,
            "minimum_payment_percentage": Decimal("0.02"),  # 2%
            "minimum_payment_amount": Money(Decimal("25.00"), Currency.USD),
            "statement_cycle_days": 30
        }
    )
```

## Interest Calculation Types

### Daily Compound Interest

```python
def calculate_daily_compound_interest(
    principal: Money,
    annual_rate: Decimal,
    days: int
) -> Money:
    """Calculate compound interest compounded daily"""
    
    daily_rate = annual_rate / 365
    compound_factor = (1 + daily_rate) ** days
    
    interest = principal * (compound_factor - 1)
    return Money(interest.amount.quantize(Decimal('0.01')), principal.currency)

# Usage in product
interest_config = InterestConfig(
    annual_rate=Decimal("0.045"),
    calculation=InterestCalculation.DAILY_COMPOUND,
    posting=InterestPosting.MONTHLY,
    day_count=DayCountConvention.ACTUAL_365
)
```

### Simple Interest

```python
def calculate_simple_interest(
    principal: Money,
    annual_rate: Decimal,
    days: int,
    day_count: DayCountConvention = DayCountConvention.ACTUAL_365
) -> Money:
    """Calculate simple interest"""
    
    days_in_year = 365 if day_count == DayCountConvention.ACTUAL_365 else 360
    interest = principal * annual_rate * (days / days_in_year)
    
    return Money(interest.amount.quantize(Decimal('0.01')), principal.currency)
```

## Fee Configuration

### Tiered Fee Structure

```python
from core_banking.products import FeeTier

# Create tiered overdraft fee
tiered_fee = FeeConfig(
    name="Tiered Overdraft Fee",
    description="Overdraft fee based on amount",
    fee_type=FeeType.TIERED,
    frequency=FeeFrequency.PER_OCCURRENCE,
    condition=FeeCondition.ALWAYS,
    tiers=[
        FeeTier(
            threshold=Money(Decimal("50.00"), Currency.USD),
            amount=Money(Decimal("15.00"), Currency.USD)
        ),
        FeeTier(
            threshold=Money(Decimal("100.00"), Currency.USD), 
            amount=Money(Decimal("25.00"), Currency.USD)
        ),
        FeeTier(
            threshold=None,  # All amounts above $100
            amount=Money(Decimal("35.00"), Currency.USD)
        )
    ]
)
```

### Conditional Fees

```python
# Monthly maintenance fee waived if balance > $1500
maintenance_fee = FeeConfig(
    name="Monthly Maintenance",
    fee_type=FeeType.FIXED,
    frequency=FeeFrequency.MONTHLY,
    condition=FeeCondition.BALANCE_BELOW,
    amount=Money(Decimal("12.00"), Currency.USD),
    threshold=Money(Decimal("1500.00"), Currency.USD)
)

# Early closure fee if account closed within 90 days
early_closure_fee = FeeConfig(
    name="Early Closure Fee",
    fee_type=FeeType.FIXED,
    frequency=FeeFrequency.ONE_TIME,
    condition=FeeCondition.CLOSED_WITHIN_DAYS,
    amount=Money(Decimal("25.00"), Currency.USD),
    days=90
)
```

## Product Management

### ProductEngine Class

```python
from core_banking.products import ProductEngine

class ProductEngine:
    def __init__(self, storage: StorageInterface):
        self.storage = storage
    
    def create_product(self, product: Product) -> Product:
        """Create new product"""
        product.id = str(uuid.uuid4())
        product.status = ProductStatus.DRAFT
        product.created_at = datetime.now(timezone.utc)
        
        self.storage.store(product)
        return product
    
    def activate_product(self, product_id: str) -> Product:
        """Activate product for use"""
        product = self.get_product(product_id)
        
        # Validate product configuration
        self.validate_product(product)
        
        product.status = ProductStatus.ACTIVE
        product.activated_at = datetime.now(timezone.utc)
        
        self.storage.update(product_id, product)
        return product
    
    def calculate_interest(self, product: Product, balance: Money, days: int) -> Money:
        """Calculate interest based on product configuration"""
        
        if not product.interest_config or balance.is_zero():
            return Money(Decimal("0"), balance.currency)
        
        config = product.interest_config
        
        if config.calculation == InterestCalculation.SIMPLE:
            return self.calculate_simple_interest(balance, config.annual_rate, days, config.day_count)
        elif config.calculation == InterestCalculation.DAILY_COMPOUND:
            return self.calculate_compound_interest(balance, config.annual_rate, days)
        elif config.calculation == InterestCalculation.DAILY_ON_BALANCE:
            return self.calculate_daily_balance_interest(balance, config.annual_rate, days)
```

## Account Creation with Products

```python
from core_banking.accounts import AccountManager
from core_banking.products import ProductEngine

def create_account_from_product(
    customer_id: str, 
    product_id: str,
    account_name: str,
    initial_deposit: Optional[Money] = None
) -> Account:
    
    # Get product template
    product = product_engine.get_product(product_id)
    
    if product.status != ProductStatus.ACTIVE:
        raise ValueError(f"Product {product_id} is not active")
    
    # Create account with product settings
    account = Account(
        customer_id=customer_id,
        product_type=product.product_type,
        currency=product.currency,
        name=account_name,
        product_id=product_id,
        
        # Apply product limits
        minimum_balance=product.minimum_balance,
        daily_transaction_limit=product.daily_transaction_limit,
        monthly_transaction_limit=product.monthly_transaction_limit,
        
        # Apply interest settings
        interest_rate=product.interest_config.annual_rate if product.interest_config else None,
        
        # Copy product settings
        settings=product.settings.copy()
    )
    
    # Apply product fees to account
    if product.fees:
        account.fee_schedules = [
            FeeSchedule.from_fee_config(fee_config) 
            for fee_config in product.fees
        ]
    
    return account_manager.create_account(account)
```

## Product Versioning

Products support versioning for regulatory compliance:

```python
@dataclass
class ProductVersion:
    product_id: str
    version: int
    effective_date: datetime
    expiry_date: Optional[datetime] = None
    changes: List[str] = field(default_factory=list)
    approved_by: Optional[str] = None

def create_product_version(product: Product, changes: List[str]) -> ProductVersion:
    """Create new version when product changes"""
    
    current_version = get_latest_version(product.id)
    
    # Archive current version
    if current_version:
        current_version.expiry_date = datetime.now(timezone.utc)
        storage.update(current_version.id, current_version)
    
    # Create new version
    new_version = ProductVersion(
        product_id=product.id,
        version=(current_version.version + 1) if current_version else 1,
        effective_date=datetime.now(timezone.utc),
        changes=changes
    )
    
    return new_version
```

## Regulatory Compliance

Products track regulatory requirements:

```python
@dataclass
class ComplianceSettings:
    truth_in_savings_required: bool = False
    truth_in_lending_required: bool = False
    regulation_dd_disclosures: List[str] = field(default_factory=list)
    regulation_z_disclosures: List[str] = field(default_factory=list)
    fdic_insured: bool = True
    maximum_fdic_coverage: Money = Money(Decimal("250000.00"), Currency.USD)

# Add to product
product.compliance_settings = ComplianceSettings(
    truth_in_savings_required=True,
    regulation_dd_disclosures=[
        "interest_rate_disclosure",
        "fee_schedule_disclosure",
        "minimum_balance_disclosure"
    ]
)
```

## Testing Product Configuration

```python
def test_savings_product_interest_calculation():
    """Test compound interest calculation for savings product"""
    
    product = create_high_yield_savings()
    engine = ProductEngine(InMemoryStorage())
    
    balance = Money(Decimal("10000.00"), Currency.USD)
    days = 30
    
    interest = engine.calculate_interest(product, balance, days)
    
    # Expected: ~$37.00 for 4.5% APY compounded daily for 30 days
    expected = Money(Decimal("37.00"), Currency.USD)
    assert abs(interest.amount - expected.amount) < Decimal("1.00")

def test_fee_application():
    """Test fee calculation based on conditions"""
    
    product = create_premium_checking()
    balance = Money(Decimal("500.00"), Currency.USD)  # Below $1500 threshold
    
    # Should apply monthly maintenance fee
    applicable_fees = engine.get_applicable_fees(product, balance)
    
    maintenance_fees = [f for f in applicable_fees if f.name == "Monthly Maintenance"]
    assert len(maintenance_fees) == 1
    assert maintenance_fees[0].amount == Money(Decimal("15.00"), Currency.USD)
```

The Product Engine provides powerful configuration capabilities that enable financial institutions to launch new products quickly while maintaining consistency and regulatory compliance across their product portfolio.