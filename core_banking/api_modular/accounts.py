"""
Account management endpoints
"""

from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status

from .auth import BankingSystem, get_banking_system
from .schemas import CreateAccountRequest, MoneyModel
from ..accounts import ProductType
from ..currency import Currency


router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
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


@router.get("/{account_id}")
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


@router.get("/{account_id}/transactions")
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