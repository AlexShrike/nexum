"""
Reporting endpoints
"""

from fastapi import APIRouter, Depends

from .auth import BankingSystem, get_banking_system


router = APIRouter()


# Placeholder endpoints - to be filled in
@router.get("")
async def list_reports(system: BankingSystem = Depends(get_banking_system)):
    """List available reports"""
    pass


@router.post("/{report_id}/run")
async def run_report(report_id: str, system: BankingSystem = Depends(get_banking_system)):
    """Run a report"""
    pass