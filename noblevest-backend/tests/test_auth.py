import pytest
from httpx import AsyncClient
import uuid

@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    email = f"test_{uuid.uuid4().hex[:6]}@noblevest.com"
    payload = {
        "email": email,
        "first_name": "Test",
        "last_name": "User",
        "password": "strongpassword123",
        "client_type": "trader",
        "company": "Test Company",
        "phone": "+12345678"
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email
    assert data["first_name"] == "Test"
    assert data["role"] == "user"

@pytest.mark.asyncio
async def test_login_user(client: AsyncClient):
    email = f"test_{uuid.uuid4().hex[:6]}@noblevest.com"
    # Register first
    payload = {
        "email": email,
        "first_name": "Test",
        "last_name": "User",
        "password": "strongpassword123",
        "client_type": "trader"
    }
    await client.post("/api/v1/auth/register", json=payload)

    # Login
    login_payload = {
        "email": email,
        "password": "strongpassword123"
    }
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "user_id" in data
