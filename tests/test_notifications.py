"""
Tests for Notification Engine Module

Tests template CRUD, template rendering, notification sending, 
channel providers, preferences, delivery stats, and retry functionality.
"""

import pytest
import asyncio
from datetime import datetime, timezone, time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import json

from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.currency import Money, Currency
from core_banking.notifications import (
    NotificationEngine,
    NotificationChannel,
    NotificationPriority,
    NotificationType,
    NotificationStatus,
    NotificationTemplate,
    Notification,
    NotificationPreference,
    ChannelProvider,
    LogChannelProvider,
    WebhookChannelProvider,
    InAppChannelProvider,
    EmailChannelProvider,
    SMSChannelProvider
)


class MockChannelProvider(ChannelProvider):
    """Mock channel provider for testing"""
    
    def __init__(self, should_succeed: bool = True):
        self.should_succeed = should_succeed
        self.sent_notifications = []
        self.call_count = 0
    
    async def send(self, notification: Notification) -> bool:
        self.call_count += 1
        self.sent_notifications.append(notification)
        return self.should_succeed


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def audit_trail(storage):
    return AuditTrail(storage)


@pytest.fixture
def notification_engine(storage, audit_trail):
    return NotificationEngine(storage, audit_trail)


class TestNotificationEngine:
    """Test the core notification engine functionality"""
    
    def test_initialization(self, notification_engine):
        """Test engine initializes with default providers and templates"""
        # Should have providers for all channels
        assert len(notification_engine.providers) == len(NotificationChannel)
        
        # Should have some default templates
        templates = notification_engine.list_templates()
        assert len(templates) >= 5  # We create 5 default templates
        
        # Verify default templates exist
        template_types = {t.notification_type for t in templates}
        assert NotificationType.TRANSACTION_ALERT in template_types
        assert NotificationType.PAYMENT_DUE in template_types
        assert NotificationType.LOAN_APPROVED in template_types
    
    def test_register_provider(self, notification_engine):
        """Test registering custom channel provider"""
        mock_provider = MockChannelProvider()
        
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        assert notification_engine.providers[NotificationChannel.EMAIL] == mock_provider


class TestNotificationTemplates:
    """Test notification template management"""
    
    def test_create_template(self, notification_engine):
        """Test creating a custom template"""
        template = NotificationTemplate(
            id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            name="Test Template",
            notification_type=NotificationType.ACCOUNT_OPENED,
            channel=NotificationChannel.EMAIL,
            subject_template="Welcome {customer_name}!",
            body_template="Hello {customer_name}, your {account_type} account has been opened.",
            is_active=True
        )
        
        template_id = notification_engine.create_template(template)
        
        assert template_id is not None
        
        # Retrieve and verify
        retrieved = notification_engine.get_template(template_id)
        assert retrieved is not None
        assert retrieved.name == "Test Template"
        assert retrieved.notification_type == NotificationType.ACCOUNT_OPENED
        assert retrieved.subject_template == "Welcome {customer_name}!"
    
    def test_template_rendering_with_placeholders(self, notification_engine):
        """Test template rendering with placeholder substitution"""
        # Create template with placeholders
        template = NotificationTemplate(
            id="test_template",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            name="Test Template",
            notification_type=NotificationType.TRANSACTION_ALERT,
            channel=NotificationChannel.EMAIL,
            subject_template="Transaction Alert: {amount} {transaction_type}",
            body_template="Dear {customer_name}, a {transaction_type} of {amount} was processed on {account_name}."
        )
        
        notification_engine.create_template(template)
        
        # Mock provider to capture the rendered notification
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        # Send notification with data
        data = {
            "customer_name": "John Doe",
            "amount": "$500.00",
            "transaction_type": "withdrawal",
            "account_name": "Savings Account"
        }
        
        # Use asyncio.run to handle async function
        async def test_send():
            return await notification_engine.send_notification(
                notification_type=NotificationType.TRANSACTION_ALERT,
                recipient_id="customer_123",
                data=data,
                channels=[NotificationChannel.EMAIL]
            )
        
        notification_ids = asyncio.run(test_send())
        
        assert len(notification_ids) == 1
        assert mock_provider.call_count == 1
        
        # Verify rendered content
        sent_notification = mock_provider.sent_notifications[0]
        assert sent_notification.subject == "Transaction Alert: $500.00 withdrawal"
        assert "Dear John Doe" in sent_notification.body
        assert "withdrawal of $500.00" in sent_notification.body
        assert "Savings Account" in sent_notification.body
    
    def test_list_templates(self, notification_engine):
        """Test listing all templates"""
        templates = notification_engine.list_templates()
        
        # Should have default templates
        assert len(templates) >= 5
        
        # Templates should be sorted
        prev_type = None
        for template in templates:
            if prev_type is not None:
                assert template.notification_type.value >= prev_type
            prev_type = template.notification_type.value
    
    def test_get_nonexistent_template(self, notification_engine):
        """Test getting a template that doesn't exist"""
        result = notification_engine.get_template("nonexistent_id")
        assert result is None


class TestNotificationSending:
    """Test notification sending functionality"""
    
    def test_send_notification_log_provider(self, notification_engine, capsys):
        """Test sending notification with log provider"""
        # Log provider is default - should just log the notification
        
        async def test_send():
            return await notification_engine.send_notification(
                notification_type=NotificationType.PAYMENT_DUE,
                recipient_id="customer_456",
                data={
                    "customer_name": "Jane Smith",
                    "amount": "$250.00",
                    "loan_type": "Personal Loan",
                    "due_date": "2024-01-15",
                    "phone": "1-800-BANK"
                }
            )
        
        notification_ids = asyncio.run(test_send())
        
        assert len(notification_ids) >= 1  # Should send to at least one channel
        
        # Should see output in logs
        captured = capsys.readouterr()
        assert "SMS to customer" in captured.out or "NOTIFICATION" in captured.out
    
    def test_send_notification_with_mock_provider(self, notification_engine):
        """Test sending notification with mock provider"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        async def test_send():
            return await notification_engine.send_notification(
                notification_type=NotificationType.LOAN_APPROVED,
                recipient_id="customer_789",
                data={
                    "customer_name": "Bob Wilson",
                    "loan_type": "Auto Loan",
                    "amount": "$25,000.00",
                    "interest_rate": "5.5",
                    "term": "60",
                    "monthly_payment": "$475.83",
                    "reference": "LOAN-2024-001"
                },
                channels=[NotificationChannel.EMAIL],
                priority=NotificationPriority.HIGH
            )
        
        notification_ids = asyncio.run(test_send())
        
        assert len(notification_ids) == 1
        assert mock_provider.call_count == 1
        
        sent_notification = mock_provider.sent_notifications[0]
        assert sent_notification.notification_type == NotificationType.LOAN_APPROVED
        assert sent_notification.channel == NotificationChannel.EMAIL
        assert sent_notification.priority == NotificationPriority.HIGH
        assert sent_notification.recipient_id == "customer_789"
        assert "Bob Wilson" in sent_notification.body
        assert "$25,000.00" in sent_notification.body
    
    def test_send_notification_with_failed_provider(self, notification_engine):
        """Test handling failed notification sending"""
        mock_provider = MockChannelProvider(should_succeed=False)
        notification_engine.register_provider(NotificationChannel.SMS, mock_provider)
        
        async def test_send():
            return await notification_engine.send_notification(
                notification_type=NotificationType.PAYMENT_OVERDUE,
                recipient_id="customer_failed",
                data={"customer_name": "Test User", "amount": "$100.00"},
                channels=[NotificationChannel.SMS]
            )
        
        notification_ids = asyncio.run(test_send())
        
        # Should return empty list for failed sends
        assert len(notification_ids) == 0
        assert mock_provider.call_count == 1
    
    def test_bulk_send_notifications(self, notification_engine):
        """Test bulk notification sending"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        recipient_ids = ["customer_1", "customer_2", "customer_3"]
        
        async def test_bulk_send():
            return await notification_engine.send_bulk(
                notification_type=NotificationType.MAINTENANCE_NOTICE,
                recipient_ids=recipient_ids,
                data={
                    "maintenance_date": "2024-01-20",
                    "duration": "2 hours",
                    "affected_services": "online banking"
                },
                channels=[NotificationChannel.EMAIL]
            )
        
        results = asyncio.run(test_bulk_send())
        
        assert len(results) == 3
        for recipient_id in recipient_ids:
            assert recipient_id in results
            assert len(results[recipient_id]) == 1  # One notification sent per recipient
        
        assert mock_provider.call_count == 3  # Called once per recipient


class TestChannelProviders:
    """Test different channel providers"""
    
    def test_log_channel_provider(self, capsys):
        """Test log channel provider"""
        provider = LogChannelProvider()
        
        notification = Notification(
            id="test_notif",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            notification_type=NotificationType.TRANSACTION_ALERT,
            channel=NotificationChannel.EMAIL,
            priority=NotificationPriority.MEDIUM,
            recipient_id="test_user",
            recipient_address="test@example.com",
            subject="Test Subject",
            body="This is a test notification body with more than 100 characters to test the truncation feature of the log provider output formatting."
        )
        
        async def test_send():
            return await provider.send(notification)
        
        result = asyncio.run(test_send())
        
        assert result is True
        
        captured = capsys.readouterr()
        assert "EMAIL to test@example.com" in captured.out
        assert "Test Subject" in captured.out
        assert "This is a test notification body" in captured.out
    
    def test_webhook_channel_provider_success(self, notification_engine):
        """Test webhook channel provider with successful response"""
        # Mock requests.post to return success
        import requests
        from unittest.mock import patch
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            provider = WebhookChannelProvider()
            
            notification = Notification(
                id="webhook_test",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                notification_type=NotificationType.SUSPICIOUS_ACTIVITY,
                channel=NotificationChannel.WEBHOOK,
                priority=NotificationPriority.CRITICAL,
                recipient_id="compliance_system",
                recipient_address="https://api.example.com/webhook",
                subject="Suspicious Activity Alert",
                body="High-risk transaction detected",
                metadata={"risk_score": 95}
            )
            
            async def test_send():
                return await provider.send(notification)
            
            result = asyncio.run(test_send())
            
            assert result is True
            assert mock_post.called
            
            # Verify payload structure
            call_args = mock_post.call_args
            assert call_args[0][0] == "https://api.example.com/webhook"
            payload = call_args[1]['json']
            assert payload['notification_id'] == "webhook_test"
            assert payload['type'] == "suspicious_activity"
            assert payload['priority'] == "critical"
            assert payload['risk_score'] == 95
    
    def test_webhook_channel_provider_failure(self):
        """Test webhook channel provider with failed response"""
        import requests
        from unittest.mock import patch
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        
        with patch('requests.post', return_value=mock_response):
            provider = WebhookChannelProvider()
            
            notification = Notification(
                id="webhook_fail_test",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                notification_type=NotificationType.SYSTEM_ALERT,
                channel=NotificationChannel.WEBHOOK,
                priority=NotificationPriority.HIGH,
                recipient_id="system",
                recipient_address="https://api.example.com/webhook",
                subject="System Alert",
                body="System error occurred"
            )
            
            async def test_send():
                return await provider.send(notification)
            
            result = asyncio.run(test_send())
            
            assert result is False
    
    def test_in_app_channel_provider(self, storage):
        """Test in-app notification provider"""
        provider = InAppChannelProvider(storage)
        
        notification = Notification(
            id="in_app_test",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            notification_type=NotificationType.WORKFLOW_PENDING,
            channel=NotificationChannel.IN_APP,
            priority=NotificationPriority.MEDIUM,
            recipient_id="user_123",
            recipient_address="user_123",
            subject="Workflow Approval Required",
            body="Please review the pending loan approval workflow."
        )
        
        async def test_send():
            return await provider.send(notification)
        
        result = asyncio.run(test_send())
        
        assert result is True
        
        # Verify stored in-app notification
        in_app_notifications = storage.find("in_app_notifications", {"recipient_id": "user_123"})
        assert len(in_app_notifications) == 1
        
        stored_notif = in_app_notifications[0]
        assert stored_notif["notification_id"] == "in_app_test"
        assert stored_notif["subject"] == "Workflow Approval Required"
        assert stored_notif["read"] is False
    
    def test_email_and_sms_placeholder_providers(self, capsys):
        """Test placeholder email and SMS providers"""
        email_provider = EmailChannelProvider()
        sms_provider = SMSChannelProvider()
        
        email_notification = Notification(
            id="email_test",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            notification_type=NotificationType.PASSWORD_RESET,
            channel=NotificationChannel.EMAIL,
            priority=NotificationPriority.HIGH,
            recipient_id="user_456",
            recipient_address="user@example.com",
            subject="Password Reset Request",
            body="Click here to reset your password."
        )
        
        sms_notification = Notification(
            id="sms_test",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            notification_type=NotificationType.OTP_VERIFICATION,
            channel=NotificationChannel.SMS,
            priority=NotificationPriority.HIGH,
            recipient_id="user_789",
            recipient_address="+15551234567",
            subject="OTP Code",
            body="Your OTP code is: 123456"
        )
        
        async def test_send():
            email_result = await email_provider.send(email_notification)
            sms_result = await sms_provider.send(sms_notification)
            return email_result, sms_result
        
        email_result, sms_result = asyncio.run(test_send())
        
        assert email_result is True
        assert sms_result is True
        
        captured = capsys.readouterr()
        assert "EMAIL (placeholder)" in captured.out
        assert "SMS (placeholder)" in captured.out
        assert "user@example.com" in captured.out
        assert "+15551234567" in captured.out


class TestNotificationManagement:
    """Test notification retrieval and management"""
    
    def test_get_notifications_for_recipient(self, notification_engine):
        """Test retrieving notifications for a specific recipient"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        # Send multiple notifications
        async def send_notifications():
            await notification_engine.send_notification(
                NotificationType.ACCOUNT_OPENED,
                "user_123",
                {"customer_name": "John Doe", "account_type": "Savings"},
                [NotificationChannel.EMAIL]
            )
            await notification_engine.send_notification(
                NotificationType.TRANSACTION_ALERT,
                "user_123",
                {"customer_name": "John Doe", "amount": "$100.00", "transaction_type": "deposit"},
                [NotificationChannel.EMAIL]
            )
            await notification_engine.send_notification(
                NotificationType.PAYMENT_DUE,
                "user_456",  # Different user
                {"customer_name": "Jane Smith", "amount": "$50.00"},
                [NotificationChannel.EMAIL]
            )
        
        asyncio.run(send_notifications())
        
        # Get notifications for user_123
        notifications = notification_engine.get_notifications("user_123")
        
        assert len(notifications) == 2
        assert all(n.recipient_id == "user_123" for n in notifications)
        
        # Should be sorted by creation time (newest first)
        assert notifications[0].created_at >= notifications[1].created_at
    
    def test_get_notifications_with_status_filter(self, notification_engine):
        """Test filtering notifications by status"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        async def send_notification():
            await notification_engine.send_notification(
                NotificationType.LOAN_APPROVED,
                "user_filter_test",
                {"customer_name": "Test User", "loan_type": "Personal"},
                [NotificationChannel.EMAIL]
            )
        
        asyncio.run(send_notification())
        
        # Get sent notifications
        sent_notifications = notification_engine.get_notifications(
            "user_filter_test", 
            status=NotificationStatus.SENT
        )
        
        assert len(sent_notifications) == 1
        assert sent_notifications[0].status == NotificationStatus.SENT
        
        # Get pending notifications (should be empty)
        pending_notifications = notification_engine.get_notifications(
            "user_filter_test",
            status=NotificationStatus.PENDING
        )
        
        assert len(pending_notifications) == 0
    
    def test_mark_notification_as_read(self, notification_engine):
        """Test marking notification as read"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        async def send_notification():
            return await notification_engine.send_notification(
                NotificationType.WORKFLOW_APPROVED,
                "read_test_user",
                {"workflow_name": "Loan Approval"},
                [NotificationChannel.EMAIL]
            )
        
        notification_ids = asyncio.run(send_notification())
        notification_id = notification_ids[0]
        
        # Mark as read
        success = notification_engine.mark_as_read(notification_id)
        assert success is True
        
        # Verify it's marked as read
        notifications = notification_engine.get_notifications("read_test_user")
        assert len(notifications) == 1
        assert notifications[0].status == NotificationStatus.READ
        assert notifications[0].read_at is not None
    
    def test_mark_nonexistent_notification_as_read(self, notification_engine):
        """Test marking non-existent notification as read"""
        success = notification_engine.mark_as_read("nonexistent_id")
        assert success is False
    
    def test_get_unread_count(self, notification_engine):
        """Test getting unread notification count"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        async def send_notifications():
            # Send 3 notifications
            await notification_engine.send_notification(
                NotificationType.ACCOUNT_OPENED,
                "unread_test_user",
                {"customer_name": "Test User", "account_type": "Checking"},
                [NotificationChannel.EMAIL]
            )
            await notification_engine.send_notification(
                NotificationType.TRANSACTION_ALERT,
                "unread_test_user",
                {"customer_name": "Test User", "amount": "$200.00"},
                [NotificationChannel.EMAIL]
            )
            return await notification_engine.send_notification(
                NotificationType.PAYMENT_RECEIVED,
                "unread_test_user",
                {"customer_name": "Test User", "amount": "$500.00"},
                [NotificationChannel.EMAIL]
            )
        
        notification_ids = asyncio.run(send_notifications())
        
        # Should have 3 unread (sent) notifications
        unread_count = notification_engine.get_unread_count("unread_test_user")
        assert unread_count == 3
        
        # Mark one as read
        notification_engine.mark_as_read(notification_ids[0])
        
        # Should now have 2 unread notifications
        unread_count = notification_engine.get_unread_count("unread_test_user")
        assert unread_count == 2


class TestNotificationStatusTracking:
    """Test notification status tracking through lifecycle"""
    
    def test_notification_status_pending_to_sent_to_delivered_to_read(self, notification_engine):
        """Test notification status transitions"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        async def send_notification():
            return await notification_engine.send_notification(
                NotificationType.COLLECTION_NOTICE,
                "status_test_user",
                {"customer_name": "Status Test User", "amount": "$300.00"},
                [NotificationChannel.EMAIL],
                priority=NotificationPriority.HIGH
            )
        
        notification_ids = asyncio.run(send_notification())
        notification_id = notification_ids[0]
        
        # Should be sent after successful send
        notifications = notification_engine.get_notifications("status_test_user")
        assert len(notifications) == 1
        assert notifications[0].status == NotificationStatus.SENT
        assert notifications[0].sent_at is not None
        assert notifications[0].priority == NotificationPriority.HIGH
        
        # Mark as read (simulates user reading the notification)
        success = notification_engine.mark_as_read(notification_id)
        assert success is True
        
        # Should now be read
        notifications = notification_engine.get_notifications("status_test_user")
        assert notifications[0].status == NotificationStatus.READ
        assert notifications[0].read_at is not None


class TestFailedNotificationRetry:
    """Test retry functionality for failed notifications"""
    
    def test_retry_failed_notifications_success(self, notification_engine):
        """Test successfully retrying failed notifications"""
        # Start with failing provider
        failing_provider = MockChannelProvider(should_succeed=False)
        notification_engine.register_provider(NotificationChannel.SMS, failing_provider)
        
        async def send_notification():
            return await notification_engine.send_notification(
                NotificationType.PAYMENT_OVERDUE,
                "retry_test_user",
                {"customer_name": "Retry Test", "amount": "$150.00"},
                [NotificationChannel.SMS]
            )
        
        # Should fail initially
        notification_ids = asyncio.run(send_notification())
        assert len(notification_ids) == 0
        assert failing_provider.call_count == 1
        
        # Now replace with succeeding provider
        succeeding_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.SMS, succeeding_provider)
        
        # Retry failed notifications
        async def retry_failed():
            return await notification_engine.retry_failed(max_retries=3)
        
        results = asyncio.run(retry_failed())
        
        assert results["attempted"] == 1
        assert results["succeeded"] == 1
        assert results["failed"] == 0
        assert succeeding_provider.call_count == 1
    
    def test_retry_failed_notifications_max_retries_exceeded(self, notification_engine):
        """Test retry with max retries exceeded"""
        failing_provider = MockChannelProvider(should_succeed=False)
        notification_engine.register_provider(NotificationChannel.EMAIL, failing_provider)
        
        async def send_and_retry():
            # Send notification (will fail)
            await notification_engine.send_notification(
                NotificationType.KYC_REQUIRED,
                "max_retry_user",
                {"customer_name": "Max Retry Test"},
                [NotificationChannel.EMAIL]
            )
            
            # Retry multiple times
            for _ in range(4):  # This should exceed max_retries of 3
                await notification_engine.retry_failed(max_retries=3)
        
        asyncio.run(send_and_retry())
        
        # The provider should be called: 1 initial + 3 retries = 4 times
        # (After 3 failed retries, it shouldn't retry again)
        assert failing_provider.call_count == 4


class TestNotificationPreferences:
    """Test customer notification preferences"""
    
    def test_set_and_get_preferences(self, notification_engine):
        """Test setting and retrieving notification preferences"""
        preferences = NotificationPreference(
            id="pref_test_customer",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            customer_id="pref_test_customer",
            channel_preferences={
                NotificationType.TRANSACTION_ALERT: [NotificationChannel.EMAIL, NotificationChannel.SMS],
                NotificationType.PAYMENT_DUE: [NotificationChannel.SMS],
                NotificationType.LOAN_APPROVED: [NotificationChannel.EMAIL, NotificationChannel.IN_APP]
            },
            quiet_hours_start=time(22, 0),  # 10 PM
            quiet_hours_end=time(8, 0),     # 8 AM
            do_not_disturb=False
        )
        
        notification_engine.set_preferences("pref_test_customer", preferences)
        
        retrieved_prefs = notification_engine.get_preferences("pref_test_customer")
        
        assert retrieved_prefs is not None
        assert retrieved_prefs.customer_id == "pref_test_customer"
        assert len(retrieved_prefs.channel_preferences) == 3
        assert retrieved_prefs.channel_preferences[NotificationType.PAYMENT_DUE] == [NotificationChannel.SMS]
        assert retrieved_prefs.quiet_hours_start == time(22, 0)
        assert retrieved_prefs.quiet_hours_end == time(8, 0)
        assert retrieved_prefs.do_not_disturb is False
    
    def test_get_nonexistent_preferences(self, notification_engine):
        """Test getting preferences for customer that doesn't have any set"""
        prefs = notification_engine.get_preferences("nonexistent_customer")
        assert prefs is None
    
    def test_do_not_disturb_setting(self, notification_engine):
        """Test do not disturb functionality"""
        # Set up customer with DND enabled
        dnd_preferences = NotificationPreference(
            id="dnd_customer",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            customer_id="dnd_customer",
            do_not_disturb=True
        )
        
        notification_engine.set_preferences("dnd_customer", dnd_preferences)
        
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        # Try to send non-critical notification
        async def send_non_critical():
            return await notification_engine.send_notification(
                NotificationType.ACCOUNT_OPENED,
                "dnd_customer",
                {"customer_name": "DND Test"},
                [NotificationChannel.EMAIL],
                priority=NotificationPriority.LOW
            )
        
        # Should be blocked due to DND
        notification_ids = asyncio.run(send_non_critical())
        assert len(notification_ids) == 0
        assert mock_provider.call_count == 0
        
        # Try to send critical notification
        async def send_critical():
            return await notification_engine.send_notification(
                NotificationType.SUSPICIOUS_ACTIVITY,
                "dnd_customer",
                {"description": "Critical security alert"},
                [NotificationChannel.EMAIL],
                priority=NotificationPriority.CRITICAL
            )
        
        # Should go through despite DND
        notification_ids = asyncio.run(send_critical())
        assert len(notification_ids) == 1
        assert mock_provider.call_count == 1


class TestNotificationPriorityHandling:
    """Test notification priority handling"""
    
    def test_priority_assignment(self, notification_engine):
        """Test that priorities are correctly assigned"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        async def send_high_priority():
            return await notification_engine.send_notification(
                NotificationType.ACCOUNT_FROZEN,
                "priority_test_user",
                {"customer_name": "Priority Test"},
                [NotificationChannel.EMAIL],
                priority=NotificationPriority.HIGH
            )
        
        notification_ids = asyncio.run(send_high_priority())
        
        assert len(notification_ids) == 1
        sent_notification = mock_provider.sent_notifications[0]
        assert sent_notification.priority == NotificationPriority.HIGH
    
    def test_default_priority(self, notification_engine):
        """Test default priority assignment"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        async def send_default_priority():
            return await notification_engine.send_notification(
                NotificationType.TRANSACTION_ALERT,
                "default_priority_user",
                {"customer_name": "Default Priority Test", "amount": "$100.00"},
                [NotificationChannel.EMAIL]
                # No priority specified - should default to MEDIUM
            )
        
        notification_ids = asyncio.run(send_default_priority())
        
        sent_notification = mock_provider.sent_notifications[0]
        assert sent_notification.priority == NotificationPriority.MEDIUM


class TestNotificationDeliveryStats:
    """Test notification delivery statistics"""
    
    def test_get_delivery_stats(self, notification_engine):
        """Test getting comprehensive delivery statistics"""
        # Set up providers with different success rates
        successful_provider = MockChannelProvider(should_succeed=True)
        failing_provider = MockChannelProvider(should_succeed=False)
        
        notification_engine.register_provider(NotificationChannel.EMAIL, successful_provider)
        notification_engine.register_provider(NotificationChannel.SMS, failing_provider)
        
        async def send_various_notifications():
            # Send successful email notifications
            await notification_engine.send_notification(
                NotificationType.ACCOUNT_OPENED,
                "stats_user_1",
                {"customer_name": "Stats User 1"},
                [NotificationChannel.EMAIL]
            )
            await notification_engine.send_notification(
                NotificationType.TRANSACTION_ALERT,
                "stats_user_2",
                {"customer_name": "Stats User 2", "amount": "$50.00"},
                [NotificationChannel.EMAIL]
            )
            
            # Send failing SMS notifications
            await notification_engine.send_notification(
                NotificationType.PAYMENT_DUE,
                "stats_user_3",
                {"customer_name": "Stats User 3", "amount": "$75.00"},
                [NotificationChannel.SMS]
            )
            
            # Mark one as read
            return await notification_engine.send_notification(
                NotificationType.LOAN_DISBURSED,
                "stats_user_4",
                {"customer_name": "Stats User 4", "amount": "$10000.00"},
                [NotificationChannel.EMAIL]
            )
        
        notification_ids = asyncio.run(send_various_notifications())
        
        # Mark one notification as read
        if notification_ids:
            notification_engine.mark_as_read(notification_ids[0])
        
        stats = notification_engine.get_delivery_stats()
        
        assert stats["total_notifications"] >= 4
        assert "by_status" in stats
        assert "by_channel" in stats
        assert "by_type" in stats
        assert "delivery_rate" in stats
        
        # Check status counts
        assert stats["by_status"]["sent"] >= 3  # Email notifications should be sent
        assert stats["by_status"]["failed"] >= 1  # SMS notification should fail
        
        # Check channel counts
        assert stats["by_channel"]["email"] >= 3
        assert stats["by_channel"]["sms"] >= 1
        
        # Delivery rate should be between 0 and 1
        assert 0 <= stats["delivery_rate"] <= 1


class TestNotificationDefaultChannels:
    """Test default channel selection for notification types"""
    
    def test_default_channels_for_notification_types(self, notification_engine):
        """Test that appropriate default channels are selected"""
        mock_email_provider = MockChannelProvider(should_succeed=True)
        mock_sms_provider = MockChannelProvider(should_succeed=True)
        mock_webhook_provider = MockChannelProvider(should_succeed=True)
        
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_email_provider)
        notification_engine.register_provider(NotificationChannel.SMS, mock_sms_provider)
        notification_engine.register_provider(NotificationChannel.WEBHOOK, mock_webhook_provider)
        
        async def test_defaults():
            # OTP should default to SMS only
            await notification_engine.send_notification(
                NotificationType.OTP_VERIFICATION,
                "otp_user",
                {"otp_code": "123456"}
            )
            
            # Suspicious activity should use webhook and email
            await notification_engine.send_notification(
                NotificationType.SUSPICIOUS_ACTIVITY,
                "suspicious_user",
                {"description": "Unusual transaction pattern"}
            )
            
            # Payment due should use SMS and email
            await notification_engine.send_notification(
                NotificationType.PAYMENT_DUE,
                "payment_user",
                {"amount": "$100.00", "due_date": "2024-01-15"}
            )
        
        asyncio.run(test_defaults())
        
        # OTP should only use SMS (based on default configuration)
        assert mock_sms_provider.call_count >= 1
        
        # Suspicious activity and payment due should trigger multiple channels
        total_calls = mock_email_provider.call_count + mock_sms_provider.call_count + mock_webhook_provider.call_count
        assert total_calls >= 5  # Should be more than 3 notifications due to multiple channels per notification


if __name__ == "__main__":
    pytest.main([__file__, "-v"])