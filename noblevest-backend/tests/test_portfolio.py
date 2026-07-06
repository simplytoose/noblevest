import pytest
from httpx import AsyncClient
import uuid

@pytest.mark.asyncio
async def test_portfolio_overview_unauthorized(client: AsyncClient):
    response = await client.get("/api/v1/portfolio/")
    assert response.status_code == 401
