import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app import queue_worker

@pytest.fixture(autouse=True)
async def cleanup_redis_client():
    yield
    # Al terminar todos los tests, cerramos el cliente de Redis
    if queue_worker._redis_client:
        try:
            await queue_worker._redis_client.aclose()
        except Exception:
            pass
        queue_worker._redis_client = None

@pytest.mark.asyncio
async def test_create_task():
    """Valida que POST /tasks devuelva 202 y un job_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/tasks", json={"query": "Test de RAG", "critical": False})
    assert response.status_code == 202
    assert "job_id" in response.json()

@pytest.mark.asyncio
async def test_get_task_not_found():
    """Valida que GET /tasks/{id} devuelva 404 para IDs inexistentes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/tasks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_validation_error():
    """Valida la protección de Pydantic."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Mandamos un JSON vacío para que Pydantic lo rechace
        response = await ac.post("/tasks", json={})
    assert response.status_code == 422