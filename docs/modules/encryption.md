# PII Encryption Module

The Encryption module provides field-level encryption for Personally Identifiable Information (PII) that is transparent to the rest of the system. It uses industry-standard encryption algorithms with graceful fallback for development environments.

## Overview

The encryption system automatically encrypts sensitive PII fields (customer names, emails, phone numbers, addresses, etc.) when storing data and decrypts them when retrieving data. This provides protection for sensitive data at rest while maintaining system functionality and performance.

## Key Features

- **Field-Level Encryption**: Only PII fields are encrypted, preserving query performance
- **Transparent Operation**: Application code doesn't need modification
- **Multiple Providers**: Support for Fernet, AES-GCM, and NoOp encryption
- **Key Management**: Secure key derivation and rotation capabilities
- **Graceful Fallback**: Works without cryptography library for development
- **Performance Optimized**: Encrypts only necessary fields

## Supported Encryption Providers

### FernetEncryptionProvider
- **Algorithm**: AES-128-CBC with HMAC-SHA256 authentication
- **Key Derivation**: PBKDF2 with 100,000 iterations
- **Use Case**: Strong encryption with authentication, good for most applications

### AESGCMEncryptionProvider (Recommended)
- **Algorithm**: AES-256-GCM with authenticated encryption
- **Key Derivation**: SHA-256 hash of master key
- **Use Case**: Modern authenticated encryption, recommended for new deployments

### NoOpEncryptionProvider
- **Algorithm**: None (pass-through)
- **Key Derivation**: N/A
- **Use Case**: Development and testing environments

## PII Field Mapping

The system automatically encrypts these fields:

```python
PII_FIELDS = {
    "customers": [
        "first_name", "last_name", "email", "phone", "address", 
        "date_of_birth", "tax_id", "nationality"
    ],
    "accounts": ["account_number"],
    "audit_events": [],  # Never encrypt audit trail
}
```

## Key Classes

### EncryptionProvider (Abstract)

Base class for all encryption providers:

```python
class EncryptionProvider(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext and return ciphertext"""
        
    @abstractmethod  
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext and return plaintext"""
```

### FernetEncryptionProvider

Fernet encryption using `cryptography` library:

```python
class FernetEncryptionProvider(EncryptionProvider):
    def __init__(self, master_key: str, salt: Optional[bytes] = None):
        # Derives Fernet key from master key using PBKDF2
        # Default salt: b'nexum_banking_salt_2024'
        
    def encrypt(self, plaintext: str) -> str:
        # Returns "ENC:<base64-encoded-ciphertext>"
        
    def decrypt(self, ciphertext: str) -> str:
        # Decrypts and returns plaintext
```

**Features:**
- PBKDF2 key derivation with 100,000 iterations
- Built-in authentication prevents tampering
- Fernet tokens include timestamps
- Base64 encoding for safe storage

### AESGCMEncryptionProvider (Recommended)

Modern AES-GCM authenticated encryption:

```python
class AESGCMEncryptionProvider(EncryptionProvider):
    def __init__(self, master_key: Union[str, bytes]):
        # Derives 256-bit key using SHA-256
        
    def encrypt(self, plaintext: str) -> str:
        # Uses random 12-byte nonce per encryption
        # Returns "ENC:<base64-encoded-nonce+ciphertext>"
        
    def decrypt(self, ciphertext: str) -> str:
        # Extracts nonce and decrypts with authentication
```

**Features:**
- AES-256-GCM authenticated encryption
- Random nonce per encryption operation
- Built-in authentication tag
- Resistance to chosen-ciphertext attacks

### NoOpEncryptionProvider

Pass-through provider for development:

```python
class NoOpEncryptionProvider(EncryptionProvider):
    def encrypt(self, plaintext: str) -> str:
        return plaintext  # No encryption
        
    def decrypt(self, ciphertext: str) -> str:
        return ciphertext  # No decryption
```

### EncryptedStorage

Storage wrapper that transparently encrypts/decrypts PII fields:

```python
class EncryptedStorage(StorageInterface):
    def __init__(self, inner: StorageInterface, 
                 encryption_provider: EncryptionProvider,
                 pii_fields: Optional[Dict[str, List[str]]] = None):
        # Wraps any storage implementation with encryption
        
    def save(self, table: str, record_id: str, data: Dict[str, Any]) -> None:
        # Automatically encrypts PII fields before saving
        
    def load(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        # Automatically decrypts PII fields after loading
        
    def find(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Note: Cannot efficiently filter on encrypted fields
        # Loads all and filters after decryption
```

**Features:**
- Transparent encryption/decryption
- Maintains full `StorageInterface` compatibility
- Only encrypts configured PII fields
- Handles mixed encrypted/unencrypted data
- Statistics tracking for monitoring

### KeyManager

Handles key derivation and rotation:

```python
class KeyManager:
    def __init__(self, master_key: str):
        # Initialize with master encryption key
        
    def derive_field_key(self, table: str, field: str) -> bytes:
        # Derive unique key per table+field using HMAC
        
    def rotate_key(self, storage: EncryptedStorage, 
                   old_provider: EncryptionProvider,
                   new_provider: EncryptionProvider) -> Dict[str, int]:
        # Re-encrypt all data with new provider/key
```

## Usage Examples

### Basic Setup

```python
from core_banking.encryption import (
    create_encryption_provider, EncryptedStorage, 
    AESGCMEncryptionProvider, is_encryption_available
)

# Check if encryption is available
if is_encryption_available():
    print("Cryptography library available")
else:
    print("Cryptography library not found - using NoOp encryption")

# Create encryption provider
provider = create_encryption_provider("aesgcm", "your-master-key-here")

# Wrap storage with encryption
base_storage = PostgreSQLStorage(connection_string)
encrypted_storage = EncryptedStorage(base_storage, provider)

# Use encrypted storage normally
customer_id = encrypted_storage.save("customers", {
    "first_name": "John",      # This will be encrypted
    "last_name": "Doe",        # This will be encrypted  
    "email": "john@example.com",  # This will be encrypted
    "account_type": "checking"    # This will NOT be encrypted
})

# Data is automatically decrypted when retrieved
customer = encrypted_storage.load("customers", customer_id)
print(customer["first_name"])  # Prints "John" (decrypted automatically)
```

### Production Configuration

```python
import os
from core_banking.encryption import create_encryption_provider

# Read configuration from environment
encryption_enabled = os.getenv("NEXUM_ENCRYPTION_ENABLED", "false").lower() == "true"
encryption_provider = os.getenv("NEXUM_ENCRYPTION_PROVIDER", "aesgcm")
master_key = os.getenv("NEXUM_ENCRYPTION_MASTER_KEY")

if encryption_enabled and master_key:
    # Production encryption setup
    provider = create_encryption_provider(encryption_provider, master_key)
    storage = EncryptedStorage(base_storage, provider)
    print(f"Encryption enabled using {encryption_provider}")
else:
    # Development/testing without encryption
    provider = create_encryption_provider("noop", "")
    storage = EncryptedStorage(base_storage, provider)
    print("Encryption disabled - using NoOp provider")
```

### Custom PII Field Configuration

```python
# Custom PII field mapping
custom_pii_fields = {
    "customers": [
        "first_name", "last_name", "email", "phone", "address",
        "ssn", "passport_number", "drivers_license"  # Additional fields
    ],
    "accounts": ["account_number", "routing_number"],
    "transactions": [],  # No PII fields in transactions
    "employees": ["first_name", "last_name", "email", "employee_id"]  # New table
}

# Create encrypted storage with custom mapping
encrypted_storage = EncryptedStorage(
    base_storage, 
    provider, 
    pii_fields=custom_pii_fields
)
```

### Key Rotation

```python
from core_banking.encryption import KeyManager, FernetEncryptionProvider, AESGCMEncryptionProvider

# Current and new encryption providers
old_provider = FernetEncryptionProvider("old-master-key")
new_provider = AESGCMEncryptionProvider("new-master-key") 

# Initialize key manager
key_manager = KeyManager("new-master-key")

# Perform key rotation
stats = key_manager.rotate_key(encrypted_storage, old_provider, new_provider)
print(f"Key rotation completed: {stats}")
# Output: {'rotated_records': 1500, 'rotated_fields': 7500, 'errors': 0}
```

### Encryption Statistics

```python
# Get encryption statistics for monitoring
stats = encrypted_storage.get_encryption_stats()
print(f"Encryption operations: {stats['encrypt_count']}")
print(f"Decryption operations: {stats['decrypt_count']}")

# Monitor encryption performance
import time

start_time = time.time()
customer = encrypted_storage.load("customers", "cust_123")
load_time = time.time() - start_time

print(f"Customer load with decryption took {load_time:.3f}s")
```

### Migration to Encryption

```python
def migrate_to_encryption():
    """Migrate existing unencrypted data to encrypted storage"""
    
    # Create encryption provider
    provider = AESGCMEncryptionProvider("your-master-key")
    
    # Setup encrypted storage
    encrypted_storage = EncryptedStorage(base_storage, provider)
    
    # Migrate each table with PII fields
    pii_tables = ["customers", "accounts"]
    
    for table in pii_tables:
        print(f"Migrating {table}...")
        
        # Load all records (will be unencrypted)
        records = base_storage.load_all(table)
        
        for record in records:
            record_id = record["id"]
            
            # Save through encrypted storage (will encrypt PII fields)
            encrypted_storage.save(table, record_id, record)
        
        print(f"Migrated {len(records)} records in {table}")
    
    print("Migration to encryption completed")
```

## Configuration

Configure encryption via environment variables:

### Basic Configuration

```bash
# Enable/disable encryption
export NEXUM_ENCRYPTION_ENABLED="true"

# Choose encryption provider
export NEXUM_ENCRYPTION_PROVIDER="aesgcm"  # or "fernet" or "noop"

# Master encryption key (keep secret!)
export NEXUM_ENCRYPTION_MASTER_KEY="your-256-bit-master-key-here"
```

### Advanced Configuration

```bash
# Custom salt for key derivation (Fernet only)
export NEXUM_ENCRYPTION_SALT="custom-salt-for-pbkdf2"

# Key derivation iterations (Fernet only, default: 100000)
export NEXUM_ENCRYPTION_ITERATIONS="150000"

# Enable encryption performance logging
export NEXUM_ENCRYPTION_LOGGING="true"

# Encryption cache size for derived keys
export NEXUM_ENCRYPTION_CACHE_SIZE="1000"
```

### Security Best Practices

```bash
# Use strong, random master keys
export NEXUM_ENCRYPTION_MASTER_KEY="$(openssl rand -base64 32)"

# Store master key securely (examples)
export NEXUM_ENCRYPTION_MASTER_KEY="$(aws secretsmanager get-secret-value --secret-id nexum-encryption-key --query SecretString --output text)"
export NEXUM_ENCRYPTION_MASTER_KEY="$(kubectl get secret nexum-encryption -o jsonpath='{.data.master-key}' | base64 -d)"
```

## Security Considerations

### Key Management
- **Master Key Security**: Store master keys in secure key management systems (AWS KMS, HashiCorp Vault, etc.)
- **Key Rotation**: Regularly rotate encryption keys (recommended: annually)
- **Key Backup**: Securely back up encryption keys - lost keys mean lost data
- **Access Control**: Limit access to encryption keys to authorized personnel only

### Encryption Strength
- **AES-256-GCM**: Recommended for new deployments (authenticated encryption)
- **Fernet**: Good alternative with built-in authentication
- **NoOp**: Only for development - never use in production

### Performance Impact
- **Field-Level**: Only PII fields are encrypted, maintaining query performance
- **Index Limitations**: Cannot efficiently query on encrypted fields
- **Caching**: Consider caching decrypted data for frequently accessed records

### Compliance
- **Data at Rest**: Encrypts PII data stored in database
- **Audit Trail**: All encryption/decryption operations are logged
- **Key Escrow**: Consider key escrow requirements for compliance
- **Data Residency**: Encryption helps meet data residency requirements

## Performance Optimization

### Efficient Queries

```python
# GOOD: Filter on non-encrypted fields first
customers = encrypted_storage.find("customers", {
    "status": "active",      # Non-encrypted field
    "account_type": "premium"  # Non-encrypted field
})

# Then filter by encrypted fields in application
john_does = [c for c in customers if c["last_name"] == "Doe"]

# AVOID: Filtering directly on encrypted fields (inefficient)
# This loads ALL customers and decrypts them
customers = encrypted_storage.find("customers", {"last_name": "Doe"})
```

### Caching Strategies

```python
from functools import lru_cache

class CachedEncryptedStorage:
    """Wrapper that caches decrypted records"""
    
    def __init__(self, encrypted_storage: EncryptedStorage):
        self.storage = encrypted_storage
        self.cache = {}
    
    @lru_cache(maxsize=1000)
    def load_cached(self, table: str, record_id: str):
        """Load with caching to avoid repeated decryption"""
        return self.storage.load(table, record_id)
```

### Bulk Operations

```python
# Encrypt/decrypt in batches for better performance
def bulk_encrypt_customers(customer_data_list):
    """Process multiple customers efficiently"""
    encrypted_customers = []
    
    # Batch encryption operations
    for customer_data in customer_data_list:
        encrypted_customer = encrypted_storage._encrypt_pii("customers", customer_data)
        encrypted_customers.append(encrypted_customer)
    
    # Batch save operations
    for i, encrypted_customer in enumerate(encrypted_customers):
        customer_id = f"cust_{i+1}"
        encrypted_storage.inner.save("customers", customer_id, encrypted_customer)
    
    return len(encrypted_customers)
```

## Testing Encryption

```python
import pytest
from core_banking.encryption import AESGCMEncryptionProvider, EncryptedStorage

@pytest.fixture
def encryption_provider():
    """Create test encryption provider"""
    return AESGCMEncryptionProvider("test-master-key-256-bit")

@pytest.fixture
def encrypted_storage(encryption_provider):
    """Create encrypted storage for testing"""
    base_storage = InMemoryStorage()
    return EncryptedStorage(base_storage, encryption_provider)

def test_pii_encryption(encrypted_storage):
    """Test that PII fields are encrypted"""
    # Save customer data
    customer_data = {
        "first_name": "John",
        "last_name": "Doe", 
        "email": "john.doe@example.com",
        "account_type": "checking"  # Not PII
    }
    
    encrypted_storage.save("customers", "cust_1", customer_data)
    
    # Check raw storage (should show encrypted PII)
    raw_data = encrypted_storage.inner.load("customers", "cust_1")
    assert raw_data["first_name"].startswith("ENC:")  # Encrypted
    assert raw_data["last_name"].startswith("ENC:")   # Encrypted
    assert raw_data["email"].startswith("ENC:")       # Encrypted
    assert raw_data["account_type"] == "checking"     # Not encrypted
    
    # Check encrypted storage (should show decrypted data)
    decrypted_data = encrypted_storage.load("customers", "cust_1")
    assert decrypted_data["first_name"] == "John"
    assert decrypted_data["last_name"] == "Doe"
    assert decrypted_data["email"] == "john.doe@example.com"
    assert decrypted_data["account_type"] == "checking"

def test_encryption_roundtrip(encryption_provider):
    """Test encryption/decryption roundtrip"""
    plaintext = "sensitive data"
    
    # Encrypt
    ciphertext = encryption_provider.encrypt(plaintext)
    assert ciphertext != plaintext
    assert ciphertext.startswith("ENC:")
    
    # Decrypt
    decrypted = encryption_provider.decrypt(ciphertext)
    assert decrypted == plaintext

def test_encryption_statistics(encrypted_storage):
    """Test encryption operation tracking"""
    # Perform some operations
    encrypted_storage.save("customers", "cust_1", {"first_name": "John"})
    encrypted_storage.load("customers", "cust_1")
    
    # Check statistics
    stats = encrypted_storage.get_encryption_stats()
    assert stats["encrypt_count"] > 0
    assert stats["decrypt_count"] > 0
```

## Error Handling

```python
def handle_encryption_errors():
    """Example of robust error handling"""
    try:
        # Create encryption provider
        provider = AESGCMEncryptionProvider("master-key")
        encrypted_storage = EncryptedStorage(base_storage, provider)
        
        # Perform operations
        customer = encrypted_storage.load("customers", "cust_123")
        
    except ImportError:
        # Cryptography library not available
        logger.warning("Cryptography library not available - using NoOp encryption")
        provider = NoOpEncryptionProvider()
        encrypted_storage = EncryptedStorage(base_storage, provider)
        
    except ValueError as e:
        # Decryption failed (wrong key, corrupted data, etc.)
        logger.error(f"Decryption failed: {e}")
        # Could fall back to returning encrypted data or error
        return None
        
    except Exception as e:
        # Other encryption errors
        logger.error(f"Encryption error: {e}")
        # Handle gracefully
        return None
```

## Monitoring and Alerting

```python
import logging
from core_banking.encryption import EncryptedStorage

# Setup encryption monitoring
def setup_encryption_monitoring(encrypted_storage: EncryptedStorage):
    """Setup monitoring for encryption operations"""
    
    # Log encryption statistics periodically
    def log_encryption_stats():
        stats = encrypted_storage.get_encryption_stats()
        logger.info(f"Encryption stats: {stats}")
    
    # Monitor for encryption failures
    def monitor_decryption_failures():
        # Count failed decryptions
        # Alert if failure rate exceeds threshold
        pass
    
    # Monitor key rotation events
    def monitor_key_rotation():
        # Track key rotation completion
        # Alert on rotation failures
        pass
```

## Future Enhancements

- **Hardware Security Module (HSM)** integration
- **Key versioning** and automatic rotation
- **Column-level encryption** for database engines
- **Searchable encryption** for encrypted field queries
- **Envelope encryption** with external key management services
- **Audit encryption** with separate audit keys
- **Client-side encryption** for end-to-end protection
- **Zero-knowledge encryption** architectures