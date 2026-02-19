"""
Custom fields endpoints
"""

from fastapi import APIRouter, Depends

from .auth import BankingSystem, get_banking_system


router = APIRouter()


# Placeholder endpoints - to be filled in
@router.get("/definitions")
async def list_field_definitions(system: BankingSystem = Depends(get_banking_system)):
    """List field definitions"""
    pass


@router.post("/definitions")
async def create_field_definition(system: BankingSystem = Depends(get_banking_system)):
    """Create field definition"""
    pass


@router.get("/{entity_type}/{entity_id}")
async def get_entity_fields(entity_type: str, entity_id: str, system: BankingSystem = Depends(get_banking_system)):
    """Get entity field values"""
    pass