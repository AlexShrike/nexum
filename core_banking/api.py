"""
FastAPI REST API Module

Provides REST API endpoints for all core banking operations including
customer management, account operations, transactions, credit lines, loans,
and audit queries. Runs on port 8090.
"""

from decimal import Decimal
from datetime import datetime, timezone, date
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import uvicorn

from .currency import Money, Currency
from .storage import InMemoryStorage, SQLiteStorage
from .audit import AuditTrail, AuditEventType
from .ledger import GeneralLedger, AccountType
from .accounts import AccountManager, ProductType, AccountState
from .customers import CustomerManager, KYCStatus, KYCTier, Address
from .compliance import ComplianceEngine
from .transactions import TransactionProcessor, TransactionType, TransactionChannel
from .interest import InterestEngine
from .credit import CreditLineManager, TransactionCategory
from .loans import LoanManager, LoanTerms, PaymentFrequency, AmortizationMethod


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


# Banking System Context
class BankingSystem:
    """Core banking system with all components initialized"""
    
    def __init__(self, use_sqlite: bool = True):
        # Initialize storage
        if use_sqlite:
            self.storage = SQLiteStorage("core_banking.db")
        else:
            self.storage = InMemoryStorage()
        
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


# Global banking system instance
banking_system = BankingSystem(use_sqlite=True)


# Create FastAPI app
app = FastAPI(
    title="Core Banking System API",
    description="Production-grade core banking system with double-entry bookkeeping",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency to get banking system
def get_banking_system() -> BankingSystem:
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
    system: BankingSystem = Depends(get_banking_system)
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
    system: BankingSystem = Depends(get_banking_system)
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
    system: BankingSystem = Depends(get_banking_system)
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
    limit: Optional[int] = 50,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get transaction history for account"""
    transactions = system.transaction_processor.get_account_transactions(
        account_id=account_id,
        limit=limit
    )
    
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
    
    return {"transactions": result}


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
    limit: Optional[int] = 100,
    system: BankingSystem = Depends(get_banking_system)
):
    """Get audit events"""
    if entity_type and entity_id:
        events = system.audit_trail.get_events_for_entity(entity_type, entity_id, limit)
    else:
        events = system.audit_trail.get_all_events(limit=limit)
    
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
    
    return {"events": result}


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
            "compliance": "/compliance"
        }
    }


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