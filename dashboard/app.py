#!/usr/bin/env python3
"""
Nexum Core Banking Dashboard - FastAPI Backend

Track 3: Admin Pages (RBAC/Users, Audit Trail, Workflows, Settings, Notifications)
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from decimal import Decimal

# Add parent to path so core_banking package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# Import core banking modules
from core_banking.storage import SQLiteStorage
from core_banking.rbac import RBACManager, Permission
from core_banking.audit import AuditTrail
from core_banking.workflows import WorkflowEngine
from core_banking.notifications import NotificationEngine
from core_banking.compliance import ComplianceEngine
from core_banking.tenancy import TenantManager


def create_app() -> FastAPI:
    """Create and configure the FastAPI app"""
    app = FastAPI(
        title="Nexum Core Banking Dashboard",
        description="Professional dashboard for core banking operations",
        version="1.0.0"
    )

    # Initialize storage and managers
    db_path = Path(__file__).parent.parent / "core_banking.db"
    storage = SQLiteStorage(str(db_path))
    
    # Initialize managers - need customer manager for compliance engine
    rbac = RBACManager(storage)
    audit = AuditTrail(storage)
    workflows = WorkflowEngine(storage, audit)
    notifications = NotificationEngine(storage, audit)
    
    # Import customer manager for compliance
    try:
        from core_banking.customers import CustomerManager
        customer_manager = CustomerManager(storage, audit)
        compliance = ComplianceEngine(storage, customer_manager, audit)
    except Exception as e:
        compliance = None
        print(f"Warning: Could not initialize compliance engine: {e}")
    
    try:
        tenancy = TenantManager(storage, audit)
    except Exception as e:
        tenancy = None
        print(f"Warning: Could not initialize tenancy manager: {e}")
    
    config = None  # Simplified for now

    # Mount static files
    static_path = Path(__file__).parent / "static"
    static_path.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # Root endpoint - serve HTML
    @app.get("/", response_class=HTMLResponse)
    async def dashboard_root():
        """Main dashboard page"""
        return get_dashboard_html()

    # RBAC/Users API endpoints
    @app.get("/api/users")
    async def get_users(role: Optional[str] = None, is_active: Optional[bool] = None):
        """Get all users with optional filters"""
        try:
            users = rbac.list_users(role=role, is_active=is_active)
            user_data = []
            
            for user in users:
                user_dict = {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "is_active": user.is_active,
                    "is_locked": user.is_locked,
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    "created_at": user.created_at.isoformat(),
                    "roles": []
                }
                
                # Get role names
                for role_id in user.roles:
                    role = rbac.get_role(role_id)
                    if role:
                        user_dict["roles"].append({
                            "id": role.id,
                            "name": role.name
                        })
                
                user_data.append(user_dict)
                
            return {"users": user_data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/users/{user_id}")
    async def get_user_detail(user_id: str):
        """Get detailed user information"""
        try:
            user = rbac.get_user(user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Get user permissions
            permissions = rbac.get_user_permissions(user_id)
            
            # Get user sessions
            sessions = storage.find('sessions', {'user_id': user_id})
            active_sessions = []
            for session_data in sessions:
                if session_data.get('is_active'):
                    active_sessions.append({
                        "id": session_data['id'],
                        "ip_address": session_data.get('ip_address'),
                        "user_agent": session_data.get('user_agent'),
                        "created_at": session_data['created_at'],
                        "expires_at": session_data['expires_at']
                    })
            
            # Get role details
            role_details = []
            for role_id in user.roles:
                role = rbac.get_role(role_id)
                if role:
                    role_details.append({
                        "id": role.id,
                        "name": role.name,
                        "description": role.description,
                        "permissions": len(role.permissions)
                    })
            
            return {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "is_active": user.is_active,
                    "is_locked": user.is_locked,
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    "created_at": user.created_at.isoformat(),
                    "created_by": user.created_by,
                    "branch_id": user.branch_id
                },
                "roles": role_details,
                "permissions": [p.value for p in permissions],
                "active_sessions": active_sessions
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/roles")
    async def get_roles():
        """Get all roles"""
        try:
            roles = rbac.list_roles()
            role_data = []
            
            for role in roles:
                role_data.append({
                    "id": role.id,
                    "name": role.name,
                    "description": role.description,
                    "is_system_role": role.is_system_role,
                    "permission_count": len(role.permissions),
                    "permissions": [p.value for p in role.permissions]
                })
            
            return {"roles": role_data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/sessions")
    async def get_active_sessions():
        """Get all active sessions"""
        try:
            all_sessions = storage.load_all('sessions')
            active_sessions = []
            
            for session_data in all_sessions:
                if session_data.get('is_active'):
                    user = rbac.get_user(session_data['user_id'])
                    active_sessions.append({
                        "id": session_data['id'],
                        "user_id": session_data['user_id'],
                        "username": user.username if user else "Unknown",
                        "ip_address": session_data.get('ip_address'),
                        "user_agent": session_data.get('user_agent'),
                        "created_at": session_data['created_at'],
                        "expires_at": session_data['expires_at']
                    })
            
            return {"sessions": active_sessions}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Audit Trail API endpoints
    @app.get("/api/audit")
    async def get_audit_events(
        event_type: Optional[str] = None,
        user: Optional[str] = None,
        entity_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ):
        """Get audit events with filters"""
        try:
            # Get all audit events
            all_events = audit.get_events(limit=limit + offset)
            filtered_events = []
            
            for event in all_events[offset:]:
                # Apply filters
                if event_type and event.event_type.value != event_type:
                    continue
                if user and event.user_id != user:
                    continue
                if entity_type and event.entity_type != entity_type:
                    continue
                if date_from:
                    from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                    if event.timestamp < from_date:
                        continue
                if date_to:
                    to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                    if event.timestamp > to_date:
                        continue
                
                # Get username
                username = "System"
                if event.user_id:
                    user_obj = rbac.get_user(event.user_id)
                    if user_obj:
                        username = user_obj.username
                
                filtered_events.append({
                    "id": event.id,
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type.value,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "description": event.description,
                    "user_id": event.user_id,
                    "username": username,
                    "hash": event.hash,
                    "previous_hash": event.previous_hash
                })
            
            return {"events": filtered_events[:limit]}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/audit/{event_id}")
    async def get_audit_event_detail(event_id: str):
        """Get detailed audit event information"""
        try:
            event = audit.get_event(event_id)
            if not event:
                raise HTTPException(status_code=404, detail="Event not found")
            
            # Get username
            username = "System"
            if event.user_id:
                user_obj = rbac.get_user(event.user_id)
                if user_obj:
                    username = user_obj.username
            
            return {
                "event": {
                    "id": event.id,
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type.value,
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "description": event.description,
                    "data": event.data,
                    "user_id": event.user_id,
                    "username": username,
                    "hash": event.hash,
                    "previous_hash": event.previous_hash
                }
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/audit/verify")
    async def verify_audit_chain():
        """Verify audit trail hash chain integrity"""
        try:
            is_valid = audit.verify_chain()
            return {"chain_valid": is_valid}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Workflows API endpoints
    @app.get("/api/workflows")
    async def get_active_workflows():
        """Get active workflow instances"""
        try:
            from core_banking.workflows import WorkflowStatus
            active_workflows = workflows.get_workflows(status=WorkflowStatus.IN_PROGRESS)
            workflow_data = []
            
            for workflow in active_workflows:
                # Get current step from workflow steps
                current_step = None
                for step in workflow.steps:
                    if step.step_number == workflow.current_step:
                        current_step = step
                        break
                
                workflow_data.append({
                    "id": workflow.id,
                    "type": workflow.workflow_type.value,
                    "entity_type": workflow.entity_type,
                    "entity_id": workflow.entity_id,
                    "status": workflow.status.value,
                    "current_step": current_step.name if current_step else None,
                    "current_step_status": current_step.status.value if current_step else None,
                    "created_at": workflow.created_at.isoformat(),
                    "sla_deadline": getattr(workflow, 'sla_deadline', datetime.now()).isoformat(),
                    "initiated_by": workflow.initiated_by
                })
            
            return {"workflows": workflow_data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/workflows/{workflow_id}")
    async def get_workflow_detail(workflow_id: str):
        """Get detailed workflow information"""
        try:
            workflow = workflows.get_workflow(workflow_id)
            if not workflow:
                raise HTTPException(status_code=404, detail="Workflow not found")
            
            current_step = None
            for step in workflow.steps:
                if step.step_number == workflow.current_step:
                    current_step = step
                    break
            
            step_data = []
            for step in workflow.steps:
                step_data.append({
                    "id": step.id,
                    "name": step.name,
                    "step_type": step.step_type.value,
                    "status": step.status.value,
                    "assigned_to": step.assigned_to,
                    "completed_by": step.completed_by,
                    "created_at": step.created_at.isoformat(),
                    "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                    "comments": step.comments,
                    "order": step.step_number
                })
            
            return {
                "workflow": {
                    "id": workflow.id,
                    "type": workflow.workflow_type.value,
                    "entity_type": workflow.entity_type,
                    "entity_id": workflow.entity_id,
                    "status": workflow.status.value,
                    "created_at": workflow.created_at.isoformat(),
                    "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
                    "sla_deadline": getattr(workflow, 'sla_deadline', datetime.now()).isoformat(),
                    "initiated_by": workflow.initiated_by
                },
                "steps": step_data,
                "current_step_id": current_step.id if current_step else None
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/workflows/{workflow_id}/approve")
    async def approve_workflow_step(workflow_id: str, request: Request):
        """Approve current workflow step"""
        try:
            data = await request.json()
            comments = data.get('comments', '')
            user_id = data.get('user_id', 'system')  # In real app, get from auth
            
            workflow = workflows.get_workflow(workflow_id)
            if not workflow:
                raise HTTPException(status_code=404, detail="Workflow not found")
            
            success = workflows.approve_step(workflow_id, workflow.current_step, user_id, comments)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to approve step")
            
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/workflows/definitions")
    async def get_workflow_definitions():
        """Get workflow templates/definitions"""
        try:
            definitions = workflows.list_definitions()
            def_data = []
            
            for definition in definitions:
                def_data.append({
                    "id": definition.id,
                    "name": definition.name,
                    "workflow_type": definition.workflow_type.value,
                    "description": definition.description,
                    "step_count": len(definition.steps),
                    "is_active": definition.is_active
                })
            
            return {"definitions": def_data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Notifications API endpoints
    @app.get("/api/notifications")
    async def get_notifications(
        status: Optional[str] = None,
        channel: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 100
    ):
        """Get notification log"""
        try:
            # Get all notifications directly from storage since the method requires recipient_id
            all_notifications_data = storage.load_all('notifications')
            notification_data = []
            
            for data in all_notifications_data[:limit * 2]:  # Get more to filter
                # Apply filters
                if status and data.get('status') != status:
                    continue
                if channel and data.get('channel') != channel:
                    continue
                if type and data.get('notification_type') != type:
                    continue
                
                notification_data.append({
                    "id": data.get('id', ''),
                    "recipient": data.get('recipient', ''),
                    "channel": data.get('channel', ''),
                    "type": data.get('notification_type', ''),
                    "status": data.get('status', ''),
                    "subject": data.get('subject', ''),
                    "created_at": data.get('created_at', ''),
                    "sent_at": data.get('sent_at', None),
                    "error_message": data.get('error_message', '')
                })
                
                if len(notification_data) >= limit:
                    break
            
            return {"notifications": notification_data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/notifications/stats")
    async def get_notification_stats():
        """Get notification delivery statistics"""
        try:
            stats = notifications.get_delivery_stats()
            return stats
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/notifications/templates")
    async def get_notification_templates():
        """Get notification templates"""
        try:
            templates = notifications.list_templates()
            template_data = []
            
            for template in templates:
                template_data.append({
                    "id": template.id,
                    "name": template.name,
                    "type": template.notification_type.value,
                    "channel": template.channel.value,
                    "subject": template.subject_template,
                    "is_active": template.is_active
                })
            
            return {"templates": template_data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Compliance API endpoints
    @app.get("/api/compliance/alerts")
    async def get_compliance_alerts():
        """Get compliance alerts"""
        try:
            if not compliance:
                return {"alerts": []}
                
            alerts = compliance.get_suspicious_alerts()
            alert_data = []
            
            for alert in alerts:
                # Map the severity from risk_score
                if alert.risk_score >= 80:
                    severity = "high"
                elif alert.risk_score >= 50:
                    severity = "medium"
                else:
                    severity = "low"
                
                alert_data.append({
                    "id": alert.id,
                    "customer_id": alert.customer_id,
                    "alert_type": alert.activity_type.value,
                    "severity": severity,
                    "status": alert.status,
                    "description": alert.description,
                    "created_at": alert.created_at.isoformat(),
                    "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                    "risk_score": float(alert.risk_score)
                })
            
            return {"alerts": alert_data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Settings API endpoints
    @app.get("/api/settings")
    async def get_system_settings():
        """Get system settings and status"""
        try:
            settings_data = {
                "database": {
                    "type": "SQLite",
                    "path": str(db_path),
                    "status": "Connected" if db_path.exists() else "Disconnected",
                    "size_mb": round(db_path.stat().st_size / 1024 / 1024, 2) if db_path.exists() else 0
                },
                "encryption": {
                    "status": "Enabled" if config and hasattr(config, 'encryption_enabled') else "Unknown",
                    "algorithm": "AES-256" if config else "Unknown"
                },
                "kafka": {
                    "status": "Not configured",
                    "brokers": []
                },
                "system": {
                    "version": "1.0.0",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "uptime_hours": 0
                }
            }
            
            # Add tenant info if available
            if tenancy:
                tenants = tenancy.list_tenants()
                settings_data["tenancy"] = {
                    "enabled": True,
                    "tenant_count": len(tenants),
                    "tenants": [
                        {
                            "id": t.id,
                            "name": t.name,
                            "is_active": t.is_active,
                            "created_at": t.created_at.isoformat()
                        } for t in tenants
                    ]
                }
            else:
                settings_data["tenancy"] = {"enabled": False}
            
            return settings_data
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


def get_dashboard_html() -> str:
    """Generate the main dashboard HTML"""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nexum Core Banking Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <script src="https://unpkg.com/htm/preact/standalone.umd.js"></script>
    <style>
        .sidebar { background: linear-gradient(135deg, #1A3C78 0%, #2563eb 100%); }
        .nav-item:hover { background: rgba(255,255,255,0.1); }
        .nav-item.active { background: rgba(255,255,255,0.2); border-left: 4px solid #fbbf24; }
        .card { background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .btn-primary { background: #1A3C78; }
        .btn-primary:hover { background: #2563eb; }
        .status-pending { color: #f59e0b; }
        .status-completed { color: #10b981; }
        .status-failed { color: #ef4444; }
        .hash-chain-valid { color: #10b981; }
        .hash-chain-invalid { color: #ef4444; }
    </style>
</head>
<body class="bg-gray-50">
    <div id="app"></div>
    <script type="module" src="/static/app.js"></script>
</body>
</html>'''


if __name__ == "__main__":
    import uvicorn
    
    app = create_app()
    print("🏦 Nexum Core Banking Dashboard")
    print("💻 Starting on http://localhost:8890")
    print("📊 Dashboard: http://localhost:8890/")
    print("🔌 API docs: http://localhost:8890/docs")
    print("🛑 Press Ctrl+C to quit")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8890,
        reload=False,
        access_log=False
    )