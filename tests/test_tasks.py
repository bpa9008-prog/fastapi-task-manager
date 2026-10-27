from httpx import AsyncClient


async def create_task(client: AsyncClient, owner_id: int, **fields) -> dict:
    payload = {"title": "Task", "owner_id": owner_id, **fields}
    resp = await client.post("/tasks", json=payload)
    assert resp.status_code == 201
    return resp.json()


async def test_create_task(client: AsyncClient, user: dict):
    resp = await client.post(
        "/tasks",
        json={"title": "Write tests", "description": "pytest", "owner_id": user["id"]},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Write tests"
    assert body["description"] == "pytest"
    assert body["done"] is False
    assert body["owner_id"] == user["id"]


async def test_create_task_unknown_owner(client: AsyncClient):
    resp = await client.post("/tasks", json={"title": "Orphan", "owner_id": 999})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"


async def test_list_tasks_done_filter_and_pagination(client: AsyncClient, user: dict):
    for i in range(1, 6):
        await create_task(client, user["id"], title=f"Task {i}", done=i % 2 == 0)

    resp = await client.get("/tasks", params={"done": True})
    assert resp.status_code == 200
    assert [t["title"] for t in resp.json()] == ["Task 2", "Task 4"]

    resp = await client.get("/tasks", params={"done": False})
    assert [t["title"] for t in resp.json()] == ["Task 1", "Task 3", "Task 5"]

    page1 = (await client.get("/tasks", params={"limit": 2, "offset": 0})).json()
    page2 = (await client.get("/tasks", params={"limit": 2, "offset": 2})).json()
    page3 = (await client.get("/tasks", params={"limit": 2, "offset": 4})).json()
    assert [t["id"] for t in page1] == [1, 2]
    assert [t["id"] for t in page2] == [3, 4]
    assert [t["id"] for t in page3] == [5]

    resp = await client.get("/tasks", params={"done": False, "limit": 1, "offset": 1})
    assert [t["title"] for t in resp.json()] == ["Task 3"]


async def test_list_tasks_invalid_limit(client: AsyncClient):
    resp = await client.get("/tasks", params={"limit": 0})

    assert resp.status_code == 422


async def test_patch_task_updates_only_passed_fields(client: AsyncClient, user: dict):
    task = await create_task(
        client, user["id"], title="Original", description="Keep me"
    )

    resp = await client.patch(f"/tasks/{task['id']}", json={"done": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["done"] is True
    assert body["title"] == "Original"
    assert body["description"] == "Keep me"
    assert body["owner_id"] == task["owner_id"]
    assert body["created_at"] == task["created_at"]


async def test_delete_task_then_get_404(client: AsyncClient, user: dict):
    task = await create_task(client, user["id"])

    resp = await client.delete(f"/tasks/{task['id']}")
    assert resp.status_code == 204

    resp = await client.get(f"/tasks/{task['id']}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


async def test_process_time_header(client: AsyncClient):
    resp = await client.get("/tasks")

    assert resp.status_code == 200
    assert "X-Process-Time" in resp.headers
    assert float(resp.headers["X-Process-Time"]) >= 0
