"""
RBAC (Role-Based Access Control) endpoints
"""

from fastapi import APIRouter, Depends

from .auth import BankingSystem, get_banking_system


router = APIRouter()


# Placeholder endpoints - to be filled in
@router.get("/roles")
async def list_roles(system: BankingSystem = Depends(get_banking_system)):
    """List roles"""
    pass


@router.post("/roles")
async def create_role(system: BankingSystem = Depends(get_banking_system)):
    """Create role"""
    pass


@router.get("/users")
async def list_users(system: BankingSystem = Depends(get_banking_system)):
    """List users"""
    pass


@router.post("/users")
async def create_user(system: BankingSystem = Depends(get_banking_system)):
    """Create user"""
    pass