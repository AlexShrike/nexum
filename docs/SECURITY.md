# Security Guide

This guide covers Nexum's security features and best practices for production deployment. Nexum is designed with security-first principles to protect sensitive financial data and maintain regulatory compliance.

---

## Table of Contents

1. [JWT Authentication](#jwt-authentication)
2. [User Management (RBAC)](#user-management-rbac)
3. [PII Encryption at Rest](#pii-encryption-at-rest)
4. [Password Security](#password-security)
5. [Rate Limiting](#rate-limiting)
6. [Multi-Tenancy Isolation](#multi-tenancy-isolation)
7. [Audit Trail Security](#audit-trail-security)
8. [API Security Best Practices](#api-security-best-practices)
9. [Key Management & Rotation](#key-management--rotation)
10. [Compliance Considerations](#compliance-considerations)
11. [Network Security](#network-security)
12. [Deployment Security](#deployment-security)
13. [Security Monitoring](#security-monitoring)
14. [Security Checklist](#security-checklist)

---

## JWT Authentication

Nexum supports industry-standard JWT (JSON Web Token) authentication with configurable expiry and role-based access control.

### Configuration

```bash
# Enable JWT authentication (required for production)
export NEXUM_JWT_SECRET="your-secure-256-bit-secret-key-here"
export NEXUM_JWT_EXPIRY_HOURS=8
export NEXUM_JWT_ALGORITHM=HS256

# Session management
export NEXUM_SESSION_TIMEOUT_MINUTES=30
```

### Creating Admin User

**First-time setup:**
```bash
curl -X POST http://localhost:8090/auth/setup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "SecurePassword123!",
    "email": "admin@yourbank.com",
    "full_name": "Bank Administrator"
  }'
```

**Response:**
```json
{
  "user_id": "user_01HPH123ABC456DEF789",
  "username": "admin",
  "message": "Admin user created successfully",
  "default_roles": ["admin"]
}
```

### Obtaining Tokens

**Login endpoint:**
```bash
curl -X POST http://localhost:8090/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "SecurePassword123!"
  }'
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_at": "2024-02-20T15:32:00.000000",
  "session_id": "sess_01HPH456ABC789DEF012",
  "user_id": "user_01HPH123ABC456DEF789",
  "roles": ["admin"]
}
```

### Using Tokens

Include JWT token in Authorization header:

```bash
curl -X GET http://localhost:8090/customers \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE"
```

### Token Security Best Practices

**JWT Secret Management:**
- Use cryptographically secure random secret (minimum 256 bits)
- Store secrets in environment variables, never in code
- Rotate JWT secrets regularly (see Key Rotation section)
- Use different secrets for different environments

**Token Expiry:**
- Set appropriate expiry based on usage patterns (recommended: 4-8 hours)
- Implement automatic token refresh in client applications
- Monitor for expired token usage attempts

**Example secure configuration:**

```bash
# Generate secure secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Production configuration
export NEXUM_JWT_SECRET="$(cat /secure/path/jwt-secret.txt)"
export NEXUM_JWT_EXPIRY_HOURS=4
export NEXUM_JWT_ALGORITHM=HS256
```

---

## User Management (RBAC)

Nexum includes comprehensive Role-Based Access Control with fine-grained permissions for different banking operations.

### Default Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| **Admin** | All permissions | System administrators |
| **Manager** | Approve transactions, view reports, manage customers | Branch managers |
| **Teller** | Create transactions, view customers, process deposits/withdrawals | Bank tellers |
| **Loan Officer** | Create loans, approve loans up to limit, manage loan payments | Loan officers |
| **Auditor** | View audit logs, generate reports | Compliance and audit |
| **Customer Service** | View customers, update KYC, view account history | Customer support |

### Creating Users

**Create user with specific roles:**
```bash
curl -X POST http://localhost:8090/auth/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "username": "branch_manager_01",
    "password": "SecurePass456!",
    "email": "manager@yourbank.com",
    "full_name": "Branch Manager",
    "roles": ["manager"],
    "is_active": true
  }'
```

### Available Permissions

| Category | Permissions | Description |
|----------|-------------|-------------|
| **Accounts** | `CREATE_ACCOUNT`, `VIEW_ACCOUNT`, `MODIFY_ACCOUNT`, `CLOSE_ACCOUNT` | Account management |
| **Transactions** | `CREATE_TRANSACTION`, `APPROVE_TRANSACTION`, `REVERSE_TRANSACTION`, `VIEW_TRANSACTION` | Transaction processing |
| **Loans** | `CREATE_LOAN`, `APPROVE_LOAN`, `DISBURSE_LOAN`, `WRITE_OFF_LOAN` | Loan operations |
| **Credit** | `CREATE_CREDIT_LINE`, `MODIFY_CREDIT_LIMIT`, `VIEW_CREDIT_LINE` | Credit line management |
| **Customers** | `CREATE_CUSTOMER`, `VIEW_CUSTOMER`, `MODIFY_CUSTOMER`, `DELETE_CUSTOMER` | Customer operations |
| **Admin** | `MANAGE_USERS`, `MANAGE_ROLES`, `VIEW_AUDIT_LOG`, `SYSTEM_CONFIG` | Administrative functions |
| **Reports** | `VIEW_REPORTS`, `CREATE_REPORTS`, `EXPORT_REPORTS` | Reporting and analytics |

### Creating Custom Roles

**Define role with specific permissions and limits:**
```bash
curl -X POST http://localhost:8090/rbac/roles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "name": "junior_loan_officer",
    "description": "Junior loan officer with limited approval authority",
    "permissions": [
      "CREATE_LOAN",
      "VIEW_LOAN", 
      "VIEW_CUSTOMER",
      "MODIFY_CUSTOMER"
    ],
    "max_transaction_amount": {
      "amount": "50000.00",
      "currency": "USD"
    },
    "max_approval_amount": {
      "amount": "25000.00", 
      "currency": "USD"
    }
  }'
```

### Permission Checking

Nexum automatically checks permissions for all API endpoints:

**Example: Only users with `CREATE_CUSTOMER` permission can create customers**
```bash
# This will return 403 Forbidden if user lacks CREATE_CUSTOMER permission
curl -X POST http://localhost:8090/customers \
  -H "Authorization: Bearer $TELLER_TOKEN" \
  -d '{"first_name": "John", "last_name": "Doe", ...}'
```

### User Session Management

**View active sessions:**
```bash
curl -X GET http://localhost:8090/auth/sessions \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Revoke user session:**
```bash
curl -X DELETE http://localhost:8090/auth/sessions/sess_01HPH456ABC789DEF012 \
  -H "Authorization: Bearer $JWT_TOKEN"
```

---

## PII Encryption at Rest

Nexum provides transparent field-level encryption for Personally Identifiable Information (PII) stored in the database.

### What Gets Encrypted

**Automatically encrypted fields:**

| Record Type | Encrypted Fields |
|-------------|------------------|
| **Customers** | `first_name`, `last_name`, `email`, `phone`, `address`, `date_of_birth`, `tax_id`, `nationality` |
| **Accounts** | `account_number` |
| **Transactions** | Customer-specific transaction details when linked |
| **Audit Events** | Never encrypted (maintains tamper-evident trail) |

### Configuration

```bash
# Enable PII encryption
export NEXUM_ENCRYPTION_ENABLED=true

# Set master encryption key (base64-encoded 256-bit key)
export NEXUM_ENCRYPTION_MASTER_KEY="base64-encoded-256-bit-key"

# Choose encryption provider (recommended: aesgcm)
export NEXUM_ENCRYPTION_PROVIDER=aesgcm  # or fernet, or noop
```

### Encryption Providers

| Provider | Algorithm | Key Size | Authentication | Performance | Use Case |
|----------|-----------|----------|----------------|-------------|----------|
| **AES-GCM** | AES-256-GCM | 256-bit | Built-in | High | Modern deployments (recommended) |
| **Fernet** | AES-128-CBC + HMAC-SHA256 | 256-bit | Built-in | Medium | General purpose, proven |
| **NoOp** | None | None | None | Highest | Development/testing only |

### Key Generation

**Generate a master key:**

```python
from core_banking.encryption import KeyManager
import base64
import secrets

# Generate 256-bit key
key_bytes = secrets.token_bytes(32)
master_key = base64.urlsafe_b64encode(key_bytes).decode()
print(f"Master key: {master_key}")

# Store securely (never log or commit to code!)
```

**Manual generation:**

```bash
# Generate 256-bit key and base64 encode
python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

### Key Derivation

Nexum uses PBKDF2 key derivation for deterministic key generation:

- **Algorithm:** PBKDF2-HMAC-SHA256
- **Iterations:** 100,000 (OWASP recommended minimum)
- **Salt:** SHA256 hash of table+field context
- **Output:** 256-bit encryption key per field

This enables key rotation without re-encrypting all data.

### Encryption in Action

**Customer data before encryption (in application):**
```json
{
  "customer_id": "cust_01HPH123ABC456DEF789",
  "first_name": "Sarah",
  "last_name": "Johnson",
  "email": "sarah.johnson@example.com",
  "phone": "+1-555-0199"
}
```

**Customer data after encryption (in database):**
```json
{
  "customer_id": "cust_01HPH123ABC456DEF789", 
  "first_name": "ENC:gAAAAABh1234567890abcdef...",
  "last_name": "ENC:gAAAAABh0987654321fedcba...",
  "email": "ENC:gAAAAABhabcdef1234567890...",
  "phone": "ENC:gAAAAABhfedcba0987654321..."
}
```

### Migration and Compatibility

**Encrypting existing data:**

```python
from core_banking.storage import get_storage
from core_banking.encryption import EncryptedStorage, AESGCMEncryptionProvider
from core_banking.config import get_config

config = get_config()
storage = get_storage(config.database_url)

# Enable encryption for existing deployment
provider = AESGCMEncryptionProvider(config.encryption_master_key)
encrypted_storage = EncryptedStorage(storage, provider)

# Migrate existing customer records
customers = storage.find("customers", {})
for customer in customers:
    encrypted_storage.save("customers", customer["id"], customer)
    print(f"Encrypted customer: {customer['id']}")
```

### Performance Considerations

| Operation | Overhead | Notes |
|-----------|----------|-------|
| **Encryption on write** | ~0.1ms per field | Negligible for normal volumes |
| **Decryption on read** | ~0.1ms per field | Cached for repeated access |
| **Bulk operations** | ~5-10% slower | Acceptable for batch processing |
| **Search operations** | Degraded | Cannot search encrypted fields directly |

**Important:** Searching on encrypted fields requires loading all records and filtering in memory. For high-performance searches on PII, consider tokenization or searchable encryption techniques.

---

## Password Security

Nexum implements industry-standard password security with scrypt hashing and configurable policies.

### Password Hashing

**Algorithm:** scrypt (RFC 7914)
- **N:** 32768 (CPU/memory cost factor)
- **r:** 8 (block size)
- **p:** 1 (parallelization factor)  
- **dkLen:** 64 (derived key length)
- **Salt:** 32 random bytes per password

This configuration provides strong resistance against brute-force and rainbow table attacks.

### Password Policy Configuration

```bash
# Password complexity requirements
export NEXUM_PASSWORD_MIN_LENGTH=12
export NEXUM_PASSWORD_REQUIRE_UPPERCASE=true
export NEXUM_PASSWORD_REQUIRE_LOWERCASE=true  
export NEXUM_PASSWORD_REQUIRE_NUMBERS=true
export NEXUM_PASSWORD_REQUIRE_SYMBOLS=true

# Account lockout policy
export NEXUM_MAX_LOGIN_ATTEMPTS=5
export NEXUM_ACCOUNT_LOCKOUT_MINUTES=30

# Password history
export NEXUM_PASSWORD_HISTORY_COUNT=12
export NEXUM_PASSWORD_MAX_AGE_DAYS=90
```

### Password Validation

**Example of secure password creation:**
```bash
curl -X POST http://localhost:8090/auth/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "username": "loan_officer_01",
    "password": "MySecure#Password123!",
    "email": "loan.officer@yourbank.com",
    "full_name": "Loan Officer"
  }'
```

**Password validation response:**
```json
{
  "user_id": "user_01HPH567DEF890GHI123",
  "username": "loan_officer_01",
  "password_strength": "strong",
  "password_policies_met": [
    "minimum_length",
    "contains_uppercase", 
    "contains_lowercase",
    "contains_numbers",
    "contains_symbols"
  ]
}
```

### Password Change Policy

**Force password change:**
```bash
curl -X PUT http://localhost:8090/auth/users/user_01HPH567DEF890GHI123/password \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "new_password": "NewSecure#Password456!",
    "force_change_on_next_login": false,
    "send_notification": true
  }'
```

### Account Lockout Protection

**View locked accounts:**
```bash
curl -X GET http://localhost:8090/auth/locked-accounts \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Unlock account:**
```bash
curl -X POST http://localhost:8090/auth/users/user_01HPH567DEF890GHI123/unlock \
  -H "Authorization: Bearer $JWT_TOKEN"
```

---

## Rate Limiting

Nexum includes configurable rate limiting to prevent abuse and DoS attacks.

### Configuration

```bash
# Enable rate limiting (enabled by default)
export NEXUM_ENABLE_RATE_LIMITING=true

# Global rate limits (requests per minute per IP)
export NEXUM_RATE_LIMIT_GLOBAL=1000

# Endpoint-specific limits
export NEXUM_RATE_LIMIT_AUTH=10        # Authentication endpoints
export NEXUM_RATE_LIMIT_TRANSACTIONS=500  # Transaction processing
export NEXUM_RATE_LIMIT_REPORTS=50     # Report generation
```

### Default Rate Limits

| Endpoint Category | Default Limit | Reasoning |
|------------------|---------------|-----------|
| **Authentication** | 10/min | Prevent brute force attacks |
| **Transaction Processing** | 500/min | High-volume production use |
| **Account Operations** | 200/min | Normal banking operations |
| **Report Generation** | 50/min | Resource-intensive operations |
| **Admin Operations** | 100/min | Administrative tasks |

### Rate Limit Headers

Nexum returns standard rate limit headers:

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 500
X-RateLimit-Remaining: 487
X-RateLimit-Reset: 1708354800
X-RateLimit-Window: 60
```

**When rate limit is exceeded:**

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 500
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1708354860
Retry-After: 60

{
  "error": "Rate limit exceeded",
  "limit": 500,
  "reset_at": "2024-02-19T16:01:00.000000",
  "retry_after": 60
}
```

### Custom Rate Limiting

**Per-user rate limiting based on roles:**

```python
# Higher limits for admin users
ROLE_RATE_LIMITS = {
    "admin": 2000,      # 2000 requests/minute
    "manager": 1000,    # 1000 requests/minute  
    "teller": 500,      # 500 requests/minute
    "customer": 100     # 100 requests/minute
}
```

### Rate Limiting Monitoring

**View rate limiting statistics:**
```bash
curl -X GET http://localhost:8090/admin/rate-limits/stats \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Response:**
```json
{
  "total_requests": 156789,
  "blocked_requests": 234,
  "top_ips_by_requests": [
    {"ip": "192.168.1.100", "requests": 1234, "blocked": 5},
    {"ip": "10.0.0.50", "requests": 987, "blocked": 0}
  ],
  "blocked_endpoints": [
    {"endpoint": "/auth/login", "blocked": 45},
    {"endpoint": "/transactions", "blocked": 12}
  ]
}
```

---

## Multi-Tenancy Isolation

Nexum supports multi-tenant deployments with strong data isolation between financial institutions.

### Tenant Isolation Strategies

| Strategy | Description | Security Level | Use Case |
|----------|-------------|----------------|----------|
| **Shared Table** | All tenants in same tables, filtered by tenant_id | Medium | Cost-effective SaaS |
| **Schema Per Tenant** | Each tenant gets PostgreSQL schema | High | Regulatory compliance |
| **Database Per Tenant** | Each tenant gets separate database | Highest | Maximum isolation |

### Configuration

```bash
# Enable multi-tenancy
export NEXUM_MULTI_TENANT_ENABLED=true
export NEXUM_TENANT_ISOLATION_STRATEGY=shared_table

# Tenant identification
export NEXUM_TENANT_HEADER_NAME=X-Tenant-ID
export NEXUM_TENANT_SUBDOMAIN_ENABLED=true
```

### Creating Tenants

**Create a new financial institution tenant:**
```bash
curl -X POST http://localhost:8090/admin/tenants \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "name": "Community Bank of Portland",
    "code": "CBPORTLAND", 
    "display_name": "CB Portland",
    "description": "Regional community bank serving Portland metro",
    "subscription_tier": "professional",
    "contact_email": "admin@cbportland.com",
    "max_users": 50,
    "max_accounts": 10000,
    "settings": {
      "default_currency": "USD",
      "interest_calculation_method": "daily_balance",
      "allow_overdrafts": true
    }
  }'
```

### Tenant Context

**API requests include tenant identification:**

**Option 1: HTTP Header**
```bash
curl -X GET http://localhost:8090/customers \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "X-Tenant-ID: tenant_cbportland"
```

**Option 2: Subdomain routing**
```bash
curl -X GET https://cbportland.nexum.yourbank.com/customers \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Option 3: JWT tenant claim**
```json
{
  "sub": "user_admin", 
  "tenant_id": "tenant_cbportland",
  "roles": ["admin"],
  "exp": 1708354800
}
```

### Data Isolation Verification

**Tenant data is automatically isolated:**
```bash
# User in Tenant A cannot see Tenant B's customers
curl -X GET http://localhost:8090/customers \
  -H "Authorization: Bearer $TENANT_A_TOKEN" \
  -H "X-Tenant-ID: tenant_a"

# Returns only Tenant A's customers, even if database contains Tenant B data
```

### Tenant Security Features

**Quota enforcement:**
```bash
# Tenant B is limited to 1000 accounts
curl -X POST http://localhost:8090/accounts \
  -H "X-Tenant-ID: tenant_b" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{...}'

# Returns 429 if tenant has reached account limit
```

**Cross-tenant access prevention:**
```bash
# Attempting to access another tenant's account
curl -X GET http://localhost:8090/accounts/acc_tenant_b_account \
  -H "X-Tenant-ID: tenant_a" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Returns 404 (account not found) instead of 403 to prevent information disclosure
```

---

## Audit Trail Security

Nexum's audit trail is designed to be tamper-evident and suitable for regulatory compliance with hash chaining and integrity verification.

### Hash Chaining

Each audit entry includes SHA-256 hash of the previous entry, creating a blockchain-like structure:

```json
{
  "id": "ae_01HPH123ABC456DEF789",
  "event_type": "transaction_posted",
  "entity_type": "transaction",
  "entity_id": "txn_01HPH456GHI789JKL012",
  "timestamp": "2024-02-19T15:30:00.000000",
  "user_id": "user_teller_01",
  "metadata": {
    "transaction_type": "deposit",
    "amount": "1500.00",
    "currency": "USD"
  },
  "current_hash": "a1b2c3d4e5f6789012345678...",
  "previous_hash": "f6e5d4c3b2a1987654321098..."
}
```

### Integrity Verification

**Verify complete audit trail:**
```bash
curl -X POST http://localhost:8090/audit/verify-integrity \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Response:**
```json
{
  "is_valid": true,
  "total_events": 15847,
  "verified_events": 15847,
  "hash_chain_valid": true,
  "first_event_hash": "genesis_hash",
  "last_event_hash": "a1b2c3d4e5f6789012345678...",
  "verification_time": "2024-02-19T16:15:00.000000"
}
```

**Detect tampering:**
```json
{
  "is_valid": false,
  "broken_chain_at": "ae_01HPH789DEF012GHI345", 
  "expected_hash": "a1b2c3d4e5f6...",
  "actual_hash": "tampered_hash...",
  "total_events": 15847,
  "verified_events": 12453,
  "error": "Hash chain broken at event ae_01HPH789DEF012GHI345"
}
```

### Automated Integrity Monitoring

**Set up periodic integrity checks:**
```bash
# Add to crontab for hourly verification
0 * * * * curl -s -X POST http://localhost:8090/audit/verify-integrity \
  -H "Authorization: Bearer $AUDIT_TOKEN" | \
  jq -r '.is_valid // false' | \
  grep -q false && echo "ALERT: Audit trail compromised" | \
  mail -s "Audit Alert" security@yourbank.com
```

### Regulatory Export

**Generate compliance reports:**
```bash
# Export audit trail for specific date range
curl -X GET "http://localhost:8090/audit/export?start_date=2024-01-01&end_date=2024-01-31&format=xml" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -o "audit_report_jan2024.xml"
```

**Export formats supported:**
- **JSON** - Machine readable format
- **XML** - Common regulatory format  
- **CSV** - Excel-compatible format
- **PDF** - Human readable reports

---

## API Security Best Practices

### HTTPS/TLS Configuration

**Always use HTTPS in production:**

```bash
# Using uvicorn with SSL certificates
uvicorn core_banking.api:app \
  --host 0.0.0.0 \
  --port 443 \
  --ssl-keyfile /path/to/private.key \
  --ssl-certfile /path/to/certificate.crt \
  --ssl-ca-certs /path/to/ca-bundle.crt
```

**Nginx reverse proxy (recommended):**

```nginx
server {
    listen 443 ssl http2;
    server_name banking-api.yourbank.com;
    
    # SSL Configuration
    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5:!3DES;
    ssl_prefer_server_ciphers on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Content-Security-Policy "default-src 'self'";
    
    # Hide server information
    server_tokens off;
    
    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        
        # Timeouts
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
        proxy_connect_timeout 30s;
    }
}
```

### Input Validation

All API inputs are validated using Pydantic models with strict type checking:

```python
# Example: Transaction creation validates all fields
{
  "account_id": "acc_01HPH456GHI789JKL012",  # Must be valid account ID format
  "amount": {
    "amount": "1500.00",                     # Must be valid decimal string
    "currency": "USD"                        # Must be valid ISO currency code
  },
  "description": "Payroll deposit",          # Max 255 characters
  "channel": "online"                        # Must be valid channel enum
}
```

**Validation errors return detailed feedback:**
```json
{
  "detail": [
    {
      "field": "amount.amount",
      "error": "Amount must be positive",
      "provided_value": "-100.00"
    }
  ],
  "error_code": "VALIDATION_ERROR"
}
```

### SQL Injection Prevention

- **Parameterized queries:** All database queries use parameter binding
- **ORM protection:** SQLAlchemy ORM prevents most injection attacks  
- **Input sanitization:** All user input is validated and escaped

### CORS Configuration

**Restrict CORS origins in production:**

```bash
# Development (permissive)
export NEXUM_CORS_ORIGINS="*"

# Production (restrictive)
export NEXUM_CORS_ORIGINS="https://banking-app.yourbank.com,https://admin.yourbank.com"
```

---

## Key Management & Rotation

Regular key rotation is essential for maintaining security. Nexum supports automated key rotation procedures.

### JWT Secret Rotation

**Step 1: Generate new secret**
```bash
NEW_JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
echo "New JWT secret: $NEW_JWT_SECRET"
```

**Step 2: Gradual rollover (zero-downtime)**
```bash
# Enable dual-secret validation during transition
export NEXUM_JWT_SECRET="$NEW_JWT_SECRET"
export NEXUM_JWT_SECRET_OLD="$OLD_JWT_SECRET"
```

**Step 3: Complete migration**
After all tokens expire (8 hours default):
```bash
unset NEXUM_JWT_SECRET_OLD
```

### Encryption Key Rotation

**Option 1: Master key rotation with re-encryption**
```python
from core_banking.encryption import KeyManager, EncryptedStorage
from core_banking.storage import get_storage
from core_banking.config import get_config
import os

# Generate new master key
new_master_key = KeyManager.generate_master_key()
old_master_key = os.getenv('NEXUM_ENCRYPTION_MASTER_KEY')

# Update environment
os.environ['NEXUM_ENCRYPTION_MASTER_KEY'] = new_master_key

# Re-encrypt all PII data
config = get_config()
storage = get_storage(config.database_url)

# This would run as a background job in production
for table in ['customers', 'accounts']:
    records = storage.find(table, {})
    for record in records:
        # Decrypt with old key, encrypt with new key
        decrypted = decrypt_with_key(record, old_master_key)
        encrypted = encrypt_with_key(decrypted, new_master_key)
        storage.save(table, record['id'], encrypted)
    print(f"Re-encrypted {len(records)} records in {table}")
```

**Option 2: Key versioning (recommended for large datasets)**
```python
from core_banking.encryption import VersionedKeyManager

# Add new key version without disrupting existing data
key_manager = VersionedKeyManager()
new_version = key_manager.add_key_version(new_master_key)

# New data automatically uses latest key version
# Old data remains readable with previous key versions
```

### Automated Key Rotation

**Using AWS Secrets Manager:**
```python
import boto3
from datetime import datetime, timedelta

def rotate_encryption_keys():
    secrets_client = boto3.client('secretsmanager')
    
    # Generate new master key
    new_key = KeyManager.generate_master_key()
    
    # Store in AWS Secrets Manager with rotation
    secrets_client.update_secret(
        SecretId='nexum/encryption-master-key',
        SecretString=new_key,
        Description=f'Rotated on {datetime.now().isoformat()}'
    )
    
    return new_key

# Schedule monthly rotation
```

**Key backup and recovery:**
```bash
# Backup current encryption keys (encrypt backup!)
echo "$NEXUM_ENCRYPTION_MASTER_KEY" | gpg --encrypt --armor -r security@yourbank.com > nexum-key-backup.gpg

# Store in secure location
aws s3 cp nexum-key-backup.gpg s3://yourbank-security-backups/nexum/keys/$(date +%Y%m%d)/

# Recovery procedure
aws s3 cp s3://yourbank-security-backups/nexum/keys/20240219/nexum-key-backup.gpg .
RESTORED_KEY=$(gpg --decrypt nexum-key-backup.gpg)
export NEXUM_ENCRYPTION_MASTER_KEY="$RESTORED_KEY"
```

---

## Compliance Considerations

Nexum is designed to support compliance with major financial regulations.

### BSA/AML Compliance (Bank Secrecy Act/Anti-Money Laundering)

**Transaction monitoring:**
```bash
# Set up large transaction reporting (>$10,000)
export NEXUM_CTR_THRESHOLD=10000.00

# Enable suspicious activity monitoring
export NEXUM_SAR_ENABLED=true
export NEXUM_SAR_VELOCITY_THRESHOLD=5000.00
```

**Compliance API endpoints:**
```bash
# Flag suspicious transaction
curl -X POST http://localhost:8090/compliance/suspicious-activity \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "transaction_id": "txn_01HPH456GHI789JKL012",
    "reason": "Unusual velocity pattern",
    "severity": "medium"
  }'

# Generate CTR report
curl -X GET "http://localhost:8090/compliance/ctr-report?date=2024-02-19" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### GDPR Compliance (General Data Protection Regulation)

**Right to be Forgotten (Article 17):**
```bash
# Delete all customer data (irreversible)
curl -X DELETE http://localhost:8090/compliance/gdpr/customer/cust_01HPH123ABC456DEF789 \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "reason": "Customer requested deletion",
    "confirmation": "I confirm this will permanently delete all data"
  }'
```

**Data Portability (Article 20):**
```bash
# Export all customer data in machine-readable format
curl -X GET http://localhost:8090/compliance/gdpr/export/cust_01HPH123ABC456DEF789 \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -o customer_data_export.json
```

### PCI DSS Compliance (Payment Card Industry)

**Data minimization:**
- Credit card numbers are never stored (use tokenization)
- PCI-sensitive fields are encrypted or excluded
- Audit logs track all card data access

```bash
# Tokenize credit card (instead of storing)
curl -X POST http://localhost:8090/payments/tokenize \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "card_number": "4532123456789012",
    "expiry_month": "12",
    "expiry_year": "2027"
  }'

# Response contains token, not actual card number
{
  "token": "tok_01HPH789ABC123DEF456",
  "last_four": "9012",
  "card_type": "visa",
  "expires_at": "2027-12-31"
}
```

### SOX Compliance (Sarbanes-Oxley)

**Internal controls:**
- Segregation of duties enforced by RBAC
- All financial transactions require approval workflows
- Immutable audit trail for all changes

**Change management:**
```bash
# All system configuration changes are logged
curl -X PUT http://localhost:8090/admin/config \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "max_daily_transaction_limit": "25000.00"
  }'

# Audit event is automatically created
{
  "event_type": "system_config_changed",
  "changed_by": "user_admin",
  "changes": {
    "max_daily_transaction_limit": {
      "old_value": "10000.00",
      "new_value": "25000.00"
    }
  }
}
```

---

## Network Security

### Firewall Configuration

**Recommended iptables rules:**
```bash
# Allow HTTPS traffic only
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow PostgreSQL from application servers only
iptables -A INPUT -p tcp --dport 5432 -s 10.0.1.0/24 -j ACCEPT

# Allow Kafka from application servers (if used)
iptables -A INPUT -p tcp --dport 9092 -s 10.0.1.0/24 -j ACCEPT

# Allow SSH from management network
iptables -A INPUT -p tcp --dport 22 -s 10.0.0.0/24 -j ACCEPT

# Block all other traffic
iptables -A INPUT -j DROP
```

### VPC/Network Segmentation

**AWS VPC architecture:**
```yaml
# Private subnets for application servers
ApplicationSubnet:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref VPC
    CidrBlock: 10.0.1.0/24
    AvailabilityZone: us-east-1a

# Database subnet (isolated)
DatabaseSubnet:
  Type: AWS::EC2::Subnet  
  Properties:
    VpcId: !Ref VPC
    CidrBlock: 10.0.2.0/24
    AvailabilityZone: us-east-1b

# Security group - HTTPS only from load balancer
ApplicationSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupDescription: Nexum application security group
    VpcId: !Ref VPC
    SecurityGroupIngress:
      - IpProtocol: tcp
        FromPort: 8090
        ToPort: 8090
        SourceSecurityGroupId: !Ref LoadBalancerSecurityGroup
```

---

## Deployment Security

### Container Security

**Secure Dockerfile:**
```dockerfile
FROM python:3.12-slim

# Create non-root user first
RUN groupadd --gid 1000 nexum \
    && useradd --uid 1000 --gid nexum --shell /bin/bash --create-home nexum

# Install system dependencies as root
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory and change ownership
WORKDIR /app
COPY --chown=nexum:nexum . .

# Install Python dependencies
USER root
RUN pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install -E full --no-dev

# Switch to non-root user for runtime
USER nexum

# Expose port
EXPOSE 8090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8090/health || exit 1

# Run application
CMD ["python", "run.py"]
```

### Kubernetes Security

**Secure deployment manifest:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nexum-api
  namespace: banking
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nexum-api
  template:
    metadata:
      labels:
        app: nexum-api
    spec:
      serviceAccountName: nexum-service-account
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
      containers:
      - name: nexum
        image: nexum:latest
        ports:
        - containerPort: 8090
          name: http
        env:
        - name: NEXUM_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: nexum-secrets
              key: database-url
        - name: NEXUM_JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: nexum-secrets  
              key: jwt-secret
        - name: NEXUM_ENCRYPTION_MASTER_KEY
          valueFrom:
            secretKeyRef:
              name: nexum-secrets
              key: encryption-key
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
            - ALL
        resources:
          limits:
            memory: "2Gi"
            cpu: "1000m"
          requests:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8090
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8090
          initialDelaySeconds: 10
          periodSeconds: 10
        volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: tmp
        emptyDir: {}
      - name: logs
        emptyDir: {}
```

### Environment Variable Security

**Use secret management:**

```bash
# ❌ Bad - secrets in plain text environment files
echo "NEXUM_JWT_SECRET=my-secret" >> .env

# ✅ Good - use secret management systems
export NEXUM_JWT_SECRET="$(aws secretsmanager get-secret-value --secret-id nexum/jwt-secret --query SecretString --output text)"
export NEXUM_ENCRYPTION_MASTER_KEY="$(kubectl get secret nexum-secrets -o jsonpath='{.data.encryption-key}' | base64 -d)"
```

**Secret management options:**

| Platform | Secret Storage | Configuration Example |
|----------|---------------|----------------------|
| **AWS** | Secrets Manager | `aws secretsmanager get-secret-value --secret-id nexum/jwt-secret` |
| **Azure** | Key Vault | `az keyvault secret show --vault-name nexum-vault --name jwt-secret` |
| **GCP** | Secret Manager | `gcloud secrets versions access latest --secret=nexum-jwt-secret` |
| **Kubernetes** | Secrets | `kubectl get secret nexum-secrets -o jsonpath='{.data.jwt-secret}'` |
| **HashiCorp** | Vault | `vault kv get -field=jwt_secret secret/nexum` |

---

## Security Monitoring

### Security Event Logging

**Security events are automatically logged:**

```json
{
  "timestamp": "2024-02-19T15:30:00.000000",
  "level": "WARNING", 
  "event": "authentication_failed",
  "details": {
    "username": "admin",
    "ip_address": "192.168.1.100",
    "user_agent": "curl/7.68.0",
    "failure_reason": "invalid_password"
  }
}
```

**Critical security alerts:**

```json
{
  "timestamp": "2024-02-19T15:31:00.000000",
  "level": "CRITICAL",
  "event": "account_lockout",
  "details": {
    "username": "loan_officer_01",
    "ip_address": "192.168.1.100", 
    "failed_attempts": 5,
    "lockout_duration_minutes": 30
  }
}
```

### Intrusion Detection

**Monitor for suspicious patterns:**

```python
from core_banking.security import SecurityMonitor

security = SecurityMonitor()

# Monitor failed login attempts
security.monitor_failed_logins(threshold=5, window_minutes=5)

# Monitor rate limit violations
security.monitor_rate_limits(alert_threshold=0.8)

# Monitor unusual transaction patterns  
security.monitor_transaction_patterns(
    velocity_threshold=10,  # 10+ transactions in 5 minutes
    amount_threshold=50000  # Single transaction >$50K
)

# Monitor privilege escalation attempts
security.monitor_privilege_escalation()
```

### SIEM Integration

**Forward security logs to SIEM:**

```python
import json
import socket
import logging

class SIEMHandler(logging.Handler):
    def __init__(self, siem_host, siem_port):
        super().__init__()
        self.siem_host = siem_host
        self.siem_port = siem_port
        
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            log_entry = {
                'timestamp': record.created,
                'level': record.levelname,
                'message': record.getMessage(),
                'source': 'nexum-core-banking'
            }
            
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                message = json.dumps(log_entry)
                sock.sendto(message.encode(), (self.siem_host, self.siem_port))
                sock.close()
            except Exception:
                pass  # Don't break application if SIEM is down

# Configure security logging
security_logger = logging.getLogger('nexum.security')
security_logger.addHandler(SIEMHandler('siem-server', 514))
```

### Security Metrics Dashboard

**Key security metrics to monitor:**

| Metric | Normal Range | Alert Threshold | Action |
|--------|--------------|----------------|---------|
| **Failed logins/hour** | 0-20 | >100 | Investigate source IPs |
| **Rate limit hits/hour** | 0-50 | >200 | Block abusive sources |
| **Account lockouts/day** | 0-5 | >20 | Check for brute force attacks |
| **Privilege escalation attempts** | 0 | >0 | Immediate investigation |
| **Audit integrity checks** | Pass | Fail | Critical security incident |
| **Large transactions/day** | Normal pattern | 3x deviation | Review for money laundering |

**Monitoring dashboard query examples:**

```bash
# Count failed logins in last hour
curl -X GET "http://localhost:8090/admin/security/metrics?metric=failed_logins&period=1h" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Get rate limiting statistics
curl -X GET "http://localhost:8090/admin/security/rate-limits" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Check audit integrity status  
curl -X GET "http://localhost:8090/admin/security/audit-integrity" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

---

## Security Checklist

Use this checklist for production security review:

### Authentication & Authorization
- [ ] JWT authentication enabled with strong secret (minimum 256 bits)
- [ ] Appropriate token expiry configured (4-8 hours recommended)
- [ ] Default admin credentials changed or removed
- [ ] User roles and permissions properly configured
- [ ] RBAC policies tested and verified
- [ ] Account lockout policies configured

### Data Protection  
- [ ] PII encryption enabled for all sensitive fields
- [ ] Strong master encryption key generated and stored securely
- [ ] Encryption provider chosen (AES-GCM recommended)
- [ ] Key backup and recovery procedures documented
- [ ] Existing data migration completed (if upgrading)

### Password Security
- [ ] Strong password policies enforced (12+ characters, complexity)
- [ ] scrypt password hashing configured
- [ ] Password history tracking enabled
- [ ] Account lockout after failed attempts
- [ ] Password rotation policies established

### Network Security
- [ ] HTTPS/TLS configured with strong ciphers (TLS 1.2+)
- [ ] CORS origins restricted to allowed domains
- [ ] Firewall rules configured (allow 443, block others)
- [ ] Load balancer security headers configured
- [ ] VPC/network segmentation implemented

### Rate Limiting & DoS Protection
- [ ] Rate limiting enabled with appropriate limits per endpoint
- [ ] Custom rate limits configured for different user roles
- [ ] Rate limit monitoring and alerting configured  
- [ ] DDoS protection implemented (CloudFlare, AWS Shield, etc.)

### Audit & Compliance
- [ ] Audit logging enabled with hash chaining
- [ ] Audit trail integrity verification automated
- [ ] Compliance requirements mapped (BSA/AML, GDPR, PCI DSS, SOX)
- [ ] Regulatory export procedures documented
- [ ] Data retention policies configured

### Multi-Tenancy (if enabled)
- [ ] Tenant isolation strategy selected and configured
- [ ] Data isolation verified through testing
- [ ] Cross-tenant access prevention tested
- [ ] Tenant quota enforcement configured

### Deployment Security
- [ ] Containers running as non-root user
- [ ] Read-only root filesystem configured (where possible)
- [ ] Resource limits set (CPU, memory)
- [ ] Health checks configured
- [ ] Secrets managed via secret store (not environment files)

### Monitoring & Alerting  
- [ ] Security event logging configured
- [ ] Critical security alerts configured (lockouts, integrity failures)
- [ ] SIEM integration implemented (if required)
- [ ] Security metrics dashboard configured
- [ ] Incident response procedures documented

### Key Management
- [ ] Key rotation procedures documented and tested
- [ ] Key backup and recovery procedures tested  
- [ ] Key versioning implemented (for large datasets)
- [ ] Automated rotation scheduled (recommended quarterly)

---

## Incident Response

### Security Incident Types

| Incident Type | Immediate Response | Investigation Steps |
|---------------|-------------------|-------------------|
| **Unauthorized Access** | Revoke user sessions, lock affected accounts | Review audit logs, identify entry point |
| **Data Breach** | Isolate affected systems, preserve evidence | Assess data exposure, notify stakeholders |
| **Brute Force Attack** | Enable aggressive rate limiting, block source IPs | Analyze attack patterns, strengthen authentication |
| **Audit Tampering** | Lock system, preserve logs, notify compliance | Forensic analysis, integrity verification |
| **Key Compromise** | Rotate all keys immediately, force re-authentication | Identify compromise source, update procedures |
| **Privilege Escalation** | Lock affected accounts, review permissions | Check for system vulnerabilities, audit user actions |

### Emergency Response Contacts

Document emergency contacts for security incidents:

```yaml
Security Incident Response Team:
  Primary: security-team@yourbank.com
  Secondary: ciso@yourbank.com
  
External Contacts:
  Legal Counsel: legal@yourbank.com
  Compliance Officer: compliance@yourbank.com
  Law Enforcement: (if required by jurisdiction)
  
Technical Contacts:
  Database Administrator: dba@yourbank.com
  Network Security: netops@yourbank.com
  Cloud Provider Support: (AWS/Azure/GCP premium support)

Regulatory Bodies:
  Financial Crimes Enforcement Network: fincen@treasury.gov
  Office of the Comptroller of the Currency: customer.assistance@occ.treas.gov
```

This comprehensive security guide ensures Nexum is deployed with enterprise-grade security controls appropriate for handling sensitive financial data and meeting regulatory compliance requirements in the banking industry.