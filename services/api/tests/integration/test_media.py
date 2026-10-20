import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy.exc import IntegrityError

from domain import clock
from persistence.db import SessionLocal
from persistence.media import media_path, signed_url, store_bytes, store_file, verify_signature

PNG = b"\x89PNG\r\n\x1a\n" + b"veyra-frame" * 10


@pytest.fixture
def stored(client):
    with SessionLocal() as session:
        media = store_bytes(session, "farm-wahyu", "frame", PNG, "image/png", "png")
        session.commit()
        return media


def _query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_store_bytes_writes_file_and_hash(stored, settings_env):
    path = media_path(stored)
    assert path == settings_env.media_dir / "farm-wahyu" / f"{stored.id}.png"
    assert path.read_bytes() == PNG
    assert stored.sha256 == hashlib.sha256(PNG).hexdigest()
    assert stored.bytes == len(PNG)


def test_store_file_copies_source(client, tmp_path):
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.7 ownership")
    with SessionLocal() as session:
        media = store_file(session, "farm-wahyu", "document", source, "application/pdf")
        session.commit()
    assert media_path(media).read_bytes() == source.read_bytes()
    assert media_path(media).suffix == ".pdf"


def test_signed_url_round_trips(client, stored):
    url = signed_url(stored.id)

    response = client.get(url)

    assert url.startswith(f"/api/v1/media/{stored.id}?exp=")
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"


@pytest.mark.parametrize("tamper", [
    lambda q: {**q, "sig": "0" * 64},
    lambda q: {**q, "sig": ""},
    lambda q: {**q, "sig": "é"},
    lambda q: {**q, "exp": str(int(q["exp"]) + 60)},
    lambda q: {**q, "exp": "soon"},
    lambda q: {"exp": q["exp"]},
])
def test_tampered_signature_is_not_found(client, stored, tamper):
    response = client.get(f"/api/v1/media/{stored.id}", params=tamper(_query(signed_url(stored.id))))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_expired_signature_is_not_found(client, stored):
    url = signed_url(stored.id, ttl_s=60)
    later = datetime.now(UTC) + timedelta(minutes=2)
    clock.set_now(lambda: later)

    response = client.get(url)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unknown_media_is_not_found(client):
    response = client.get(signed_url("media-000000000000"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_verify_signature_rejects_empty_and_expired(stored):
    query = _query(signed_url(stored.id))
    exp = int(query["exp"])

    assert verify_signature(stored.id, exp, query["sig"]) is True
    assert verify_signature(stored.id, exp, "") is False
    assert verify_signature("", exp, query["sig"]) is False
    assert verify_signature("media-other", exp, query["sig"]) is False
    assert verify_signature(stored.id, int(clock.now().timestamp()) - 1, query["sig"]) is False


@pytest.mark.parametrize("ext", ["png/../../../escaped", "", "p ng", "toolongext"])
def test_store_rejects_unsafe_extension(client, ext, settings_env):
    with SessionLocal() as session, pytest.raises(ValueError):
        store_bytes(session, "farm-wahyu", "frame", PNG, "image/png", ext)
    assert not (settings_env.data_dir / "escaped").exists()


@pytest.mark.parametrize("farm_id", ["../escaped", "farm/wahyu", "Farm-Wahyu", ""])
def test_store_rejects_unsafe_farm_id(client, farm_id):
    with SessionLocal() as session, pytest.raises(ValueError):
        store_bytes(session, farm_id, "frame", PNG, "image/png", "png")


@pytest.mark.parametrize(("kind", "content_type"), [
    ("frame", "text/html"), ("frame", "image/svg+xml"), ("video", "image/png"), ("document", "text/html"),
])
def test_store_rejects_content_type_outside_allow_list(client, kind, content_type):
    with SessionLocal() as session, pytest.raises(ValueError):
        store_bytes(session, "farm-wahyu", kind, PNG, content_type, "png")


def test_failed_flush_removes_written_file(client, settings_env):
    with SessionLocal() as session, pytest.raises(IntegrityError):
        store_bytes(session, "farm-missing", "frame", PNG, "image/png", "png")
    assert list((settings_env.media_dir / "farm-missing").glob("*")) == []


def test_media_response_is_not_sniffed_and_inline(client, stored):
    response = client.get(signed_url(stored.id))

    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-disposition" not in response.headers


def test_document_is_served_as_attachment(client, tmp_path):
    source = tmp_path / "ownership.pdf"
    source.write_bytes(b"%PDF-1.7 ownership")
    with SessionLocal() as session:
        media = store_file(session, "farm-wahyu", "document", source, "application/pdf")
        session.commit()

    response = client.get(signed_url(media.id))

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"
