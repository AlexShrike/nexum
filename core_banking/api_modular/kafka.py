"""
Kafka integration endpoints
"""

from fastapi import APIRouter, Depends

from .auth import BankingSystem, get_banking_system


router = APIRouter()


# Placeholder endpoints - to be filled in
@router.get("/status")
async def get_kafka_status(system: BankingSystem = Depends(get_banking_system)):
    """Get Kafka status"""
    pass


@router.post("/publish-test")
async def publish_test_event(system: BankingSystem = Depends(get_banking_system)):
    """Publish test event"""
    pass


@router.get("/events")
async def get_recent_events(system: BankingSystem = Depends(get_banking_system)):
    """Get recent events"""
    pass