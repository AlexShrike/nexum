"""
Credit line endpoints
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends

from .auth import BankingSystem, get_banking_system
from .schemas import CreditPaymentRequest, MoneyModel


router = APIRouter()


@router.post("/payment")
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


@router.post("/{account_id}/statement")
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


@router.get("/{account_id}/statements")
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