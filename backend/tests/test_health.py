async def test_healthz(client):
    response = await client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"].startswith("req_")
