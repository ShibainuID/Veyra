def test_health_reports_perception_and_llm(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["perception"]["mode"] == "fixture"
    assert set(body["perception"]["capabilities"]) == {"video", "muzzle", "weight", "age"}
    assert body["perception"]["capabilities"]["age"] is True
    assert body["llm"] == {"mode": "offline", "provider": "anthropic", "model": "claude-opus-5-5"}


def test_health_reports_effective_capabilities_for_the_mode(client):
    effective = client.get("/api/v1/health").json()["perception"]["effective"]

    assert effective == {"video": False, "muzzle": False, "weight": False, "age": True}
