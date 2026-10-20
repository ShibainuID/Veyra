"""Passport documents: upload, list, download as an attachment, and the ownership reference that makes
Mortality + Theft eligible."""

import hashlib

import pytest

from persistence.db import read_session
from persistence.models import Animal
from tests.support import MANAGER, OPERATOR, OTHER_FARM, VET

PDF = b"%PDF-1.4\n% sample ownership certificate\n%%EOF\n"
SARI = "animal-demo-001"


@pytest.fixture
def post_enrollment(client):
    response = client.post("/api/v1/demo/reset", params={"scenario": "post-enrollment"}, headers=MANAGER)
    assert response.status_code == 200, response.text
    return client


def _upload(client, *, kind="ownership", title="Ownership certificate", data=PDF, filename="sari.pdf",
            content_type="application/pdf", headers=MANAGER, animal_id=SARI):
    fields = {"kind": kind} if title is None else {"kind": kind, "title": title}
    return client.post(f"/api/v1/animals/{animal_id}/documents", headers=headers, data=fields,
                       files={"file": (filename, data, content_type)})


def _theft(client):
    response = client.post(f"/api/v1/animals/{SARI}/insurance-recommendations", headers=MANAGER)
    assert response.status_code == 200, response.text
    return next(r for r in response.json()["results"] if r["product_id"] == "mortality-theft")


def test_ownership_document_makes_mortality_theft_eligible(post_enrollment):
    client = post_enrollment
    before = _theft(client)
    assert before["outcome"] == "unknown" and before["needs_review"] == ["Add an ownership document reference"]

    response = _upload(client, headers=OPERATOR)

    assert response.status_code == 201, response.text
    document = response.json()
    assert (document["kind"], document["title"], document["filename"]) == ("ownership", "Ownership certificate",
                                                                         "sari.pdf")
    assert document["bytes"] == len(PDF) and document["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert document["uploaded_by"] == "A. Pratama"
    with read_session() as session:
        assert session.get(Animal, SARI).ownership_doc_refs == [document["id"]]
    after = _theft(client)
    assert after["outcome"] == "eligible" and after["needs_review"] == []
    ownership = next(r for r in after["reasons"] if r["field"] == "ownership_document")
    assert ownership["status"] == "pass"


def test_document_lists_downloads_and_posts_to_the_passbook(post_enrollment):
    client = post_enrollment
    document = _upload(client, kind="vet_record", title=None, filename="checkup.pdf").json()
    assert document["title"] == "checkup"  # the file name stands in for a missing title

    listed = client.get(f"/api/v1/animals/{SARI}/documents", headers=VET)
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()["items"]] == [document["id"]]

    download = client.get(document["url"])
    assert download.status_code == 200 and download.content == PDF
    assert download.headers["content-disposition"].startswith("attachment")
    assert download.headers["x-content-type-options"] == "nosniff"

    passport = client.get(f"/api/v1/animals/{SARI}/passport", headers=MANAGER).json()
    assert passport["animal"]["ownership_doc_refs"] == []  # only an ownership document is an ownership reference
    line = next(l for l in passport["passbook"]["lines"] if l["event_type"] == "animal.document_added")
    assert (line["title"], line["detail"]) == ("Document on file · Vet record", "checkup")
    events = client.get("/api/v1/audit-events", params={"animal_id": SARI}, headers=MANAGER).json()
    added = next(e for e in events if e["event_type"] == "animal.document_added")
    assert added["data"]["sha256"] == document["sha256"] and added["actor"]["name"] == "W. Santoso"


@pytest.mark.parametrize(("data", "content_type", "filename"), [
    (b"MZ\x90\x00 not a pdf", "application/pdf", "evil.pdf"),  # contents don't match the declared type
    (b"GIF89a", "image/gif", "tag.gif"),  # type not on the allow-list
    (b"", "application/pdf", "empty.pdf"),
])
def test_refuses_bad_files(post_enrollment, data, content_type, filename):
    response = _upload(post_enrollment, data=data, content_type=content_type, filename=filename)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert post_enrollment.get(f"/api/v1/animals/{SARI}/documents", headers=MANAGER).json()["items"] == []


def test_extension_stands_in_for_a_missing_type(post_enrollment):
    response = _upload(post_enrollment, content_type="application/octet-stream")
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == "application/pdf"


def test_refuses_unknown_kind_and_roles_and_other_farms(post_enrollment):
    client = post_enrollment
    assert _upload(client, kind="passport").status_code == 422
    assert _upload(client, headers=VET).status_code == 403
    assert _upload(client, headers=OTHER_FARM).status_code == 404
    assert client.get(f"/api/v1/animals/{SARI}/documents", headers=OTHER_FARM).status_code == 404
    assert _upload(client, animal_id="animal-nope").status_code == 404
