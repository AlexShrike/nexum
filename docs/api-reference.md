# API Reference

Nexum provides 130+ REST API endpoints organized by functional modules. All endpoints support JSON request/response format and follow REST conventions.

## Base URL

- Development: `http://localhost:8090`
- Production: Configure with `NEXUM_HOST` and `NEXUM_PORT` environment variables

## Authentication

Nexum uses JWT (JSON Web Token) authentication with bearer tokens. All protected endpoints require a valid JWT token in the Authorization header.

### JWT Authentication Flow

1. **Login**: POST to `/auth/login` with username/password
2. **Receive Token**: Get JWT token and session information  
3. **Use Token**: Include token in Authorization header for subsequent requests
4. **Token Expiry**: Tokens expire after 24 hours (configurable via `NEXUM_JWT_EXPIRY_HOURS`)

### Authentication Headers

```bash
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Rate Limiting

API requests are rate limited to 60 requests per minute per IP address. Rate limit headers are included in responses:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45  
X-RateLimit-Reset: 1735603260
```

When rate limit is exceeded, API returns HTTP 429 with:

```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 60
}
```

## Authentication Endpoints (3 endpoints)

### POST /auth/login
Authenticate user and receive JWT token.

**Request:**
```json
{
  "username": "admin",
  "password": "secure_password_123"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer", 
  "session_id": "sess_abc123def456",
  "expires_at": "2026-02-20T15:32:00.000000",
  "message": "Login successful"
}
```

**Error Responses:**
- **401 Unauthorized**: Invalid username/password
- **423 Locked**: Account locked due to failed attempts

### POST /auth/logout
Logout user and invalidate session.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "message": "Logged out successfully"
}
```

### POST /auth/setup
Create the first admin user (only works if no users exist).

**Request:**
```json
{
  "username": "admin",
  "password": "secure_password_123", 
  "email": "admin@example.com",
  "full_name": "Administrator"
}
```

## Common Data Types

### Money
```json
{
  "amount": "123.45",
  "currency": "USD"
}
```

### Address
```json
{
  "line1": "123 Main Street",
  "line2": "Apt 4B",
  "city": "Anytown",
  "state": "CA",
  "postal_code": "12345",
  "country": "US"
}
```

### Pagination

List endpoints support pagination with query parameters:

- `skip`: Number of records to skip (default: 0)  
- `limit`: Maximum number of records to return (default: 50, max: 1000)

**Example Request:**
```
GET /customers?skip=0&limit=20
```

**Paginated Response:**
```json
{
  "items": [...],
  "total": 156,
  "skip": 0,
  "limit": 20,
  "has_more": true
}
```

## Health & Status (2 endpoints)

### GET /health
Check system health status.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-02-19T15:32:00.000000",
  "version": "1.0.0"
}
```

### GET /
System information and welcome message.

## Customer Management (5 endpoints)

### POST /customers
Create a new customer.

**Request:**
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "phone": "+1-555-0123",
  "date_of_birth": "1990-01-15",
  "address": {
    "line1": "123 Main Street",
    "city": "Anytown",
    "state": "CA",
    "postal_code": "12345",
    "country": "US"
  }
}
```

**Response (201):**
```json
{
  "customer_id": "cust_abc123def456",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "kyc_status": "none",
  "kyc_tier": "tier_0",
  "created_at": "2026-02-19T15:32:00.000000"
}
```

### GET /customers/{customer_id}
Retrieve customer details.

### PUT /customers/{customer_id}
Update customer information.

### PUT /customers/{customer_id}/kyc
Update customer KYC status and tier.

**Request:**
```json
{
  "status": "verified",
  "tier": "tier_2",
  "documents": ["drivers_license", "proof_of_address"],
  "expiry_days": 365
}
```

## Account Management (8 endpoints)

### POST /accounts
Create a new account.

**Request:**
```json
{
  "customer_id": "cust_abc123def456",
  "product_type": "savings",
  "currency": "USD",
  "name": "Primary Savings",
  "interest_rate": "0.025",
  "minimum_balance": {
    "amount": "100.00",
    "currency": "USD"
  }
}
```

### GET /accounts/{account_id}
Get account details and current balance.

**Response:**
```json
{
  "account_id": "acc_xyz789ghi012",
  "customer_id": "cust_abc123def456",
  "product_type": "savings",
  "currency": "USD",
  "balance": {
    "amount": "1000.00",
    "currency": "USD"
  },
  "available_balance": {
    "amount": "900.00",
    "currency": "USD"
  },
  "status": "active"
}
```

### GET /customers/{customer_id}/accounts
List all accounts for a customer.

### GET /accounts/{account_id}/transactions
Get transaction history for an account.

**Query Parameters:**
- `limit`: Maximum number of transactions (default: 50)
- `offset`: Pagination offset (default: 0)
- `start_date`: Filter from date (ISO format)
- `end_date`: Filter to date (ISO format)

## Transaction Processing (4 endpoints)

### POST /transactions/deposit
Make a deposit to an account.

**Request:**
```json
{
  "account_id": "acc_xyz789ghi012",
  "amount": {
    "amount": "500.00",
    "currency": "USD"
  },
  "description": "Payroll deposit",
  "channel": "online",
  "reference": "PAY001"
}
```

### POST /transactions/withdraw
Withdraw from an account.

**Request:**
```json
{
  "account_id": "acc_xyz789ghi012",
  "amount": {
    "amount": "100.00",
    "currency": "USD"
  },
  "description": "ATM withdrawal",
  "channel": "atm"
}
```

### POST /transactions/transfer
Transfer between accounts.

**Request:**
```json
{
  "from_account_id": "acc_xyz789ghi012",
  "to_account_id": "acc_abc123def456",
  "amount": {
    "amount": "200.00",
    "currency": "USD"
  },
  "description": "Transfer to savings",
  "channel": "online"
}
```

## Credit Line Management (3 endpoints)

### POST /credit/payment
Make a payment to a credit line.

**Request:**
```json
{
  "account_id": "acc_credit123",
  "amount": {
    "amount": "150.00",
    "currency": "USD"
  },
  "payment_date": "2026-02-19"
}
```

### POST /credit/{account_id}/statement
Generate credit line statement.

### GET /credit/{account_id}/statements
Retrieve statement history for a credit line.

## Loan Management (5 endpoints)

### POST /loans
Create a new loan.

**Request:**
```json
{
  "customer_id": "cust_abc123def456",
  "terms": {
    "principal_amount": {
      "amount": "10000.00",
      "currency": "USD"
    },
    "annual_interest_rate": "0.06",
    "term_months": 36,
    "payment_frequency": "monthly",
    "amortization_method": "equal_installment",
    "first_payment_date": "2026-03-19",
    "allow_prepayment": true,
    "grace_period_days": 10
  },
  "currency": "USD"
}
```

### POST /loans/{loan_id}/disburse
Disburse loan funds.

### POST /loans/payment
Make a loan payment.

**Request:**
```json
{
  "loan_id": "loan_xyz789",
  "amount": {
    "amount": "304.22",
    "currency": "USD"
  },
  "payment_date": "2026-03-19",
  "source_account_id": "acc_checking123"
}
```

### GET /loans/{loan_id}
Get loan details and current status.

### GET /loans/{loan_id}/schedule
Get loan amortization schedule.

## Interest Management (2 endpoints)

### POST /admin/interest/daily-accrual
Run daily interest accrual for all accounts.

### POST /admin/interest/monthly-posting
Post monthly interest to accounts.

## Product Management (9 endpoints)

### POST /products
Create a new banking product.

**Request:**
```json
{
  "name": "High Yield Savings",
  "description": "Premium savings with higher rate",
  "product_type": "savings",
  "currency": "USD",
  "product_code": "HYS001",
  "interest_rate": "0.035"
}
```

### GET /products
List all banking products.

### GET /products/{product_id}
Get product details.

### PUT /products/{product_id}
Update product configuration.

### POST /products/{product_id}/activate
Activate a product for new accounts.

### POST /products/{product_id}/suspend
Suspend a product (no new accounts).

### POST /products/{product_id}/retire
Retire a product permanently.

### GET /products/{product_id}/fees
Get product fee schedule.

### GET /products/{product_id}/interest-rate
Get current interest rate for product.

## Collections Management (12 endpoints)

### POST /collections/scan
Scan for delinquent accounts.

### GET /collections/cases
List active collection cases.

### GET /collections/cases/{case_id}
Get collection case details.

### PUT /collections/cases/{case_id}/assign
Assign case to collector.

### POST /collections/cases/{case_id}/actions
Record collection action.

### POST /collections/cases/{case_id}/promises
Record payment promise.

### POST /collections/promises/check
Check promise fulfillment.

### POST /collections/cases/{case_id}/resolve
Resolve collection case.

### GET /collections/summary
Get collections portfolio summary.

### GET /collections/recovery-rate
Calculate recovery statistics.

### POST /collections/auto-actions
Configure automated collection actions.

### POST /collections/strategies
Create collection strategy.

### GET /collections/strategies
List collection strategies.

## Compliance & Audit (3 endpoints)

### GET /audit/events
Query audit trail events.

**Query Parameters:**
- `entity_id`: Filter by entity
- `event_type`: Filter by event type
- `start_date`: From date
- `end_date`: To date
- `user_id`: Filter by user

### GET /audit/integrity
Verify audit trail integrity.

### GET /compliance/alerts
Get compliance alerts and violations.

## Reporting (13 endpoints)

### GET /reports/portfolio-summary
Portfolio overview and key metrics.

### GET /reports/loan-portfolio
Detailed loan portfolio analysis.

### GET /reports/deposit-portfolio
Deposit account portfolio summary.

### GET /reports/delinquency
Delinquency and collections report.

### GET /reports/income-statement
Income statement for specified period.

### GET /reports/transaction-volume
Transaction volume analytics.

### GET /reports/product-performance
Product performance metrics.

### GET /reports/customer-segments
Customer segmentation analysis.

### GET /reports/collection-performance
Collections performance metrics.

### POST /reports/definitions
Create custom report definition.

### GET /reports/definitions
List report definitions.

### POST /reports/definitions/{report_id}/run
Execute custom report.

### GET /reports/definitions/{report_id}/export
Export report results.

## Workflow Management (16 endpoints)

### POST /workflows/definitions
Create workflow definition.

**Request:**
```json
{
  "name": "Loan Approval Workflow",
  "description": "Multi-step loan approval process",
  "trigger": "loan_application",
  "steps": [
    {
      "name": "Credit Check",
      "type": "approval",
      "required_role": "underwriter",
      "sla_hours": 24
    },
    {
      "name": "Manager Approval", 
      "type": "approval",
      "required_role": "manager",
      "sla_hours": 48,
      "conditions": [
        {"field": "amount", "operator": ">", "value": 10000}
      ]
    }
  ]
}
```

### GET /workflows/definitions
List workflow definitions.

### GET /workflows/definitions/{definition_id}
Get workflow definition details.

### POST /workflows/definitions/{definition_id}/activate
Activate workflow definition.

### POST /workflows/definitions/{definition_id}/deactivate
Deactivate workflow definition.

### POST /workflows
Start new workflow instance.

### GET /workflows
List workflow instances.

### GET /workflows/{instance_id}
Get workflow instance status.

### GET /workflows/pending-tasks
Get pending approval tasks.

### POST /workflows/{instance_id}/steps/{step_number}/approve
Approve workflow step.

### POST /workflows/{instance_id}/steps/{step_number}/reject
Reject workflow step.

### POST /workflows/{instance_id}/steps/{step_number}/skip
Skip workflow step (if allowed).

### POST /workflows/{instance_id}/steps/{step_number}/assign
Assign step to specific user.

### POST /workflows/{instance_id}/cancel
Cancel workflow instance.

### POST /workflows/check-sla
Check SLA violations across workflows.

### GET /workflows/history/{entity_type}/{entity_id}
Get workflow history for entity.

## RBAC (Role-Based Access Control) (20 endpoints)

### POST /rbac/roles
Create new role.

### GET /rbac/roles
List all roles.

### GET /rbac/roles/{role_id}
Get role details and permissions.

### PUT /rbac/roles/{role_id}
Update role configuration.

### DELETE /rbac/roles/{role_id}
Delete role.

### POST /rbac/users
Create new user.

### GET /rbac/users
List all users.

### GET /rbac/users/{user_id}
Get user details.

### PUT /rbac/users/{user_id}
Update user information.

### POST /rbac/users/{user_id}/activate
Activate user account.

### POST /rbac/users/{user_id}/deactivate
Deactivate user account.

### POST /rbac/users/{user_id}/lock
Lock user account (security).

### POST /rbac/users/{user_id}/unlock
Unlock user account.

### POST /rbac/users/{user_id}/roles/{role_id}
Assign role to user.

### DELETE /rbac/users/{user_id}/roles/{role_id}
Remove role from user.

### GET /rbac/users/{user_id}/permissions
Get effective permissions for user.

### POST /rbac/auth/login
User authentication.

### POST /rbac/auth/logout
End user session.

### POST /rbac/auth/change-password
Change user password.

### GET /rbac/auth/session/{session_id}
Validate session token.

## Custom Fields (14 endpoints)

### POST /custom-fields/definitions
Create custom field definition.

**Request:**
```json
{
  "name": "risk_score",
  "display_name": "Risk Score",
  "entity_type": "customer",
  "data_type": "integer",
  "required": false,
  "validation_rules": {
    "min_value": 1,
    "max_value": 10
  }
}
```

### GET /custom-fields/definitions
List custom field definitions.

### GET /custom-fields/definitions/{field_id}
Get field definition details.

### PUT /custom-fields/definitions/{field_id}
Update field definition.

### DELETE /custom-fields/definitions/{field_id}
Delete field definition.

### POST /custom-fields/definitions/{field_id}/activate
Activate field definition.

### POST /custom-fields/definitions/{field_id}/deactivate
Deactivate field definition.

### POST /custom-fields/values/{entity_type}/{entity_id}
Set custom field value for entity.

### GET /custom-fields/values/{entity_type}/{entity_id}
Get all custom field values for entity.

### GET /custom-fields/values/{entity_type}/{entity_id}/{field_name}
Get specific custom field value.

### DELETE /custom-fields/values/{entity_type}/{entity_id}/{field_name}
Delete custom field value.

### POST /custom-fields/values/{entity_type}/{entity_id}/bulk
Set multiple custom field values.

### GET /custom-fields/search/{entity_type}
Search entities by custom field values.

### GET /custom-fields/export/{entity_type}
Export entities with custom fields.

### POST /custom-fields/validate/{entity_type}/{entity_id}
Validate custom field values for entity.

## Error Responses

All endpoints return standardized error responses:

```json
{
  "detail": "Human-readable error message",
  "error_code": "MACHINE_READABLE_CODE",
  "timestamp": "2026-02-19T15:40:00.000000"
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `ACCOUNT_NOT_FOUND` | 404 | Account ID does not exist |
| `CUSTOMER_NOT_FOUND` | 404 | Customer ID does not exist |
| `INSUFFICIENT_FUNDS` | 400 | Account balance too low |
| `COMPLIANCE_VIOLATION` | 400 | Transaction violates compliance rules |
| `INVALID_AMOUNT` | 400 | Amount must be positive |
| `CURRENCY_MISMATCH` | 400 | Currency doesn't match account |
| `KYC_REQUIRED` | 403 | Customer needs KYC verification |
| `AUTHENTICATION_REQUIRED` | 401 | Valid authentication required |
| `INSUFFICIENT_PERMISSIONS` | 403 | User lacks required permissions |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |

## Rate Limiting

API endpoints are rate-limited to prevent abuse:

- **Default**: 1000 requests per hour per IP
- **Authentication endpoints**: 10 requests per minute
- **Transaction endpoints**: 100 requests per minute per account

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640995200
```

## Kafka Event Streaming (6 endpoints)

### GET /kafka/status
Get Kafka integration status and health.

**Response (200):**
```json
{
  "enabled": true,
  "connected": true,
  "bootstrap_servers": "localhost:9092",
  "producer_status": "healthy",
  "consumer_status": "healthy",
  "topics": {
    "nexum.transactions.created": {"partitions": 3, "replicas": 1},
    "nexum.accounts.created": {"partitions": 3, "replicas": 1},
    "nexum.customers.updated": {"partitions": 3, "replicas": 1},
    "nexum.loans.originated": {"partitions": 3, "replicas": 1}
  }
}
```

### GET /kafka/events
List recent events published to Kafka.

**Query Parameters:**
- `topic`: Filter by topic name (optional)
- `limit`: Maximum events to return (default: 50)
- `since`: ISO timestamp to filter events after (optional)

**Response (200):**
```json
{
  "events": [
    {
      "id": "evt_abc123",
      "topic": "nexum.transactions.created",
      "timestamp": "2026-02-19T15:32:00.000000Z",
      "event_type": "TransactionCreated", 
      "data": {
        "transaction_id": "txn_def456",
        "account_id": "acc_xyz789",
        "amount": "1000.00",
        "currency": "USD"
      }
    }
  ],
  "total": 1,
  "has_more": false
}
```

### POST /kafka/events/replay
Replay events to Kafka (admin only).

**Request:**
```json
{
  "event_ids": ["evt_abc123", "evt_def456"],
  "target_topic": "nexum.events.replay"
}
```

### GET /kafka/consumers
List active consumer groups and their status.

### POST /kafka/consumers/{group}/reset
Reset consumer group offset (admin only).

### DELETE /kafka/events/{event_id}
Delete a specific event from the event store (admin only).

## Advanced Features

### Idempotency 

All mutation endpoints support idempotency keys to prevent duplicate operations:

**Header:**
```
Idempotency-Key: unique-operation-key-123
```

If the same idempotency key is used within 24 hours, the original response is returned instead of processing a new operation.

## Pagination

List endpoints support pagination:

**Query Parameters:**
- `limit`: Items per page (default: 50, max: 1000)
- `offset`: Skip items (default: 0)

**Response:**
```json
{
  "items": [...],
  "total": 1234,
  "limit": 50,
  "offset": 0,
  "has_more": true
}
```

## Webhooks

Configure webhooks to receive real-time notifications:

### Supported Events
- `transaction.completed`
- `account.created`
- `loan.disbursed`
- `payment.missed`
- `compliance.alert`

### Webhook Payload
```json
{
  "event": "transaction.completed",
  "data": {
    "transaction_id": "txn_abc123",
    "account_id": "acc_def456",
    "amount": {
      "amount": "100.00",
      "currency": "USD"
    }
  },
  "timestamp": "2026-02-19T15:32:00.000000"
}
```

## Notification Engine Endpoints (10 endpoints)

### POST /notifications/send
Send a notification to a recipient via specified channels.

**Request:**
```json
{
  "notification_type": "transaction_alert",
  "recipient_id": "cust_123",
  "data": {
    "customer_name": "John Doe",
    "amount": "$500.00",
    "transaction_type": "withdrawal",
    "account_name": "Checking Account",
    "timestamp": "2026-02-19T15:32:00.000000",
    "reference": "txn_abc123"
  },
  "channels": ["email", "sms"],
  "priority": "medium"
}
```

**Response (200):**
```json
{
  "notification_ids": ["notif_abc123", "notif_def456"],
  "sent_count": 2,
  "failed_count": 0
}
```

### POST /notifications/bulk
Send notifications to multiple recipients.

**Request:**
```json
{
  "notification_type": "payment_due",
  "recipient_ids": ["cust_123", "cust_456"],
  "data": {
    "amount": "$1,200.00",
    "due_date": "2026-03-01",
    "loan_type": "Personal Loan"
  },
  "channels": ["email"]
}
```

### GET /notifications/templates
List all notification templates.

**Response (200):**
```json
{
  "templates": [
    {
      "id": "transaction_alert_email",
      "name": "Transaction Alert - Email",
      "notification_type": "transaction_alert",
      "channel": "email",
      "subject_template": "Transaction Alert: {amount} {transaction_type}",
      "body_template": "Dear {customer_name}...",
      "is_active": true
    }
  ]
}
```

### POST /notifications/templates
Create a new notification template.

**Request:**
```json
{
  "name": "Loan Approval - SMS",
  "notification_type": "loan_approved", 
  "channel": "sms",
  "subject_template": "Loan Approved!",
  "body_template": "Congratulations! Your {loan_type} for {amount} has been approved."
}
```

### GET /notifications/{recipient_id}
Get notifications for a specific recipient.

**Query Parameters:**
- `status`: Filter by notification status (sent, pending, failed, read)
- `limit`: Maximum notifications to return (default: 50)

**Response (200):**
```json
{
  "notifications": [
    {
      "id": "notif_abc123",
      "notification_type": "transaction_alert",
      "channel": "email",
      "priority": "medium",
      "subject": "Transaction Alert: $500.00 withdrawal",
      "status": "sent",
      "sent_at": "2026-02-19T15:32:00.000000"
    }
  ],
  "unread_count": 3
}
```

### PUT /notifications/{notification_id}/read
Mark a notification as read.

**Response (200):**
```json
{
  "message": "Notification marked as read",
  "read_at": "2026-02-19T15:35:00.000000"
}
```

### GET /notifications/{recipient_id}/preferences
Get notification preferences for a recipient.

### PUT /notifications/{recipient_id}/preferences
Update notification preferences for a recipient.

**Request:**
```json
{
  "channel_preferences": {
    "transaction_alert": ["email", "in_app"],
    "payment_due": ["sms", "email"]
  },
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00",
  "do_not_disturb": false
}
```

### POST /notifications/retry
Retry failed notifications.

**Request:**
```json
{
  "max_retries": 3
}
```

### GET /notifications/stats
Get notification delivery statistics.

**Response (200):**
```json
{
  "total_notifications": 1250,
  "delivery_rate": 0.97,
  "by_status": {
    "sent": 1213,
    "failed": 25,
    "pending": 12
  },
  "by_channel": {
    "email": 750,
    "sms": 300,
    "in_app": 200
  }
}
```

## Multi-Tenancy Endpoints (8 endpoints)

### POST /tenants
Create a new tenant.

**Request:**
```json
{
  "name": "ACME Bank",
  "code": "ACME_BANK",
  "display_name": "ACME Bank",
  "description": "Leading community bank",
  "subscription_tier": "professional",
  "contact_email": "admin@acmebank.com",
  "max_users": 100,
  "max_accounts": 10000,
  "primary_color": "#1976D2"
}
```

**Response (201):**
```json
{
  "id": "tenant_abc123",
  "name": "ACME Bank",
  "code": "ACME_BANK",
  "display_name": "ACME Bank",
  "is_active": true,
  "created_at": "2026-02-19T15:32:00.000000"
}
```

### GET /tenants
List all tenants (super-admin only).

**Query Parameters:**
- `is_active`: Filter by active status
- `subscription_tier`: Filter by subscription tier

**Response (200):**
```json
{
  "tenants": [
    {
      "id": "tenant_abc123",
      "name": "ACME Bank",
      "code": "ACME_BANK",
      "subscription_tier": "professional",
      "is_active": true,
      "user_count": 25,
      "account_count": 1500
    }
  ]
}
```

### GET /tenants/{tenant_id}
Get tenant details.

### PUT /tenants/{tenant_id}
Update tenant configuration.

### POST /tenants/{tenant_id}/activate
Activate a tenant.

### POST /tenants/{tenant_id}/deactivate
Deactivate a tenant.

### GET /tenants/{tenant_id}/stats
Get tenant usage statistics.

**Response (200):**
```json
{
  "tenant_id": "tenant_abc123",
  "user_count": 25,
  "account_count": 1500,
  "transaction_count": 50000,
  "total_balance": "15750000.00",
  "last_activity": "2026-02-19T15:30:00.000000"
}
```

### GET /tenants/usage-report
Get usage report for all tenants (super-admin only).

**Headers:** `X-Tenant-ID: tenant_abc123` (for tenant-specific requests)

## Encryption Management Endpoints (3 endpoints)

### GET /encryption/status
Get encryption status and configuration.

**Response (200):**
```json
{
  "encryption_enabled": true,
  "provider": "aesgcm",
  "encrypted_tables": ["customers", "accounts"],
  "pii_fields": {
    "customers": ["first_name", "last_name", "email", "phone", "address"],
    "accounts": ["account_number"]
  },
  "encryption_stats": {
    "encrypt_count": 15230,
    "decrypt_count": 45670
  }
}
```

### POST /encryption/rotate-keys
Rotate encryption keys (super-admin only).

**Request:**
```json
{
  "new_master_key": "new-256-bit-master-key",
  "provider": "aesgcm",
  "dry_run": false
}
```

**Response (200):**
```json
{
  "message": "Key rotation completed successfully",
  "stats": {
    "rotated_records": 1500,
    "rotated_fields": 7500,
    "errors": 0
  },
  "duration_seconds": 45.2
}
```

### GET /encryption/health
Health check for encryption system.

**Response (200):**
```json
{
  "status": "healthy",
  "provider_available": true,
  "key_accessible": true,
  "last_operation": "2026-02-19T15:30:00.000000"
}
```