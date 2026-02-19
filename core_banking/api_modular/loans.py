"""
Loan endpoints
"""

from datetime import date
from fastapi import APIRouter, HTTPException, Depends, status

from .auth import BankingSystem, get_banking_system
from .schemas import CreateLoanRequest, LoanPaymentRequest, MoneyModel
from ..currency import Currency


router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
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


@router.post("/{loan_id}/disburse")
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


@router.post("/payment")
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


@router.get("/{loan_id}")
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


@router.get("/{loan_id}/schedule")
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