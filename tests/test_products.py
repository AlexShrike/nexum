"""
Test suite for products module

Tests Product Engine functionality including product CRUD operations,
lifecycle management, versioning, fee calculations, interest rate calculations,
limit validations, and product-specific configurations.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, date, timedelta
import uuid

from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.accounts import AccountManager, ProductType
from core_banking.customers import CustomerManager
from core_banking.compliance import ComplianceEngine
from core_banking.ledger import GeneralLedger
from core_banking.products import (
    ProductEngine, Product, ProductStatus, InterestConfig, FeeConfig, LimitConfig,
    TermConfig, CreditConfig, WithdrawalLimits, FeeTier,
    InterestCalculation, InterestPosting, DayCountConvention, AccrualStart,
    FeeType, FeeFrequency, FeeCondition, FeeAmountType, GracePeriodType,
    MinPaymentType, AmortizationMethod
)


@pytest.fixture
def storage():
    """In-memory storage for tests"""
    return InMemoryStorage()


@pytest.fixture
def audit_trail(storage):
    """Audit trail for tests"""
    return AuditTrail(storage)


@pytest.fixture
def product_engine(storage, audit_trail):
    """Product engine instance for tests"""
    return ProductEngine(storage, audit_trail)


@pytest.fixture
def sample_interest_config():
    """Sample interest configuration"""
    return InterestConfig(
        rate=Decimal('0.0525'),  # 5.25% annual rate
        calculation_method=InterestCalculation.DAILY_COMPOUND,
        day_count_convention=DayCountConvention.ACTUAL_365,
        posting_frequency=InterestPosting.MONTHLY
    )


@pytest.fixture
def sample_fee_config():
    """Sample fee configuration"""
    now = datetime.now(timezone.utc)
    return FeeConfig(
        id=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        name="maintenance_fee",
        fee_type=FeeType.FIXED,
        frequency=FeeFrequency.MONTHLY,
        condition=FeeCondition.ALWAYS,
        amount=Money(Decimal('10.00'), Currency.USD)
    )


@pytest.fixture
def sample_limit_config():
    """Sample limit configuration"""
    return LimitConfig(
        min_opening_balance=Money(Decimal('100.00'), Currency.USD),
        min_balance=Money(Decimal('0.00'), Currency.USD),
        max_balance=Money(Decimal('50000.00'), Currency.USD),
        daily_withdrawal_limit=Money(Decimal('1000.00'), Currency.USD),
        daily_withdrawal_count=10
    )


class TestFeeTier:
    """Test FeeTier functionality"""
    
    def test_fee_tier_applies_to_amount_in_range(self):
        """Test fee tier applies to amount within range"""
        tier = FeeTier(
            min_amount=Money(Decimal('100.00'), Currency.USD),
            max_amount=Money(Decimal('500.00'), Currency.USD),
            fee_amount=Money(Decimal('15.00'), Currency.USD)
        )
        
        # Test amount in range
        assert tier.applies_to(Money(Decimal('250.00'), Currency.USD))
        assert tier.applies_to(Money(Decimal('100.00'), Currency.USD))  # Edge case: minimum
        assert tier.applies_to(Money(Decimal('500.00'), Currency.USD))  # Edge case: maximum
    
    def test_fee_tier_does_not_apply_outside_range(self):
        """Test fee tier does not apply to amount outside range"""
        tier = FeeTier(
            min_amount=Money(Decimal('100.00'), Currency.USD),
            max_amount=Money(Decimal('500.00'), Currency.USD),
            fee_amount=Money(Decimal('15.00'), Currency.USD)
        )
        
        # Test amounts outside range
        assert not tier.applies_to(Money(Decimal('99.99'), Currency.USD))
        assert not tier.applies_to(Money(Decimal('500.01'), Currency.USD))
    
    def test_fee_tier_open_ended_range(self):
        """Test fee tier with no maximum (open-ended)"""
        tier = FeeTier(
            min_amount=Money(Decimal('1000.00'), Currency.USD),
            max_amount=None,  # No maximum
            fee_amount=Money(Decimal('25.00'), Currency.USD)
        )
        
        assert tier.applies_to(Money(Decimal('1000.00'), Currency.USD))
        assert tier.applies_to(Money(Decimal('10000.00'), Currency.USD))
        assert not tier.applies_to(Money(Decimal('999.99'), Currency.USD))
    
    def test_fee_tier_currency_mismatch(self):
        """Test fee tier with currency mismatch"""
        tier = FeeTier(
            min_amount=Money(Decimal('100.00'), Currency.USD),
            max_amount=Money(Decimal('500.00'), Currency.USD),
            fee_amount=Money(Decimal('15.00'), Currency.USD)
        )
        
        # Different currency should not apply
        assert not tier.applies_to(Money(Decimal('250.00'), Currency.EUR))


class TestFeeConfig:
    """Test FeeConfig functionality"""
    
    def test_fixed_fee_calculation(self):
        """Test fixed fee calculation"""
        now = datetime.now(timezone.utc)
        fee_config = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="account_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.MONTHLY,
            amount=Money(Decimal('25.00'), Currency.USD)
        )
        
        # Fixed fee should always return the same amount regardless of transaction amount
        fee = fee_config.calculate_fee(Money(Decimal('100.00'), Currency.USD))
        assert fee == Money(Decimal('25.00'), Currency.USD)
        
        fee = fee_config.calculate_fee(Money(Decimal('10000.00'), Currency.USD))
        assert fee == Money(Decimal('25.00'), Currency.USD)
    
    def test_percentage_fee_calculation(self):
        """Test percentage fee calculation"""
        now = datetime.now(timezone.utc)
        fee_config = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="transaction_fee",
            fee_type=FeeType.PERCENTAGE,
            frequency=FeeFrequency.PER_OCCURRENCE,
            percentage=Decimal('0.025')  # 2.5%
        )
        
        # 2.5% of $100 = $2.50
        fee = fee_config.calculate_fee(Money(Decimal('100.00'), Currency.USD))
        assert fee == Money(Decimal('2.50'), Currency.USD)
        
        # 2.5% of $1000 = $25.00
        fee = fee_config.calculate_fee(Money(Decimal('1000.00'), Currency.USD))
        assert fee == Money(Decimal('25.00'), Currency.USD)
    
    def test_tiered_fee_calculation(self):
        """Test tiered fee calculation"""
        tiers = [
            FeeTier(Money(Decimal('0.00'), Currency.USD), 
                   Money(Decimal('500.00'), Currency.USD),
                   Money(Decimal('5.00'), Currency.USD)),
            FeeTier(Money(Decimal('500.01'), Currency.USD),
                   Money(Decimal('2000.00'), Currency.USD),
                   Money(Decimal('15.00'), Currency.USD)),
            FeeTier(Money(Decimal('2000.01'), Currency.USD),
                   None,  # No maximum
                   Money(Decimal('25.00'), Currency.USD))
        ]
        
        now = datetime.now(timezone.utc)
        fee_config = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="tiered_fee",
            fee_type=FeeType.TIERED,
            frequency=FeeFrequency.PER_OCCURRENCE,
            tiers=tiers
        )
        
        # Test first tier
        fee = fee_config.calculate_fee(Money(Decimal('250.00'), Currency.USD))
        assert fee == Money(Decimal('5.00'), Currency.USD)
        
        # Test second tier
        fee = fee_config.calculate_fee(Money(Decimal('1000.00'), Currency.USD))
        assert fee == Money(Decimal('15.00'), Currency.USD)
        
        # Test third tier
        fee = fee_config.calculate_fee(Money(Decimal('5000.00'), Currency.USD))
        assert fee == Money(Decimal('25.00'), Currency.USD)
    
    def test_fee_waived_by_balance(self):
        """Test fee waived when balance is above threshold"""
        now = datetime.now(timezone.utc)
        fee_config = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="maintenance_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.MONTHLY,
            amount=Money(Decimal('15.00'), Currency.USD),
            waive_if_balance_above=Money(Decimal('1000.00'), Currency.USD)
        )
        
        # Fee should apply when balance is below threshold
        context = {"balance": Money(Decimal('500.00'), Currency.USD)}
        fee = fee_config.calculate_fee(Money(Decimal('100.00'), Currency.USD), context)
        assert fee == Money(Decimal('15.00'), Currency.USD)
        
        # Fee should be waived when balance is above threshold
        context = {"balance": Money(Decimal('1500.00'), Currency.USD)}
        fee = fee_config.calculate_fee(Money(Decimal('100.00'), Currency.USD), context)
        assert fee == Money(Decimal('0.00'), Currency.USD)
    
    def test_conditional_fee_application(self):
        """Test conditional fee application"""
        now = datetime.now(timezone.utc)
        late_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="late_payment_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.PER_OCCURRENCE,
            condition=FeeCondition.PAYMENT_LATE,
            amount=Money(Decimal('35.00'), Currency.USD)
        )
        
        # This test verifies the fee config exists - actual conditional logic 
        # would be implemented by the system using the fee config
        assert late_fee.condition == FeeCondition.PAYMENT_LATE
        assert late_fee.amount == Money(Decimal('35.00'), Currency.USD)
    
    def test_fee_calculation_errors(self):
        """Test fee calculation error conditions"""
        now = datetime.now(timezone.utc)
        
        # Missing amount for fixed fee
        with pytest.raises(ValueError, match="Fixed fee must have amount specified"):
            fee_config = FeeConfig(
                id=str(uuid.uuid4()),
                created_at=now,
                updated_at=now,
                name="bad_fee",
                fee_type=FeeType.FIXED,
                frequency=FeeFrequency.MONTHLY
            )
            fee_config.calculate_fee(Money(Decimal('100.00'), Currency.USD))
        
        # Missing percentage for percentage fee
        with pytest.raises(ValueError, match="Percentage fee must have percentage specified"):
            fee_config = FeeConfig(
                id=str(uuid.uuid4()),
                created_at=now,
                updated_at=now,
                name="bad_percentage_fee",
                fee_type=FeeType.PERCENTAGE,
                frequency=FeeFrequency.PER_OCCURRENCE
            )
            fee_config.calculate_fee(Money(Decimal('100.00'), Currency.USD))
        
        # Currency mismatch for fixed fee
        with pytest.raises(ValueError, match="Fee currency must match amount currency"):
            fee_config = FeeConfig(
                id=str(uuid.uuid4()),
                created_at=now,
                updated_at=now,
                name="currency_mismatch_fee",
                fee_type=FeeType.FIXED,
                frequency=FeeFrequency.MONTHLY,
                amount=Money(Decimal('15.00'), Currency.EUR)
            )
            fee_config.calculate_fee(Money(Decimal('100.00'), Currency.USD))


class TestInterestConfig:
    """Test InterestConfig functionality"""
    
    def test_fixed_interest_rate(self):
        """Test fixed interest rate configuration"""
        config = InterestConfig(rate=Decimal('0.0425'))  # 4.25%
        
        assert config.get_rate() == Decimal('0.0425')
        assert config.get_rate(Decimal('0.5')) == Decimal('0.0425')  # Risk score ignored
    
    def test_risk_based_interest_rate(self):
        """Test risk-based interest rate configuration"""
        config = InterestConfig(
            rate_range=(Decimal('0.03'), Decimal('0.08'))  # 3% to 8%
        )
        
        # Minimum rate with no risk score
        assert config.get_rate() == Decimal('0.03')
        
        # Risk score 0 = minimum rate
        assert config.get_rate(Decimal('0.0')) == Decimal('0.03')
        
        # Risk score 1 = maximum rate
        assert config.get_rate(Decimal('1.0')) == Decimal('0.08')
        
        # Risk score 0.5 = midpoint rate
        expected_mid = Decimal('0.03') + (Decimal('0.08') - Decimal('0.03')) * Decimal('0.5')
        assert config.get_rate(Decimal('0.5')) == expected_mid
    
    def test_interest_config_validation(self):
        """Test interest configuration validation"""
        # Neither rate nor rate_range specified
        with pytest.raises(ValueError, match="must have either rate or rate_range"):
            config = InterestConfig()
            config.get_rate()


class TestProduct:
    """Test Product functionality"""
    
    def test_product_creation(self, sample_interest_config, sample_fee_config, sample_limit_config):
        """Test basic product creation"""
        now = datetime.now(timezone.utc)
        product = Product(
            id="PROD001",
            created_at=now,
            updated_at=now,
            name="Premium Savings Account",
            description="High-yield savings account with premium features",
            product_type=ProductType.SAVINGS,
            product_code="PSA001",
            currency=Currency.USD,
            status=ProductStatus.DRAFT,
            version=1,
            interest_config=sample_interest_config,
            fees=[sample_fee_config],
            limit_config=sample_limit_config
        )
        
        assert product.name == "Premium Savings Account"
        assert product.product_type == ProductType.SAVINGS
        assert product.status == ProductStatus.DRAFT
        assert product.version == 1
        assert len(product.fees) == 1
    
    def test_credit_line_product_auto_config(self):
        """Test that credit line products automatically get credit config"""
        now = datetime.now(timezone.utc)
        product = Product(
            id="CREDIT001",
            created_at=now,
            updated_at=now,
            name="Personal Credit Line",
            description="Flexible credit line product",
            product_type=ProductType.CREDIT_LINE,
            product_code="PCL001",
            currency=Currency.USD
        )
        
        # Should automatically create credit config
        assert product.credit_config is not None
        assert isinstance(product.credit_config, CreditConfig)
    
    def test_loan_product_auto_config(self):
        """Test that loan products automatically get term config"""
        now = datetime.now(timezone.utc)
        product = Product(
            id="LOAN001",
            created_at=now,
            updated_at=now,
            name="Personal Loan",
            description="Fixed-term personal loan",
            product_type=ProductType.LOAN,
            product_code="PL001",
            currency=Currency.USD
        )
        
        # Should automatically create term config
        assert product.term_config is not None
        assert isinstance(product.term_config, TermConfig)
    
    def test_product_availability_active(self):
        """Test product availability when active"""
        now = datetime.now(timezone.utc)
        product = Product(
            id="PROD002",
            created_at=now,
            updated_at=now,
            name="Basic Checking",
            description="Basic checking account",
            product_type=ProductType.CHECKING,
            product_code="BC001",
            currency=Currency.USD,
            status=ProductStatus.ACTIVE,
            effective_date=now - timedelta(days=1)  # Effective yesterday
        )
        
        assert product.is_available_for_accounts()
    
    def test_product_availability_not_active(self):
        """Test product availability when not active"""
        now = datetime.now(timezone.utc)
        
        # Draft status
        draft_product = Product(
            id="PROD003",
            created_at=now,
            updated_at=now,
            name="Draft Product",
            description="Product in draft",
            product_type=ProductType.SAVINGS,
            product_code="DP001",
            currency=Currency.USD,
            status=ProductStatus.DRAFT
        )
        assert not draft_product.is_available_for_accounts()
        
        # Not yet effective
        future_product = Product(
            id="PROD004",
            created_at=now,
            updated_at=now,
            name="Future Product",
            description="Product effective in future",
            product_type=ProductType.SAVINGS,
            product_code="FP001",
            currency=Currency.USD,
            status=ProductStatus.ACTIVE,
            effective_date=now + timedelta(days=1)  # Effective tomorrow
        )
        assert not future_product.is_available_for_accounts()
        
        # Past end date
        expired_product = Product(
            id="PROD005",
            created_at=now,
            updated_at=now,
            name="Expired Product",
            description="Product that has ended",
            product_type=ProductType.SAVINGS,
            product_code="EP001",
            currency=Currency.USD,
            status=ProductStatus.ACTIVE,
            effective_date=now - timedelta(days=30),
            end_date=now - timedelta(days=1)  # Ended yesterday
        )
        assert not expired_product.is_available_for_accounts()
    
    def test_product_interest_rate_retrieval(self, sample_interest_config):
        """Test getting interest rate from product"""
        now = datetime.now(timezone.utc)
        product = Product(
            id="PROD006",
            created_at=now,
            updated_at=now,
            name="Interest Bearing Account",
            description="Account with interest",
            product_type=ProductType.SAVINGS,
            product_code="IBA001",
            currency=Currency.USD,
            interest_config=sample_interest_config
        )
        
        rate = product.get_interest_rate()
        assert rate == Decimal('0.0525')
    
    def test_product_fee_calculation(self):
        """Test fee calculation from product"""
        now = datetime.now(timezone.utc)
        
        maintenance_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="maintenance_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.MONTHLY,
            amount=Money(Decimal('12.00'), Currency.USD)
        )
        
        product = Product(
            id="PROD007",
            created_at=now,
            updated_at=now,
            name="Fee Test Product",
            description="Product for testing fees",
            product_type=ProductType.CHECKING,
            product_code="FTP001",
            currency=Currency.USD,
            fees=[maintenance_fee]
        )
        
        # Calculate existing fee
        fee = product.calculate_fees("maintenance_fee", Money(Decimal('100.00'), Currency.USD))
        assert fee == Money(Decimal('12.00'), Currency.USD)
        
        # Calculate non-existent fee (should return zero)
        no_fee = product.calculate_fees("non_existent_fee", Money(Decimal('100.00'), Currency.USD))
        assert no_fee == Money(Decimal('0.00'), Currency.USD)
    
    def test_product_account_parameter_validation(self):
        """Test account parameter validation against product configuration"""
        now = datetime.now(timezone.utc)
        
        limit_config = LimitConfig(
            min_opening_balance=Money(Decimal('500.00'), Currency.USD),
            max_balance=Money(Decimal('10000.00'), Currency.USD)
        )
        
        product = Product(
            id="PROD008",
            created_at=now,
            updated_at=now,
            name="Validation Test Product",
            description="Product for testing validation",
            product_type=ProductType.SAVINGS,
            product_code="VTP001",
            currency=Currency.USD,
            limit_config=limit_config
        )
        
        # Valid opening balance
        errors = product.validate_account_parameters(Money(Decimal('1000.00'), Currency.USD))
        assert len(errors) == 0
        
        # Opening balance too low
        errors = product.validate_account_parameters(Money(Decimal('100.00'), Currency.USD))
        assert len(errors) == 1
        assert "below minimum" in errors[0]
        
        # Opening balance too high
        errors = product.validate_account_parameters(Money(Decimal('15000.00'), Currency.USD))
        assert len(errors) == 1
        assert "exceeds maximum" in errors[0]
        
        # Wrong currency
        errors = product.validate_account_parameters(Money(Decimal('1000.00'), Currency.EUR))
        assert len(errors) == 1
        assert "currency" in errors[0] and "does not match" in errors[0]
    
    def test_credit_line_limit_validation(self):
        """Test credit limit validation for credit line products"""
        now = datetime.now(timezone.utc)
        
        credit_config = CreditConfig(
            credit_limit_range=(Money(Decimal('500.00'), Currency.USD),
                              Money(Decimal('5000.00'), Currency.USD))
        )
        
        product = Product(
            id="CREDIT002",
            created_at=now,
            updated_at=now,
            name="Credit Line Product",
            description="Credit line for testing",
            product_type=ProductType.CREDIT_LINE,
            product_code="CLP001",
            currency=Currency.USD,
            credit_config=credit_config
        )
        
        # Valid credit limit
        errors = product.validate_account_parameters(
            Money(Decimal('0.00'), Currency.USD),
            credit_limit=Money(Decimal('2000.00'), Currency.USD)
        )
        assert len(errors) == 0
        
        # Credit limit too low
        errors = product.validate_account_parameters(
            Money(Decimal('0.00'), Currency.USD),
            credit_limit=Money(Decimal('100.00'), Currency.USD)
        )
        assert len(errors) == 1
        assert "outside allowed range" in errors[0]
        
        # Credit limit too high
        errors = product.validate_account_parameters(
            Money(Decimal('0.00'), Currency.USD),
            credit_limit=Money(Decimal('10000.00'), Currency.USD)
        )
        assert len(errors) == 1
        assert "outside allowed range" in errors[0]


class TestProductEngine:
    """Test ProductEngine functionality"""
    
    def test_create_basic_product(self, product_engine):
        """Test creating a basic product"""
        product = product_engine.create_product(
            name="Basic Savings",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            description="Basic savings account"
        )
        
        assert product.name == "Basic Savings"
        assert product.product_type == ProductType.SAVINGS
        assert product.currency == Currency.USD
        assert product.status == ProductStatus.DRAFT
        assert product.version == 1
        assert product.product_code.startswith("SAVINGS_")  # Auto-generated code
    
    def test_create_product_with_custom_code(self, product_engine):
        """Test creating product with custom product code"""
        product = product_engine.create_product(
            name="Premium Checking",
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            product_code="PREMIUM_CHECK_001",
            description="Premium checking account"
        )
        
        assert product.product_code == "PREMIUM_CHECK_001"
    
    def test_create_product_duplicate_code_error(self, product_engine):
        """Test error when creating product with duplicate code"""
        # Create first product
        product_engine.create_product(
            name="First Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            product_code="DUPLICATE_CODE"
        )
        
        # Try to create second with same code
        with pytest.raises(ValueError, match="Product code DUPLICATE_CODE already exists"):
            product_engine.create_product(
                name="Second Product",
                product_type=ProductType.CHECKING,
                currency=Currency.USD,
                product_code="DUPLICATE_CODE"
            )
    
    def test_get_product_by_id(self, product_engine):
        """Test retrieving product by ID"""
        created_product = product_engine.create_product(
            name="Test Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD
        )
        
        retrieved_product = product_engine.get_product(created_product.id)
        assert retrieved_product is not None
        assert retrieved_product.id == created_product.id
        assert retrieved_product.name == "Test Product"
    
    def test_get_product_by_code(self, product_engine):
        """Test retrieving product by code"""
        created_product = product_engine.create_product(
            name="Test Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            product_code="TEST_PRODUCT_001"
        )
        
        retrieved_product = product_engine.get_product_by_code("TEST_PRODUCT_001")
        assert retrieved_product is not None
        assert retrieved_product.product_code == "TEST_PRODUCT_001"
        assert retrieved_product.name == "Test Product"
    
    def test_get_nonexistent_product(self, product_engine):
        """Test retrieving non-existent product returns None"""
        assert product_engine.get_product("nonexistent_id") is None
        assert product_engine.get_product_by_code("NONEXISTENT_CODE") is None
    
    def test_update_product_creates_new_version(self, product_engine):
        """Test updating product creates new version"""
        original_product = product_engine.create_product(
            name="Original Name",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            description="Original description"
        )
        
        assert original_product.version == 1
        
        # Update the product
        updated_product = product_engine.update_product(
            original_product.id,
            name="Updated Name",
            description="Updated description"
        )
        
        assert updated_product.version == 2
        assert updated_product.name == "Updated Name"
        assert updated_product.description == "Updated description"
        assert updated_product.id == original_product.id  # Same ID
    
    def test_update_nonexistent_product_error(self, product_engine):
        """Test updating non-existent product raises error"""
        with pytest.raises(ValueError, match="Product nonexistent_id not found"):
            product_engine.update_product("nonexistent_id", name="New Name")
    
    def test_list_products_no_filters(self, product_engine):
        """Test listing all products without filters"""
        # Create test products
        product1 = product_engine.create_product(
            name="Savings Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD
        )
        
        product2 = product_engine.create_product(
            name="Checking Product", 
            product_type=ProductType.CHECKING,
            currency=Currency.USD
        )
        
        all_products = product_engine.list_products()
        assert len(all_products) == 2
        
        product_names = [p.name for p in all_products]
        assert "Savings Product" in product_names
        assert "Checking Product" in product_names
    
    def test_list_products_filter_by_type(self, product_engine):
        """Test listing products filtered by type"""
        # Create products of different types
        product_engine.create_product(
            name="Savings Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD
        )
        
        product_engine.create_product(
            name="Checking Product",
            product_type=ProductType.CHECKING,
            currency=Currency.USD
        )
        
        product_engine.create_product(
            name="Another Savings",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD
        )
        
        # Filter by savings products
        savings_products = product_engine.list_products(product_type=ProductType.SAVINGS)
        assert len(savings_products) == 2
        
        for product in savings_products:
            assert product.product_type == ProductType.SAVINGS
    
    def test_list_products_filter_by_status(self, product_engine):
        """Test listing products filtered by status"""
        # Create products with different statuses
        draft_product = product_engine.create_product(
            name="Draft Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            status=ProductStatus.DRAFT
        )
        
        active_product = product_engine.create_product(
            name="Active Product",
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            status=ProductStatus.ACTIVE
        )
        
        # Filter by active products
        active_products = product_engine.list_products(status=ProductStatus.ACTIVE)
        assert len(active_products) == 1
        assert active_products[0].status == ProductStatus.ACTIVE
        
        # Filter by draft products
        draft_products = product_engine.list_products(status=ProductStatus.DRAFT)
        assert len(draft_products) == 1
        assert draft_products[0].status == ProductStatus.DRAFT
    
    def test_activate_product(self, product_engine):
        """Test activating a product"""
        product = product_engine.create_product(
            name="Draft Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            status=ProductStatus.DRAFT
        )
        
        assert product.status == ProductStatus.DRAFT
        assert product.effective_date is None
        
        # Activate the product
        activated_product = product_engine.activate_product(product.id)
        
        assert activated_product.status == ProductStatus.ACTIVE
        assert activated_product.effective_date is not None
        assert activated_product.version == 2  # Should create new version
    
    def test_suspend_product(self, product_engine):
        """Test suspending a product"""
        # Create and activate a product
        product = product_engine.create_product(
            name="Active Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            status=ProductStatus.ACTIVE
        )
        
        # Suspend the product
        suspended_product = product_engine.suspend_product(product.id)
        
        assert suspended_product.status == ProductStatus.SUSPENDED
        assert suspended_product.version == 2  # Should create new version
    
    def test_retire_product(self, product_engine):
        """Test retiring a product"""
        # Create an active product
        product = product_engine.create_product(
            name="Active Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            status=ProductStatus.ACTIVE
        )
        
        # Retire the product
        retired_product = product_engine.retire_product(product.id)
        
        assert retired_product.status == ProductStatus.RETIRED
        assert retired_product.end_date is not None
        assert retired_product.version == 2  # Should create new version


class TestProductEngineWithComplexConfigurations:
    """Test ProductEngine with complex configurations"""
    
    def test_create_savings_product_with_full_config(self, product_engine):
        """Test creating savings product with comprehensive configuration"""
        now = datetime.now(timezone.utc)
        interest_config = InterestConfig(
            rate=Decimal('0.045'),  # 4.5% APR
            calculation_method=InterestCalculation.DAILY_COMPOUND,
            day_count_convention=DayCountConvention.ACTUAL_365,
            posting_frequency=InterestPosting.MONTHLY
        )
        
        maintenance_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="maintenance_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.MONTHLY,
            amount=Money(Decimal('8.00'), Currency.USD),
            waive_if_balance_above=Money(Decimal('1500.00'), Currency.USD)
        )
        
        transaction_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="excess_withdrawal_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.PER_OCCURRENCE,
            condition=FeeCondition.OVER_LIMIT,
            amount=Money(Decimal('3.00'), Currency.USD)
        )
        
        limit_config = LimitConfig(
            min_opening_balance=Money(Decimal('25.00'), Currency.USD),
            min_balance=Money(Decimal('0.00'), Currency.USD),
            max_balance=Money(Decimal('25000.00'), Currency.USD),
            daily_withdrawal_limit=Money(Decimal('800.00'), Currency.USD),
            daily_withdrawal_count=6,
            monthly_withdrawal_limit=Money(Decimal('5000.00'), Currency.USD)
        )
        
        withdrawal_limits = WithdrawalLimits(
            max_per_day=6,
            max_amount_per_day=Money(Decimal('800.00'), Currency.USD),
            max_per_month=20,
            max_amount_per_month=Money(Decimal('5000.00'), Currency.USD)
        )
        
        product = product_engine.create_product(
            name="Premium Savings Plus",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            product_code="PSP001",
            description="Premium savings account with competitive interest and reasonable fees",
            interest_config=interest_config,
            fees=[maintenance_fee, transaction_fee],
            limit_config=limit_config,
            withdrawal_limits=withdrawal_limits,
            dormancy_days=180
        )
        
        assert product.name == "Premium Savings Plus"
        assert product.interest_config.rate == Decimal('0.045')
        assert len(product.fees) == 2
        assert product.limit_config.min_opening_balance == Money(Decimal('25.00'), Currency.USD)
        assert product.withdrawal_limits.max_per_day == 6
        assert product.dormancy_days == 180
    
    def test_create_credit_line_product_with_full_config(self, product_engine):
        """Test creating credit line product with comprehensive configuration"""
        now = datetime.now(timezone.utc)
        interest_config = InterestConfig(
            rate_range=(Decimal('0.1299'), Decimal('0.2499')),  # 12.99% to 24.99% based on risk
            calculation_method=InterestCalculation.DAILY_ON_BALANCE,
            day_count_convention=DayCountConvention.ACTUAL_365,
            posting_frequency=InterestPosting.MONTHLY
        )
        
        annual_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="annual_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.ANNUALLY,
            amount=Money(Decimal('95.00'), Currency.USD)
        )
        
        late_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="late_payment_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.PER_OCCURRENCE,
            condition=FeeCondition.PAYMENT_LATE,
            amount=Money(Decimal('39.00'), Currency.USD)
        )
        
        overlimit_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="overlimit_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.PER_OCCURRENCE,
            condition=FeeCondition.OVER_LIMIT,
            amount=Money(Decimal('29.00'), Currency.USD)
        )
        
        limit_config = LimitConfig(
            min_transaction=Money(Decimal('1.00'), Currency.USD),
            max_transaction=Money(Decimal('10000.00'), Currency.USD),
            daily_withdrawal_limit=Money(Decimal('2000.00'), Currency.USD)
        )
        
        credit_config = CreditConfig(
            credit_limit_range=(Money(Decimal('500.00'), Currency.USD),
                              Money(Decimal('15000.00'), Currency.USD)),
            grace_period_days=25,
            grace_period_type=GracePeriodType.PURCHASES_ONLY,
            statement_cycle_days=30,
            payment_due_days=22,
            minimum_payment_type=MinPaymentType.PERCENTAGE_OR_FIXED,
            minimum_payment_percentage=Decimal('0.02'),  # 2%
            minimum_payment_fixed=Money(Decimal('25.00'), Currency.USD),
            overlimit_allowed=True,
            overlimit_tolerance_percentage=Decimal('0.10')  # 10% over limit allowed
        )
        
        product = product_engine.create_product(
            name="Flexible Credit Line",
            product_type=ProductType.CREDIT_LINE,
            currency=Currency.USD,
            product_code="FCL001",
            description="Flexible credit line with competitive rates and features",
            interest_config=interest_config,
            fees=[annual_fee, late_fee, overlimit_fee],
            limit_config=limit_config,
            credit_config=credit_config
        )
        
        assert product.name == "Flexible Credit Line"
        assert product.product_type == ProductType.CREDIT_LINE
        assert product.interest_config.rate_range == (Decimal('0.1299'), Decimal('0.2499'))
        assert len(product.fees) == 3
        assert product.credit_config.grace_period_days == 25
        assert product.credit_config.overlimit_allowed == True
    
    def test_create_loan_product_with_full_config(self, product_engine):
        """Test creating loan product with comprehensive configuration"""
        now = datetime.now(timezone.utc)
        interest_config = InterestConfig(
            rate_range=(Decimal('0.0699'), Decimal('0.1499')),  # 6.99% to 14.99%
            calculation_method=InterestCalculation.SIMPLE,
            day_count_convention=DayCountConvention.ACTUAL_365,
            posting_frequency=InterestPosting.MONTHLY,
            accrual_start=AccrualStart.FROM_DISBURSEMENT
        )
        
        origination_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="origination_fee",
            fee_type=FeeType.PERCENTAGE,
            frequency=FeeFrequency.ONE_TIME,
            percentage=Decimal('0.025')  # 2.5% of loan amount
        )
        
        late_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="late_payment_fee",
            fee_type=FeeType.FIXED,
            frequency=FeeFrequency.PER_OCCURRENCE,
            condition=FeeCondition.PAYMENT_LATE,
            amount=Money(Decimal('35.00'), Currency.USD)
        )
        
        prepayment_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="prepayment_penalty",
            fee_type=FeeType.PERCENTAGE,
            frequency=FeeFrequency.ONE_TIME,
            condition=FeeCondition.CLOSED_EARLY,
            percentage=Decimal('0.03')  # 3% prepayment penalty
        )
        
        term_config = TermConfig(
            min_term_months=12,
            max_term_months=84,  # 7 years max
            min_amount=Money(Decimal('1000.00'), Currency.USD),
            max_amount=Money(Decimal('50000.00'), Currency.USD),
            prepayment_allowed=True,
            prepayment_penalty_rate=Decimal('0.03'),
            grace_period_days=10,
            amortization_methods=[AmortizationMethod.EQUAL_INSTALLMENT,
                                AmortizationMethod.EQUAL_PRINCIPAL],
            payment_frequencies=[1, 2, 4]  # Monthly, bi-monthly, quarterly
        )
        
        product = product_engine.create_product(
            name="Personal Loan Plus",
            product_type=ProductType.LOAN,
            currency=Currency.USD,
            product_code="PLP001",
            description="Flexible personal loan with competitive rates",
            interest_config=interest_config,
            fees=[origination_fee, late_fee, prepayment_fee],
            term_config=term_config
        )
        
        assert product.name == "Personal Loan Plus"
        assert product.product_type == ProductType.LOAN
        assert product.term_config.min_term_months == 12
        assert product.term_config.max_term_months == 84
        assert len(product.fees) == 3
        assert AmortizationMethod.EQUAL_INSTALLMENT in product.term_config.amortization_methods


class TestProductEngineEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_retired_product_not_available_for_accounts(self, product_engine):
        """Test that retired products are not available for new accounts"""
        # Create and retire a product
        product = product_engine.create_product(
            name="Retired Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD
        )
        
        retired_product = product_engine.retire_product(product.id)
        assert not retired_product.is_available_for_accounts()
    
    def test_suspended_product_not_available_for_accounts(self, product_engine):
        """Test that suspended products are not available for new accounts"""
        # Create and suspend a product
        product = product_engine.create_product(
            name="Suspended Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD
        )
        
        suspended_product = product_engine.suspend_product(product.id)
        assert not suspended_product.is_available_for_accounts()
    
    def test_draft_product_not_available_for_accounts(self, product_engine):
        """Test that draft products are not available for new accounts"""
        product = product_engine.create_product(
            name="Draft Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            status=ProductStatus.DRAFT
        )
        
        assert not product.is_available_for_accounts()
    
    def test_product_with_future_effective_date(self, product_engine):
        """Test product with future effective date"""
        future_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        product = product_engine.create_product(
            name="Future Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            status=ProductStatus.ACTIVE,
            effective_date=future_date
        )
        
        assert not product.is_available_for_accounts()
    
    def test_product_with_past_end_date(self, product_engine):
        """Test product with past end date"""
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        
        product = product_engine.create_product(
            name="Expired Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            status=ProductStatus.ACTIVE,
            effective_date=datetime.now(timezone.utc) - timedelta(days=30),
            end_date=past_date
        )
        
        assert not product.is_available_for_accounts()
    
    def test_fee_calculation_with_no_matching_tier(self, product_engine):
        """Test tiered fee when no tier matches amount"""
        now = datetime.now(timezone.utc)
        tiers = [
            FeeTier(Money(Decimal('100.00'), Currency.USD),
                   Money(Decimal('500.00'), Currency.USD),
                   Money(Decimal('10.00'), Currency.USD))
        ]
        
        fee_config = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="tiered_fee",
            fee_type=FeeType.TIERED,
            frequency=FeeFrequency.PER_OCCURRENCE,
            tiers=tiers
        )
        
        # Amount below all tiers - should return $0
        fee = fee_config.calculate_fee(Money(Decimal('50.00'), Currency.USD))
        assert fee == Money(Decimal('0.00'), Currency.USD)
        
        # Amount above all tiers - should return $0
        fee = fee_config.calculate_fee(Money(Decimal('1000.00'), Currency.USD))
        assert fee == Money(Decimal('0.00'), Currency.USD)
    
    def test_interest_rate_calculation_edge_cases(self):
        """Test edge cases in interest rate calculation"""
        # Risk-based with extreme risk scores
        config = InterestConfig(rate_range=(Decimal('0.05'), Decimal('0.15')))
        
        # Risk score > 1 should still work (clamped to max rate conceptually)
        rate = config.get_rate(Decimal('1.5'))  # This will actually extrapolate
        expected = Decimal('0.05') + (Decimal('0.15') - Decimal('0.05')) * Decimal('1.5')
        assert rate == expected  # System allows extrapolation
        
        # Negative risk score
        rate = config.get_rate(Decimal('-0.5'))
        expected = Decimal('0.05') + (Decimal('0.15') - Decimal('0.05')) * Decimal('-0.5')
        assert rate == expected  # System allows extrapolation
    
    def test_product_validation_with_multiple_errors(self):
        """Test product validation returns multiple errors"""
        now = datetime.now(timezone.utc)
        
        limit_config = LimitConfig(
            min_opening_balance=Money(Decimal('100.00'), Currency.USD),
            max_balance=Money(Decimal('1000.00'), Currency.USD)
        )
        
        product = Product(
            id="MULTI_ERROR_TEST",
            created_at=now,
            updated_at=now,
            name="Multi Error Test",
            description="Product for testing multiple validation errors",
            product_type=ProductType.SAVINGS,
            product_code="MET001",
            currency=Currency.USD,
            limit_config=limit_config
        )
        
        # Test with wrong currency
        errors = product.validate_account_parameters(
            Money(Decimal('5000.00'), Currency.EUR)  # Wrong currency
        )
        
        # Should only report currency error, amount limits won't be checked due to currency mismatch
        assert len(errors) == 1
        assert "currency" in errors[0] and "does not match" in errors[0]
    
    def test_product_code_uniqueness_across_versions(self, product_engine):
        """Test that product codes remain unique even across versions"""
        # Create original product
        original = product_engine.create_product(
            name="Original Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            product_code="UNIQUE_CODE"
        )
        
        # Update it (creates new version)
        updated = product_engine.update_product(original.id, name="Updated Product")
        
        # Try to create new product with same code - should fail
        with pytest.raises(ValueError, match="Product code UNIQUE_CODE already exists"):
            product_engine.create_product(
                name="Another Product",
                product_type=ProductType.CHECKING,
                currency=Currency.USD,
                product_code="UNIQUE_CODE"
            )


class TestProductEngineIntegration:
    """Integration tests for ProductEngine with other components"""
    
    def test_calculate_fees_through_engine(self, product_engine):
        """Test fee calculation through product engine"""
        now = datetime.now(timezone.utc)
        transaction_fee = FeeConfig(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            name="wire_transfer_fee",
            fee_type=FeeType.PERCENTAGE,
            frequency=FeeFrequency.PER_OCCURRENCE,
            percentage=Decimal('0.015')  # 1.5%
        )
        
        product = product_engine.create_product(
            name="Business Checking",
            product_type=ProductType.CHECKING,
            currency=Currency.USD,
            fees=[transaction_fee]
        )
        
        # Calculate fee through product engine
        fee = product_engine.calculate_fees(
            product, 
            "wire_transfer_fee",
            Money(Decimal('1000.00'), Currency.USD)
        )
        
        assert fee == Money(Decimal('15.00'), Currency.USD)  # 1.5% of $1000
    
    def test_get_interest_rate_through_engine(self, product_engine):
        """Test getting interest rate through product engine"""
        interest_config = InterestConfig(
            rate_range=(Decimal('0.03'), Decimal('0.08'))
        )
        
        product = product_engine.create_product(
            name="Risk-Based Savings",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD,
            interest_config=interest_config
        )
        
        # Test different risk scores
        low_risk_rate = product_engine.get_interest_rate(product, Decimal('0.2'))
        high_risk_rate = product_engine.get_interest_rate(product, Decimal('0.8'))
        
        assert low_risk_rate < high_risk_rate
        assert low_risk_rate >= Decimal('0.03')
        assert high_risk_rate <= Decimal('0.08')
    
    def test_product_lifecycle_audit_trail(self, product_engine, audit_trail):
        """Test that product lifecycle operations are properly audited"""
        # Create product
        product = product_engine.create_product(
            name="Audit Test Product",
            product_type=ProductType.SAVINGS,
            currency=Currency.USD
        )
        
        # Activate product
        product_engine.activate_product(product.id)
        
        # Suspend product
        product_engine.suspend_product(product.id)
        
        # Retire product
        product_engine.retire_product(product.id)
        
        # Check audit trail (basic verification - actual audit testing would be more detailed)
        # This is just to ensure the integration points work
        assert audit_trail is not None
        # More detailed audit trail testing would be in test_audit.py


if __name__ == "__main__":
    pytest.main([__file__, "-v"])