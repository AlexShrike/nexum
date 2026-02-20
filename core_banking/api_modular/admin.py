"""
Admin endpoints (interest accrual, maintenance, etc.)
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from pydantic import BaseModel

from .auth import BankingSystem, get_banking_system
from ..config import get_config
from ..encryption import (
    is_encryption_available, create_encryption_provider, 
    EncryptedStorage, KeyManager, PII_FIELDS
)


router = APIRouter()


class KeyRotationRequest(BaseModel):
    old_key: str
    new_key: str


@router.get("/encryption/status")
async def get_encryption_status(system: BankingSystem = Depends(get_banking_system)) -> Dict[str, Any]:
    """Get encryption status and configuration"""
    config = get_config()
    
    # Check if encryption is available
    crypto_available = is_encryption_available()
    
    # Determine actual provider based on config and availability
    actual_provider = "noop"
    if config.encryption_enabled and config.encryption_master_key and crypto_available:
        actual_provider = config.encryption_provider
    elif config.encryption_enabled and not crypto_available:
        actual_provider = "noop (fallback - cryptography not available)"
    
    return {
        "encryption_enabled": config.encryption_enabled,
        "cryptography_available": crypto_available,
        "configured_provider": config.encryption_provider,
        "actual_provider": actual_provider,
        "has_master_key": bool(config.encryption_master_key),
        "pii_fields": PII_FIELDS
    }


@router.post("/encryption/rotate-key")
async def rotate_encryption_key(
    request: KeyRotationRequest,
    system: BankingSystem = Depends(get_banking_system)
) -> Dict[str, Any]:
    """Trigger encryption key rotation (admin only)"""
    config = get_config()
    
    if not config.encryption_enabled:
        raise HTTPException(status_code=400, detail="Encryption is not enabled")
    
    if not is_encryption_available():
        raise HTTPException(status_code=400, detail="Cryptography library not available")
    
    try:
        # Create old and new providers
        old_provider = create_encryption_provider(config.encryption_provider, request.old_key)
        new_provider = create_encryption_provider(config.encryption_provider, request.new_key)
        
        # Get the current storage (assuming it's encrypted)
        storage = system.storage
        if not isinstance(storage, EncryptedStorage):
            raise HTTPException(
                status_code=400, 
                detail="Storage is not configured for encryption"
            )
        
        # Perform key rotation
        key_manager = KeyManager(request.new_key)
        stats = key_manager.rotate_key(storage, old_provider, new_provider)
        
        return {
            "success": True,
            "message": "Key rotation completed successfully",
            "statistics": stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Key rotation failed: {str(e)}")


@router.get("/encryption/audit")
async def get_encryption_audit(system: BankingSystem = Depends(get_banking_system)) -> Dict[str, Any]:
    """Get encryption/decryption statistics"""
    storage = system.storage
    
    if isinstance(storage, EncryptedStorage):
        stats = storage.get_encryption_stats()
        return {
            "encryption_statistics": stats,
            "provider_type": type(storage.provider).__name__,
            "pii_fields_configured": storage.pii_fields
        }
    else:
        return {
            "encryption_statistics": {"encrypt_count": 0, "decrypt_count": 0},
            "provider_type": "none",
            "message": "Storage is not configured for encryption"
        }


# Existing placeholder endpoints
@router.post("/interest/accrue")
async def run_interest_accrual(system: BankingSystem = Depends(get_banking_system)):
    """Run interest accrual process"""
    pass


@router.get("/stats")
async def get_system_stats(system: BankingSystem = Depends(get_banking_system)):
    """Get system statistics"""
    pass


# Fraud detection endpoints
@router.get("/fraud/status")
async def get_fraud_status(system: BankingSystem = Depends(get_banking_system)) -> Dict[str, Any]:
    """Get Bastion connection status and fraud scoring statistics"""
    if not system.transaction_processor.fraud_client:
        return {
            "fraud_detection_enabled": False,
            "message": "Fraud client not configured"
        }
    
    fraud_client = system.transaction_processor.fraud_client
    is_healthy = fraud_client.health_check()
    
    # Get some basic stats from recent transactions
    # This is a simplified implementation - in production would query actual transaction history
    recent_transactions = system.storage.load_all("transactions")
    fraud_stats = {
        "total_scored": 0,
        "blocked": 0,
        "reviewed": 0,
        "approved": 0,
        "avg_latency_ms": 0.0
    }
    
    total_latency = 0.0
    for tx_data in recent_transactions[-100:]:  # Last 100 transactions
        if tx_data.get("metadata", {}).get("fraud_score") is not None:
            fraud_stats["total_scored"] += 1
            decision = tx_data.get("metadata", {}).get("fraud_decision", "APPROVE")
            if decision == "BLOCK":
                fraud_stats["blocked"] += 1
            elif decision == "REVIEW":
                fraud_stats["reviewed"] += 1
            else:
                fraud_stats["approved"] += 1
            
            latency = tx_data.get("metadata", {}).get("fraud_latency_ms", 0.0)
            total_latency += latency
    
    if fraud_stats["total_scored"] > 0:
        fraud_stats["avg_latency_ms"] = total_latency / fraud_stats["total_scored"]
    
    return {
        "fraud_detection_enabled": fraud_client.enabled,
        "bastion_url": fraud_client.base_url,
        "bastion_healthy": is_healthy,
        "timeout_seconds": fraud_client.timeout,
        "fallback_decision": fraud_client.fallback_on_error,
        "statistics": fraud_stats
    }