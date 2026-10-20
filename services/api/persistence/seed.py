"""Demo seed and reset.

`fresh` loads `demo/fixtures/herd.json`: two farms, the demo users, cameras, five confirmed animals with
references, estimates, valuations, two active policies, last observations, one open alert, and the wallet.
`post-enrollment` also adds Sari (`animal-demo-001`) as if confirmed from `sample-enrollment-001`.
Age estimates come from the ML age adapter so the seed and live enrollment share one source of truth.
"""

import json
import math
import shutil
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.age import estimate_age
from config import get_settings
from domain import audit, clock
from domain.ids import new_id
from persistence.db import Base, SessionLocal, init_db
from persistence.lifecycle import run_reset_hooks
from persistence.models import (
    Alert, Animal, AnimalReference, Camera, CameraScanZone, DemoSettings, Enrollment, Estimate, Farm, Observation,
    Policy, Track, User, Valuation, WalletEntry,
)

SCENARIOS = ("fresh", "post-enrollment")
DEMO_FARM_ID = "farm-wahyu"
SEED_CONFIRMER = "user-operator"
SEED_VALUER = "user-manager"
SEED_ACTOR = "seed"
REFERENCE_VIEWS = ("muzzle", "teeth", "body")
SEED_BBOX = [0.4, 0.4, 0.2, 0.25]
SARI_ID = "animal-demo-001"
SARI_SAMPLE = "sample-enrollment-001"
SARI_TEETH_FRAMES = ["frame_0006"]
_AGE_COLUMNS = ("range_low", "range_high", "unit", "source", "method_version", "review_required", "review_reason")


def _check_scenario(scenario: str) -> None:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; expected one of {', '.join(SCENARIOS)}")


def _load(name: str) -> dict:
    return json.loads((get_settings().fixtures_dir / name).read_text(encoding="utf-8"))


def _audit(session: Session, farm_id: str, event_type: str, subject_type: str, subject_id: str,
           animal_id: str | None = None, data: dict | None = None) -> None:
    audit.record(session, farm_id=farm_id, actor_type="system", actor_id=SEED_ACTOR, event_type=event_type,
                 subject_type=subject_type, subject_id=subject_id, animal_id=animal_id, data=data)


def _references(session: Session, animal_id: str, now: datetime, quality_note: str,
                enrollment_id: str | None = None, views: dict | None = None) -> None:
    for view in REFERENCE_VIEWS:
        time_s = (views or {}).get(view, {}).get("time_s")
        session.add(AnimalReference(id=new_id("ref"), animal_id=animal_id, view=view, media_id=None,
                                    enrollment_id=enrollment_id, frame_time_s=time_s,
                                    quality={"note": quality_note}, created_at=now))


def _age_estimate(session: Session, animal_id: str, result: dict, now: datetime) -> None:
    evidence = {k: v for k, v in result.items() if k not in _AGE_COLUMNS}
    session.add(Estimate(id=new_id("est"), animal_id=animal_id, kind="age", point=None, evidence=evidence,
                         created_at=now, **{k: result[k] for k in _AGE_COLUMNS}))


def _valuation(session: Session, animal_id: str, weight: Estimate, price: dict, now: datetime) -> None:
    unit_price = price["unit_price_minor_per_kg"]
    session.add(Valuation(
        id=new_id("val"), animal_id=animal_id, version=1, weight_low_kg=weight.range_low,
        weight_high_kg=weight.range_high, weight_basis="estimate", estimate_id=weight.id,
        unit_price_minor_per_kg=unit_price, currency=price["currency"], price_source=price["price_source"],
        price_date=date.fromisoformat(price["price_date"]),
        value_low_minor=math.floor(Decimal(str(weight.range_low)) * unit_price),
        value_high_minor=math.floor(Decimal(str(weight.range_high)) * unit_price),
        confirmed_by=SEED_VALUER, created_at=now,
    ))


def _policy(session: Session, animal: Animal, spec: dict, currency: str, now: datetime) -> None:
    policy = Policy(id=new_id("pol"), farm_id=animal.farm_id, animal_id=animal.id, application_id=None,
                    currency=currency, status="active", created_at=now,
                    effective_date=date.fromisoformat(spec["effective_date"]),
                    expiry_date=date.fromisoformat(spec["expiry_date"]),
                    activation_receipt={"activated": True, "effective_date": spec["effective_date"],
                                        "provider_id": spec["provider_id"], "source": "seed_fixture"},
                    **{k: spec[k] for k in ("product_id", "provider_id", "terms_version", "insured_value_minor",
                                            "premium_minor", "deductible_minor")})
    session.add(policy)
    session.add(WalletEntry(id=new_id("wal"), farm_id=animal.farm_id, entry_type="debit",
                            amount_minor=spec["premium_minor"], currency=currency, created_at=now,
                            description=f"Premium · {animal.id} · {spec['product_id']} (seeded history)"))
    _audit(session, animal.farm_id, "seed.policy_created", "policy", policy.id, animal_id=animal.id,
           data={"product_id": policy.product_id, "provider_id": policy.provider_id,
                 "terms_version": policy.terms_version, "status": policy.status,
                 "insured_value_minor": policy.insured_value_minor, "currency": policy.currency})


def _last_observation(session: Session, animal: Animal, spec: dict, now: datetime) -> Track:
    seen = now - timedelta(minutes=spec["minutes_ago"])
    track = Track(id=new_id("trk"), replay_id=None, camera_id=spec["camera_id"], track_key=f"seed-{animal.id}",
                  animal_id=animal.id, association_status="associated", association_method="seed_fixture",
                  first_seen=seen, last_seen=seen)
    session.add(track)
    session.flush()
    session.add(Observation(id=new_id("obs"), farm_id=animal.farm_id, camera_id=spec["camera_id"], track_id=track.id,
                            animal_id=animal.id, association_status="associated", observed_at=seen,
                            bbox=SEED_BBOX, visibility=spec["visibility"], event="frame", source="simulated"))
    return track


def _seed_animal(session: Session, spec: dict, price: dict, now: datetime) -> None:
    birth_date = date.fromisoformat(spec["birth_date"]) if spec["birth_date"] else None
    animal = Animal(id=spec["id"], farm_id=spec["farm_id"], name=spec["name"], breed=spec["breed"],
                    breed_category=spec["breed_category"], sex=spec["sex"], birth_date=birth_date,
                    identity_status="confirmed", confirmed_by=SEED_CONFIRMER, confirmed_at=now,
                    ownership_doc_refs=spec["ownership_doc_refs"], created_at=now)
    session.add(animal)
    session.flush()
    _references(session, animal.id, now, "seeded reference, footage not attached")
    weight = Estimate(id=new_id("est"), animal_id=animal.id, kind="weight", range_low=spec["weight_kg"]["low"],
                      range_high=spec["weight_kg"]["high"], point=None, unit="kg", source="simulated",
                      method_version="seed_fixture_v1", evidence={}, review_required=False, created_at=now)
    session.add(weight)
    _age_estimate(session, animal.id, estimate_age("", [], documented_birth_date=birth_date, observed_on=now.date()),
                  now)
    session.flush()
    _valuation(session, animal.id, weight, price, now)
    _audit(session, animal.farm_id, "seed.animal_created", "animal", animal.id, animal_id=animal.id,
           data={"name": animal.name, "identity_status": animal.identity_status})
    if spec["policy"]:
        _policy(session, animal, spec["policy"], price["currency"], now)
    track = _last_observation(session, animal, spec["last_observation"], now) if spec["last_observation"] else None
    for alert in spec["alerts"]:
        session.add(Alert(id=new_id("alr"), farm_id=animal.farm_id, kind=alert["kind"], animal_id=animal.id,
                          track_id=track.id if track else None, camera_id=alert["camera_id"],
                          window_start=now - timedelta(minutes=alert["window_start_minutes_ago"]),
                          window_end=now - timedelta(minutes=alert["window_end_minutes_ago"]),
                          rule=alert["rule"], clip=None, status="open", notes=[], created_at=now, updated_at=now))
    session.flush()


def _seed_enrolled_sari(session: Session, price: dict, now: datetime) -> None:
    sample = _load("enrollment_samples.json")[SARI_SAMPLE]
    weight_out = sample["weight"]
    age_out = estimate_age(SARI_SAMPLE, SARI_TEETH_FRAMES)
    enrollment_id = new_id("enr")
    animal = Animal(id=SARI_ID, farm_id=DEMO_FARM_ID, birth_date=None, identity_status="confirmed",
                    confirmed_by=SEED_CONFIRMER, confirmed_at=now, ownership_doc_refs=[],
                    enrollment_id=enrollment_id, created_at=now, **sample["proposed_animal"])
    session.add(animal)
    session.flush()
    session.add(Enrollment(
        id=enrollment_id, farm_id=DEMO_FARM_ID, status="confirmed", sample_key=SARI_SAMPLE, processing_mode="fixture",
        manifest={"views": sample["views"]}, identity=sample["identity"],
        estimates={"weight": weight_out, "age": age_out}, review_reasons=[],
        decision={"outcome": "new_animal", "animal_id": SARI_ID, "decided_by": SEED_CONFIRMER},
        reviewer_id=SEED_CONFIRMER, animal_id=SARI_ID, created_by=SEED_CONFIRMER, created_at=now, updated_at=now,
    ))
    session.flush()
    _references(session, SARI_ID, now, "sample enrollment, footage not attached", enrollment_id, sample["views"])
    weight = Estimate(id=new_id("est"), animal_id=SARI_ID, kind="weight", range_low=weight_out["range_low"],
                      range_high=weight_out["range_high"], point=weight_out["point_kg"], unit=weight_out["unit"],
                      source=weight_out["source"], method_version=weight_out["method_version"],
                      evidence={"band": weight_out["band"], "path": weight_out["path"]},
                      review_required=weight_out["review_required"], review_reason=weight_out["review_reason"],
                      created_at=now)
    session.add(weight)
    _age_estimate(session, SARI_ID, age_out, now)
    session.flush()
    _valuation(session, SARI_ID, weight, price, now)
    _audit(session, DEMO_FARM_ID, "seed.enrollment_confirmed", "enrollment", enrollment_id, animal_id=SARI_ID,
           data={"sample_key": SARI_SAMPLE, "outcome": "new_animal"})
    _audit(session, DEMO_FARM_ID, "seed.animal_created", "animal", SARI_ID, animal_id=SARI_ID,
           data={"name": animal.name, "identity_status": animal.identity_status, "enrollment_id": enrollment_id})
    session.flush()


def seed(session: Session, scenario: str = "fresh") -> None:
    """Insert the demo records into an empty schema. The caller commits."""
    _check_scenario(scenario)
    herd = _load("herd.json")
    price = herd["price"]
    now = clock.now()
    session.add_all(Farm(**farm) for farm in herd["farms"])
    session.flush()
    session.add_all(User(**user) for user in herd["users"])
    session.add_all(Camera(**{k: v for k, v in camera.items() if k != "scan_zone"}) for camera in herd["cameras"])
    session.flush()
    ensure_scan_zones(session, herd, now)
    session.add(DemoSettings(farm_id=DEMO_FARM_ID, updated_at=now))
    # The opening top-up lands a second before the seeded premiums, so the ledger reads in order.
    session.add_all(WalletEntry(id=new_id("wal"), currency=price["currency"], created_at=now - timedelta(seconds=1),
                                **entry) for entry in herd["wallet"])
    session.flush()
    for spec in herd["animals"]:
        _seed_animal(session, spec, price, now)
    if scenario == "post-enrollment":
        _seed_enrolled_sari(session, price, now)


def reset_database(scenario: str = "fresh") -> int:
    """Stop background writers, then empty every table and reseed in one transaction; stored media is wiped
    after the commit. Returns the demo farm's animal count."""
    _check_scenario(scenario)
    run_reset_hooks()
    init_db()
    with SessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        seed(session, scenario)
        session.commit()
        animals = session.scalar(select(func.count()).select_from(Animal).where(Animal.farm_id == DEMO_FARM_ID))
    media_dir = get_settings().media_dir
    shutil.rmtree(media_dir, ignore_errors=True)
    media_dir.mkdir(parents=True, exist_ok=True)
    return animals


def ensure_scan_zones(session: Session, herd: dict | None = None, now: datetime | None = None) -> int:
    """Add the fixture scan zone of every seeded camera that has none yet (a database created before scan zones
    existed gains them on startup). Returns how many were added. The caller commits."""
    herd = herd or _load("herd.json")
    added = 0
    for camera in herd["cameras"]:
        zone = camera.get("scan_zone")
        if not zone or session.get(Camera, camera["id"]) is None or session.get(CameraScanZone, camera["id"]):
            continue
        session.add(CameraScanZone(camera_id=camera["id"], polygon=[list(p) for p in zone["polygon"]],
                                   label=zone["label"], source=zone["source"], calibrated_at=now or clock.now()))
        added += 1
    return added


def seed_if_empty() -> bool:
    with SessionLocal() as session:
        if session.scalar(select(Farm.id).limit(1)) is not None:
            if ensure_scan_zones(session):
                session.commit()
            return False
        seed(session)
        session.commit()
        return True
