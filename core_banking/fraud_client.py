"""
Fraud Detection Client Module

REST client for integrating with Bastion fraud detection engine.
Provides synchronous scoring of transactions before approval.
"""

import httpx
import logging
import time
from dataclasses import dataclass
from typing import Optional
from decimal import Decimal

logger = logging.getLogger("nexum.fraud")


@dataclass
class FraudScore:
    """Result from fraud scoring engine"""
    score: float  # 0.0 - 1.0
    decision: str  # APPROVE, REVIEW, BLOCK
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    reasons: list  # explanation codes
    latency_ms: float  # how long the call took


class BastionClient:
    """REST client for Bastion fraud detection engine"""
    
    def __init__(
        self, 
        base_url: str = "http://localhost:8080", 
        timeout: float = 2.0,  # 2 second timeout — don't block transactions too long
        api_key: Optional[str] = None,
        enabled: bool = True,
        fallback_on_error: str = "APPROVE"  # If Bastion is down, approve by default
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        self.enabled = enabled
        self.fallback_on_error = fallback_on_error
        self._client = httpx.Client(timeout=timeout)
    
    def score_transaction(self, transaction_data: dict) -> FraudScore:
        """Score a transaction via Bastion API
        
        Args:
            transaction_data: dict with transaction_id, amount, currency, 
                            customer_id, merchant_id, channel, etc.
        
        Returns:
            FraudScore with decision
        """
        if not self.enabled:
            return FraudScore(
                score=0.0, 
                decision="APPROVE", 
                risk_level="LOW", 
                reasons=["fraud_scoring_disabled"], 
                latency_ms=0.0
            )
        
        try:
            start = time.time()
            
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # Map transaction data to Bastion's expected format
            bastion_request = {
                "transaction_id": transaction_data.get("transaction_id", ""),
                "cif_id": transaction_data.get("customer_id", ""),  # Bastion uses cif_id
                "amount": float(transaction_data.get("amount", 0)),
                "currency": transaction_data.get("currency", "USD"),
                "merchant_id": transaction_data.get("merchant_id", ""),
                "merchant_category": transaction_data.get("merchant_category", ""),
                "channel": transaction_data.get("channel", "online"),
                "country": transaction_data.get("country", ""),
                "timestamp": transaction_data.get("timestamp", start),
                "metadata": {
                    "transaction_type": transaction_data.get("transaction_type", ""),
                    "description": transaction_data.get("description", ""),
                    **transaction_data.get("metadata", {})
                }
            }
            
            response = self._client.post(
                f"{self.base_url}/score",
                json=bastion_request,
                headers=headers
            )
            
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                return FraudScore(
                    score=data.get("risk_score", 0.0),  # Bastion returns risk_score
                    decision=data.get("action", "APPROVE").upper(),  # Bastion returns action
                    risk_level=self._map_risk_level(data.get("risk_score", 0.0)),
                    reasons=data.get("reasons", []),
                    latency_ms=latency_ms
                )
            else:
                logger.warning(f"Bastion returned {response.status_code}: {response.text}")
                return self._fallback(latency_ms)
                
        except Exception as e:
            logger.error(f"Bastion connection failed: {e}")
            return self._fallback(0.0)
    
    def _map_risk_level(self, risk_score: float) -> str:
        """Map numeric risk score to risk level"""
        if risk_score >= 0.8:
            return "CRITICAL"
        elif risk_score >= 0.6:
            return "HIGH"
        elif risk_score >= 0.3:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _fallback(self, latency_ms: float) -> FraudScore:
        """Return fallback decision when Bastion is unavailable"""
        return FraudScore(
            score=0.0, 
            decision=self.fallback_on_error, 
            risk_level="UNKNOWN",
            reasons=["bastion_unavailable"], 
            latency_ms=latency_ms
        )
    
    def health_check(self) -> bool:
        """Check if Bastion is healthy"""
        try:
            r = self._client.get(f"{self.base_url}/health")
            return r.status_code == 200
        except:
            return False
    
    def close(self):
        """Close the HTTP client"""
        self._client.close()


class MockBastionClient(BastionClient):
    """Mock client for testing — scores based on amount thresholds"""
    
    def __init__(self, **kwargs):
        super().__init__(enabled=True, **kwargs)
    
    def score_transaction(self, transaction_data: dict) -> FraudScore:
        """Mock scoring based on transaction amount"""
        amount = float(transaction_data.get("amount", 0))
        
        if amount > 50000:
            return FraudScore(0.85, "BLOCK", "CRITICAL", ["high_amount"], 1.0)
        elif amount > 10000:
            return FraudScore(0.55, "REVIEW", "HIGH", ["large_amount"], 1.0)
        elif amount > 5000:
            return FraudScore(0.35, "REVIEW", "MEDIUM", ["medium_amount"], 1.0)
        
        return FraudScore(0.1, "APPROVE", "LOW", [], 1.0)
    
    def health_check(self) -> bool:
        """Mock health check always returns True"""
        return True