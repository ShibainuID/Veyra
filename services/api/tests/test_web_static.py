from fastapi.testclient import TestClient

from main import create_app


def _dist(tmp_path):
    dist = tmp_path / "web"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>veyra shell</html>")
    (dist / "assets" / "app.js").write_text("console.log('veyra')")
    (dist / "favicon.svg").write_text("<svg/>")
    (dist / "manifest.webmanifest").write_text('{"name": "VEYRA"}')
    return dist


def test_built_web_app_is_served_beside_the_api(tmp_path, monkeypatch):
    monkeypatch.setenv("VEYRA_WEB_DIST", str(_dist(tmp_path)))
    with TestClient(create_app()) as client:
        assert "veyra shell" in client.get("/").text
        assert "veyra shell" in client.get("/animals/animal-demo-002").text  # client-side route
        assert client.get("/assets/app.js").text == "console.log('veyra')"
        assert client.get("/favicon.svg").text == "<svg/>"
        manifest = client.get("/manifest.webmanifest")
        assert manifest.json() == {"name": "VEYRA"}
        assert manifest.headers["content-type"].startswith("application/manifest+json")
        assert client.get("/api/v1/health").status_code == 200


def test_unknown_api_paths_keep_the_json_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("VEYRA_WEB_DIST", str(_dist(tmp_path)))
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_no_web_routes_without_a_build(client):
    response = client.get("/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
