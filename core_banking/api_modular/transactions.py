"""
Transaction endpoints
"""

from fastapi import APIRouter, HTTPException, Depends

from .auth import BankingSystem, get_banking_system
from .schemas import DepositRequest, WithdrawRequest, TransferRequest
from ..transactions import TransactionChannel


router = APIRouter()


@router.post("/deposit")
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


@router.post("/withdraw")
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


@router.post("/transfer")
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