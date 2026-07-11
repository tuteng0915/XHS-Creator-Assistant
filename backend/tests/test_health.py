import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


async def get_health_response(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/health")


def test_health_endpoint(app: FastAPI) -> None:
    response = asyncio.run(get_health_response(app))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "creator-workspace-backend",
    }
