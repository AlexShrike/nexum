"""
FastAPI REST API Module

Provides REST API endpoints for all core banking operations including
customer management, account operations, transactions, credit lines, loans,
and audit queries. Runs on port 8090.
"""

from decimal import Decimal
from datetime import datetime, timezone, date, timedelta
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Depends, status, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import uvicorn
import jwt
import os
from collections import defaultdict
import time

from .currency import Money, Currency
from .storage import InMemoryStorage, SQLiteStorage
from .async_storage import AsyncStorageInterface, create_async_storage
from .audit import AuditTrail, AuditEventType
from .ledger import GeneralLedger, AccountType
from .accounts import AccountManager, ProductType, AccountState
from .customers import CustomerManager, KYCStatus, KYCTier, Address
from .compliance import ComplianceEngine
from .transactions import TransactionProcessor, TransactionType, TransactionChannel
from .interest import InterestEngine
from .credit import CreditLineManager, TransactionCategory
from .loans import LoanManager, LoanTerms, PaymentFrequency, AmortizationMethod
from .rbac import RBACManager, Permission
from .logging_config import setup_logging, get_logger, log_action


# Configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-in-production')
NEXUM_AUTH_ENABLED = os.getenv('NEXUM_AUTH_ENABLED', 'true').lower() == 'true'

# Setup logging
logger = setup_logging()

# JWT Security
security = HTTPBearer(auto_error=False)


# Rate Limiting
class RateLimiter:
    def __init__(self, requests_per_minute=60):
        self.requests = defaultdict(list)
        self.rpm = requests_per_minute
    
    async def __call__(self, request: Request, call_next):
        client_ip = request.client.host
        now = time.time()
        # Clean old entries
        self.requests[client_ip] = [t for t in self.requests[client_ip] if now - t < 60]
        if len(self.requests[client_ip]) >= self.rpm:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        self.requests[client_ip].append(now)
        return await call_next(request)


# Authentication Dependencies
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[str]:
    """Dependency that validates JWT and returns current user"""
    if not NEXUM_AUTH_ENABLED:
        return "test_user"  # For tests when auth is disabled
        
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Validate user exists and is active (using a simple approach for now)
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_permission(permission: str):
    """Dependency factory for permission checking"""
    def check(user_id: str = Depends(get_current_user), 
              system: 'BankingSystem' = Depends(lambda: get_banking_system())):
        if not NEXUM_AUTH_ENABLED:
            return user_id  # Skip permission checks for tests
            
        try:
            perm = Permission[permission]
            if not system.rbac_manager.check_permission(user_id, perm):
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return user_id
        except KeyError:
            raise HTTPException(status_code=500, detail=f"Invalid permission: {permission}")
    return check


# Pydantic models for API requests/responses
class MoneyModel(BaseModel):
    amount: str = Field(..., description="Decimal amount as string")
    currency: str = Field(..., description="Currency code (USD, EUR, etc.)")
    
    def to_money(self) -> Money:
        return Money(Decimal(self.amount), Currency[self.currency])
    
    @classmethod
    def from_money(cls, money: Money) -> 'MoneyModel':
        return cls(amount=str(money.amount), currency=money.currency.code)


class AddressModel(BaseModel):
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str
    
    def to_address(self) -> Address:
        return Address(
            line1=self.line1,
            line2=self.line2,
            city=self.city,
            state=self.state,
            postal_code=self.postal_code,
            country=self.country
        )


class CreateCustomerRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None  # ISO date string
    address: Optional[AddressModel] = None


class UpdateCustomerRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[AddressModel] = None


class UpdateKYCRequest(BaseModel):
    status: str = Field(..., description="KYC status (none, pending, verified, expired, rejected)")
    tier: Optional[str] = Field(None, description="KYC tier (tier_0, tier_1, tier_2, tier_3)")
    documents: Optional[List[str]] = None
    expiry_days: Optional[int] = None


class CreateAccountRequest(BaseModel):
    customer_id: str
    product_type: str = Field(..., description="Product type (savings, checking, credit_line, loan)")
    currency: str = Field(..., description="Currency code")
    name: str
    account_number: Optional[str] = None
    interest_rate: Optional[str] = None  # Decimal as string
    credit_limit: Optional[MoneyModel] = None
    minimum_balance: Optional[MoneyModel] = None
    daily_transaction_limit: Optional[MoneyModel] = None
    monthly_transaction_limit: Optional[MoneyModel] = None


class CreateTransactionRequest(BaseModel):
    transaction_type: str = Field(..., description="Transaction type")
    amount: MoneyModel
    description: str
    channel: str = Field(..., description="Transaction channel")
    from_account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    reference: Optional[str] = None
    idempotency_key: Optional[str] = None


class DepositRequest(BaseModel):
    account_id: str
    amount: MoneyModel
    description: str
    channel: str = "online"
    reference: Optional[str] = None


class WithdrawRequest(BaseModel):
    account_id: str
    amount: MoneyModel
    description: str
    channel: str = "online"
    reference: Optional[str] = None


class TransferRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount: MoneyModel
    description: str
    channel: str = "online"
    reference: Optional[str] = None


class CreditPaymentRequest(BaseModel):
    account_id: str
    amount: MoneyModel
    payment_date: Optional[str] = None  # ISO date string


class LoanTermsModel(BaseModel):
    principal_amount: MoneyModel
    annual_interest_rate: str  # Decimal as string
    term_months: int
    payment_frequency: str = "monthly"
    amortization_method: str = "equal_installment"
    first_payment_date: str  # ISO date string
    allow_prepayment: bool = True
    prepayment_penalty_rate: Optional[str] = None
    grace_period_days: int = 10
    late_fee: Optional[MoneyModel] = None
    
    def to_loan_terms(self) -> LoanTerms:
        return LoanTerms(
            principal_amount=self.principal_amount.to_money(),
            annual_interest_rate=Decimal(self.annual_interest_rate),
            term_months=self.term_months,
            payment_frequency=PaymentFrequency(self.payment_frequency),
            amortization_method=AmortizationMethod(self.amortization_method),
            first_payment_date=date.fromisoformat(self.first_payment_date),
            allow_prepayment=self.allow_prepayment,
            prepayment_penalty_rate=Decimal(self.prepayment_penalty_rate) if self.prepayment_penalty_rate else None,
            grace_period_days=self.grace_period_days,
            late_fee=self.late_fee.to_money() if self.late_fee else None
        )


class CreateLoanRequest(BaseModel):
    customer_id: str
    terms: LoanTermsModel
    currency: str


class LoanPaymentRequest(BaseModel):
    loan_id: str
    amount: MoneyModel
    payment_date: Optional[str] = None
    source_account_id: Optional[str] = None


# Pydantic models for new modules

# Product models
class CreateProductRequest(BaseModel):
    name: str
    description: str
    product_type: str = Field(..., description="Product type (savings, checking, loan, credit_line)")
    currency: str = Field(..., description="Currency code")
    product_code: Optional[str] = None
    interest_rate: Optional[str] = None
    fees: Optional[List[str]] = None


class UpdateProductRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    interest_rate: Optional[str] = None
    fees: Optional[List[str]] = None


class CalculateFeesRequest(BaseModel):
    event_type: str
    amount: MoneyModel


# Collections models
class RecordActionRequest(BaseModel):
    action_type: str
    performed_by: str
    notes: str
    result: str
    next_follow_up: Optional[str] = None


class RecordPromiseRequest(BaseModel):
    promised_amount: MoneyModel
    promised_date: str


class AssignCollectorRequest(BaseModel):
    collector_id: str


class ResolveCaseRequest(BaseModel):
    resolution: str


class SetStrategyRequest(BaseModel):
    product_id: Optional[str] = None
    escalation_rules: Optional[List[Dict]] = None
    auto_write_off_days: Optional[int] = None


# Reporting models
class CreateReportRequest(BaseModel):
    name: str
    description: str
    report_type: str


class RunReportRequest(BaseModel):
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None


# Workflow models
class CreateWorkflowDefinitionRequest(BaseModel):
    name: str
    description: str
    workflow_type: str
    steps: List[Dict[str, Any]]
    sla_hours: Optional[int] = None


class StartWorkflowRequest(BaseModel):
    definition_id: str
    entity_type: str
    entity_id: str
    context: Optional[Dict[str, Any]] = None


class ApproveStepRequest(BaseModel):
    comments: Optional[str] = None


class RejectStepRequest(BaseModel):
    comments: Optional[str] = None


class SkipStepRequest(BaseModel):
    reason: str


class AssignStepRequest(BaseModel):
    user: str


class CancelWorkflowRequest(BaseModel):
    reason: str


# RBAC models
class CreateRoleRequest(BaseModel):
    name: str
    description: str
    permissions: List[str]
    max_transaction_amount: Optional[MoneyModel] = None
    max_approval_amount: Optional[MoneyModel] = None


class UpdateRoleRequest(BaseModel):
    description: Optional[str] = None
    permissions: Optional[List[str]] = None
    max_transaction_amount: Optional[MoneyModel] = None
    max_approval_amount: Optional[MoneyModel] = None


class CreateUserRequest(BaseModel):
    username: str
    email: str
    full_name: str
    roles: List[str]
    password: Optional[str] = None


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    branch_id: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# Custom Fields models
class CreateFieldRequest(BaseModel):
    name: str
    label: str
    description: str
    field_type: str
    entity_type: str
    is_required: bool = False
    is_searchable: bool = False
    is_reportable: bool = False
    default_value: Optional[Any] = None
    enum_values: Optional[List[str]] = None
    group_name: Optional[str] = None


class UpdateFieldRequest(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    is_required: Optional[bool] = None
    is_searchable: Optional[bool] = None
    is_reportable: Optional[bool] = None
    default_value: Optional[Any] = None
    enum_values: Optional[List[str]] = None
    group_name: Optional[str] = None


class SetFieldValueRequest(BaseModel):
    field_name: str
    value: Any


class BulkSetValuesRequest(BaseModel):
    values: Dict[str, Any]


# Notification API Models
class NotificationTemplateRequest(BaseModel):
    name: str
    notification_type: str = Field(..., description="Notification type")
    channel: str = Field(..., description="Channel (email, sms, push, webhook, in_app)")
    subject_template: str = Field(..., description="Subject template with {placeholders}")
    body_template: str = Field(..., description="Body template with {placeholders}")
    is_active: bool = True


class SendNotificationRequest(BaseModel):
    notification_type: str = Field(..., description="Notification type")
    recipient_id: str = Field(..., description="Recipient customer/user ID")
    data: Dict[str, Any] = Field(..., description="Template data for rendering")
    channels: Optional[List[str]] = Field(None, description="Specific channels to use")
    priority: str = Field("medium", description="Priority (low, medium, high, critical)")


class BulkNotificationRequest(BaseModel):
    notification_type: str = Field(..., description="Notification type")
    recipient_ids: List[str] = Field(..., description="List of recipient IDs")
    data: Dict[str, Any] = Field(..., description="Template data for rendering")
    channels: Optional[List[str]] = Field(None, description="Specific channels to use")


class NotificationPreferencesRequest(BaseModel):
    channel_preferences: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Mapping of notification type to preferred channels"
    )
    quiet_hours_start: Optional[str] = Field(None, description="Quiet hours start time (HH:MM)")
    quiet_hours_end: Optional[str] = Field(None, description="Quiet hours end time (HH:MM)")
    do_not_disturb: bool = False


class RetryFailedRequest(BaseModel):
    max_retries: int = Field(3, description="Maximum retry attempts")


# Import new modules
from .products import ProductEngine, Product, ProductStatus, ProductType as ProductEngineType
from .collections import CollectionsManager, DelinquencyStatus, CollectionAction, ActionResult
from .reporting import ReportingEngine, ReportType, ReportFormat
from .workflows import WorkflowEngine, WorkflowType, WorkflowStatus, StepStatus
from .rbac import RBACManager, Permission, Role as RBACRole
from .custom_fields import CustomFieldManager, FieldType, EntityType as CustomEntityType
from .notifications import NotificationEngine, NotificationChannel, NotificationPriority, NotificationType, NotificationPreference


# Banking System Context
class BankingSystem:
    """Core banking system with all components initialized"""
    
    def __init__(self, use_sqlite: bool = True, async_storage: AsyncStorageInterface = None):
        # Initialize storage
        if async_storage:
            self.storage = async_storage
            self.is_async = True
        elif use_sqlite:
            self.storage = SQLiteStorage("core_banking.db")
            self.is_async = False
        else:
            self.storage = InMemoryStorage()
            self.is_async = False
        
        # Initialize core components
        self.audit_trail = AuditTrail(self.storage)
        self.ledger = GeneralLedger(self.storage, self.audit_trail)
        self.account_manager = AccountManager(self.storage, self.ledger, self.audit_trail)
        self.customer_manager = CustomerManager(self.storage, self.audit_trail)
        self.compliance_engine = ComplianceEngine(self.storage, self.customer_manager, self.audit_trail)
        self.transaction_processor = TransactionProcessor(
            self.storage, self.ledger, self.account_manager, 
            self.customer_manager, self.compliance_engine, self.audit_trail
        )
        self.interest_engine = InterestEngine(
            self.storage, self.ledger, self.account_manager,
            self.transaction_processor, self.audit_trail
        )
        self.credit_manager = CreditLineManager(
            self.storage, self.account_manager, self.transaction_processor,
            self.interest_engine, self.audit_trail
        )
        self.loan_manager = LoanManager(
            self.storage, self.account_manager, self.transaction_processor,
            self.audit_trail
        )
        
        # Initialize new modules
        self.product_engine = ProductEngine(self.storage, self.audit_trail)
        self.collections_manager = CollectionsManager(
            self.storage, self.account_manager, self.loan_manager, self.credit_manager
        )
        self.reporting_engine = ReportingEngine(
            self.storage, self.ledger, self.account_manager, self.loan_manager,
            self.credit_manager, self.collections_manager, self.customer_manager,
            self.product_engine, self.audit_trail
        )
        self.workflow_engine = WorkflowEngine(self.storage, self.audit_trail)
        self.rbac_manager = RBACManager(self.storage, self.audit_trail)
        self.custom_field_manager = CustomFieldManager(self.storage, self.audit_trail)
        self.notification_engine = NotificationEngine(self.storage, self.audit_trail)


# Global banking system instance - will be initialized in lifespan
banking_system = None
async_storage_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager for async storage pool management"""
    global banking_system, async_storage_instance
    
    # Startup: initialize async storage if configured
    try:
        async_storage_instance = create_async_storage()
        
        # Initialize the storage if it has an initialize method (e.g., PostgreSQL pool)
        if hasattr(async_storage_instance, 'initialize'):
            await async_storage_instance.initialize()
        
        # Create banking system with async storage
        banking_system = BankingSystem(async_storage=async_storage_instance)
        
        print("✅ Banking system initialized with async storage")
        
    except Exception as e:
        print(f"⚠️  Falling back to sync storage due to: {e}")
        # Fall back to sync storage
        banking_system = BankingSystem(use_sqlite=True)
    
    yield
    
    # Shutdown: close async storage pool
    if async_storage_instance and hasattr(async_storage_instance, 'close'):
        await async_storage_instance.close()
        print("✅ Async storage pool closed")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Core Banking System API",
    description="Production-grade core banking system with double-entry bookkeeping",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
app.middleware("http")(RateLimiter(requests_per_minute=60))


# Dependency to get banking system
def get_banking_system() -> BankingSystem:
    if banking_system is None:
        raise HTTPException(status_code=503, detail="Banking system not initialized")
    return banking_system


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


# Customer Management Endpoints
@app.post("/customers", status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: CreateCustomerRequest,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(require_permission("CREATE_CUSTOMER"))
):
    """Create a new customer"""
    try:
        date_of_birth = None
        if request.date_of_birth:
            date_of_birth = datetime.fromisoformat(request.date_of_birth)
        
        address = None
        if request.address:
            address = request.address.to_address()
        
        customer = system.customer_manager.create_customer(
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
            date_of_birth=date_of_birth,
            address=address
        )
        
        return {"customer_id": customer.id, "message": "Customer created successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/customers/{customer_id}")
async def get_customer(
    customer_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get customer by ID"""
    customer = system.customer_manager.get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    return {
        "id": customer.id,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email,
        "phone": customer.phone,
        "kyc_status": customer.kyc_status.value,
        "kyc_tier": customer.kyc_tier.value,
        "is_active": customer.is_active,
        "created_at": customer.created_at.isoformat()
    }


@app.put("/customers/{customer_id}")
async def update_customer(
    customer_id: str,
    request: UpdateCustomerRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Update customer information"""
    try:
        address = None
        if request.address:
            address = request.address.to_address()
        
        customer = system.customer_manager.update_customer_info(
            customer_id=customer_id,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
            address=address
        )
        
        return {"message": "Customer updated successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/customers/{customer_id}/kyc")
async def update_kyc_status(
    customer_id: str,
    request: UpdateKYCRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Update customer KYC status"""
    try:
        new_tier = None
        if request.tier:
            new_tier = KYCTier(request.tier)
        
        customer = system.customer_manager.update_kyc_status(
            customer_id=customer_id,
            new_status=KYCStatus(request.status),
            new_tier=new_tier,
            documents=request.documents,
            expiry_days=request.expiry_days
        )
        
        return {"message": "KYC status updated successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Account Management Endpoints
@app.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(
    request: CreateAccountRequest,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(require_permission("CREATE_ACCOUNT"))
):
    """Create a new account"""
    try:
        interest_rate = None
        if request.interest_rate:
            interest_rate = Decimal(request.interest_rate)
        
        credit_limit = None
        if request.credit_limit:
            credit_limit = request.credit_limit.to_money()
        
        minimum_balance = None
        if request.minimum_balance:
            minimum_balance = request.minimum_balance.to_money()
        
        daily_limit = None
        if request.daily_transaction_limit:
            daily_limit = request.daily_transaction_limit.to_money()
        
        monthly_limit = None
        if request.monthly_transaction_limit:
            monthly_limit = request.monthly_transaction_limit.to_money()
        
        account = system.account_manager.create_account(
            customer_id=request.customer_id,
            product_type=ProductType(request.product_type),
            currency=Currency[request.currency],
            name=request.name,
            account_number=request.account_number,
            interest_rate=interest_rate,
            credit_limit=credit_limit,
            minimum_balance=minimum_balance,
            daily_transaction_limit=daily_limit,
            monthly_transaction_limit=monthly_limit
        )
        
        return {
            "account_id": account.id,
            "account_number": account.account_number,
            "message": "Account created successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get account details"""
    account = system.account_manager.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    book_balance = system.account_manager.get_book_balance(account_id)
    available_balance = system.account_manager.get_available_balance(account_id)
    
    return {
        "id": account.id,
        "account_number": account.account_number,
        "customer_id": account.customer_id,
        "product_type": account.product_type.value,
        "currency": account.currency.code,
        "name": account.name,
        "state": account.state.value,
        "book_balance": MoneyModel.from_money(book_balance).dict(),
        "available_balance": MoneyModel.from_money(available_balance).dict(),
        "created_at": account.created_at.isoformat()
    }


@app.get("/customers/{customer_id}/accounts")
async def get_customer_accounts(
    customer_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get all accounts for a customer"""
    accounts = system.account_manager.get_customer_accounts(customer_id)
    
    result = []
    for account in accounts:
        book_balance = system.account_manager.get_book_balance(account.id)
        result.append({
            "id": account.id,
            "account_number": account.account_number,
            "product_type": account.product_type.value,
            "currency": account.currency.code,
            "name": account.name,
            "state": account.state.value,
            "book_balance": MoneyModel.from_money(book_balance).dict()
        })
    
    return {"accounts": result}


# Transaction Endpoints
@app.post("/transactions/deposit")
async def deposit(
    request: DepositRequest,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(require_permission("CREATE_TRANSACTION"))
):
    """Make a deposit"""
    try:
        transaction = system.transaction_processor.deposit(
            account_id=request.account_id,
            amount=request.amount.to_money(),
            description=request.description,
            channel=TransactionChannel(request.channel),
            reference=request.reference
        )
        
        processed_txn = system.transaction_processor.process_transaction(transaction.id)
        
        return {
            "transaction_id": processed_txn.id,
            "state": processed_txn.state.value,
            "message": "Deposit processed successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/transactions/withdraw")
async def withdraw(
    request: WithdrawRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Make a withdrawal"""
    try:
        transaction = system.transaction_processor.withdraw(
            account_id=request.account_id,
            amount=request.amount.to_money(),
            description=request.description,
            channel=TransactionChannel(request.channel),
            reference=request.reference
        )
        
        processed_txn = system.transaction_processor.process_transaction(transaction.id)
        
        return {
            "transaction_id": processed_txn.id,
            "state": processed_txn.state.value,
            "message": "Withdrawal processed successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/transactions/transfer")
async def transfer(
    request: TransferRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Make a transfer between accounts"""
    try:
        transaction = system.transaction_processor.transfer(
            from_account_id=request.from_account_id,
            to_account_id=request.to_account_id,
            amount=request.amount.to_money(),
            description=request.description,
            channel=TransactionChannel(request.channel),
            reference=request.reference
        )
        
        processed_txn = system.transaction_processor.process_transaction(transaction.id)
        
        return {
            "transaction_id": processed_txn.id,
            "state": processed_txn.state.value,
            "message": "Transfer processed successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/accounts/{account_id}/transactions")
async def get_account_transactions(
    account_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(require_permission("VIEW_TRANSACTION"))
):
    """Get transaction history for account with pagination"""
    all_transactions = system.transaction_processor.get_account_transactions(
        account_id=account_id,
        limit=None  # Get all for proper pagination
    )
    
    # Apply pagination
    total = len(all_transactions)
    transactions = all_transactions[skip:skip + limit]
    
    result = []
    for txn in transactions:
        result.append({
            "id": txn.id,
            "transaction_type": txn.transaction_type.value,
            "amount": MoneyModel.from_money(txn.amount).dict(),
            "description": txn.description,
            "state": txn.state.value,
            "created_at": txn.created_at.isoformat(),
            "processed_at": txn.processed_at.isoformat() if txn.processed_at else None
        })
    
    return {
        "items": result,
        "total": total,
        "skip": skip,
        "limit": limit
    }


# Credit Line Endpoints
@app.post("/credit/payment")
async def make_credit_payment(
    request: CreditPaymentRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Make a payment toward credit line balance"""
    try:
        payment_date = None
        if request.payment_date:
            payment_date = date.fromisoformat(request.payment_date)
        
        transaction_id = system.credit_manager.make_payment(
            account_id=request.account_id,
            amount=request.amount.to_money(),
            payment_date=payment_date
        )
        
        return {
            "transaction_id": transaction_id,
            "message": "Credit payment processed successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/credit/{account_id}/statement")
async def generate_credit_statement(
    account_id: str,
    statement_date: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Generate monthly credit statement"""
    try:
        stmt_date = None
        if statement_date:
            stmt_date = date.fromisoformat(statement_date)
        
        statement = system.credit_manager.generate_monthly_statement(
            account_id=account_id,
            statement_date=stmt_date
        )
        
        return {
            "statement_id": statement.id,
            "statement_date": statement.statement_date.isoformat(),
            "due_date": statement.due_date.isoformat(),
            "current_balance": MoneyModel.from_money(statement.current_balance).dict(),
            "minimum_payment_due": MoneyModel.from_money(statement.minimum_payment_due).dict(),
            "message": "Statement generated successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/credit/{account_id}/statements")
async def get_credit_statements(
    account_id: str,
    limit: Optional[int] = 12,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get credit statements for account"""
    statements = system.credit_manager.get_account_statements(account_id, limit)
    
    result = []
    for stmt in statements:
        result.append({
            "id": stmt.id,
            "statement_date": stmt.statement_date.isoformat(),
            "due_date": stmt.due_date.isoformat(),
            "current_balance": MoneyModel.from_money(stmt.current_balance).dict(),
            "minimum_payment_due": MoneyModel.from_money(stmt.minimum_payment_due).dict(),
            "status": stmt.status.value
        })
    
    return {"statements": result}


# Loan Endpoints
@app.post("/loans", status_code=status.HTTP_201_CREATED)
async def create_loan(
    request: CreateLoanRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Originate a new loan"""
    try:
        loan = system.loan_manager.originate_loan(
            customer_id=request.customer_id,
            terms=request.terms.to_loan_terms(),
            currency=Currency[request.currency]
        )
        
        return {
            "loan_id": loan.id,
            "account_id": loan.account_id,
            "state": loan.state.value,
            "message": "Loan originated successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/loans/{loan_id}/disburse")
async def disburse_loan(
    loan_id: str,
    disbursement_account_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Disburse loan funds"""
    try:
        transaction_id = system.loan_manager.disburse_loan(
            loan_id=loan_id,
            disbursement_account_id=disbursement_account_id
        )
        
        return {
            "transaction_id": transaction_id,
            "message": "Loan disbursed successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/loans/payment")
async def make_loan_payment(
    request: LoanPaymentRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Make a loan payment"""
    try:
        payment_date = None
        if request.payment_date:
            payment_date = date.fromisoformat(request.payment_date)
        
        payment = system.loan_manager.make_payment(
            loan_id=request.loan_id,
            payment_amount=request.amount.to_money(),
            payment_date=payment_date,
            source_account_id=request.source_account_id
        )
        
        return {
            "payment_id": payment.id,
            "principal_amount": MoneyModel.from_money(payment.principal_amount).dict(),
            "interest_amount": MoneyModel.from_money(payment.interest_amount).dict(),
            "message": "Loan payment processed successfully"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/loans/{loan_id}")
async def get_loan(
    loan_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get loan details"""
    loan = system.loan_manager.get_loan(loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    
    return {
        "id": loan.id,
        "customer_id": loan.customer_id,
        "account_id": loan.account_id,
        "state": loan.state.value,
        "principal_amount": MoneyModel.from_money(loan.terms.principal_amount).dict(),
        "current_balance": MoneyModel.from_money(loan.current_balance).dict(),
        "annual_interest_rate": str(loan.terms.annual_interest_rate),
        "term_months": loan.terms.term_months,
        "monthly_payment": MoneyModel.from_money(loan.monthly_payment).dict(),
        "originated_date": loan.originated_date.isoformat() if loan.originated_date else None,
        "maturity_date": loan.maturity_date.isoformat() if loan.maturity_date else None
    }


@app.get("/loans/{loan_id}/schedule")
async def get_loan_schedule(
    loan_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get loan amortization schedule"""
    schedule = system.loan_manager.get_amortization_schedule(loan_id)
    
    result = []
    for entry in schedule:
        result.append({
            "payment_number": entry.payment_number,
            "payment_date": entry.payment_date.isoformat(),
            "payment_amount": MoneyModel.from_money(entry.payment_amount).dict(),
            "principal_amount": MoneyModel.from_money(entry.principal_amount).dict(),
            "interest_amount": MoneyModel.from_money(entry.interest_amount).dict(),
            "remaining_balance": MoneyModel.from_money(entry.remaining_balance).dict()
        })
    
    return {"schedule": result}


# Interest and Maintenance Endpoints
@app.post("/admin/interest/daily-accrual")
async def run_daily_interest_accrual(
    accrual_date: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Run daily interest accrual for all accounts"""
    try:
        date_to_process = None
        if accrual_date:
            date_to_process = date.fromisoformat(accrual_date)
        
        results = system.interest_engine.run_daily_accrual(date_to_process)
        
        return {
            "results": results,
            "message": "Daily interest accrual completed"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/admin/interest/monthly-posting")
async def post_monthly_interest(
    month: Optional[int] = None,
    year: Optional[int] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Post accrued interest as transactions"""
    try:
        results = system.interest_engine.post_monthly_interest(month, year)
        
        return {
            "results": results,
            "message": "Monthly interest posting completed"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Audit and Compliance Endpoints
@app.get("/audit/events")
async def get_audit_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(require_permission("VIEW_AUDIT_LOG"))
):
    """Get audit events with pagination"""
    if entity_type and entity_id:
        all_events = system.audit_trail.get_events_for_entity(entity_type, entity_id, limit=None)
    else:
        all_events = system.audit_trail.get_all_events(limit=None)
    
    # Apply pagination
    total = len(all_events)
    events = all_events[skip:skip + limit]
    
    result = []
    for event in events:
        result.append({
            "id": event.id,
            "event_type": event.event_type.value,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "created_at": event.created_at.isoformat(),
            "metadata": event.metadata
        })
    
    return {
        "items": result,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@app.get("/audit/integrity")
async def verify_audit_integrity(
    system: BankingSystem = Depends(get_banking_system)
):
    """Verify audit trail integrity"""
    integrity_result = system.audit_trail.verify_integrity()
    return integrity_result


@app.get("/compliance/alerts")
async def get_compliance_alerts(
    status: Optional[str] = None,
    min_risk_score: Optional[int] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get suspicious activity alerts"""
    alerts = system.compliance_engine.get_suspicious_alerts(status, min_risk_score)
    
    result = []
    for alert in alerts:
        result.append({
            "id": alert.id,
            "customer_id": alert.customer_id,
            "activity_type": alert.activity_type.value,
            "description": alert.description,
            "risk_score": alert.risk_score,
            "status": alert.status,
            "created_at": alert.created_at.isoformat()
        })
    
    return {"alerts": result}


# Products API Endpoints
@app.post("/products", status_code=status.HTTP_201_CREATED, tags=["Products"])
async def create_product(
    request: CreateProductRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Create a new product definition"""
    try:
        product = system.product_engine.create_product(
            name=request.name,
            description=request.description,
            product_type=ProductType[request.product_type.upper()],
            currency=Currency[request.currency.upper()],
            product_code=request.product_code
        )
        
        return {
            "product_id": product.id,
            "product_code": product.product_code,
            "message": "Product created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/products", tags=["Products"])
async def list_products(
    product_type: Optional[str] = None,
    status: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """List products with optional filters"""
    try:
        pt_filter = None
        status_filter = None
        
        if product_type:
            pt_filter = ProductType[product_type.upper()]
        if status:
            status_filter = ProductStatus[status.upper()]
        
        products = system.product_engine.list_products(pt_filter, status_filter)
        
        result = []
        for product in products:
            result.append({
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "product_type": product.product_type.value,
                "currency": product.currency.code,
                "product_code": product.product_code,
                "status": product.status.value,
                "created_at": product.created_at.isoformat()
            })
        
        return {"products": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/products/{product_id}", tags=["Products"])
async def get_product(
    product_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get product by ID"""
    product = system.product_engine.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "product_type": product.product_type.value,
        "currency": product.currency.code,
        "product_code": product.product_code,
        "status": product.status.value,
        "version": product.version,
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat()
    }


@app.put("/products/{product_id}", tags=["Products"])
async def update_product(
    product_id: str,
    request: UpdateProductRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Update product"""
    try:
        updates = {}
        if request.name:
            updates["name"] = request.name
        if request.description:
            updates["description"] = request.description
        if request.interest_rate:
            from decimal import Decimal
            updates["interest_rate"] = Decimal(request.interest_rate)
        
        product = system.product_engine.update_product(product_id, **updates)
        
        return {"message": "Product updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/products/{product_id}/activate", tags=["Products"])
async def activate_product(
    product_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Activate product"""
    try:
        product = system.product_engine.activate_product(product_id)
        return {"message": "Product activated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/products/{product_id}/suspend", tags=["Products"])
async def suspend_product(
    product_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Suspend product"""
    try:
        product = system.product_engine.suspend_product(product_id)
        return {"message": "Product suspended successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/products/{product_id}/retire", tags=["Products"])
async def retire_product(
    product_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Retire product"""
    try:
        product = system.product_engine.retire_product(product_id)
        return {"message": "Product retired successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/products/{product_id}/fees", tags=["Products"])
async def calculate_fees(
    product_id: str,
    event_type: str,
    amount: str,
    currency: str = "USD",
    system: BankingSystem = Depends(get_banking_system)
):
    """Calculate fees for a product"""
    try:
        product = system.product_engine.get_product(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        amount_money = Money(Decimal(amount), Currency[currency.upper()])
        fee_amount = system.product_engine.calculate_fees(product, event_type, amount_money)
        
        return {
            "event_type": event_type,
            "amount": MoneyModel.from_money(amount_money).dict(),
            "fee_amount": MoneyModel.from_money(fee_amount).dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/products/{product_id}/interest-rate", tags=["Products"])
async def get_interest_rate(
    product_id: str,
    risk_score: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get interest rate for product"""
    try:
        product = system.product_engine.get_product(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        risk_score_decimal = None
        if risk_score:
            risk_score_decimal = Decimal(risk_score)
        
        rate = system.product_engine.get_interest_rate(product, risk_score_decimal)
        
        return {
            "product_id": product_id,
            "interest_rate": str(rate) if rate else None,
            "risk_score": risk_score
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Collections API Endpoints
@app.post("/collections/scan", tags=["Collections"])
async def scan_delinquencies(
    system: BankingSystem = Depends(get_banking_system)
):
    """Scan for delinquencies"""
    try:
        results = system.collections_manager.scan_delinquencies()
        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/collections/cases", tags=["Collections"])
async def list_cases(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    collector: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """List collection cases"""
    try:
        status_filter = None
        if status:
            status_filter = DelinquencyStatus[status.upper()]
        
        cases = system.collections_manager.get_cases(status_filter, priority, collector)
        
        result = []
        for case in cases:
            result.append({
                "id": case.id,
                "status": case.status.value,
                "days_past_due": case.days_past_due,
                "amount_overdue": MoneyModel.from_money(case.amount_overdue).dict(),
                "priority": case.priority,
                "assigned_collector": case.assigned_collector,
                "customer_id": case.customer_id,
                "created_at": case.created_at.isoformat()
            })
        
        return {"cases": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/collections/cases/{case_id}", tags=["Collections"])
async def get_case(
    case_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get case details"""
    case = system.collections_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    return {
        "id": case.id,
        "status": case.status.value,
        "days_past_due": case.days_past_due,
        "amount_overdue": MoneyModel.from_money(case.amount_overdue).dict(),
        "total_outstanding": MoneyModel.from_money(case.total_outstanding).dict(),
        "priority": case.priority,
        "assigned_collector": case.assigned_collector,
        "customer_id": case.customer_id,
        "account_id": case.account_id,
        "created_at": case.created_at.isoformat(),
        "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None
    }


@app.put("/collections/cases/{case_id}/assign", tags=["Collections"])
async def assign_collector(
    case_id: str,
    request: AssignCollectorRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Assign collector to case"""
    try:
        case = system.collections_manager.assign_collector(case_id, request.collector_id)
        return {"message": "Collector assigned successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/collections/cases/{case_id}/actions", tags=["Collections"])
async def record_action(
    case_id: str,
    request: RecordActionRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Record collection action"""
    try:
        next_follow_up = None
        if request.next_follow_up:
            next_follow_up = date.fromisoformat(request.next_follow_up)
        
        action = system.collections_manager.record_action(
            case_id=case_id,
            action_type=CollectionAction[request.action_type.upper()],
            performed_by=request.performed_by,
            notes=request.notes,
            result=ActionResult[request.result.upper()],
            next_follow_up=next_follow_up
        )
        
        return {
            "action_id": action.id,
            "message": "Action recorded successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/collections/cases/{case_id}/promises", tags=["Collections"])
async def record_promise(
    case_id: str,
    request: RecordPromiseRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Record payment promise"""
    try:
        promise = system.collections_manager.record_promise(
            case_id=case_id,
            promised_amount=request.promised_amount.to_money(),
            promised_date=date.fromisoformat(request.promised_date)
        )
        
        return {
            "promise_id": promise.id,
            "message": "Promise recorded successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/collections/promises/check", tags=["Collections"])
async def check_promises(
    system: BankingSystem = Depends(get_banking_system)
):
    """Check for broken promises"""
    try:
        results = system.collections_manager.check_promises()
        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/collections/cases/{case_id}/resolve", tags=["Collections"])
async def resolve_case(
    case_id: str,
    request: ResolveCaseRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Resolve collection case"""
    try:
        from .collections import CaseResolution
        case = system.collections_manager.resolve_case(
            case_id=case_id,
            resolution=CaseResolution[request.resolution.upper()]
        )
        
        return {"message": "Case resolved successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/collections/summary", tags=["Collections"])
async def get_collection_summary(
    system: BankingSystem = Depends(get_banking_system)
):
    """Get portfolio collection summary"""
    try:
        summary = system.collections_manager.get_collection_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/collections/recovery-rate", tags=["Collections"])
async def get_recovery_rate(
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get recovery rate statistics"""
    try:
        start_date = None
        end_date = None
        
        if period_start:
            start_date = date.fromisoformat(period_start)
        if period_end:
            end_date = date.fromisoformat(period_end)
        
        stats = system.collections_manager.get_recovery_rate(start_date, end_date)
        return stats
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/collections/auto-actions", tags=["Collections"])
async def run_auto_actions(
    system: BankingSystem = Depends(get_banking_system)
):
    """Run automatic collection actions"""
    try:
        results = system.collections_manager.run_auto_actions()
        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/collections/strategies", tags=["Collections"])
async def set_strategy(
    request: SetStrategyRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Set collection strategy"""
    try:
        from .collections import CollectionStrategy
        strategy = CollectionStrategy(
            product_id=request.product_id,
            auto_write_off_days=request.auto_write_off_days
        )
        system.collections_manager.set_strategy(strategy)
        
        return {"message": "Strategy updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/collections/strategies", tags=["Collections"])
async def get_strategy(
    product_id: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get collection strategy"""
    try:
        strategy = system.collections_manager.get_strategy(product_id)
        
        return {
            "product_id": strategy.product_id,
            "auto_write_off_days": strategy.auto_write_off_days,
            "promise_tolerance_days": strategy.promise_tolerance_days
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# System Information
@app.get("/")
async def root():
    """Root endpoint with system information"""
    return {
        "system": "Core Banking System",
        "version": "1.0.0",
        "description": "Production-grade banking system with double-entry bookkeeping",
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "customers": "/customers",
            "accounts": "/accounts", 
            "transactions": "/transactions",
            "credit": "/credit",
            "loans": "/loans",
            "audit": "/audit",
            "compliance": "/compliance",
            "products": "/products",
            "collections": "/collections",
            "reports": "/reports",
            "workflows": "/workflows",
            "rbac": "/rbac",
            "custom-fields": "/custom-fields"
        }
    }


# Reporting API Endpoints
@app.get("/reports/portfolio-summary", tags=["Reports"])
async def portfolio_summary(
    currency: str = "USD",
    system: BankingSystem = Depends(get_banking_system)
):
    """Get portfolio summary report"""
    try:
        result = system.reporting_engine.portfolio_summary(Currency[currency.upper()])
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/loan-portfolio", tags=["Reports"])
async def loan_portfolio_report(
    currency: str = "USD",
    product_type: Optional[str] = None,
    state: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get loan portfolio report"""
    try:
        filters = {"currency": currency}
        if product_type:
            filters["product_type"] = product_type
        if state:
            filters["state"] = state
        
        result = system.reporting_engine.loan_portfolio_report(filters)
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/deposit-portfolio", tags=["Reports"])
async def deposit_portfolio_report(
    currency: str = "USD",
    system: BankingSystem = Depends(get_banking_system)
):
    """Get deposit portfolio report"""
    try:
        filters = {"currency": currency}
        result = system.reporting_engine.deposit_portfolio_report(filters)
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/delinquency", tags=["Reports"])
async def delinquency_report(
    currency: str = "USD",
    system: BankingSystem = Depends(get_banking_system)
):
    """Get delinquency aging report"""
    try:
        result = system.reporting_engine.delinquency_report(Currency[currency.upper()])
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/income-statement", tags=["Reports"])
async def income_statement(
    period_start: str,
    period_end: str,
    currency: str = "USD",
    system: BankingSystem = Depends(get_banking_system)
):
    """Get income statement"""
    try:
        start_date = datetime.fromisoformat(period_start)
        end_date = datetime.fromisoformat(period_end)
        
        result = system.reporting_engine.income_statement(start_date, end_date, Currency[currency.upper()])
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "period_start": result.period_start.isoformat(),
            "period_end": result.period_end.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/transaction-volume", tags=["Reports"])
async def transaction_volume_report(
    period_start: str,
    period_end: str,
    currency: str = "USD",
    system: BankingSystem = Depends(get_banking_system)
):
    """Get transaction volume report"""
    try:
        start_date = datetime.fromisoformat(period_start)
        end_date = datetime.fromisoformat(period_end)
        
        result = system.reporting_engine.transaction_volume_report(start_date, end_date, Currency[currency.upper()])
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "period_start": result.period_start.isoformat(),
            "period_end": result.period_end.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/product-performance", tags=["Reports"])
async def product_performance_report(
    currency: str = "USD",
    system: BankingSystem = Depends(get_banking_system)
):
    """Get product performance report"""
    try:
        result = system.reporting_engine.product_performance_report(Currency[currency.upper()])
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/customer-segments", tags=["Reports"])
async def customer_segments_report(
    currency: str = "USD",
    system: BankingSystem = Depends(get_banking_system)
):
    """Get customer segments report"""
    try:
        result = system.reporting_engine.customer_segment_report(Currency[currency.upper()])
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/collection-performance", tags=["Reports"])
async def collection_performance_report(
    currency: str = "USD",
    system: BankingSystem = Depends(get_banking_system)
):
    """Get collection performance report"""
    try:
        result = system.reporting_engine.collection_performance_report(Currency[currency.upper()])
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reports/definitions", status_code=status.HTTP_201_CREATED, tags=["Reports"])
async def create_report_definition(
    request: CreateReportRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Create custom report definition"""
    try:
        from .reporting import ReportDefinition
        definition = ReportDefinition(
            name=request.name,
            description=request.description,
            report_type=ReportType[request.report_type.upper()]
        )
        
        created_def = system.reporting_engine.create_report_definition(definition)
        
        return {
            "definition_id": created_def.id,
            "message": "Report definition created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/definitions", tags=["Reports"])
async def list_report_definitions(
    system: BankingSystem = Depends(get_banking_system)
):
    """List report definitions"""
    try:
        definitions = system.reporting_engine.list_report_definitions()
        
        result = []
        for definition in definitions:
            result.append({
                "id": definition.id,
                "name": definition.name,
                "description": definition.description,
                "report_type": definition.report_type.value,
                "is_template": definition.is_template,
                "created_at": definition.created_at.isoformat()
            })
        
        return {"definitions": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/reports/definitions/{report_id}/run", tags=["Reports"])
async def run_custom_report(
    report_id: str,
    request: RunReportRequest = RunReportRequest(),
    system: BankingSystem = Depends(get_banking_system)
):
    """Run custom report"""
    try:
        period_start = None
        period_end = None
        
        if request.period_start:
            period_start = datetime.fromisoformat(request.period_start)
        if request.period_end:
            period_end = datetime.fromisoformat(request.period_end)
        
        result = system.reporting_engine.run_report(
            report_id=report_id,
            period_start=period_start,
            period_end=period_end,
            filters=request.filters
        )
        
        return {
            "report_id": result.report_id,
            "generated_at": result.generated_at.isoformat(),
            "data": result.data,
            "totals": result.totals,
            "metadata": result.metadata
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/reports/definitions/{report_id}/export", tags=["Reports"])
async def export_report(
    report_id: str,
    format: str = "json",
    system: BankingSystem = Depends(get_banking_system)
):
    """Export report"""
    try:
        # First run the report
        result = system.reporting_engine.run_report(report_id)
        
        # Then export it
        export_format = ReportFormat[format.upper()]
        exported = system.reporting_engine.export_report(result, export_format)
        
        if format.lower() == "csv":
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(content=exported, media_type="text/csv")
        else:
            return exported
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Workflows API Endpoints
@app.post("/workflows/definitions", status_code=status.HTTP_201_CREATED, tags=["Workflows"])
async def create_workflow_definition(
    request: CreateWorkflowDefinitionRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Create workflow definition"""
    try:
        from .workflows import WorkflowDefinition, WorkflowStepDefinition, StepType
        
        # Convert steps
        steps = []
        for i, step_data in enumerate(request.steps):
            step = WorkflowStepDefinition(
                step_number=i + 1,
                name=step_data.get("name", f"Step {i + 1}"),
                step_type=StepType[step_data.get("step_type", "APPROVAL").upper()],
                required_role=step_data.get("required_role", "BRANCH_MANAGER"),
                required_approvals=step_data.get("required_approvals", 1)
            )
            steps.append(step)
        
        definition = WorkflowDefinition(
            name=request.name,
            description=request.description,
            workflow_type=WorkflowType[request.workflow_type.upper()],
            steps=steps,
            sla_hours=request.sla_hours
        )
        
        definition_id = system.workflow_engine.create_definition(definition)
        
        return {
            "definition_id": definition_id,
            "message": "Workflow definition created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/workflows/definitions", tags=["Workflows"])
async def list_workflow_definitions(
    workflow_type: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """List workflow definitions"""
    try:
        wf_type = None
        if workflow_type:
            wf_type = WorkflowType[workflow_type.upper()]
        
        definitions = system.workflow_engine.list_definitions(wf_type)
        
        result = []
        for definition in definitions:
            result.append({
                "id": definition.id,
                "name": definition.name,
                "description": definition.description,
                "workflow_type": definition.workflow_type.value,
                "is_active": definition.is_active,
                "steps_count": len(definition.steps),
                "created_at": definition.created_at.isoformat()
            })
        
        return {"definitions": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/workflows/definitions/{definition_id}", tags=["Workflows"])
async def get_workflow_definition(
    definition_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get workflow definition"""
    definition = system.workflow_engine.get_definition(definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    
    steps = []
    for step in definition.steps:
        steps.append({
            "step_number": step.step_number,
            "name": step.name,
            "step_type": step.step_type.value,
            "required_role": step.required_role,
            "required_approvals": step.required_approvals,
            "sla_hours": step.sla_hours,
            "can_skip": step.can_skip
        })
    
    return {
        "id": definition.id,
        "name": definition.name,
        "description": definition.description,
        "workflow_type": definition.workflow_type.value,
        "is_active": definition.is_active,
        "steps": steps,
        "created_at": definition.created_at.isoformat()
    }


@app.post("/workflows/definitions/{definition_id}/activate", tags=["Workflows"])
async def activate_workflow_definition(
    definition_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Activate workflow definition"""
    try:
        success = system.workflow_engine.activate_definition(definition_id)
        if success:
            return {"message": "Workflow definition activated successfully"}
        else:
            raise HTTPException(status_code=404, detail="Workflow definition not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/workflows/definitions/{definition_id}/deactivate", tags=["Workflows"])
async def deactivate_workflow_definition(
    definition_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Deactivate workflow definition"""
    try:
        success = system.workflow_engine.deactivate_definition(definition_id)
        if success:
            return {"message": "Workflow definition deactivated successfully"}
        else:
            raise HTTPException(status_code=404, detail="Workflow definition not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/workflows", status_code=status.HTTP_201_CREATED, tags=["Workflows"])
async def start_workflow(
    request: StartWorkflowRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Start workflow instance"""
    try:
        instance_id = system.workflow_engine.start_workflow(
            definition_id=request.definition_id,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            initiated_by="system",
            context=request.context
        )
        
        if instance_id:
            return {
                "instance_id": instance_id,
                "message": "Workflow started successfully"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to start workflow")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/workflows", tags=["Workflows"])
async def list_workflows(
    status: Optional[str] = None,
    workflow_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """List workflow instances"""
    try:
        status_filter = None
        type_filter = None
        
        if status:
            status_filter = WorkflowStatus[status.upper()]
        if workflow_type:
            type_filter = WorkflowType[workflow_type.upper()]
        
        workflows = system.workflow_engine.get_workflows(status_filter, type_filter, entity_id)
        
        result = []
        for workflow in workflows:
            result.append({
                "id": workflow.id,
                "status": workflow.status.value,
                "workflow_type": workflow.workflow_type.value,
                "entity_type": workflow.entity_type,
                "entity_id": workflow.entity_id,
                "current_step": workflow.current_step,
                "initiated_by": workflow.initiated_by,
                "initiated_at": workflow.initiated_at.isoformat(),
                "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None
            })
        
        return {"workflows": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/workflows/{instance_id}", tags=["Workflows"])
async def get_workflow(
    instance_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get workflow instance"""
    workflow = system.workflow_engine.get_workflow(instance_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    steps = []
    for step in workflow.steps:
        steps.append({
            "step_number": step.step_number,
            "name": step.name,
            "status": step.status.value,
            "assigned_to": step.assigned_to,
            "decision": step.decision,
            "comments": step.comments,
            "completed_at": step.completed_at.isoformat() if step.completed_at else None
        })
    
    return {
        "id": workflow.id,
        "status": workflow.status.value,
        "workflow_type": workflow.workflow_type.value,
        "entity_type": workflow.entity_type,
        "entity_id": workflow.entity_id,
        "current_step": workflow.current_step,
        "steps": steps,
        "context": workflow.context,
        "initiated_at": workflow.initiated_at.isoformat(),
        "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None
    }


@app.get("/workflows/pending-tasks", tags=["Workflows"])
async def get_pending_tasks(
    role: Optional[str] = None,
    user: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get pending workflow tasks"""
    try:
        tasks = system.workflow_engine.get_pending_tasks(role, user)
        return {"tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/workflows/{instance_id}/steps/{step_number}/approve", tags=["Workflows"])
async def approve_workflow_step(
    instance_id: str,
    step_number: int,
    request: ApproveStepRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Approve workflow step"""
    try:
        success = system.workflow_engine.approve_step(
            instance_id=instance_id,
            step_number=step_number,
            approver="system",
            comments=request.comments
        )
        
        if success:
            return {"message": "Step approved successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to approve step")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/workflows/{instance_id}/steps/{step_number}/reject", tags=["Workflows"])
async def reject_workflow_step(
    instance_id: str,
    step_number: int,
    request: RejectStepRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Reject workflow step"""
    try:
        success = system.workflow_engine.reject_step(
            instance_id=instance_id,
            step_number=step_number,
            rejector="system",
            comments=request.comments
        )
        
        if success:
            return {"message": "Step rejected successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to reject step")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/workflows/{instance_id}/steps/{step_number}/skip", tags=["Workflows"])
async def skip_workflow_step(
    instance_id: str,
    step_number: int,
    request: SkipStepRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Skip workflow step"""
    try:
        success = system.workflow_engine.skip_step(
            instance_id=instance_id,
            step_number=step_number,
            skipped_by="system",
            reason=request.reason
        )
        
        if success:
            return {"message": "Step skipped successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to skip step")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/workflows/{instance_id}/steps/{step_number}/assign", tags=["Workflows"])
async def assign_workflow_step(
    instance_id: str,
    step_number: int,
    request: AssignStepRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Assign workflow step"""
    try:
        success = system.workflow_engine.assign_step(
            instance_id=instance_id,
            step_number=step_number,
            user=request.user
        )
        
        if success:
            return {"message": "Step assigned successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to assign step")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/workflows/{instance_id}/cancel", tags=["Workflows"])
async def cancel_workflow(
    instance_id: str,
    request: CancelWorkflowRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Cancel workflow"""
    try:
        success = system.workflow_engine.cancel_workflow(
            instance_id=instance_id,
            cancelled_by="system",
            reason=request.reason
        )
        
        if success:
            return {"message": "Workflow cancelled successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to cancel workflow")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/workflows/check-sla", tags=["Workflows"])
async def check_sla_breaches(
    system: BankingSystem = Depends(get_banking_system)
):
    """Check SLA breaches"""
    try:
        breaches = system.workflow_engine.check_sla_breaches()
        return {"breaches": breaches}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/workflows/history/{entity_type}/{entity_id}", tags=["Workflows"])
async def get_workflow_history(
    entity_type: str,
    entity_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get workflow history for entity"""
    try:
        workflows = system.workflow_engine.get_workflow_history(entity_type, entity_id)
        
        result = []
        for workflow in workflows:
            result.append({
                "id": workflow.id,
                "status": workflow.status.value,
                "workflow_type": workflow.workflow_type.value,
                "initiated_at": workflow.initiated_at.isoformat(),
                "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None
            })
        
        return {"workflows": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# RBAC API Endpoints
@app.post("/rbac/roles", status_code=status.HTTP_201_CREATED, tags=["RBAC"])
async def create_role(
    request: CreateRoleRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Create role"""
    try:
        permissions = {Permission[p.upper()] for p in request.permissions}
        
        max_transaction = None
        if request.max_transaction_amount:
            max_transaction = request.max_transaction_amount.to_money()
        
        max_approval = None
        if request.max_approval_amount:
            max_approval = request.max_approval_amount.to_money()
        
        role_id = system.rbac_manager.create_role(
            name=request.name,
            description=request.description,
            permissions=permissions,
            max_transaction_amount=max_transaction,
            max_approval_amount=max_approval
        )
        
        return {
            "role_id": role_id,
            "message": "Role created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rbac/roles", tags=["RBAC"])
async def list_roles(
    system: BankingSystem = Depends(get_banking_system)
):
    """List roles"""
    try:
        roles = system.rbac_manager.list_roles()
        
        result = []
        for role in roles:
            result.append({
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "permissions": [p.value for p in role.permissions],
                "is_system_role": role.is_system_role,
                "created_at": role.created_at.isoformat()
            })
        
        return {"roles": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rbac/roles/{role_id}", tags=["RBAC"])
async def get_role(
    role_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get role"""
    role = system.rbac_manager.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "permissions": [p.value for p in role.permissions],
        "is_system_role": role.is_system_role,
        "max_transaction_amount": MoneyModel.from_money(role.max_transaction_amount).dict() if role.max_transaction_amount else None,
        "max_approval_amount": MoneyModel.from_money(role.max_approval_amount).dict() if role.max_approval_amount else None,
        "created_at": role.created_at.isoformat()
    }


@app.put("/rbac/roles/{role_id}", tags=["RBAC"])
async def update_role(
    role_id: str,
    request: UpdateRoleRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Update role"""
    try:
        updates = {}
        if request.description:
            updates["description"] = request.description
        if request.permissions:
            updates["permissions"] = {Permission[p.upper()] for p in request.permissions}
        if request.max_transaction_amount:
            updates["max_transaction_amount"] = request.max_transaction_amount.to_money()
        if request.max_approval_amount:
            updates["max_approval_amount"] = request.max_approval_amount.to_money()
        
        success = system.rbac_manager.update_role(role_id, **updates)
        if success:
            return {"message": "Role updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="Role not found or cannot be updated")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/rbac/roles/{role_id}", tags=["RBAC"])
async def delete_role(
    role_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Delete role"""
    try:
        success = system.rbac_manager.delete_role(role_id)
        if success:
            return {"message": "Role deleted successfully"}
        else:
            raise HTTPException(status_code=400, detail="Role cannot be deleted")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rbac/users", status_code=status.HTTP_201_CREATED, tags=["RBAC"])
async def create_user(
    request: CreateUserRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Create user"""
    try:
        user_id = system.rbac_manager.create_user(
            username=request.username,
            email=request.email,
            full_name=request.full_name,
            roles=request.roles,
            created_by="system",
            password=request.password
        )
        
        return {
            "user_id": user_id,
            "message": "User created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rbac/users", tags=["RBAC"])
async def list_users(
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """List users"""
    try:
        users = system.rbac_manager.list_users(role, is_active)
        
        result = []
        for user in users:
            result.append({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "roles": user.roles,
                "is_active": user.is_active,
                "is_locked": user.is_locked,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "created_at": user.created_at.isoformat()
            })
        
        return {"users": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rbac/users/{user_id}", tags=["RBAC"])
async def get_user(
    user_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get user"""
    user = system.rbac_manager.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "roles": user.roles,
        "is_active": user.is_active,
        "is_locked": user.is_locked,
        "branch_id": user.branch_id,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat()
    }


@app.put("/rbac/users/{user_id}", tags=["RBAC"])
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Update user"""
    try:
        success = system.rbac_manager.update_user(
            user_id=user_id,
            email=request.email,
            full_name=request.full_name,
            branch_id=request.branch_id
        )
        
        if success:
            return {"message": "User updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rbac/users/{user_id}/activate", tags=["RBAC"])
async def activate_user(
    user_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Activate user"""
    try:
        success = system.rbac_manager.activate_user(user_id)
        if success:
            return {"message": "User activated successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rbac/users/{user_id}/deactivate", tags=["RBAC"])
async def deactivate_user(
    user_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Deactivate user"""
    try:
        success = system.rbac_manager.deactivate_user(user_id)
        if success:
            return {"message": "User deactivated successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rbac/users/{user_id}/lock", tags=["RBAC"])
async def lock_user(
    user_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Lock user"""
    try:
        success = system.rbac_manager.lock_user(user_id)
        if success:
            return {"message": "User locked successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rbac/users/{user_id}/unlock", tags=["RBAC"])
async def unlock_user(
    user_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Unlock user"""
    try:
        success = system.rbac_manager.unlock_user(user_id)
        if success:
            return {"message": "User unlocked successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rbac/users/{user_id}/roles/{role_id}", tags=["RBAC"])
async def assign_role_to_user(
    user_id: str,
    role_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Assign role to user"""
    try:
        success = system.rbac_manager.assign_role(user_id, role_id)
        if success:
            return {"message": "Role assigned successfully"}
        else:
            raise HTTPException(status_code=404, detail="User or role not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/rbac/users/{user_id}/roles/{role_id}", tags=["RBAC"])
async def remove_role_from_user(
    user_id: str,
    role_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Remove role from user"""
    try:
        success = system.rbac_manager.remove_role(user_id, role_id)
        if success:
            return {"message": "Role removed successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rbac/users/{user_id}/permissions", tags=["RBAC"])
async def get_user_permissions(
    user_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get user's permissions"""
    try:
        permissions = system.rbac_manager.get_user_permissions(user_id)
        return {"permissions": [p.value for p in permissions]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rbac/auth/login", tags=["RBAC"])
async def login(
    request: LoginRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Authenticate user and return JWT token"""
    try:
        session = system.rbac_manager.authenticate(
            username=request.username,
            password=request.password
        )
        
        # Log successful authentication
        log_action(
            logger, "info", f"User authenticated successfully",
            user_id=session.user_id, action="login", resource="auth"
        )
        
        # Generate JWT token
        token_payload = {
            "sub": session.user_id,
            "session_id": session.id,
            "exp": datetime.now(timezone.utc) + timedelta(hours=24),
            "iat": datetime.now(timezone.utc)
        }
        
        token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "session_id": session.id,
            "expires_at": session.expires_at.isoformat(),
            "message": "Login successful"
        }
    except Exception as e:
        # Log failed authentication
        log_action(
            logger, "warning", f"Authentication failed: {str(e)}",
            action="login_failed", resource="auth",
            extra={"username": request.username}
        )
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/rbac/auth/logout", tags=["RBAC"])
async def logout(
    session_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Logout user"""
    try:
        success = system.rbac_manager.logout(session_id)
        if success:
            return {"message": "Logout successful"}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rbac/auth/change-password", tags=["RBAC"])
async def change_password(
    user_id: str,
    request: ChangePasswordRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Change user password"""
    try:
        success = system.rbac_manager.change_password(
            user_id=user_id,
            old_password=request.old_password,
            new_password=request.new_password
        )
        
        if success:
            return {"message": "Password changed successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to change password")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/rbac/auth/session/{session_id}", tags=["RBAC"])
async def validate_session(
    session_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Validate session"""
    try:
        user = system.rbac_manager.validate_session(session_id)
        if user:
            return {
                "valid": True,
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name
            }
        else:
            return {"valid": False}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Custom Fields API Endpoints
@app.post("/custom-fields/definitions", status_code=status.HTTP_201_CREATED, tags=["Custom Fields"])
async def create_field_definition(
    request: CreateFieldRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Create field definition"""
    try:
        field_def = system.custom_field_manager.create_field(
            name=request.name,
            label=request.label,
            description=request.description,
            field_type=FieldType[request.field_type.upper()],
            entity_type=CustomEntityType[request.entity_type.upper()],
            is_required=request.is_required,
            is_searchable=request.is_searchable,
            is_reportable=request.is_reportable,
            default_value=request.default_value,
            enum_values=request.enum_values or [],
            group_name=request.group_name
        )
        
        return {
            "field_id": field_def.id,
            "message": "Field definition created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/custom-fields/definitions", tags=["Custom Fields"])
async def list_field_definitions(
    entity_type: Optional[str] = None,
    group: Optional[str] = None,
    is_active: Optional[bool] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """List field definitions"""
    try:
        entity_type_filter = None
        if entity_type:
            entity_type_filter = CustomEntityType[entity_type.upper()]
        
        fields = system.custom_field_manager.list_fields(entity_type_filter, group, is_active)
        
        result = []
        for field_def in fields:
            result.append({
                "id": field_def.id,
                "name": field_def.name,
                "label": field_def.label,
                "description": field_def.description,
                "field_type": field_def.field_type.value,
                "entity_type": field_def.entity_type.value,
                "is_required": field_def.is_required,
                "is_active": field_def.is_active,
                "group_name": field_def.group_name,
                "created_at": field_def.created_at.isoformat()
            })
        
        return {"fields": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/custom-fields/definitions/{field_id}", tags=["Custom Fields"])
async def get_field_definition(
    field_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get field definition"""
    field_def = system.custom_field_manager.get_field(field_id)
    if not field_def:
        raise HTTPException(status_code=404, detail="Field definition not found")
    
    return {
        "id": field_def.id,
        "name": field_def.name,
        "label": field_def.label,
        "description": field_def.description,
        "field_type": field_def.field_type.value,
        "entity_type": field_def.entity_type.value,
        "is_required": field_def.is_required,
        "is_searchable": field_def.is_searchable,
        "is_reportable": field_def.is_reportable,
        "default_value": field_def.default_value,
        "enum_values": field_def.enum_values,
        "group_name": field_def.group_name,
        "is_active": field_def.is_active,
        "created_at": field_def.created_at.isoformat()
    }


@app.put("/custom-fields/definitions/{field_id}", tags=["Custom Fields"])
async def update_field_definition(
    field_id: str,
    request: UpdateFieldRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Update field definition"""
    try:
        updates = {}
        if request.label:
            updates["label"] = request.label
        if request.description:
            updates["description"] = request.description
        if request.is_required is not None:
            updates["is_required"] = request.is_required
        if request.is_searchable is not None:
            updates["is_searchable"] = request.is_searchable
        if request.is_reportable is not None:
            updates["is_reportable"] = request.is_reportable
        if request.default_value is not None:
            updates["default_value"] = request.default_value
        if request.enum_values is not None:
            updates["enum_values"] = request.enum_values
        if request.group_name is not None:
            updates["group_name"] = request.group_name
        
        field_def = system.custom_field_manager.update_field(field_id, **updates)
        return {"message": "Field definition updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/custom-fields/definitions/{field_id}", tags=["Custom Fields"])
async def delete_field_definition(
    field_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Delete field definition"""
    try:
        success = system.custom_field_manager.delete_field(field_id)
        if success:
            return {"message": "Field definition deleted successfully"}
        else:
            raise HTTPException(status_code=400, detail="Cannot delete field with existing values")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/custom-fields/definitions/{field_id}/activate", tags=["Custom Fields"])
async def activate_field_definition(
    field_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Activate field definition"""
    try:
        field_def = system.custom_field_manager.activate_field(field_id)
        return {"message": "Field definition activated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/custom-fields/definitions/{field_id}/deactivate", tags=["Custom Fields"])
async def deactivate_field_definition(
    field_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Deactivate field definition"""
    try:
        field_def = system.custom_field_manager.deactivate_field(field_id)
        return {"message": "Field definition deactivated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/custom-fields/values/{entity_type}/{entity_id}", tags=["Custom Fields"])
async def set_field_value(
    entity_type: str,
    entity_id: str,
    request: SetFieldValueRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Set field value"""
    try:
        field_value = system.custom_field_manager.set_value(
            entity_type=CustomEntityType[entity_type.upper()],
            entity_id=entity_id,
            field_name=request.field_name,
            value=request.value,
            updated_by="system"
        )
        
        return {
            "field_value_id": field_value.id,
            "message": "Field value set successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/custom-fields/values/{entity_type}/{entity_id}", tags=["Custom Fields"])
async def get_all_field_values(
    entity_type: str,
    entity_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get all field values for entity"""
    try:
        values = system.custom_field_manager.get_all_values(
            entity_type=CustomEntityType[entity_type.upper()],
            entity_id=entity_id
        )
        
        return {"values": values}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/custom-fields/values/{entity_type}/{entity_id}/{field_name}", tags=["Custom Fields"])
async def get_field_value(
    entity_type: str,
    entity_id: str,
    field_name: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get single field value"""
    try:
        value = system.custom_field_manager.get_value(
            entity_type=CustomEntityType[entity_type.upper()],
            entity_id=entity_id,
            field_name=field_name
        )
        
        return {"value": value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/custom-fields/values/{entity_type}/{entity_id}/{field_name}", tags=["Custom Fields"])
async def delete_field_value(
    entity_type: str,
    entity_id: str,
    field_name: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Delete field value"""
    try:
        success = system.custom_field_manager.delete_value(
            entity_type=CustomEntityType[entity_type.upper()],
            entity_id=entity_id,
            field_name=field_name
        )
        
        if success:
            return {"message": "Field value deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Field value not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/custom-fields/values/{entity_type}/{entity_id}/bulk", tags=["Custom Fields"])
async def bulk_set_field_values(
    entity_type: str,
    entity_id: str,
    request: BulkSetValuesRequest,
    system: BankingSystem = Depends(get_banking_system)
):
    """Bulk set field values"""
    try:
        field_values = system.custom_field_manager.bulk_set_values(
            entity_type=CustomEntityType[entity_type.upper()],
            entity_id=entity_id,
            values_dict=request.values,
            updated_by="system"
        )
        
        return {
            "count": len(field_values),
            "message": "Field values set successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/custom-fields/search/{entity_type}", tags=["Custom Fields"])
async def search_entities_by_field(
    entity_type: str,
    field_name: str,
    value: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Search entities by field value"""
    try:
        entity_ids = system.custom_field_manager.search_entities(
            entity_type=CustomEntityType[entity_type.upper()],
            field_name=field_name,
            value=value
        )
        
        return {"entity_ids": entity_ids}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/custom-fields/export/{entity_type}", tags=["Custom Fields"])
async def export_field_data(
    entity_type: str,
    field_names: Optional[str] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Export field data"""
    try:
        field_name_list = None
        if field_names:
            field_name_list = field_names.split(",")
        
        data = system.custom_field_manager.export_field_data(
            entity_type=CustomEntityType[entity_type.upper()],
            field_names=field_name_list
        )
        
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/custom-fields/validate/{entity_type}/{entity_id}", tags=["Custom Fields"])
async def validate_required_fields(
    entity_type: str,
    entity_id: str,
    system: BankingSystem = Depends(get_banking_system)
):
    """Validate required fields for entity"""
    try:
        is_valid, missing_fields = system.custom_field_manager.validate_all_required(
            entity_type=CustomEntityType[entity_type.upper()],
            entity_id=entity_id
        )
        
        return {
            "valid": is_valid,
            "missing_fields": missing_fields
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Kafka Integration Endpoints
@app.post("/kafka/publish-test", tags=["Kafka Integration"])
async def publish_test_event(
    topic: str,
    event_type: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    system: BankingSystem = Depends(get_banking_system)
):
    """Publish a test event (development only)"""
    try:
        from .kafka_integration import EventSchema
        import uuid
        from datetime import datetime, timezone
        
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            entity_type=entity_type,
            entity_id=entity_id,
            data=data or {},
            metadata={"test": True}
        )
        
        # Get event bus from system
        event_bus = getattr(system, 'event_bus', None)
        if not event_bus:
            raise HTTPException(status_code=503, detail="Event bus not configured")
        
        event_bus.publish(topic, event)
        
        return {
            "message": "Test event published successfully",
            "event_id": event.event_id,
            "topic": topic
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/kafka/status", tags=["Kafka Integration"])
async def get_kafka_status(system: BankingSystem = Depends(get_banking_system)):
    """Get event bus status"""
    try:
        event_bus = getattr(system, 'event_bus', None)
        if not event_bus:
            return {
                "status": "not_configured",
                "message": "Event bus not configured"
            }
        
        status_info = {
            "status": "running" if event_bus.is_running() else "stopped",
            "type": type(event_bus).__name__
        }
        
        # Add additional info for InMemoryEventBus
        if hasattr(event_bus, 'get_events'):
            events = event_bus.get_events()
            status_info["total_events"] = len(events)
            
            # Count events by topic
            topic_counts = {}
            for topic, event, key in events:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
            status_info["events_by_topic"] = topic_counts
        
        return status_info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/kafka/events", tags=["Kafka Integration"])
async def get_recent_events(
    topic: Optional[str] = None,
    limit: int = 50,
    system: BankingSystem = Depends(get_banking_system)
):
    """List recent events (for InMemoryEventBus only)"""
    try:
        event_bus = getattr(system, 'event_bus', None)
        if not event_bus:
            raise HTTPException(status_code=503, detail="Event bus not configured")
        
        if not hasattr(event_bus, 'get_events'):
            raise HTTPException(
                status_code=400, 
                detail="Event listing only supported for InMemoryEventBus"
            )
        
        events = event_bus.get_events(topic)
        
        # Convert to API-friendly format and limit results
        result_events = []
        for event_topic, event, key in events[-limit:]:
            result_events.append({
                "topic": event_topic,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "key": key,
                "data": event.data
            })
        
        return {
            "events": result_events,
            "total": len(events),
            "showing": len(result_events)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/kafka/config", tags=["Kafka Integration"])
async def configure_kafka(
    bus_type: str,
    bootstrap_servers: Optional[str] = None,
    client_id: str = "nexum",
    system: BankingSystem = Depends(get_banking_system)
):
    """Configure event bus"""
    try:
        from .kafka_integration import InMemoryEventBus, LogEventBus, KafkaEventBus
        from .event_hooks import create_event_enabled_banking_system
        
        # Stop existing event bus if running
        old_event_bus = getattr(system, 'event_bus', None)
        if old_event_bus and old_event_bus.is_running():
            old_event_bus.stop()
        
        # Create new event bus
        if bus_type == "memory":
            event_bus = InMemoryEventBus()
        elif bus_type == "log":
            event_bus = LogEventBus()
        elif bus_type == "kafka":
            if not bootstrap_servers:
                raise HTTPException(
                    status_code=400, 
                    detail="bootstrap_servers required for Kafka event bus"
                )
            event_bus = KafkaEventBus(bootstrap_servers, client_id)
        else:
            raise HTTPException(
                status_code=400, 
                detail="Invalid bus_type. Use 'memory', 'log', or 'kafka'"
            )
        
        # Set up event hooks
        banking_components = {
            'transaction_processor': system.transaction_processor,
            'account_manager': system.account_manager,
            'customer_manager': system.customer_manager,
            'loan_manager': system.loan_manager,
            'compliance_engine': system.compliance_engine,
            'audit_trail': system.audit_trail
        }
        
        # Add collections manager if it exists
        if hasattr(system, 'collections_manager'):
            banking_components['collections_manager'] = system.collections_manager
        
        # Add workflow engine if it exists
        if hasattr(system, 'workflow_engine'):
            banking_components['workflow_engine'] = system.workflow_engine
        
        hook_manager = create_event_enabled_banking_system(event_bus, banking_components)
        
        # Start the event bus
        event_bus.start()
        
        # Store references on the system
        system.event_bus = event_bus
        system.event_hook_manager = hook_manager
        
        return {
            "message": f"Event bus configured successfully",
            "type": bus_type,
            "status": "running" if event_bus.is_running() else "stopped"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Notification Engine Endpoints

@app.post("/notifications/send", tags=["Notifications"])
async def send_notification(
    request: SendNotificationRequest,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(get_current_user)
):
    """Send a notification to a recipient"""
    try:
        # Convert string enums
        notification_type = NotificationType(request.notification_type)
        priority = NotificationPriority(request.priority)
        channels = None
        if request.channels:
            channels = [NotificationChannel(ch) for ch in request.channels]
        
        # Send notification
        notification_ids = await system.notification_engine.send_notification(
            notification_type=notification_type,
            recipient_id=request.recipient_id,
            data=request.data,
            channels=channels,
            priority=priority
        )
        
        return {
            "message": "Notification sent successfully",
            "notification_ids": notification_ids,
            "sent_count": len(notification_ids)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/notifications/send/bulk", tags=["Notifications"])
async def send_bulk_notifications(
    request: BulkNotificationRequest,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(get_current_user)
):
    """Send bulk notifications to multiple recipients"""
    try:
        notification_type = NotificationType(request.notification_type)
        channels = None
        if request.channels:
            channels = [NotificationChannel(ch) for ch in request.channels]
        
        results = await system.notification_engine.send_bulk(
            notification_type=notification_type,
            recipient_ids=request.recipient_ids,
            data=request.data,
            channels=channels
        )
        
        total_sent = sum(len(sent_ids) for sent_ids in results.values())
        
        return {
            "message": "Bulk notifications processed",
            "results": results,
            "total_recipients": len(request.recipient_ids),
            "total_sent": total_sent
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/notifications/{recipient_id}", tags=["Notifications"])
async def get_notifications(
    recipient_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(get_current_user)
):
    """Get notifications for a recipient"""
    try:
        notification_status = None
        if status:
            from .notifications import NotificationStatus
            notification_status = NotificationStatus(status)
        
        notifications = system.notification_engine.get_notifications(
            recipient_id=recipient_id,
            status=notification_status,
            limit=limit
        )
        
        # Convert to API format
        notifications_data = []
        for notification in notifications:
            data = {
                "id": notification.id,
                "created_at": notification.created_at.isoformat(),
                "notification_type": notification.notification_type.value,
                "channel": notification.channel.value,
                "priority": notification.priority.value,
                "recipient_id": notification.recipient_id,
                "subject": notification.subject,
                "body": notification.body,
                "status": notification.status.value,
                "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
                "delivered_at": notification.delivered_at.isoformat() if notification.delivered_at else None,
                "read_at": notification.read_at.isoformat() if notification.read_at else None,
                "failed_reason": notification.failed_reason,
                "retry_count": notification.retry_count,
                "metadata": notification.metadata
            }
            notifications_data.append(data)
        
        return {
            "notifications": notifications_data,
            "count": len(notifications_data)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/notifications/{notification_id}/read", tags=["Notifications"])
async def mark_notification_as_read(
    notification_id: str,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(get_current_user)
):
    """Mark notification as read"""
    try:
        success = system.notification_engine.mark_as_read(notification_id)
        
        if success:
            return {"message": "Notification marked as read"}
        else:
            raise HTTPException(status_code=404, detail="Notification not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/notifications/{recipient_id}/unread-count", tags=["Notifications"])
async def get_unread_count(
    recipient_id: str,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(get_current_user)
):
    """Get unread notification count for recipient"""
    try:
        count = system.notification_engine.get_unread_count(recipient_id)
        return {"unread_count": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/notifications/templates", tags=["Notifications"])
async def create_notification_template(
    request: NotificationTemplateRequest,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """Create a new notification template"""
    try:
        from .notifications import NotificationTemplate
        
        template = NotificationTemplate(
            id=None,  # Will be generated
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            name=request.name,
            notification_type=NotificationType(request.notification_type),
            channel=NotificationChannel(request.channel),
            subject_template=request.subject_template,
            body_template=request.body_template,
            is_active=request.is_active
        )
        
        template_id = system.notification_engine.create_template(template)
        
        return {
            "message": "Template created successfully",
            "template_id": template_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/notifications/templates", tags=["Notifications"])
async def list_notification_templates(
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(get_current_user)
):
    """List all notification templates"""
    try:
        templates = system.notification_engine.list_templates()
        
        templates_data = []
        for template in templates:
            data = {
                "id": template.id,
                "created_at": template.created_at.isoformat(),
                "name": template.name,
                "notification_type": template.notification_type.value,
                "channel": template.channel.value,
                "subject_template": template.subject_template,
                "body_template": template.body_template,
                "is_active": template.is_active
            }
            templates_data.append(data)
        
        return {
            "templates": templates_data,
            "count": len(templates_data)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/notifications/retry-failed", tags=["Notifications"])
async def retry_failed_notifications(
    request: RetryFailedRequest,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """Retry failed notifications"""
    try:
        results = await system.notification_engine.retry_failed(request.max_retries)
        
        return {
            "message": "Failed notification retry completed",
            "attempted": results["attempted"],
            "succeeded": results["succeeded"],
            "failed": results["failed"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/notifications/stats", tags=["Notifications"])
async def get_notification_stats(
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(get_current_user)
):
    """Get notification delivery statistics"""
    try:
        stats = system.notification_engine.get_delivery_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/notifications/preferences/{customer_id}", tags=["Notifications"])
async def set_notification_preferences(
    customer_id: str,
    request: NotificationPreferencesRequest,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(get_current_user)
):
    """Set notification preferences for a customer"""
    try:
        from datetime import time
        
        # Convert channel preferences
        channel_preferences = {}
        for notif_type_str, channels_list in request.channel_preferences.items():
            try:
                notif_type = NotificationType(notif_type_str)
                channels = [NotificationChannel(ch) for ch in channels_list]
                channel_preferences[notif_type] = channels
            except ValueError:
                continue  # Skip invalid types/channels
        
        # Parse quiet hours
        quiet_hours_start = None
        quiet_hours_end = None
        if request.quiet_hours_start:
            hour, minute = map(int, request.quiet_hours_start.split(':'))
            quiet_hours_start = time(hour, minute)
        if request.quiet_hours_end:
            hour, minute = map(int, request.quiet_hours_end.split(':'))
            quiet_hours_end = time(hour, minute)
        
        preferences = NotificationPreference(
            id=customer_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            customer_id=customer_id,
            channel_preferences=channel_preferences,
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            do_not_disturb=request.do_not_disturb
        )
        
        system.notification_engine.set_preferences(customer_id, preferences)
        
        return {"message": "Notification preferences updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/notifications/preferences/{customer_id}", tags=["Notifications"])
async def get_notification_preferences(
    customer_id: str,
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(get_current_user)
):
    """Get notification preferences for a customer"""
    try:
        preferences = system.notification_engine.get_preferences(customer_id)
        
        if not preferences:
            return {"preferences": None}
        
        # Convert to API format
        channel_prefs = {}
        for notif_type, channels in preferences.channel_preferences.items():
            channel_prefs[notif_type.value] = [ch.value for ch in channels]
        
        data = {
            "customer_id": preferences.customer_id,
            "channel_preferences": channel_prefs,
            "quiet_hours_start": preferences.quiet_hours_start.isoformat() if preferences.quiet_hours_start else None,
            "quiet_hours_end": preferences.quiet_hours_end.isoformat() if preferences.quiet_hours_end else None,
            "do_not_disturb": preferences.do_not_disturb
        }
        
        return {"preferences": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===============================
# MULTI-TENANCY API ENDPOINTS
# ===============================

# Import tenancy components
from .tenancy import (
    TenantManager, TenantAwareStorage, Tenant, SubscriptionTier, 
    TenantStats, TenantMiddleware, tenant_middleware_func
)

# Tenant API Models
class CreateTenantRequest(BaseModel):
    name: str = Field(..., description="Tenant name")
    code: str = Field(..., description="Unique tenant code (e.g., ACME_BANK)")
    display_name: str = Field(..., description="Display name for the tenant")
    description: str = Field("", description="Tenant description")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Tenant-specific settings")
    database_schema: Optional[str] = Field(None, description="Database schema for schema-per-tenant isolation")
    max_users: Optional[int] = Field(None, description="Maximum users quota")
    max_accounts: Optional[int] = Field(None, description="Maximum accounts quota")
    subscription_tier: str = Field("free", description="Subscription tier (free, basic, professional, enterprise)")
    contact_email: Optional[str] = Field(None, description="Contact email")
    contact_phone: Optional[str] = Field(None, description="Contact phone")
    logo_url: Optional[str] = Field(None, description="Logo URL")
    primary_color: Optional[str] = Field(None, description="Primary color (hex)")

class UpdateTenantRequest(BaseModel):
    name: Optional[str] = Field(None, description="Tenant name")
    display_name: Optional[str] = Field(None, description="Display name")
    description: Optional[str] = Field(None, description="Tenant description")
    settings: Optional[Dict[str, Any]] = Field(None, description="Tenant-specific settings")
    database_schema: Optional[str] = Field(None, description="Database schema")
    max_users: Optional[int] = Field(None, description="Maximum users quota")
    max_accounts: Optional[int] = Field(None, description="Maximum accounts quota")
    subscription_tier: Optional[str] = Field(None, description="Subscription tier")
    contact_email: Optional[str] = Field(None, description="Contact email")
    contact_phone: Optional[str] = Field(None, description="Contact phone")
    logo_url: Optional[str] = Field(None, description="Logo URL")
    primary_color: Optional[str] = Field(None, description="Primary color (hex)")

class TenantResponse(BaseModel):
    id: str
    name: str
    code: str
    display_name: str
    description: str
    is_active: bool
    created_at: str
    updated_at: str
    settings: Dict[str, Any]
    database_schema: Optional[str]
    max_users: Optional[int]
    max_accounts: Optional[int]
    subscription_tier: str
    contact_email: Optional[str]
    contact_phone: Optional[str]
    logo_url: Optional[str]
    primary_color: Optional[str]

class TenantStatsResponse(BaseModel):
    tenant_id: str
    user_count: int
    account_count: int
    transaction_count: int
    total_balance: str
    last_activity: Optional[str]

# Initialize tenant manager
def get_tenant_manager() -> TenantManager:
    """Get or create tenant manager"""
    if not hasattr(banking_system, '_tenant_manager'):
        banking_system._tenant_manager = TenantManager(banking_system.storage)
    return banking_system._tenant_manager

# Tenant Management Endpoints
@app.post("/tenants", status_code=status.HTTP_201_CREATED, response_model=TenantResponse, tags=["Tenants"])
async def create_tenant(
    request: CreateTenantRequest,
    system: BankingSystem = Depends(get_banking_system),
    tenant_manager: TenantManager = Depends(get_tenant_manager),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """Create a new tenant (super-admin only)"""
    try:
        # Parse subscription tier
        subscription_tier = SubscriptionTier(request.subscription_tier.lower())
        
        tenant = tenant_manager.create_tenant(
            name=request.name,
            code=request.code,
            display_name=request.display_name,
            description=request.description,
            settings=request.settings,
            database_schema=request.database_schema,
            max_users=request.max_users,
            max_accounts=request.max_accounts,
            subscription_tier=subscription_tier,
            contact_email=request.contact_email,
            contact_phone=request.contact_phone,
            logo_url=request.logo_url,
            primary_color=request.primary_color
        )
        
        # Convert to response model
        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            code=tenant.code,
            display_name=tenant.display_name,
            description=tenant.description,
            is_active=tenant.is_active,
            created_at=tenant.created_at.isoformat(),
            updated_at=tenant.updated_at.isoformat(),
            settings=tenant.settings,
            database_schema=tenant.database_schema,
            max_users=tenant.max_users,
            max_accounts=tenant.max_accounts,
            subscription_tier=tenant.subscription_tier.value,
            contact_email=tenant.contact_email,
            contact_phone=tenant.contact_phone,
            logo_url=tenant.logo_url,
            primary_color=tenant.primary_color
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create tenant: {str(e)}")

@app.get("/tenants", response_model=List[TenantResponse], tags=["Tenants"])
async def list_tenants(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    tenant_manager: TenantManager = Depends(get_tenant_manager),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """List all tenants (super-admin only)"""
    try:
        tenants = tenant_manager.list_tenants(is_active=is_active)
        
        return [
            TenantResponse(
                id=tenant.id,
                name=tenant.name,
                code=tenant.code,
                display_name=tenant.display_name,
                description=tenant.description,
                is_active=tenant.is_active,
                created_at=tenant.created_at.isoformat(),
                updated_at=tenant.updated_at.isoformat(),
                settings=tenant.settings,
                database_schema=tenant.database_schema,
                max_users=tenant.max_users,
                max_accounts=tenant.max_accounts,
                subscription_tier=tenant.subscription_tier.value,
                contact_email=tenant.contact_email,
                contact_phone=tenant.contact_phone,
                logo_url=tenant.logo_url,
                primary_color=tenant.primary_color
            )
            for tenant in tenants
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to list tenants: {str(e)}")

@app.get("/tenants/{tenant_id}", response_model=TenantResponse, tags=["Tenants"])
async def get_tenant(
    tenant_id: str,
    tenant_manager: TenantManager = Depends(get_tenant_manager),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """Get tenant by ID (super-admin only)"""
    try:
        tenant = tenant_manager.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            code=tenant.code,
            display_name=tenant.display_name,
            description=tenant.description,
            is_active=tenant.is_active,
            created_at=tenant.created_at.isoformat(),
            updated_at=tenant.updated_at.isoformat(),
            settings=tenant.settings,
            database_schema=tenant.database_schema,
            max_users=tenant.max_users,
            max_accounts=tenant.max_accounts,
            subscription_tier=tenant.subscription_tier.value,
            contact_email=tenant.contact_email,
            contact_phone=tenant.contact_phone,
            logo_url=tenant.logo_url,
            primary_color=tenant.primary_color
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get tenant: {str(e)}")

@app.put("/tenants/{tenant_id}", response_model=TenantResponse, tags=["Tenants"])
async def update_tenant(
    tenant_id: str,
    request: UpdateTenantRequest,
    tenant_manager: TenantManager = Depends(get_tenant_manager),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """Update tenant (super-admin only)"""
    try:
        # Build update dict with only provided fields
        update_fields = {}
        for field, value in request.dict(exclude_unset=True).items():
            if field == 'subscription_tier' and value:
                update_fields[field] = SubscriptionTier(value.lower())
            else:
                update_fields[field] = value
        
        tenant = tenant_manager.update_tenant(tenant_id, **update_fields)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            code=tenant.code,
            display_name=tenant.display_name,
            description=tenant.description,
            is_active=tenant.is_active,
            created_at=tenant.created_at.isoformat(),
            updated_at=tenant.updated_at.isoformat(),
            settings=tenant.settings,
            database_schema=tenant.database_schema,
            max_users=tenant.max_users,
            max_accounts=tenant.max_accounts,
            subscription_tier=tenant.subscription_tier.value,
            contact_email=tenant.contact_email,
            contact_phone=tenant.contact_phone,
            logo_url=tenant.logo_url,
            primary_color=tenant.primary_color
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update tenant: {str(e)}")

@app.post("/tenants/{tenant_id}/activate", tags=["Tenants"])
async def activate_tenant(
    tenant_id: str,
    tenant_manager: TenantManager = Depends(get_tenant_manager),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """Activate a tenant (super-admin only)"""
    try:
        success = tenant_manager.activate_tenant(tenant_id)
        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return {"message": "Tenant activated successfully", "tenant_id": tenant_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to activate tenant: {str(e)}")

@app.post("/tenants/{tenant_id}/deactivate", tags=["Tenants"])
async def deactivate_tenant(
    tenant_id: str,
    tenant_manager: TenantManager = Depends(get_tenant_manager),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """Deactivate a tenant (super-admin only)"""
    try:
        success = tenant_manager.deactivate_tenant(tenant_id)
        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return {"message": "Tenant deactivated successfully", "tenant_id": tenant_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to deactivate tenant: {str(e)}")

@app.get("/tenants/{tenant_id}/stats", response_model=TenantStatsResponse, tags=["Tenants"])
async def get_tenant_stats(
    tenant_id: str,
    tenant_manager: TenantManager = Depends(get_tenant_manager),
    system: BankingSystem = Depends(get_banking_system),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """Get usage statistics for a tenant (super-admin only)"""
    try:
        stats = tenant_manager.get_tenant_stats(tenant_id, system)
        if not stats:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return TenantStatsResponse(
            tenant_id=stats.tenant_id,
            user_count=stats.user_count,
            account_count=stats.account_count,
            transaction_count=stats.transaction_count,
            total_balance=str(stats.total_balance),
            last_activity=stats.last_activity.isoformat() if stats.last_activity else None
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get tenant stats: {str(e)}")

@app.get("/tenants/usage-report", response_model=List[TenantStatsResponse], tags=["Tenants"])
async def get_usage_report(
    tenant_manager: TenantManager = Depends(get_tenant_manager),
    current_user: str = Depends(require_permission("ADMIN"))
):
    """Get usage report for all active tenants (super-admin only)"""
    try:
        report = tenant_manager.get_usage_report()
        
        return [
            TenantStatsResponse(
                tenant_id=stats.tenant_id,
                user_count=stats.user_count,
                account_count=stats.account_count,
                transaction_count=stats.transaction_count,
                total_balance=str(stats.total_balance),
                last_activity=stats.last_activity.isoformat() if stats.last_activity else None
            )
            for stats in report
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get usage report: {str(e)}")


# Run server function
def run_server(host: str = "0.0.0.0", port: int = 8090, debug: bool = False):
    """Run the FastAPI server"""
    uvicorn.run(
        "core_banking.api:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )