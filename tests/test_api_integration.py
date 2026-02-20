"""
Integration tests for the Nexum Core Banking API
Tests end-to-end workflows using FastAPI TestClient
"""

import pytest
from fastapi.testclient import TestClient
from core_banking.api_old import app, banking_system as global_banking_system, BankingSystem


@pytest.fixture
def client():
    """Create a test client for the API with initialized banking system"""
    # Create a test banking system instance
    test_banking_system = BankingSystem(use_sqlite=False)  # Use in-memory storage for tests
    
    # Replace the global banking system for testing
    import core_banking.api_old
    original_banking_system = core_banking.api_old.banking_system
    original_auth_enabled = core_banking.api_old.NEXUM_AUTH_ENABLED
    
    core_banking.api_old.banking_system = test_banking_system
    core_banking.api_old.NEXUM_AUTH_ENABLED = False  # Disable auth for tests
    
    client = TestClient(app)
    
    # Restore original values after test
    yield client
    core_banking.api_old.banking_system = original_banking_system
    core_banking.api_old.NEXUM_AUTH_ENABLED = original_auth_enabled


class TestHealthEndpoints:
    """Test basic health and root endpoints"""
    
    def test_health(self, client):
        """Test health endpoint"""
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data

    def test_root(self, client):
        """Test root endpoint"""
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert "system" in data
        assert "endpoints" in data
        assert data["system"] == "Core Banking System"


class TestCustomerFlow:
    """End-to-end customer management tests"""
    
    def test_create_customer(self, client):
        """Test creating a new customer"""
        r = client.post("/customers", json={
            "first_name": "John",
            "last_name": "Doe", 
            "email": "john@example.com",
            "phone": "+1234567890"
        })
        assert r.status_code == 201
        data = r.json()
        assert "customer_id" in data
        assert "message" in data
        assert data["message"] == "Customer created successfully"

    def test_get_customer(self, client):
        """Test retrieving a customer"""
        # First create a customer
        create_response = client.post("/customers", json={
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@example.com",
            "phone": "+1987654321"
        })
        assert create_response.status_code == 201
        customer_id = create_response.json()["customer_id"]
        
        # Then get the customer
        r = client.get(f"/customers/{customer_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == customer_id
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Smith"

    def test_update_customer(self, client):
        """Test updating customer information"""
        # First create a customer
        create_response = client.post("/customers", json={
            "first_name": "Bob",
            "last_name": "Johnson",
            "email": "bob@example.com"
        })
        assert create_response.status_code == 201
        customer_id = create_response.json()["customer_id"]
        
        # Update the customer
        r = client.put(f"/customers/{customer_id}", json={
            "phone": "+1555123456"
        })
        assert r.status_code == 200
        
        # Verify the update
        get_response = client.get(f"/customers/{customer_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["phone"] == "+1555123456"

    def test_full_customer_lifecycle(self, client):
        """Test complete customer workflow: create → get → update → get accounts"""
        # Create customer
        r = client.post("/customers", json={
            "first_name": "Alice",
            "last_name": "Wilson",
            "email": "alice@example.com",
            "phone": "+1444555666"
        })
        assert r.status_code == 201
        customer_id = r.json()["customer_id"]
        
        # Get customer
        r = client.get(f"/customers/{customer_id}")
        assert r.status_code == 200
        
        # Get customer accounts (should be empty initially)
        r = client.get(f"/customers/{customer_id}/accounts")
        assert r.status_code == 200
        data = r.json()
        assert "accounts" in data
        assert data["accounts"] == []


class TestAccountFlow:
    """End-to-end account management tests"""
    
    def test_create_account(self, client):
        """Test creating a new account"""
        # First create a customer
        customer_response = client.post("/customers", json={
            "first_name": "Michael",
            "last_name": "Brown",
            "email": "michael@example.com"
        })
        assert customer_response.status_code == 201
        customer_id = customer_response.json()["customer_id"]
        
        # Create account
        r = client.post("/accounts", json={
            "customer_id": customer_id,
            "product_type": "checking",
            "currency": "USD",
            "name": "Primary Checking"
        })
        assert r.status_code == 201
        data = r.json()
        assert "account_id" in data
        assert "account_number" in data
        assert "message" in data
        assert data["message"] == "Account created successfully"

    def test_get_account(self, client):
        """Test retrieving account details"""
        # Create customer and account
        customer_response = client.post("/customers", json={
            "first_name": "Sarah",
            "last_name": "Davis",
            "email": "sarah@example.com"
        })
        customer_id = customer_response.json()["customer_id"]
        
        account_response = client.post("/accounts", json={
            "customer_id": customer_id,
            "product_type": "savings",
            "currency": "USD",
            "name": "Emergency Fund"
        })
        account_id = account_response.json()["account_id"]
        
        # Get account details
        r = client.get(f"/accounts/{account_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == account_id
        assert data["product_type"] == "savings"


class TestTransactionFlow:
    """End-to-end transaction tests"""
    
    def test_deposit_flow(self, client):
        """Test making a deposit"""
        # Create customer and account
        customer_response = client.post("/customers", json={
            "first_name": "David",
            "last_name": "Miller",
            "email": "david@example.com"
        })
        customer_id = customer_response.json()["customer_id"]
        
        account_response = client.post("/accounts", json={
            "customer_id": customer_id,
            "product_type": "checking",
            "currency": "USD",
            "name": "Main Account"
        })
        account_id = account_response.json()["account_id"]
        
        # Make deposit
        r = client.post("/transactions/deposit", json={
            "account_id": account_id,
            "amount": {
                "amount": "100.00",
                "currency": "USD"
            },
            "description": "Initial deposit",
            "channel": "online"
        })
        assert r.status_code == 200
        data = r.json()
        assert "transaction_id" in data
        assert "state" in data
        assert data["state"] == "completed"

    def test_withdraw_flow(self, client):
        """Test making a withdrawal"""
        # Create customer and account
        customer_response = client.post("/customers", json={
            "first_name": "Lisa",
            "last_name": "Garcia",
            "email": "lisa@example.com"
        })
        customer_id = customer_response.json()["customer_id"]
        
        account_response = client.post("/accounts", json={
            "customer_id": customer_id,
            "product_type": "checking",
            "currency": "USD",
            "name": "Checking Account"
        })
        account_id = account_response.json()["account_id"]
        
        # First deposit money
        client.post("/transactions/deposit", json={
            "account_id": account_id,
            "amount": {"amount": "50.00", "currency": "USD"},
            "description": "Initial deposit",
            "channel": "online"
        })
        
        # Then withdraw
        r = client.post("/transactions/withdraw", json={
            "account_id": account_id,
            "amount": {"amount": "10.00", "currency": "USD"},
            "description": "ATM withdrawal",
            "channel": "atm"
        })
        assert r.status_code == 200
        data = r.json()
        assert "transaction_id" in data
        assert "state" in data
        assert data["state"] == "completed"

    def test_transfer_flow(self, client):
        """Test transferring money between accounts"""
        # Create customer and two accounts
        customer_response = client.post("/customers", json={
            "first_name": "Robert",
            "last_name": "Taylor",
            "email": "robert@example.com"
        })
        customer_id = customer_response.json()["customer_id"]
        
        # Create source account
        from_account_response = client.post("/accounts", json={
            "customer_id": customer_id,
            "product_type": "checking",
            "currency": "USD",
            "name": "Checking Account"
        })
        from_account_id = from_account_response.json()["account_id"]
        
        # Create destination account
        to_account_response = client.post("/accounts", json={
            "customer_id": customer_id,
            "product_type": "savings",
            "currency": "USD",
            "name": "Savings Account"
        })
        to_account_id = to_account_response.json()["account_id"]
        
        # Deposit money in source account
        client.post("/transactions/deposit", json={
            "account_id": from_account_id,
            "amount": {"amount": "100.00", "currency": "USD"},
            "description": "Initial funding",
            "channel": "online"
        })
        
        # Transfer money
        r = client.post("/transactions/transfer", json={
            "from_account_id": from_account_id,
            "to_account_id": to_account_id,
            "amount": {"amount": "25.00", "currency": "USD"},
            "description": "Transfer to savings",
            "channel": "online"
        })
        assert r.status_code == 200
        data = r.json()
        assert "transaction_id" in data
        assert "state" in data
        assert data["state"] == "completed"

    def test_get_account_transactions(self, client):
        """Test retrieving account transaction history"""
        # Create customer and account
        customer_response = client.post("/customers", json={
            "first_name": "Emma",
            "last_name": "Anderson",
            "email": "emma@example.com"
        })
        customer_id = customer_response.json()["customer_id"]
        
        account_response = client.post("/accounts", json={
            "customer_id": customer_id,
            "product_type": "checking",
            "currency": "USD",
            "name": "Transaction History Test"
        })
        account_id = account_response.json()["account_id"]
        
        # Make some transactions
        client.post("/transactions/deposit", json={
            "account_id": account_id,
            "amount": {"amount": "50.00", "currency": "USD"},
            "description": "Deposit 1",
            "channel": "online"
        })
        
        client.post("/transactions/deposit", json={
            "account_id": account_id,
            "amount": {"amount": "30.00", "currency": "USD"},
            "description": "Deposit 2",
            "channel": "online"
        })
        
        # Get transaction history
        r = client.get(f"/accounts/{account_id}/transactions")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert len(data["items"]) >= 2
        assert data["total"] >= 2


class TestEndpointErrors:
    """Test error handling and edge cases"""
    
    def test_nonexistent_customer(self, client):
        """Test getting a non-existent customer"""
        r = client.get("/customers/nonexistent-id")
        assert r.status_code == 404
        data = r.json()
        assert "detail" in data

    def test_nonexistent_account(self, client):
        """Test getting a non-existent account"""
        r = client.get("/accounts/nonexistent-id")
        assert r.status_code == 404
        data = r.json()
        assert "detail" in data

    def test_invalid_deposit_account(self, client):
        """Test deposit to non-existent account"""
        r = client.post("/transactions/deposit", json={
            "account_id": "nonexistent-account",
            "amount": {"amount": "100.00", "currency": "USD"},
            "description": "Test deposit",
            "channel": "online"
        })
        assert r.status_code in [404, 400, 422]