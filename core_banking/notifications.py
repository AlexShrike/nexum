"""
Notification Engine Module

Handles sending alerts via multiple channels for banking events including transaction alerts,
payment reminders, loan notifications, workflow updates, and compliance alerts.
"""

from decimal import Decimal
from datetime import datetime, timezone, time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import json
import requests
from abc import ABC, abstractmethod

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType


class NotificationChannel(Enum):
    """Available notification channels"""
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


class NotificationPriority(Enum):
    """Notification priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationType(Enum):
    """Types of notifications"""
    # Transaction notifications
    TRANSACTION_ALERT = "transaction_alert"
    LARGE_TRANSACTION = "large_transaction"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    
    # Payment notifications  
    PAYMENT_DUE = "payment_due"
    PAYMENT_OVERDUE = "payment_overdue"
    PAYMENT_RECEIVED = "payment_received"
    
    # Loan notifications
    LOAN_APPROVED = "loan_approved"
    LOAN_DISBURSED = "loan_disbursed"
    LOAN_PAYMENT_DUE = "loan_payment_due"
    
    # Account notifications
    ACCOUNT_OPENED = "account_opened"
    ACCOUNT_FROZEN = "account_frozen"
    KYC_REQUIRED = "kyc_required"
    
    # Workflow notifications
    WORKFLOW_PENDING = "workflow_pending"
    WORKFLOW_APPROVED = "workflow_approved"
    WORKFLOW_REJECTED = "workflow_rejected"
    
    # Collection notifications
    COLLECTION_NOTICE = "collection_notice"
    COLLECTION_ESCALATION = "collection_escalation"
    
    # System notifications
    SYSTEM_ALERT = "system_alert"
    MAINTENANCE_NOTICE = "maintenance_notice"
    
    # Security notifications
    OTP_VERIFICATION = "otp_verification"
    PASSWORD_RESET = "password_reset"


class NotificationStatus(Enum):
    """Status of notifications"""
    PENDING = "pending"
    SENT = "sent" 
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"


@dataclass
class NotificationTemplate(StorageRecord):
    """Template for notifications"""
    name: str
    notification_type: NotificationType
    channel: NotificationChannel
    subject_template: str  # Template with {placeholders}
    body_template: str     # Template with {placeholders}
    is_active: bool = True


@dataclass  
class Notification(StorageRecord):
    """Individual notification instance"""
    notification_type: NotificationType
    channel: NotificationChannel
    priority: NotificationPriority
    recipient_id: str  # Customer/user ID
    recipient_address: str  # Email/phone/webhook URL
    subject: str
    body: str
    status: NotificationStatus = NotificationStatus.PENDING
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    failed_reason: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationPreference(StorageRecord):
    """Customer notification preferences"""
    customer_id: str
    channel_preferences: Dict[NotificationType, List[NotificationChannel]] = field(default_factory=dict)
    quiet_hours_start: Optional[time] = None  # e.g., 22:00
    quiet_hours_end: Optional[time] = None    # e.g., 08:00  
    do_not_disturb: bool = False


class ChannelProvider(ABC):
    """Abstract base class for notification channel providers"""
    
    @abstractmethod
    async def send(self, notification: Notification) -> bool:
        """Send notification via this channel. Returns True if successful."""
        pass


class LogChannelProvider(ChannelProvider):
    """Simple logging channel provider for development"""
    
    def __init__(self, logger=None):
        self.logger = logger
    
    async def send(self, notification: Notification) -> bool:
        """Log the notification instead of actually sending"""
        message = (
            f"📧 {notification.channel.value.upper()} to {notification.recipient_address}: "
            f"{notification.subject} | {notification.body[:100]}..."
        )
        
        if self.logger:
            self.logger.info(message)
        else:
            print(f"[NOTIFICATION] {message}")
        
        return True


class WebhookChannelProvider(ChannelProvider):
    """Webhook channel provider for external integrations"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    async def send(self, notification: Notification) -> bool:
        """Send notification via webhook POST"""
        try:
            payload = {
                "notification_id": notification.id,
                "type": notification.notification_type.value,
                "priority": notification.priority.value,
                "recipient_id": notification.recipient_id,
                "subject": notification.subject,
                "body": notification.body,
                "timestamp": notification.created_at.isoformat(),
                "metadata": notification.metadata
            }
            
            response = requests.post(
                notification.recipient_address,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            return response.status_code == 200
        except Exception as e:
            print(f"Webhook send failed: {e}")
            return False


class InAppChannelProvider(ChannelProvider):
    """In-app notification provider using storage"""
    
    def __init__(self, storage: StorageInterface):
        self.storage = storage
        self.table = "in_app_notifications"
    
    async def send(self, notification: Notification) -> bool:
        """Store notification for in-app display"""
        try:
            in_app_data = {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "notification_id": notification.id,
                "recipient_id": notification.recipient_id,
                "type": notification.notification_type.value,
                "priority": notification.priority.value,
                "subject": notification.subject,
                "body": notification.body,
                "read": False,
                "metadata": notification.metadata
            }
            
            self.storage.save(self.table, in_app_data["id"], in_app_data)
            return True
        except Exception as e:
            print(f"In-app notification storage failed: {e}")
            return False


class EmailChannelProvider(ChannelProvider):
    """Email channel provider (placeholder - requires SMTP config)"""
    
    def __init__(self, smtp_config: Optional[Dict] = None):
        self.smtp_config = smtp_config
    
    async def send(self, notification: Notification) -> bool:
        """Send email notification (placeholder implementation)"""
        # TODO: Implement actual SMTP sending
        print(f"📧 EMAIL (placeholder) to {notification.recipient_address}: {notification.subject}")
        return True


class SMSChannelProvider(ChannelProvider):
    """SMS channel provider (placeholder - requires Twilio config)"""
    
    def __init__(self, twilio_config: Optional[Dict] = None):
        self.twilio_config = twilio_config
    
    async def send(self, notification: Notification) -> bool:
        """Send SMS notification (placeholder implementation)"""
        # TODO: Implement actual SMS sending via Twilio
        print(f"📱 SMS (placeholder) to {notification.recipient_address}: {notification.body}")
        return True


class NotificationEngine:
    """Main notification engine for managing templates and sending notifications"""
    
    def __init__(self, storage: StorageInterface, audit_manager: Optional[AuditTrail] = None):
        self.storage = storage
        self.audit = audit_manager or AuditTrail(storage)
        
        # Storage tables
        self.templates_table = "notification_templates"
        self.notifications_table = "notifications"
        self.preferences_table = "notification_preferences"
        
        # Channel providers
        self.providers: Dict[NotificationChannel, ChannelProvider] = {}
        
        # Initialize default providers
        self._initialize_default_providers()
        self._initialize_default_templates()
    
    def _initialize_default_providers(self):
        """Initialize default channel providers"""
        # Log provider (always available for development)
        self.providers[NotificationChannel.IN_APP] = InAppChannelProvider(self.storage)
        self.providers[NotificationChannel.WEBHOOK] = WebhookChannelProvider()
        self.providers[NotificationChannel.EMAIL] = EmailChannelProvider()
        self.providers[NotificationChannel.SMS] = SMSChannelProvider()
        
        # Set log provider as fallback
        log_provider = LogChannelProvider()
        for channel in NotificationChannel:
            if channel not in self.providers:
                self.providers[channel] = log_provider
    
    def _initialize_default_templates(self):
        """Initialize default notification templates"""
        default_templates = [
            NotificationTemplate(
                id="transaction_alert_email",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                name="Transaction Alert - Email",
                notification_type=NotificationType.TRANSACTION_ALERT,
                channel=NotificationChannel.EMAIL,
                subject_template="Transaction Alert: {amount} {transaction_type}",
                body_template="Dear {customer_name},\n\nA {transaction_type} of {amount} has been processed on your account {account_name} at {timestamp}.\n\nIf you did not authorize this transaction, please contact us immediately.\n\nReference: {reference}"
            ),
            NotificationTemplate(
                id="payment_due_sms",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                name="Payment Due - SMS",
                notification_type=NotificationType.PAYMENT_DUE,
                channel=NotificationChannel.SMS,
                subject_template="Payment Due",
                body_template="Payment due: {amount} for {loan_type}. Due date: {due_date}. Pay via mobile app or call {phone}."
            ),
            NotificationTemplate(
                id="loan_approved_email",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                name="Loan Approved - Email",
                notification_type=NotificationType.LOAN_APPROVED,
                channel=NotificationChannel.EMAIL,
                subject_template="Congratulations! Your {loan_type} has been approved",
                body_template="Dear {customer_name},\n\nGreat news! Your {loan_type} application has been approved.\n\nLoan Details:\n- Amount: {amount}\n- Interest Rate: {interest_rate}%\n- Term: {term} months\n- Monthly Payment: {monthly_payment}\n\nFunds will be disbursed within 1-2 business days.\n\nReference: {reference}"
            ),
            NotificationTemplate(
                id="suspicious_activity_webhook",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                name="Suspicious Activity - Webhook",
                notification_type=NotificationType.SUSPICIOUS_ACTIVITY,
                channel=NotificationChannel.WEBHOOK,
                subject_template="Suspicious Activity Alert",
                body_template="Suspicious activity detected: {description}. Customer: {customer_id}. Risk score: {risk_score}. Requires review."
            ),
            NotificationTemplate(
                id="workflow_pending_in_app",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                name="Workflow Pending - In-App",
                notification_type=NotificationType.WORKFLOW_PENDING,
                channel=NotificationChannel.IN_APP,
                subject_template="Action Required: {workflow_name}",
                body_template="A {workflow_name} workflow requires your approval. Entity: {entity_type} {entity_id}. Step: {step_name}."
            )
        ]
        
        # Only create templates that don't already exist
        for template in default_templates:
            existing = self.storage.load(self.templates_table, template.id)
            if not existing:
                template_dict = self._template_to_dict(template)
                self.storage.save(self.templates_table, template.id, template_dict)
    
    def register_provider(self, channel: NotificationChannel, provider: ChannelProvider):
        """Register a channel provider"""
        self.providers[channel] = provider
    
    # Template Management
    
    def create_template(self, template: NotificationTemplate) -> str:
        """Create a new notification template"""
        if not template.id:
            template.id = str(uuid.uuid4())
        
        now = datetime.now(timezone.utc)
        template.created_at = now
        template.updated_at = now
        
        template_dict = self._template_to_dict(template)
        self.storage.save(self.templates_table, template.id, template_dict)
        
        return template.id
    
    def get_template(self, template_id: str) -> Optional[NotificationTemplate]:
        """Get a notification template by ID"""
        template_dict = self.storage.load(self.templates_table, template_id)
        if template_dict:
            return self._template_from_dict(template_dict)
        return None
    
    def list_templates(self) -> List[NotificationTemplate]:
        """List all notification templates"""
        templates_data = self.storage.load_all(self.templates_table)
        templates = [self._template_from_dict(data) for data in templates_data]
        
        # Sort by notification type and channel
        templates.sort(key=lambda t: (t.notification_type.value, t.channel.value))
        return templates
    
    # Notification Sending
    
    async def send_notification(
        self,
        notification_type: NotificationType,
        recipient_id: str,
        data: Dict[str, Any],
        channels: Optional[List[NotificationChannel]] = None,
        priority: NotificationPriority = NotificationPriority.MEDIUM
    ) -> List[str]:
        """Send notification to recipient via specified channels"""
        sent_notifications = []
        
        # Get customer preferences
        preferences = self.get_preferences(recipient_id)
        
        # Determine channels to use
        if channels is None:
            # Use customer preferences or default channels
            if preferences and notification_type in preferences.channel_preferences:
                channels = preferences.channel_preferences[notification_type]
            else:
                # Default channels based on notification type
                channels = self._get_default_channels(notification_type)
        
        # Check quiet hours
        if self._is_quiet_hours(preferences):
            # Only send critical notifications during quiet hours
            if priority != NotificationPriority.CRITICAL:
                print(f"Skipping notification due to quiet hours: {notification_type.value}")
                return []
        
        # Send via each channel
        for channel in channels:
            notification_id = await self._send_via_channel(
                notification_type, channel, recipient_id, data, priority
            )
            if notification_id:
                sent_notifications.append(notification_id)
        
        return sent_notifications
    
    async def send_bulk(
        self,
        notification_type: NotificationType,
        recipient_ids: List[str],
        data: Dict[str, Any],
        channels: Optional[List[NotificationChannel]] = None
    ) -> Dict[str, List[str]]:
        """Send bulk notifications to multiple recipients"""
        results = {}
        
        for recipient_id in recipient_ids:
            try:
                sent_ids = await self.send_notification(
                    notification_type, recipient_id, data, channels
                )
                results[recipient_id] = sent_ids
            except Exception as e:
                print(f"Failed to send to {recipient_id}: {e}")
                results[recipient_id] = []
        
        return results
    
    async def _send_via_channel(
        self,
        notification_type: NotificationType,
        channel: NotificationChannel,
        recipient_id: str,
        data: Dict[str, Any],
        priority: NotificationPriority
    ) -> Optional[str]:
        """Send notification via specific channel"""
        # Find appropriate template
        template = self._find_template(notification_type, channel)
        if not template:
            print(f"No template found for {notification_type.value} via {channel.value}")
            return None
        
        # Render template
        try:
            subject = template.subject_template.format(**data)
            body = template.body_template.format(**data)
        except KeyError as e:
            print(f"Template rendering failed - missing key: {e}")
            return None
        
        # Get recipient address
        recipient_address = self._get_recipient_address(recipient_id, channel)
        if not recipient_address:
            print(f"No recipient address found for {recipient_id} via {channel.value}")
            return None
        
        # Create notification record
        notification_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        notification = Notification(
            id=notification_id,
            created_at=now,
            updated_at=now,
            notification_type=notification_type,
            channel=channel,
            priority=priority,
            recipient_id=recipient_id,
            recipient_address=recipient_address,
            subject=subject,
            body=body,
            metadata=data
        )
        
        # Send via provider
        provider = self.providers.get(channel)
        if not provider:
            print(f"No provider registered for channel: {channel.value}")
            return None
        
        try:
            success = await provider.send(notification)
            
            if success:
                notification.status = NotificationStatus.SENT
                notification.sent_at = now
            else:
                notification.status = NotificationStatus.FAILED
                notification.failed_reason = "Provider send failed"
        except Exception as e:
            notification.status = NotificationStatus.FAILED
            notification.failed_reason = str(e)
        
        # Save notification record
        notification_dict = self._notification_to_dict(notification)
        self.storage.save(self.notifications_table, notification.id, notification_dict)
        
        # Audit log
        self.audit.log_event(
            AuditEventType.SYSTEM_START,
            "notification",
            notification_id,
            {
                "type": notification_type.value,
                "channel": channel.value,
                "recipient_id": recipient_id,
                "status": notification.status.value
            },
            "system"
        )
        
        return notification_id if success else None
    
    def _find_template(self, notification_type: NotificationType, channel: NotificationChannel) -> Optional[NotificationTemplate]:
        """Find the best template for notification type and channel"""
        # First try exact match
        templates_data = self.storage.find(self.templates_table, {
            "notification_type": notification_type.value,
            "channel": channel.value,
            "is_active": True
        })
        
        if templates_data:
            return self._template_from_dict(templates_data[0])
        
        # Fallback to any active template for this notification type
        templates_data = self.storage.find(self.templates_table, {
            "notification_type": notification_type.value,
            "is_active": True
        })
        
        if templates_data:
            return self._template_from_dict(templates_data[0])
        
        return None
    
    def _get_recipient_address(self, recipient_id: str, channel: NotificationChannel) -> Optional[str]:
        """Get recipient address for channel"""
        # For webhooks, could be configured per customer
        if channel == NotificationChannel.WEBHOOK:
            return "https://api.example.com/webhooks/notifications"  # Default webhook URL
        
        # For other channels, would typically look up customer contact info
        # Simplified implementation for now
        if channel == NotificationChannel.EMAIL:
            return f"customer-{recipient_id}@example.com"
        elif channel == NotificationChannel.SMS:
            return f"+1555{recipient_id[-7:]}"  # Mock phone number
        elif channel == NotificationChannel.IN_APP:
            return recipient_id
        
        return recipient_id  # Fallback
    
    def _get_default_channels(self, notification_type: NotificationType) -> List[NotificationChannel]:
        """Get default channels for notification type"""
        # Define sensible defaults
        defaults = {
            NotificationType.TRANSACTION_ALERT: [NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            NotificationType.LARGE_TRANSACTION: [NotificationChannel.EMAIL, NotificationChannel.SMS],
            NotificationType.SUSPICIOUS_ACTIVITY: [NotificationChannel.WEBHOOK, NotificationChannel.EMAIL],
            NotificationType.PAYMENT_DUE: [NotificationChannel.SMS, NotificationChannel.EMAIL],
            NotificationType.PAYMENT_OVERDUE: [NotificationChannel.SMS, NotificationChannel.EMAIL],
            NotificationType.PAYMENT_RECEIVED: [NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            NotificationType.LOAN_APPROVED: [NotificationChannel.EMAIL, NotificationChannel.SMS],
            NotificationType.LOAN_DISBURSED: [NotificationChannel.EMAIL, NotificationChannel.SMS],
            NotificationType.LOAN_PAYMENT_DUE: [NotificationChannel.SMS, NotificationChannel.EMAIL],
            NotificationType.ACCOUNT_OPENED: [NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            NotificationType.ACCOUNT_FROZEN: [NotificationChannel.EMAIL, NotificationChannel.SMS],
            NotificationType.KYC_REQUIRED: [NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            NotificationType.WORKFLOW_PENDING: [NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            NotificationType.WORKFLOW_APPROVED: [NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            NotificationType.WORKFLOW_REJECTED: [NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            NotificationType.COLLECTION_NOTICE: [NotificationChannel.SMS, NotificationChannel.EMAIL],
            NotificationType.COLLECTION_ESCALATION: [NotificationChannel.SMS, NotificationChannel.EMAIL],
            NotificationType.SYSTEM_ALERT: [NotificationChannel.WEBHOOK, NotificationChannel.EMAIL],
            NotificationType.MAINTENANCE_NOTICE: [NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            NotificationType.OTP_VERIFICATION: [NotificationChannel.SMS],
            NotificationType.PASSWORD_RESET: [NotificationChannel.EMAIL]
        }
        
        return defaults.get(notification_type, [NotificationChannel.EMAIL])
    
    def _is_quiet_hours(self, preferences: Optional[NotificationPreference]) -> bool:
        """Check if it's currently quiet hours for recipient"""
        if not preferences or not preferences.quiet_hours_start or not preferences.quiet_hours_end:
            return False
        
        if preferences.do_not_disturb:
            return True
        
        current_time = datetime.now(timezone.utc).time()
        start = preferences.quiet_hours_start
        end = preferences.quiet_hours_end
        
        # Handle overnight quiet hours (e.g., 22:00 to 08:00)
        if start > end:
            return current_time >= start or current_time <= end
        else:
            return start <= current_time <= end
    
    # Notification Management
    
    def get_notifications(
        self,
        recipient_id: str,
        status: Optional[NotificationStatus] = None,
        limit: int = 50
    ) -> List[Notification]:
        """Get notifications for a recipient"""
        filters = {"recipient_id": recipient_id}
        if status:
            filters["status"] = status.value
        
        notifications_data = self.storage.find(self.notifications_table, filters)
        notifications = [self._notification_from_dict(data) for data in notifications_data]
        
        # Sort by creation time (newest first) and limit
        notifications.sort(key=lambda n: n.created_at, reverse=True)
        return notifications[:limit]
    
    def mark_as_read(self, notification_id: str) -> bool:
        """Mark notification as read"""
        notification_dict = self.storage.load(self.notifications_table, notification_id)
        if not notification_dict:
            return False
        
        notification = self._notification_from_dict(notification_dict)
        if notification.status != NotificationStatus.READ:
            notification.status = NotificationStatus.READ
            notification.read_at = datetime.now(timezone.utc)
            notification.updated_at = notification.read_at
            
            notification_dict = self._notification_to_dict(notification)
            self.storage.save(self.notifications_table, notification_id, notification_dict)
        
        return True
    
    def get_unread_count(self, recipient_id: str) -> int:
        """Get count of unread notifications for recipient"""
        notifications_data = self.storage.find(self.notifications_table, {
            "recipient_id": recipient_id,
            "status": NotificationStatus.SENT.value
        })
        return len(notifications_data)
    
    async def retry_failed(self, max_retries: int = 3) -> Dict[str, int]:
        """Retry failed notifications"""
        results = {"attempted": 0, "succeeded": 0, "failed": 0}
        
        # Find failed notifications that haven't exceeded retry limit
        failed_data = self.storage.find(self.notifications_table, {
            "status": NotificationStatus.FAILED.value
        })
        
        for data in failed_data:
            notification = self._notification_from_dict(data)
            
            if notification.retry_count >= max_retries:
                continue  # Skip notifications that have exceeded retry limit
            
            results["attempted"] += 1
            
            # Retry sending
            provider = self.providers.get(notification.channel)
            if provider:
                try:
                    success = await provider.send(notification)
                    
                    notification.retry_count += 1
                    notification.updated_at = datetime.now(timezone.utc)
                    
                    if success:
                        notification.status = NotificationStatus.SENT
                        notification.sent_at = notification.updated_at
                        notification.failed_reason = None
                        results["succeeded"] += 1
                    else:
                        if notification.retry_count >= max_retries:
                            results["failed"] += 1
                    
                    # Save updated notification
                    notification_dict = self._notification_to_dict(notification)
                    self.storage.save(self.notifications_table, notification.id, notification_dict)
                    
                except Exception as e:
                    notification.retry_count += 1
                    notification.failed_reason = str(e)
                    notification.updated_at = datetime.now(timezone.utc)
                    
                    if notification.retry_count >= max_retries:
                        results["failed"] += 1
                    
                    notification_dict = self._notification_to_dict(notification)
                    self.storage.save(self.notifications_table, notification.id, notification_dict)
        
        return results
    
    # Preferences Management
    
    def set_preferences(self, customer_id: str, preferences: NotificationPreference):
        """Set notification preferences for customer"""
        preferences.customer_id = customer_id
        
        if not preferences.id:
            preferences.id = customer_id  # Use customer ID as preferences ID
        
        now = datetime.now(timezone.utc)
        preferences.created_at = now
        preferences.updated_at = now
        
        preferences_dict = self._preferences_to_dict(preferences)
        self.storage.save(self.preferences_table, preferences.id, preferences_dict)
    
    def get_preferences(self, customer_id: str) -> Optional[NotificationPreference]:
        """Get notification preferences for customer"""
        preferences_dict = self.storage.load(self.preferences_table, customer_id)
        if preferences_dict:
            return self._preferences_from_dict(preferences_dict)
        return None
    
    # Statistics
    
    def get_delivery_stats(self) -> Dict[str, Any]:
        """Get notification delivery statistics"""
        all_notifications = self.storage.load_all(self.notifications_table)
        
        stats = {
            "total_notifications": len(all_notifications),
            "by_status": {},
            "by_channel": {},
            "by_type": {},
            "delivery_rate": 0.0
        }
        
        # Initialize counters
        for status in NotificationStatus:
            stats["by_status"][status.value] = 0
        
        for channel in NotificationChannel:
            stats["by_channel"][channel.value] = 0
        
        for notif_type in NotificationType:
            stats["by_type"][notif_type.value] = 0
        
        # Count notifications
        sent_count = 0
        for data in all_notifications:
            notification = self._notification_from_dict(data)
            
            stats["by_status"][notification.status.value] += 1
            stats["by_channel"][notification.channel.value] += 1
            stats["by_type"][notification.notification_type.value] += 1
            
            if notification.status in [NotificationStatus.SENT, NotificationStatus.DELIVERED, NotificationStatus.READ]:
                sent_count += 1
        
        # Calculate delivery rate
        if stats["total_notifications"] > 0:
            stats["delivery_rate"] = sent_count / stats["total_notifications"]
        
        return stats
    
    # Serialization methods
    
    def _template_to_dict(self, template: NotificationTemplate) -> Dict:
        """Convert template to dictionary"""
        result = template.to_dict()
        result["notification_type"] = template.notification_type.value
        result["channel"] = template.channel.value
        return result
    
    def _template_from_dict(self, data: Dict) -> NotificationTemplate:
        """Convert dictionary to template"""
        data["notification_type"] = NotificationType(data["notification_type"])
        data["channel"] = NotificationChannel(data["channel"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        
        return NotificationTemplate(**data)
    
    def _notification_to_dict(self, notification: Notification) -> Dict:
        """Convert notification to dictionary"""
        result = notification.to_dict()
        result["notification_type"] = notification.notification_type.value
        result["channel"] = notification.channel.value
        result["priority"] = notification.priority.value
        result["status"] = notification.status.value
        
        # Convert datetime fields
        if notification.sent_at:
            result["sent_at"] = notification.sent_at.isoformat()
        if notification.delivered_at:
            result["delivered_at"] = notification.delivered_at.isoformat()
        if notification.read_at:
            result["read_at"] = notification.read_at.isoformat()
        
        return result
    
    def _notification_from_dict(self, data: Dict) -> Notification:
        """Convert dictionary to notification"""
        data["notification_type"] = NotificationType(data["notification_type"])
        data["channel"] = NotificationChannel(data["channel"])
        data["priority"] = NotificationPriority(data["priority"])
        data["status"] = NotificationStatus(data["status"])
        
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        
        # Convert optional datetime fields
        if data.get("sent_at"):
            data["sent_at"] = datetime.fromisoformat(data["sent_at"])
        if data.get("delivered_at"):
            data["delivered_at"] = datetime.fromisoformat(data["delivered_at"])
        if data.get("read_at"):
            data["read_at"] = datetime.fromisoformat(data["read_at"])
        
        return Notification(**data)
    
    def _preferences_to_dict(self, preferences: NotificationPreference) -> Dict:
        """Convert preferences to dictionary"""
        result = preferences.to_dict()
        
        # Convert channel preferences
        channel_prefs = {}
        for notif_type, channels in preferences.channel_preferences.items():
            channel_prefs[notif_type.value] = [channel.value for channel in channels]
        result["channel_preferences"] = channel_prefs
        
        # Convert time fields
        if preferences.quiet_hours_start:
            result["quiet_hours_start"] = preferences.quiet_hours_start.isoformat()
        if preferences.quiet_hours_end:
            result["quiet_hours_end"] = preferences.quiet_hours_end.isoformat()
        
        return result
    
    def _preferences_from_dict(self, data: Dict) -> NotificationPreference:
        """Convert dictionary to preferences"""
        # Convert channel preferences
        channel_prefs = {}
        for notif_type_str, channels_list in data.get("channel_preferences", {}).items():
            try:
                notif_type = NotificationType(notif_type_str)
                channels = [NotificationChannel(ch) for ch in channels_list]
                channel_prefs[notif_type] = channels
            except ValueError:
                # Skip invalid notification types/channels
                pass
        
        data["channel_preferences"] = channel_prefs
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        
        # Convert time fields
        if data.get("quiet_hours_start"):
            data["quiet_hours_start"] = time.fromisoformat(data["quiet_hours_start"])
        if data.get("quiet_hours_end"):
            data["quiet_hours_end"] = time.fromisoformat(data["quiet_hours_end"])
        
        return NotificationPreference(**data)