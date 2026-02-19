# Notification Engine Module

The Notification Engine provides comprehensive multi-channel notification capabilities for banking events, including transaction alerts, payment reminders, loan notifications, workflow updates, and compliance alerts.

## Overview

The notification system supports multiple delivery channels (Email, SMS, Push, Webhook, In-App), template management, user preferences, quiet hours, and delivery tracking. It integrates with the event system to automatically send notifications based on domain events.

## Key Classes

### NotificationChannel (Enum)

Available notification delivery channels:

- `EMAIL` - Email notifications via SMTP
- `SMS` - SMS notifications via Twilio
- `PUSH` - Push notifications via Firebase
- `WEBHOOK` - HTTP webhook calls
- `IN_APP` - In-application notifications

### NotificationPriority (Enum)

Priority levels affecting delivery behavior:

- `LOW` - Best effort delivery, respects quiet hours
- `MEDIUM` - Standard delivery, respects quiet hours  
- `HIGH` - Priority delivery, limited quiet hour respect
- `CRITICAL` - Immediate delivery, ignores quiet hours

### NotificationType (Enum)

Types of notifications supported:

**Transaction Notifications:**
- `TRANSACTION_ALERT` - General transaction notifications
- `LARGE_TRANSACTION` - High-value transaction alerts
- `SUSPICIOUS_ACTIVITY` - Fraud detection alerts

**Payment Notifications:**
- `PAYMENT_DUE` - Payment due reminders
- `PAYMENT_OVERDUE` - Overdue payment notices
- `PAYMENT_RECEIVED` - Payment confirmations

**Loan Notifications:**
- `LOAN_APPROVED` - Loan approval notifications
- `LOAN_DISBURSED` - Loan disbursement confirmations
- `LOAN_PAYMENT_DUE` - Loan payment reminders

**Account Notifications:**
- `ACCOUNT_OPENED` - New account confirmations
- `ACCOUNT_FROZEN` - Account frozen alerts
- `KYC_REQUIRED` - KYC documentation requests

**Workflow Notifications:**
- `WORKFLOW_PENDING` - Approval requests
- `WORKFLOW_APPROVED` - Approval confirmations
- `WORKFLOW_REJECTED` - Rejection notifications

**Collection Notifications:**
- `COLLECTION_NOTICE` - Collection notices
- `COLLECTION_ESCALATION` - Escalation warnings

**System Notifications:**
- `SYSTEM_ALERT` - System-wide alerts
- `MAINTENANCE_NOTICE` - Maintenance notifications

**Security Notifications:**
- `OTP_VERIFICATION` - One-time password delivery
- `PASSWORD_RESET` - Password reset links

### NotificationStatus (Enum)

Tracking states for notifications:

- `PENDING` - Queued for delivery
- `SENT` - Successfully sent to provider
- `DELIVERED` - Confirmed delivered to recipient
- `FAILED` - Delivery failed
- `READ` - Read by recipient (for trackable channels)

### NotificationTemplate

Template for generating notifications:

```python
@dataclass
class NotificationTemplate(StorageRecord):
    name: str                              # Human-readable template name
    notification_type: NotificationType    # Type of notification
    channel: NotificationChannel          # Delivery channel
    subject_template: str                  # Subject with {placeholders}
    body_template: str                     # Body with {placeholders}  
    is_active: bool = True                # Whether template is enabled
```

**Template Placeholders:**
Templates support variable substitution using `{placeholder}` syntax:
- `{customer_name}` - Customer full name
- `{amount}` - Formatted monetary amount
- `{account_name}` - Account display name
- `{transaction_type}` - Type of transaction
- `{due_date}` - Formatted due date
- `{reference}` - Transaction/loan reference number

### Notification

Individual notification instance:

```python
@dataclass
class Notification(StorageRecord):
    notification_type: NotificationType
    channel: NotificationChannel  
    priority: NotificationPriority
    recipient_id: str              # Customer/user ID
    recipient_address: str         # Email/phone/webhook URL
    subject: str                   # Rendered subject
    body: str                     # Rendered body
    status: NotificationStatus = NotificationStatus.PENDING
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    failed_reason: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### NotificationPreference

Customer notification preferences:

```python
@dataclass
class NotificationPreference(StorageRecord):
    customer_id: str
    channel_preferences: Dict[NotificationType, List[NotificationChannel]]
    quiet_hours_start: Optional[time] = None  # e.g., 22:00
    quiet_hours_end: Optional[time] = None    # e.g., 08:00
    do_not_disturb: bool = False
```

## Channel Providers

### ChannelProvider (Abstract)

Base class for notification delivery providers:

```python
class ChannelProvider(ABC):
    @abstractmethod
    async def send(self, notification: Notification) -> bool:
        """Send notification via this channel. Returns True if successful."""
```

### Built-in Providers

#### LogChannelProvider
Simple logging provider for development:
```python
provider = LogChannelProvider(logger)
```

#### WebhookChannelProvider  
HTTP webhook delivery:
```python
provider = WebhookChannelProvider(timeout=30)
```

#### InAppChannelProvider
In-application notifications via storage:
```python
provider = InAppChannelProvider(storage)
```

#### EmailChannelProvider
Email delivery via SMTP:
```python
provider = EmailChannelProvider(smtp_config)
```

#### SMSChannelProvider
SMS delivery via Twilio:
```python
provider = SMSChannelProvider(twilio_config)
```

## NotificationEngine

Main engine for managing templates and sending notifications:

```python
class NotificationEngine:
    def __init__(self, storage: StorageInterface, audit_manager: Optional[AuditTrail] = None):
        # Initialize with storage and optional audit manager
        
    def register_provider(self, channel: NotificationChannel, provider: ChannelProvider):
        """Register custom channel provider"""
```

### Template Management

```python
# Create notification template
template_id = engine.create_template(NotificationTemplate(
    name="Transaction Alert - Email",
    notification_type=NotificationType.TRANSACTION_ALERT,
    channel=NotificationChannel.EMAIL,
    subject_template="Transaction Alert: {amount} {transaction_type}",
    body_template="Dear {customer_name}, a {transaction_type} of {amount} was processed..."
))

# Get template
template = engine.get_template(template_id)

# List all templates
templates = engine.list_templates()
```

### Sending Notifications

```python
# Send single notification
notification_ids = await engine.send_notification(
    notification_type=NotificationType.TRANSACTION_ALERT,
    recipient_id="cust_123", 
    data={
        "customer_name": "John Doe",
        "amount": "$500.00", 
        "transaction_type": "withdrawal",
        "account_name": "Checking Account",
        "reference": "txn_abc123"
    },
    channels=[NotificationChannel.EMAIL, NotificationChannel.SMS],
    priority=NotificationPriority.HIGH
)

# Send bulk notifications
results = await engine.send_bulk(
    notification_type=NotificationType.PAYMENT_DUE,
    recipient_ids=["cust_123", "cust_456", "cust_789"],
    data={
        "amount": "$1,200.00",
        "due_date": "March 1, 2026",
        "loan_type": "Personal Loan"
    }
)
```

### Notification Management

```python
# Get notifications for recipient
notifications = engine.get_notifications(
    recipient_id="cust_123",
    status=NotificationStatus.SENT,
    limit=50
)

# Mark notification as read
success = engine.mark_as_read("notif_abc123")

# Get unread count
unread_count = engine.get_unread_count("cust_123")

# Retry failed notifications  
stats = await engine.retry_failed(max_retries=3)
# Returns: {"attempted": 10, "succeeded": 8, "failed": 2}
```

### Preferences Management

```python
# Set customer preferences
preferences = NotificationPreference(
    customer_id="cust_123",
    channel_preferences={
        NotificationType.TRANSACTION_ALERT: [NotificationChannel.EMAIL, NotificationChannel.IN_APP],
        NotificationType.PAYMENT_DUE: [NotificationChannel.SMS, NotificationChannel.EMAIL]
    },
    quiet_hours_start=time(22, 0),  # 10:00 PM
    quiet_hours_end=time(8, 0),     # 8:00 AM
    do_not_disturb=False
)

engine.set_preferences("cust_123", preferences)

# Get customer preferences
preferences = engine.get_preferences("cust_123")
```

### Statistics and Monitoring

```python
# Get delivery statistics
stats = engine.get_delivery_stats()
# Returns:
# {
#   "total_notifications": 1250,
#   "delivery_rate": 0.97,
#   "by_status": {"sent": 1213, "failed": 25, "pending": 12},
#   "by_channel": {"email": 750, "sms": 300, "in_app": 200},
#   "by_type": {"transaction_alert": 500, "payment_due": 300, ...}
# }
```

## Usage Examples

### Basic Setup

```python
from core_banking.notifications import (
    NotificationEngine, NotificationChannel, NotificationType,
    EmailChannelProvider, SMSChannelProvider
)

# Initialize engine
engine = NotificationEngine(storage, audit_manager)

# Register providers
engine.register_provider(NotificationChannel.EMAIL, EmailChannelProvider(smtp_config))
engine.register_provider(NotificationChannel.SMS, SMSChannelProvider(twilio_config))
```

### Transaction Alert Integration

```python
from core_banking.events import get_global_dispatcher, DomainEvent

async def send_transaction_alerts(event: EventPayload):
    """Send alerts for new transactions"""
    if event.event_type == DomainEvent.TRANSACTION_CREATED:
        amount = Decimal(event.data.get('amount', '0'))
        
        # Determine notification type based on amount
        if amount > Decimal('10000.00'):
            notification_type = NotificationType.LARGE_TRANSACTION
            priority = NotificationPriority.HIGH
        elif event.data.get('risk_score', 0) > 80:
            notification_type = NotificationType.SUSPICIOUS_ACTIVITY
            priority = NotificationPriority.CRITICAL
        else:
            notification_type = NotificationType.TRANSACTION_ALERT
            priority = NotificationPriority.MEDIUM
        
        # Send notification
        await notification_engine.send_notification(
            notification_type=notification_type,
            recipient_id=event.data.get('customer_id'),
            data={
                "customer_name": event.data.get('customer_name'),
                "amount": f"${amount:,.2f}",
                "transaction_type": event.data.get('transaction_type'),
                "account_name": event.data.get('account_name'),
                "timestamp": event.timestamp.strftime('%B %d, %Y at %I:%M %p'),
                "reference": event.entity_id
            },
            priority=priority
        )

# Subscribe to transaction events
dispatcher = get_global_dispatcher()
dispatcher.subscribe(DomainEvent.TRANSACTION_CREATED, send_transaction_alerts)
```

### Loan Payment Reminders

```python
import asyncio
from datetime import datetime, timedelta

async def send_payment_reminders():
    """Daily job to send loan payment reminders"""
    # Get loans with payments due in next 3 days
    upcoming_payments = loan_manager.get_upcoming_payments(days=3)
    
    for payment in upcoming_payments:
        days_until_due = (payment.due_date - datetime.now().date()).days
        
        if days_until_due == 0:
            notification_type = NotificationType.PAYMENT_DUE
            priority = NotificationPriority.HIGH
        elif days_until_due <= 1:
            notification_type = NotificationType.PAYMENT_DUE  
            priority = NotificationPriority.MEDIUM
        else:
            continue  # Don't send too early
        
        await notification_engine.send_notification(
            notification_type=notification_type,
            recipient_id=payment.customer_id,
            data={
                "customer_name": payment.customer_name,
                "amount": f"${payment.amount:,.2f}",
                "due_date": payment.due_date.strftime('%B %d, %Y'),
                "loan_type": payment.loan_type,
                "phone": "1-800-BANK-123"
            },
            priority=priority
        )

# Schedule daily reminders
async def schedule_reminders():
    while True:
        await send_payment_reminders()
        await asyncio.sleep(24 * 3600)  # Wait 24 hours
```

### Custom Channel Provider

```python
from core_banking.notifications import ChannelProvider

class SlackChannelProvider(ChannelProvider):
    """Custom Slack notification provider"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send(self, notification: Notification) -> bool:
        """Send notification to Slack channel"""
        try:
            payload = {
                "text": notification.subject,
                "attachments": [{
                    "color": "warning" if notification.priority.value == "high" else "good",
                    "fields": [{
                        "title": "Details",
                        "value": notification.body[:500],
                        "short": False
                    }]
                }]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
            return False

# Register custom provider
engine.register_provider(NotificationChannel.WEBHOOK, SlackChannelProvider(slack_webhook_url))
```

## Configuration

Configure notification providers via environment variables:

### Email (SMTP)

```bash
export NEXUM_SMTP_HOST="smtp.gmail.com"
export NEXUM_SMTP_PORT="587" 
export NEXUM_SMTP_USERNAME="notifications@company.com"
export NEXUM_SMTP_PASSWORD="app-specific-password"
export NEXUM_SMTP_USE_TLS="true"
export NEXUM_SMTP_FROM_ADDRESS="Nexum Banking <notifications@company.com>"
```

### SMS (Twilio)

```bash
export NEXUM_TWILIO_ACCOUNT_SID="your-twilio-account-sid"
export NEXUM_TWILIO_AUTH_TOKEN="your-twilio-auth-token" 
export NEXUM_TWILIO_FROM_NUMBER="+1234567890"
```

### Push Notifications (Firebase)

```bash
export NEXUM_FIREBASE_SERVER_KEY="your-firebase-server-key"
export NEXUM_FIREBASE_PROJECT_ID="your-project-id"
```

### General Settings

```bash
export NEXUM_NOTIFICATIONS_ENABLED="true"
export NEXUM_NOTIFICATIONS_DEFAULT_TIMEZONE="America/New_York"
export NEXUM_NOTIFICATIONS_RATE_LIMIT="100"  # per minute per customer
export NEXUM_NOTIFICATIONS_RETRY_DELAY="300" # seconds between retries
```

## Template Examples

### Transaction Alert Email

```
Subject: Transaction Alert: {amount} {transaction_type}

Dear {customer_name},

A {transaction_type} of {amount} has been processed on your account {account_name} at {timestamp}.

Transaction Details:
- Amount: {amount}
- Type: {transaction_type}
- Account: {account_name}
- Reference: {reference}

If you did not authorize this transaction, please contact us immediately at 1-800-BANK-123.

Best regards,
Nexum Banking Team
```

### Payment Due SMS

```
Subject: Payment Due

Payment due: {amount} for {loan_type}. Due date: {due_date}. Pay via mobile app or call {phone}. Reply STOP to opt out.
```

### Loan Approval Email

```
Subject: Congratulations! Your {loan_type} has been approved

Dear {customer_name},

Great news! Your {loan_type} application has been approved.

Loan Details:
- Amount: {amount}
- Interest Rate: {interest_rate}%
- Term: {term} months  
- Monthly Payment: {monthly_payment}
- First Payment Due: {first_payment_date}

Funds will be disbursed to your account within 1-2 business days.

Reference: {reference}

Thank you for choosing Nexum Banking!
```

## Best Practices

### Template Design
- Keep subject lines concise and descriptive
- Include essential information in the first paragraph
- Use consistent formatting and branding
- Test templates with various data combinations
- Provide clear next steps or contact information

### Channel Selection
- Use SMS for time-sensitive alerts
- Use email for detailed information
- Use in-app for non-urgent updates
- Use webhooks for system-to-system communication
- Respect customer preferences

### Performance
- Process notifications asynchronously
- Use bulk operations when possible
- Monitor delivery rates and failures
- Implement circuit breakers for external providers
- Cache templates and preferences

### Privacy and Compliance
- Don't include sensitive data in templates
- Respect opt-out preferences
- Honor quiet hours and do-not-disturb
- Maintain delivery audit trails
- Comply with CAN-SPAM and GDPR

### Error Handling
- Implement retry logic with exponential backoff
- Log failures with sufficient detail
- Provide fallback channels
- Monitor provider health
- Alert on sustained failures

## Integration Points

### Event System
Automatically triggered by domain events from the event dispatcher.

### Workflow Engine  
Sends notifications for approval requests, completions, and rejections.

### Collections Module
Generates collection notices and escalation warnings.

### Customer Portal
Displays in-app notifications and manages preferences.

### External Systems
Webhooks enable integration with CRM, helpdesk, and other systems.

## Testing

```python
# Test notification sending
async def test_transaction_alert():
    # Create test notification engine with mock providers
    mock_provider = MockChannelProvider()
    engine = NotificationEngine(test_storage)
    engine.register_provider(NotificationChannel.EMAIL, mock_provider)
    
    # Send test notification
    notification_ids = await engine.send_notification(
        notification_type=NotificationType.TRANSACTION_ALERT,
        recipient_id="test_customer",
        data={"amount": "$100.00", "customer_name": "Test User"}
    )
    
    # Verify notification was sent
    assert len(notification_ids) == 1
    assert mock_provider.last_notification.subject == "Transaction Alert: $100.00"

# Mock provider for testing
class MockChannelProvider(ChannelProvider):
    def __init__(self):
        self.last_notification = None
        self.should_fail = False
    
    async def send(self, notification: Notification) -> bool:
        self.last_notification = notification
        return not self.should_fail
```

## Future Enhancements

- Rich content support (HTML emails, formatted SMS)
- Notification scheduling and delayed delivery
- A/B testing for notification templates
- Analytics and engagement tracking
- Multi-language template support
- Push notification targeting by device/platform
- Integration with marketing automation platforms