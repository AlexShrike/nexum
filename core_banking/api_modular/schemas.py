"""
Pydantic schemas for API requests and responses
"""

from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from ..currency import Money, Currency
from ..customers import Address
from ..loans import LoanTerms, PaymentFrequency, AmortizationMethod


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


# Customer schemas
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


# Account schemas
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


# Transaction schemas
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


# Credit schemas
class CreditPaymentRequest(BaseModel):
    account_id: str
    amount: MoneyModel
    payment_date: Optional[str] = None  # ISO date string


# Loan schemas
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


# Product schemas
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


# Collections schemas
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


# Reporting schemas
class CreateReportRequest(BaseModel):
    name: str
    description: str
    report_type: str


class RunReportRequest(BaseModel):
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None


# Workflow schemas
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


# RBAC schemas
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


# Custom Fields schemas
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