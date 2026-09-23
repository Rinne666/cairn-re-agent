from httpx import ASGITransport, AsyncClient

from app.db import get_session
from app.main import app


async def test_demo_api_exercises_full_worker_cycle(session):
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/projects/demo")
            assert response.status_code == 201
            project_id = response.json()["id"]

            graph = await client.get(f"/api/v1/projects/{project_id}/graph")
            assert graph.status_code == 200
            assert len(graph.json()["nodes"]) == 6

            workers = await client.get(f"/api/v1/projects/{project_id}/workers")
            worker_id = workers.json()[0]["id"]
            run = await client.post(f"/api/v1/projects/{project_id}/workers/{worker_id}/run-once")
            assert run.status_code == 200
            assert run.json()["created_nodes"] == 3

            evidence = await client.get(f"/api/v1/projects/{project_id}/graph?graph_type=evidence")
            assert {node["kind"] for node in evidence.json()["nodes"]} == {
                "Observation",
                "Evidence",
                "Hypothesis",
            }
    finally:
        app.dependency_overrides.clear()
