"""
Workflows endpoints
"""

from fastapi import APIRouter, Depends

from .auth import BankingSystem, get_banking_system


router = APIRouter()


# Placeholder endpoints - to be filled in
@router.get("/definitions")
async def list_workflow_definitions(system: BankingSystem = Depends(get_banking_system)):
    """List workflow definitions"""
    pass


@router.post("/definitions")
async def create_workflow_definition(system: BankingSystem = Depends(get_banking_system)):
    """Create workflow definition"""
    pass