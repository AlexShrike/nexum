"""
Admin endpoints (interest accrual, maintenance, etc.)
"""

from fastapi import APIRouter, Depends

from .auth import BankingSystem, get_banking_system


router = APIRouter()


# Placeholder endpoints - to be filled in
@router.post("/interest/accrue")
async def run_interest_accrual(system: BankingSystem = Depends(get_banking_system)):
    """Run interest accrual process"""
    pass


@router.get("/stats")
async def get_system_stats(system: BankingSystem = Depends(get_banking_system)):
    """Get system statistics"""
    pass