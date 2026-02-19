#!/usr/bin/env python3
"""
Test script to verify JWT authentication implementation
"""

import os
import jwt
import requests
from datetime import datetime, timezone, timedelta

# Set auth enabled for testing
os.environ['NEXUM_AUTH_ENABLED'] = 'true'
os.environ['JWT_SECRET'] = 'test-secret-key'

# Import after setting env vars
import core_banking.api as api_module
from fastapi.testclient import TestClient

app = api_module.app

client = TestClient(app)

def test_jwt_authentication():
    """Test JWT authentication flow"""
    print("Testing JWT authentication...")
    
    # 1. Test login endpoint (should work without auth)
    login_response = client.post("/rbac/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    
    print(f"Login status: {login_response.status_code}")
    if login_response.status_code == 200:
        login_data = login_response.json()
        print(f"Login successful. Token type: {login_data.get('token_type')}")
        
        # Extract token
        access_token = login_data.get('access_token')
        if access_token:
            print(f"Access token received: {access_token[:50]}...")
            
            # 2. Test accessing a protected endpoint with token
            headers = {"Authorization": f"Bearer {access_token}"}
            protected_response = client.post("/customers", 
                json={
                    "first_name": "Test",
                    "last_name": "Customer",
                    "email": "test@example.com"
                },
                headers=headers
            )
            
            print(f"Protected endpoint status: {protected_response.status_code}")
            
            # 3. Test accessing protected endpoint without token
            no_auth_response = client.post("/customers", 
                json={
                    "first_name": "Test2",
                    "last_name": "Customer2",
                    "email": "test2@example.com"
                }
            )
            
            print(f"No auth endpoint status: {no_auth_response.status_code}")
            
        else:
            print("No access token in response")
    else:
        print(f"Login failed: {login_response.text}")

def test_public_endpoints():
    """Test that public endpoints work without authentication"""
    print("\nTesting public endpoints...")
    
    # Health check should work
    health_response = client.get("/health")
    print(f"Health endpoint status: {health_response.status_code}")
    
def test_rate_limiting():
    """Test rate limiting"""
    print("\nTesting rate limiting...")
    
    # Make multiple requests quickly (this is simplified - real test would need more requests)
    for i in range(5):
        response = client.get("/health")
        print(f"Request {i+1} status: {response.status_code}")

if __name__ == "__main__":
    test_public_endpoints()
    test_jwt_authentication()
    test_rate_limiting()
    print("\nAuthentication testing completed!")