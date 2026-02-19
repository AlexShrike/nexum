"""
Customer management endpoints
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status

from .auth import BankingSystem, get_banking_system
from .schemas import (
    CreateCustomerRequest, 
    UpdateCustomerRequest, 
    UpdateKYCRequest,
    MoneyModel
)
from ..customers import KYCStatus, KYCTier


router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
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


@router.get("/{customer_id}")
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


@router.put("/{customer_id}")
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


@router.put("/{customer_id}/kyc")
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


@router.get("/{customer_id}/accounts")
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