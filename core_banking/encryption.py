"""
PII Encryption at Rest Module

Provides field-level encryption for PII data that is transparent to the rest of the system.
Uses cryptography library (Fernet/AES-GCM) with graceful fallback to NoOp for development.
"""

import os
import base64
import hashlib
import hmac
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union

# Import logging
logger = logging.getLogger(__name__)

# Try to import cryptography library, fall back to NoOp if not available
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    logger.warning("cryptography library not available - encryption will be disabled. Install with: pip install cryptography")
    CRYPTOGRAPHY_AVAILABLE = False
    # Stubs for type hints
    Fernet = None
    PBKDF2HMAC = None
    AESGCM = None

from .storage import StorageInterface


# PII field definitions per table
PII_FIELDS = {
    "customers": [
        "first_name", "last_name", "email", "phone", "address", 
        "date_of_birth", "tax_id", "nationality"
    ],
    "accounts": ["account_number"],
    "audit_events": [],  # Never encrypt audit trail
}

# Encryption marker prefix
ENCRYPTION_PREFIX = "ENC:"


class EncryptionProvider(ABC):
    """Abstract base class for encryption providers"""
    
    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext and return ciphertext"""
        pass
    
    @abstractmethod
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext and return plaintext"""
        pass


class NoOpEncryptionProvider(EncryptionProvider):
    """No-operation encryption provider for development/testing"""
    
    def __init__(self):
        logger.info("Using NoOpEncryptionProvider - data will NOT be encrypted")
    
    def encrypt(self, plaintext: str) -> str:
        """Return plaintext unchanged"""
        if not isinstance(plaintext, str):
            plaintext = str(plaintext)
        return plaintext
    
    def decrypt(self, ciphertext: str) -> str:
        """Return ciphertext unchanged"""
        if not isinstance(ciphertext, str):
            ciphertext = str(ciphertext)
        return ciphertext


class FernetEncryptionProvider(EncryptionProvider):
    """Fernet encryption provider using cryptography library (AES-128-CBC + HMAC-SHA256)"""
    
    def __init__(self, master_key: str, salt: Optional[bytes] = None):
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError("cryptography library required for FernetEncryptionProvider")
        
        self.master_key = master_key.encode('utf-8')
        self.salt = salt or b'nexum_banking_salt_2024'  # Use consistent salt for key derivation
        
        # Derive Fernet key from master key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,  # OWASP recommended minimum
        )
        derived_key = kdf.derive(self.master_key)
        fernet_key = base64.urlsafe_b64encode(derived_key)
        
        self.fernet = Fernet(fernet_key)
        logger.info("FernetEncryptionProvider initialized successfully")
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext using Fernet"""
        if not isinstance(plaintext, str):
            plaintext = str(plaintext)
        
        encrypted_bytes = self.fernet.encrypt(plaintext.encode('utf-8'))
        encoded = base64.urlsafe_b64encode(encrypted_bytes).decode('ascii')
        return f"{ENCRYPTION_PREFIX}{encoded}"
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext using Fernet"""
        if not isinstance(ciphertext, str):
            ciphertext = str(ciphertext)
        
        # Remove encryption prefix
        if ciphertext.startswith(ENCRYPTION_PREFIX):
            ciphertext = ciphertext[len(ENCRYPTION_PREFIX):]
        
        try:
            encrypted_bytes = base64.urlsafe_b64decode(ciphertext.encode('ascii'))
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to decrypt data: {e}")
            raise ValueError(f"Failed to decrypt data: {e}")


class AESGCMEncryptionProvider(EncryptionProvider):
    """AES-256-GCM encryption provider (more modern, authenticated encryption)"""
    
    def __init__(self, master_key: Union[str, bytes]):
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError("cryptography library required for AESGCMEncryptionProvider")
        
        if isinstance(master_key, str):
            master_key = master_key.encode('utf-8')
        
        # Derive 32-byte key from master key using SHA-256
        self.key = hashlib.sha256(master_key).digest()
        self.aesgcm = AESGCM(self.key)
        logger.info("AESGCMEncryptionProvider initialized successfully")
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext using AES-256-GCM with random nonce"""
        if not isinstance(plaintext, str):
            plaintext = str(plaintext)
        
        # Generate random 12-byte nonce for GCM
        nonce = os.urandom(12)
        
        # Encrypt data
        encrypted_bytes = self.aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        
        # Prefix ciphertext with nonce for decryption
        combined = nonce + encrypted_bytes
        encoded = base64.urlsafe_b64encode(combined).decode('ascii')
        
        return f"{ENCRYPTION_PREFIX}{encoded}"
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext using AES-256-GCM"""
        if not isinstance(ciphertext, str):
            ciphertext = str(ciphertext)
        
        # Remove encryption prefix
        if ciphertext.startswith(ENCRYPTION_PREFIX):
            ciphertext = ciphertext[len(ENCRYPTION_PREFIX):]
        
        try:
            # Decode base64
            combined = base64.urlsafe_b64decode(ciphertext.encode('ascii'))
            
            # Extract nonce (first 12 bytes) and encrypted data
            nonce = combined[:12]
            encrypted_bytes = combined[12:]
            
            # Decrypt data
            decrypted_bytes = self.aesgcm.decrypt(nonce, encrypted_bytes, None)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to decrypt data: {e}")
            raise ValueError(f"Failed to decrypt data: {e}")


class EncryptedStorage(StorageInterface):
    """
    Storage wrapper that encrypts PII fields on save and decrypts on load.
    Wraps any StorageInterface implementation.
    """
    
    def __init__(
        self, 
        inner: StorageInterface, 
        encryption_provider: EncryptionProvider,
        pii_fields: Optional[Dict[str, List[str]]] = None
    ):
        self.inner = inner
        self.provider = encryption_provider
        self.pii_fields = pii_fields or PII_FIELDS
        
        # Statistics for monitoring
        self._encrypt_count = 0
        self._decrypt_count = 0
        
        logger.info(f"EncryptedStorage initialized with {type(encryption_provider).__name__}")
    
    def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        """Save record with PII encryption"""
        encrypted_data = self._encrypt_pii(table, data.copy())
        self.inner.save(table, record_id, encrypted_data)
    
    def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Load record and decrypt PII"""
        data = self.inner.load(table, record_id)
        if data:
            return self._decrypt_pii(table, data)
        return None
    
    def load_all(self, table: str) -> List[Dict[str, Any]]:
        """Load all records and decrypt PII"""
        all_data = self.inner.load_all(table)
        return [self._decrypt_pii(table, data) for data in all_data]
    
    def delete(self, table: str, record_id: str) -> bool:
        """Delete record (pass-through)"""
        return self.inner.delete(table, record_id)
    
    def exists(self, table: str, record_id: str) -> bool:
        """Check if record exists (pass-through)"""
        return self.inner.exists(table, record_id)
    
    def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find records matching filters.
        
        NOTE: Cannot filter on encrypted fields directly.
        For encrypted field searches, the search term would need to be encrypted first,
        but this implementation returns all records and filters in memory after decryption.
        This is inefficient for large datasets but ensures correctness.
        """
        # For encrypted fields, we need to load all and filter after decryption
        encrypted_field_filters = {}
        non_encrypted_filters = {}
        
        pii_field_names = self.pii_fields.get(table, [])
        
        for key, value in filters.items():
            if key in pii_field_names:
                encrypted_field_filters[key] = value
            else:
                non_encrypted_filters[key] = value
        
        # First, filter by non-encrypted fields at the storage level
        if non_encrypted_filters:
            results = self.inner.find(table, non_encrypted_filters)
        else:
            results = self.inner.load_all(table)
        
        # Decrypt all results
        decrypted_results = [self._decrypt_pii(table, data) for data in results]
        
        # Filter by encrypted fields in memory
        if encrypted_field_filters:
            filtered_results = []
            for record in decrypted_results:
                match = True
                for key, value in encrypted_field_filters.items():
                    if key not in record or record[key] != value:
                        match = False
                        break
                if match:
                    filtered_results.append(record)
            return filtered_results
        
        return decrypted_results
    
    def count(self, table: str) -> int:
        """Count records (pass-through)"""
        return self.inner.count(table)
    
    def clear_table(self, table: str) -> None:
        """Clear table (pass-through)"""
        self.inner.clear_table(table)
    
    def close(self) -> None:
        """Close storage (pass-through)"""
        self.inner.close()
    
    def begin_transaction(self) -> None:
        """Start transaction (pass-through)"""
        self.inner.begin_transaction()
    
    def commit(self) -> None:
        """Commit transaction (pass-through)"""
        self.inner.commit()
    
    def rollback(self) -> None:
        """Rollback transaction (pass-through)"""
        self.inner.rollback()
    
    def _encrypt_pii(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt PII fields in data"""
        fields_to_encrypt = self.pii_fields.get(table, [])
        
        for field in fields_to_encrypt:
            if field in data and data[field] is not None:
                # Only encrypt if not already encrypted
                if not self._is_encrypted(data[field]):
                    try:
                        data[field] = self.provider.encrypt(str(data[field]))
                        self._encrypt_count += 1
                    except Exception as e:
                        logger.error(f"Failed to encrypt field {field} in table {table}: {e}")
                        raise
        
        return data
    
    def _decrypt_pii(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt PII fields in data"""
        if not data:
            return data
        
        # Make a copy to avoid mutating the original
        decrypted_data = data.copy()
        fields_to_decrypt = self.pii_fields.get(table, [])
        
        for field in fields_to_decrypt:
            if field in decrypted_data and decrypted_data[field] is not None:
                # Only decrypt if encrypted
                if self._is_encrypted(decrypted_data[field]):
                    try:
                        decrypted_data[field] = self.provider.decrypt(decrypted_data[field])
                        self._decrypt_count += 1
                    except Exception as e:
                        logger.error(f"Failed to decrypt field {field} in table {table}: {e}")
                        # Don't raise - return encrypted value to avoid breaking the system
                        pass
        
        return decrypted_data
    
    def _is_encrypted(self, value: Any) -> bool:
        """Check if value appears to be encrypted"""
        if not isinstance(value, str):
            return False
        return value.startswith(ENCRYPTION_PREFIX)
    
    def get_encryption_stats(self) -> Dict[str, int]:
        """Get encryption/decryption statistics"""
        return {
            "encrypt_count": self._encrypt_count,
            "decrypt_count": self._decrypt_count
        }


class KeyManager:
    """Handles key derivation and key rotation"""
    
    def __init__(self, master_key: str):
        self.master_key = master_key
    
    def derive_field_key(self, table: str, field: str) -> bytes:
        """Derive a unique key per table+field using HMAC-based key derivation"""
        # Create unique context for this table+field combination
        context = f"nexum_banking:{table}:{field}".encode('utf-8')
        
        # Use HMAC with master key to derive field-specific key
        derived = hmac.new(
            self.master_key.encode('utf-8'),
            context,
            hashlib.sha256
        ).digest()
        
        return derived
    
    def rotate_key(
        self, 
        storage: EncryptedStorage, 
        old_provider: EncryptionProvider,
        new_provider: EncryptionProvider
    ) -> Dict[str, int]:
        """
        Re-encrypt all PII data with a new encryption provider.
        Returns statistics on how many records were rotated.
        """
        stats = {"rotated_records": 0, "rotated_fields": 0, "errors": 0}
        
        # Temporarily replace provider with old one for decryption
        original_provider = storage.provider
        storage.provider = old_provider
        
        try:
            for table in storage.pii_fields.keys():
                if not storage.pii_fields[table]:  # Skip tables with no PII fields
                    continue
                
                # Load all records (will decrypt with old provider)
                records = storage.inner.load_all(table)
                
                for record in records:
                    # Decrypt with old provider
                    decrypted_record = storage._decrypt_pii(table, record)
                    
                    # Switch to new provider and encrypt
                    storage.provider = new_provider
                    encrypted_record = storage._encrypt_pii(table, decrypted_record.copy())
                    
                    # Save re-encrypted record
                    record_id = record.get('id')
                    if record_id:
                        storage.inner.save(table, record_id, encrypted_record)
                        stats["rotated_records"] += 1
                        
                        # Count rotated fields
                        pii_fields = storage.pii_fields.get(table, [])
                        for field in pii_fields:
                            if field in record and record[field] is not None:
                                stats["rotated_fields"] += 1
                    
                    # Switch back to old provider for next record
                    storage.provider = old_provider
        
        except Exception as e:
            logger.error(f"Error during key rotation: {e}")
            stats["errors"] += 1
            raise
        finally:
            # Restore new provider as the active one
            storage.provider = new_provider
        
        logger.info(f"Key rotation completed: {stats}")
        return stats


def create_encryption_provider(provider_type: str, master_key: str) -> EncryptionProvider:
    """Factory function to create encryption providers"""
    if not master_key:
        logger.warning("No master key provided - using NoOpEncryptionProvider")
        return NoOpEncryptionProvider()
    
    provider_type = provider_type.lower()
    
    if provider_type == "noop" or not CRYPTOGRAPHY_AVAILABLE:
        if provider_type != "noop" and not CRYPTOGRAPHY_AVAILABLE:
            logger.warning("Cryptography not available - falling back to NoOpEncryptionProvider")
        return NoOpEncryptionProvider()
    
    elif provider_type == "fernet":
        return FernetEncryptionProvider(master_key)
    
    elif provider_type == "aesgcm":
        return AESGCMEncryptionProvider(master_key)
    
    else:
        logger.warning(f"Unknown encryption provider '{provider_type}' - using NoOpEncryptionProvider")
        return NoOpEncryptionProvider()


def is_encryption_available() -> bool:
    """Check if encryption is available (cryptography library installed)"""
    return CRYPTOGRAPHY_AVAILABLE