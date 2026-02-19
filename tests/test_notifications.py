"""
Tests for Notification Engine Module

Tests basic functionality with existing templates and proper data.
"""

import pytest
import asyncio
from datetime import datetime, timezone, time
from unittest.mock import MagicMock
import uuid

from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
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


class TestNotificationTemplates:
    """Test notification template management"""
    
    def test_create_template(self, notification_engine):
        """Test creating a custom template"""
        now = datetime.now(timezone.utc)
        template = NotificationTemplate(
            "test_template_id",  # id
            now,                 # created_at
            now,                 # updated_at
            name="Test Template",
            notification_type=NotificationType.ACCOUNT_OPENED,
            channel=NotificationChannel.EMAIL,
            subject_template="Welcome {customer_name}!",
            body_template="Hello {customer_name}, your {account_type} account has been opened.",
            is_active=True
        )
        
        template_id = notification_engine.create_template(template)
        
        assert template_id == "test_template_id"
        
        # Retrieve and verify
        retrieved = notification_engine.get_template(template_id)
        assert retrieved is not None
        assert retrieved.name == "Test Template"
        assert retrieved.notification_type == NotificationType.ACCOUNT_OPENED
        assert retrieved.subject_template == "Welcome {customer_name}!"


class TestNotificationSending:
    """Test notification sending functionality with proper data"""
    
    def test_send_transaction_alert_with_complete_data(self, notification_engine):
        """Test sending transaction alert with all required fields"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        async def test_send():
            return await notification_engine.send_notification(
                notification_type=NotificationType.TRANSACTION_ALERT,
                recipient_id="customer_123",
                data={
                    "customer_name": "John Doe",
                    "amount": "$500.00",
                    "transaction_type": "withdrawal",
                    "account_name": "Savings Account",
                    "timestamp": "2024-01-15 10:30:00",
                    "reference": "TX-001234"
                },
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
        assert "2024-01-15 10:30:00" in sent_notification.body
        assert "TX-001234" in sent_notification.body
    
    def test_send_loan_approved_notification_complete(self, notification_engine):
        """Test sending loan approved notification with all required fields"""
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
    
    def test_send_payment_due_sms_complete(self, notification_engine):
        """Test sending payment due SMS with all required fields"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.SMS, mock_provider)
        
        async def test_send():
            return await notification_engine.send_notification(
                notification_type=NotificationType.PAYMENT_DUE,
                recipient_id="customer_456",
                data={
                    "amount": "$250.00",
                    "loan_type": "Personal Loan",
                    "due_date": "2024-01-15",
                    "phone": "1-800-BANK"
                },
                channels=[NotificationChannel.SMS]
            )
        
        notification_ids = asyncio.run(test_send())
        
        assert len(notification_ids) == 1
        assert mock_provider.call_count == 1
        
        sent_notification = mock_provider.sent_notifications[0]
        assert sent_notification.notification_type == NotificationType.PAYMENT_DUE
        assert sent_notification.channel == NotificationChannel.SMS
        assert "Payment due: $250.00 for Personal Loan" in sent_notification.body
    
    def test_send_suspicious_activity_webhook_complete(self, notification_engine):
        """Test sending suspicious activity webhook with all required fields"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.WEBHOOK, mock_provider)
        
        async def test_send():
            return await notification_engine.send_notification(
                notification_type=NotificationType.SUSPICIOUS_ACTIVITY,
                recipient_id="compliance_system",
                data={
                    "description": "Unusual transaction pattern",
                    "customer_id": "customer_123",
                    "risk_score": "85"
                },
                channels=[NotificationChannel.WEBHOOK]
            )
        
        notification_ids = asyncio.run(test_send())
        
        assert len(notification_ids) == 1
        assert mock_provider.call_count == 1
        
        sent_notification = mock_provider.sent_notifications[0]
        assert sent_notification.notification_type == NotificationType.SUSPICIOUS_ACTIVITY
        assert sent_notification.channel == NotificationChannel.WEBHOOK
        assert "Unusual transaction pattern" in sent_notification.body
    
    def test_send_notification_with_failed_provider(self, notification_engine):
        """Test handling failed notification sending"""
        mock_provider = MockChannelProvider(should_succeed=False)
        notification_engine.register_provider(NotificationChannel.SMS, mock_provider)
        
        async def test_send():
            return await notification_engine.send_notification(
                notification_type=NotificationType.PAYMENT_DUE,
                recipient_id="customer_failed",
                data={
                    "amount": "$100.00",
                    "loan_type": "Auto Loan",
                    "due_date": "2024-01-20",
                    "phone": "1-800-BANK"
                },
                channels=[NotificationChannel.SMS]
            )
        
        notification_ids = asyncio.run(test_send())
        
        # Should return empty list for failed sends
        assert len(notification_ids) == 0
        assert mock_provider.call_count == 1


class TestChannelProviders:
    """Test different channel providers"""
    
    def test_log_channel_provider(self, capsys):
        """Test log channel provider"""
        provider = LogChannelProvider()
        
        now = datetime.now(timezone.utc)
        notification = Notification(
            "test_notif",        # id
            now,                 # created_at
            now,                 # updated_at
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
    
    def test_webhook_channel_provider_success(self):
        """Test webhook channel provider with successful response"""
        # Mock requests.post to return success
        import requests
        from unittest.mock import patch
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            provider = WebhookChannelProvider()
            
            now = datetime.now(timezone.utc)
            notification = Notification(
                "webhook_test",      # id
                now,                 # created_at
                now,                 # updated_at
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
    
    def test_webhook_channel_provider_failure(self):
        """Test webhook channel provider with failed response"""
        import requests
        from unittest.mock import patch
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        
        with patch('requests.post', return_value=mock_response):
            provider = WebhookChannelProvider()
            
            now = datetime.now(timezone.utc)
            notification = Notification(
                "webhook_fail_test", # id
                now,                 # created_at
                now,                 # updated_at
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
        
        now = datetime.now(timezone.utc)
        notification = Notification(
            "in_app_test",       # id
            now,                 # created_at
            now,                 # updated_at
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
        
        now = datetime.now(timezone.utc)
        email_notification = Notification(
            "email_test",        # id
            now,                 # created_at
            now,                 # updated_at
            notification_type=NotificationType.PASSWORD_RESET,
            channel=NotificationChannel.EMAIL,
            priority=NotificationPriority.HIGH,
            recipient_id="user_456",
            recipient_address="user@example.com",
            subject="Password Reset Request",
            body="Click here to reset your password."
        )
        
        sms_notification = Notification(
            "sms_test",          # id
            now,                 # created_at
            now,                 # updated_at
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
        
        # Send multiple notifications using existing templates
        async def send_notifications():
            await notification_engine.send_notification(
                NotificationType.TRANSACTION_ALERT,
                "user_123",
                {
                    "customer_name": "John Doe",
                    "amount": "$100.00",
                    "transaction_type": "deposit",
                    "account_name": "Savings",
                    "timestamp": "2024-01-15 10:30:00",
                    "reference": "TX-001"
                },
                [NotificationChannel.EMAIL]
            )
            await notification_engine.send_notification(
                NotificationType.LOAN_APPROVED,
                "user_123",
                {
                    "customer_name": "John Doe",
                    "loan_type": "Personal",
                    "amount": "$5000",
                    "interest_rate": "5.0",
                    "term": "12",
                    "monthly_payment": "$430",
                    "reference": "LOAN-123"
                },
                [NotificationChannel.EMAIL]
            )
        
        asyncio.run(send_notifications())
        
        # Get notifications for user_123
        notifications = notification_engine.get_notifications("user_123")
        
        assert len(notifications) == 2
        assert all(n.recipient_id == "user_123" for n in notifications)
        
        # Should be sorted by creation time (newest first)
        assert notifications[0].created_at >= notifications[1].created_at
    
    def test_mark_notification_as_read(self, notification_engine):
        """Test marking notification as read"""
        mock_provider = MockChannelProvider(should_succeed=True)
        notification_engine.register_provider(NotificationChannel.EMAIL, mock_provider)
        
        async def send_notification():
            return await notification_engine.send_notification(
                NotificationType.TRANSACTION_ALERT,
                "read_test_user",
                {
                    "customer_name": "Test User",
                    "amount": "$200.00",
                    "transaction_type": "deposit",
                    "account_name": "Checking",
                    "timestamp": "2024-01-15 10:30:00",
                    "reference": "TX-002"
                },
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
            # Send 2 notifications
            await notification_engine.send_notification(
                NotificationType.TRANSACTION_ALERT,
                "unread_test_user",
                {
                    "customer_name": "Test User",
                    "amount": "$200.00",
                    "transaction_type": "deposit",
                    "account_name": "Checking",
                    "timestamp": "2024-01-15 10:30:00",
                    "reference": "TX-003"
                },
                [NotificationChannel.EMAIL]
            )
            return await notification_engine.send_notification(
                NotificationType.LOAN_APPROVED,
                "unread_test_user",
                {
                    "customer_name": "Test User",
                    "loan_type": "Personal",
                    "amount": "$5000",
                    "interest_rate": "5.0",
                    "term": "12",
                    "monthly_payment": "$430",
                    "reference": "LOAN-123"
                },
                [NotificationChannel.EMAIL]
            )
        
        notification_ids = asyncio.run(send_notifications())
        
        # Should have 2 unread (sent) notifications
        unread_count = notification_engine.get_unread_count("unread_test_user")
        assert unread_count == 2
        
        # Mark one as read
        notification_engine.mark_as_read(notification_ids[0])
        
        # Should now have 1 unread notification
        unread_count = notification_engine.get_unread_count("unread_test_user")
        assert unread_count == 1


class TestNotificationPreferences:
    """Test customer notification preferences"""
    
    def test_set_and_get_preferences(self, notification_engine):
        """Test setting and retrieving notification preferences"""
        now = datetime.now(timezone.utc)
        preferences = NotificationPreference(
            "pref_test_customer", # id
            now,                  # created_at
            now,                  # updated_at
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
                NotificationType.TRANSACTION_ALERT,
                "stats_user_1",
                {
                    "customer_name": "Stats User 1",
                    "amount": "$50.00",
                    "transaction_type": "withdrawal",
                    "account_name": "Checking",
                    "timestamp": "2024-01-15 10:30:00",
                    "reference": "TX-004"
                },
                [NotificationChannel.EMAIL]
            )
            
            # Send failing SMS notifications
            await notification_engine.send_notification(
                NotificationType.PAYMENT_DUE,
                "stats_user_2",
                {
                    "amount": "$75.00",
                    "loan_type": "Auto",
                    "due_date": "2024-01-20",
                    "phone": "1-800-BANK"
                },
                [NotificationChannel.SMS]
            )
            
            # Send successful email notification
            return await notification_engine.send_notification(
                NotificationType.LOAN_APPROVED,
                "stats_user_3",
                {
                    "customer_name": "Stats User 3",
                    "loan_type": "Personal",
                    "amount": "$10000.00",
                    "interest_rate": "5.5",
                    "term": "24",
                    "monthly_payment": "$450",
                    "reference": "LOAN-456"
                },
                [NotificationChannel.EMAIL]
            )
        
        notification_ids = asyncio.run(send_various_notifications())
        
        # Mark one notification as read
        if notification_ids:
            notification_engine.mark_as_read(notification_ids[0])
        
        stats = notification_engine.get_delivery_stats()
        
        assert stats["total_notifications"] >= 3
        assert "by_status" in stats
        assert "by_channel" in stats
        assert "by_type" in stats
        assert "delivery_rate" in stats
        
        # Check status counts
        assert stats["by_status"]["sent"] >= 1  # Email notifications should be sent
        assert stats["by_status"]["failed"] >= 1  # SMS notification should fail
        
        # Check channel counts
        assert stats["by_channel"]["email"] >= 2
        assert stats["by_channel"]["sms"] >= 1
        
        # Delivery rate should be between 0 and 1
        assert 0 <= stats["delivery_rate"] <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])