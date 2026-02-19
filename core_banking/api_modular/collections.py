"""
Collections endpoints
"""

from fastapi import APIRouter, Depends

from .auth import BankingSystem, get_banking_system


router = APIRouter()


# Placeholder endpoints - to be filled in
@router.get("/cases")
async def list_collection_cases(system: BankingSystem = Depends(get_banking_system)):
    """List collection cases"""
    pass


@router.post("/cases/{case_id}/actions")
async def record_collection_action(case_id: str, system: BankingSystem = Depends(get_banking_system)):
    """Record collection action"""
    pass