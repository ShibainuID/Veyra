"""The natural-language locator (plan Section 4: assistant).

Two steps, and only the first may use a language model:
1. `parse` turns the question into a `QueryIntent`. Claude does it when live (`adapters/llm/query.py`); the regex
   parser does it offline or whenever the live call fails. Either way, animal refs are validated against the
   farm's animals and anything else is dropped (and reported as not found).
2. `resolve` reads the farm's records and writes the answer itself, sentence by sentence from those records, with
   a fact per value (`record_type`, `record_id`) and a `missing` list for evidence that is not on record.

Location answers state the camera and the time of the last associated observation, never a current location;
an observation older than `STALE_AFTER` adds "It may have moved since."
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.llm.query import QueryIntent, parse_with_claude
from config import Settings
from domain import alerts as alert_rules
from domain import clock
from domain.catalog import load_catalog, provider_name
from domain.passbook import product_name
from domain.passport import list_herd
from persistence.db import read_session
from persistence.models import Animal, Camera, Observation, Policy

WANT_ORDER = ("passport", "location", "coverage", "alerts")
DEFAULT_WANTS = {"animal_lookup": ["passport"], "location_lookup": ["location"], "coverage_lookup": ["coverage"],
                 "alert_lookup": ["alerts"]}
STALE_AFTER = timedelta(minutes=60)
KEYWORDS = {
    "location": r"\bwhere\b|last\s+seen|\bseen\b|\blocation\b|\blocated\b|\bcameras?\b|\bpen\b",
    "coverage": r"\bcoverage\b|\bcovered\b|\bpolic(?:y|ies)\b|\binsured\b|\binsurance\b",
    "alerts": r"\balerts?\b|\bwarnings?\b",
    "passport": r"\bshow\b|\bpassport\b|\bdetails?\b|\btell me about\b|\bprofile\b",
}
_ID_PATTERN = re.compile(r"\banimal-[a-z]+-\d+\b|\b\d{3}\b", re.IGNORECASE)
_NAMED_PATTERN = re.compile(r"\b(?:where\s+(?:is|was)|show(?:\s+me)?|find|locate|about)\s+([A-Za-z][\w'-]*)",
                            re.IGNORECASE)
_NOT_NAMES = {"the", "my", "all", "me", "our", "animals", "animal", "cows", "cattle", "herd", "everyone", "which",
              "what", "any", "open", "alerts", "alert", "coverage", "policies", "it", "she", "he", "they", "a", "an",
              "last", "this", "that", "every", "each", "insurance", "warnings", "details", "passport"}
FALLBACK_ANSWER = (
    "I can answer from this farm's records: an animal's passport (\"Show me animal-demo-002\"), where an animal "
    "was last observed on camera (\"Where is Dewi?\"), its active coverage (\"What coverage does Bima have?\"), "
    "and open alerts (\"Which animals have open alerts?\").")


MAX_ECHO = 40


@dataclass
class ParsedQuery:
    intent: QueryIntent
    unmatched_refs: list[str] = field(default_factory=list)  # safe to echo: typed by the user, at most 40 chars
    parsed_by: str = "simulated"
    fallback_reason: str | None = None
    dropped_refs: int = 0  # refs not in the farm that are not echoed (e.g. a model ref absent from the text)

    @property
    def has_unmatched(self) -> bool:
        return bool(self.unmatched_refs) or self.dropped_refs > 0


def _echoable(refs: list[str], text: str) -> tuple[list[str], int]:
    """Only echo refs the user actually typed (case-insensitively), cut to `MAX_ECHO` characters."""
    lowered = text.lower()
    echo = [ref[:MAX_ECHO] for ref in refs if ref and ref.lower() in lowered]
    return echo, len(refs) - len(echo)


def _match_ref(ref: str, animals: list[dict]) -> str | None:
    value = ref.strip().lower()
    if re.fullmatch(r"\d{3}", value):
        value = f"animal-demo-{value}"
    for animal in animals:
        if value in (animal["id"].lower(), animal["name"].lower()):
            return animal["id"]
    return None


def validate_refs(refs: list[str], animals: list[dict]) -> tuple[list[str], list[str]]:
    """Map refs (ids, short numbers, or names) to the farm's animal ids; return (ids, refs not in the farm)."""
    ids, dropped = [], []
    for ref in refs:
        animal_id = _match_ref(ref, animals)
        if animal_id is None:
            dropped.append(ref)
        elif animal_id not in ids:
            ids.append(animal_id)
    return ids, dropped


def _intent_for(wants: list[str], has_refs: bool) -> str:
    if "location" in wants:
        return "location_lookup"
    if has_refs and "passport" in wants:
        return "animal_lookup"
    if "coverage" in wants:
        return "coverage_lookup"
    if "alerts" in wants:
        return "alert_lookup"
    return "animal_lookup" if has_refs else "unknown"


def parse_offline(text: str, animals: list[dict]) -> tuple[QueryIntent, list[str]]:
    """The deterministic parser: ids (`animal-demo-001` or `001`), names, and keywords. Returns the intent and the
    animal-like refs that are not in the farm."""
    refs: list[tuple[int, str]] = []
    unmatched: list[str] = []
    for match in _ID_PATTERN.finditer(text):
        animal_id = _match_ref(match.group(0), animals)
        if animal_id is None:
            unmatched.append(match.group(0))
        else:
            refs.append((match.start(), animal_id))
    lowered = text.lower()
    for animal in animals:
        for match in re.finditer(rf"\b{re.escape(animal['name'].lower())}\b", lowered):
            refs.append((match.start(), animal["id"]))
    for match in _NAMED_PATTERN.finditer(text):
        word = re.sub(r"'s$", "", match.group(1))
        if word.lower() in _NOT_NAMES or _ID_PATTERN.fullmatch(word) or word.lower().startswith("animal-"):
            continue
        if _match_ref(word, animals) is None and word not in unmatched:
            unmatched.append(word)
    animal_ids: list[str] = []
    for _, animal_id in sorted(refs):
        if animal_id not in animal_ids:
            animal_ids.append(animal_id)
    wants = [want for want in WANT_ORDER if re.search(KEYWORDS[want], lowered)]
    if animal_ids and not wants:
        wants = ["passport"]
    if not animal_ids and wants == ["passport"] and not unmatched:
        wants = []
    intent = _intent_for(wants, bool(animal_ids or unmatched))
    if intent == "unknown" and not unmatched:
        wants = []
    return QueryIntent(intent=intent, animal_refs=animal_ids, wants=wants), unmatched


def parse(settings: Settings, text: str, animals: list[dict], *, client: Any | None = None) -> ParsedQuery:
    live = parse_with_claude(settings, text, animals, client=client)
    if live.output is not None:
        ids, dropped = validate_refs(live.output.animal_refs, animals)
        wants = [w for w in WANT_ORDER if w in live.output.wants] or DEFAULT_WANTS.get(live.output.intent, [])
        intent = QueryIntent(intent=live.output.intent, animal_refs=ids, wants=wants)
        echo, silent = _echoable(dropped, text)
        return ParsedQuery(intent, echo, "live", None, silent)
    intent, unmatched = parse_offline(text, animals)
    echo, silent = _echoable(unmatched, text)
    return ParsedQuery(intent, echo, "simulated", live.fallback_reason, silent)


# --- resolution ---------------------------------------------------------------------------------------------


def _money(minor: int | None, currency: str | None) -> str:
    if minor is None:
        return "unknown"
    # Amount first, then the currency, as everywhere else in the app (2,496.00 USD).
    return f"{minor // 100:,}.{minor % 100:02d} {currency or ''}".strip()


def _ago(at: datetime, now: datetime) -> str:
    minutes = int((now - at).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 48:
        rest = minutes % 60
        return f"{hours} h {rest} min ago" if rest and hours < 6 else f"{hours} h ago"
    return f"{hours // 24} days ago"


def _zone(offset_minutes: int | None) -> tzinfo:
    """The asker's UTC offset (sent by the browser, minutes east of UTC), or UTC when it is missing."""
    if not offset_minutes:
        return UTC
    hours, minutes = divmod(abs(offset_minutes), 60)
    sign = "+" if offset_minutes > 0 else "-"
    return timezone(timedelta(minutes=offset_minutes), f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else ""))


def _when(at: datetime, now: datetime, zone: tzinfo = UTC) -> str:
    local, today = at.astimezone(zone), now.astimezone(zone)
    clock_text = local.strftime("%H:%M") if local.date() == today.date() else local.strftime("%Y-%m-%d %H:%M")
    return f"{clock_text} {local.tzname()}"


def _fact(label: str, value: Any, record_type: str, record_id: str) -> dict:
    return {"label": label, "value": value, "record_type": record_type, "record_id": record_id}


@dataclass
class _Answer:
    sentences: list[str] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    records: dict = field(default_factory=lambda: {"animals": [], "last_observations": [], "coverage": [],
                                                   "alerts": []})

    def miss(self, key: str) -> None:
        if key not in self.missing:
            self.missing.append(key)


def _label(card: dict) -> str:
    return f"{card['name']} ({card['id']})"


def _passport(out: _Answer, card: dict) -> None:
    sex = {"M": "male", "F": "female"}.get(card["sex"], card["sex"])
    text = f"{_label(card)} is a {sex} {card['breed']} ({card['breed_category']}); identity {card['identity_status']}."
    out.facts += [_fact("Name", card["name"], "animal", card["id"]),
                  _fact("Breed", card["breed"], "animal", card["id"]),
                  _fact("Sex", sex, "animal", card["id"]),
                  _fact("Identity status", card["identity_status"], "animal", card["id"])]
    for kind in ("age", "weight"):
        estimate = card.get(kind)
        if estimate and estimate.get("range_low") is not None:
            low, high = estimate["range_low"], estimate["range_high"]
            span = f"{low:g}" if high is None or high == low else f"{low:g}–{high:g}"
            out.facts.append(_fact(f"{kind.title()} estimate", f"{span} {estimate['unit']} ({estimate['source']})",
                                   "animal", card["id"]))
    valuation = card.get("valuation")
    if valuation:
        value = (f"{_money(valuation['value_low_minor'], None)}–"
                 f"{_money(valuation['value_high_minor'], valuation['currency'])}")
        text += f" Indicative value {value} (valuation v{valuation['version']})."
        out.facts.append(_fact("Indicative value", value, "animal", card["id"]))
    else:
        text += " No confirmed valuation is on record."
        out.miss("valuation")
    out.sentences.append(text)


def _last_observation(session: Session, farm_id: str, animal_id: str) -> Observation | None:
    query = (select(Observation)
             .where(Observation.farm_id == farm_id, Observation.animal_id == animal_id,
                    Observation.association_status == "associated")
             .order_by(Observation.observed_at.desc(), Observation.id.desc()).limit(1))
    return session.scalar(query)


def _location(out: _Answer, session: Session, farm_id: str, card: dict, cameras: dict[str, str],
              now: datetime, zone: tzinfo = UTC) -> None:
    observation = _last_observation(session, farm_id, card["id"])
    if observation is None:
        out.sentences.append(f"No camera observation is on record for {_label(card)}.")
        out.miss("last_observation")
        return
    camera = cameras.get(observation.camera_id, observation.camera_id)
    text = (f"{_label(card)} was last observed on {camera} at {_when(observation.observed_at, now, zone)} "
            f"({_ago(observation.observed_at, now)}).")
    if now - observation.observed_at > STALE_AFTER:
        text += " It may have moved since."
    out.sentences.append(text)
    out.facts += [_fact("Last observed on", camera, "camera", observation.camera_id),
                  _fact("Last observed at", clock.isoformat(observation.observed_at), "observation", observation.id)]
    out.records["last_observations"].append({
        "id": observation.id, "animal_id": card["id"], "camera_id": observation.camera_id, "camera_name": camera,
        "observed_at": clock.isoformat(observation.observed_at), "bbox": list(observation.bbox),
        "visibility": observation.visibility, "association_status": observation.association_status,
        "track_id": observation.track_id})


def _coverage(out: _Answer, session: Session, farm_id: str, card: dict) -> None:
    coverage = card["coverage"]
    entry = {"animal_id": card["id"], "status": coverage["status"], "policy_id": coverage["policy_id"],
             "product_id": coverage["product_id"], "policy_status": coverage["policy_status"]}
    if coverage["status"] == "active":
        policy = session.get(Policy, coverage["policy_id"])
        name = product_name(policy.product_id)
        period = (f", {policy.effective_date.isoformat()} to {policy.expiry_date.isoformat()}"
                  if policy.effective_date and policy.expiry_date else "")
        insured = _money(policy.insured_value_minor, policy.currency)
        out.sentences.append(f"Active coverage for {card['name']}: {name} with {provider_name(load_catalog(), policy.provider_id)}, insured value "
                             f"{insured}{period}.")
        out.facts += [_fact("Active policy", name, "policy", policy.id),
                      _fact("Insured value", insured, "policy", policy.id)]
        if period:
            out.facts.append(_fact("Coverage period", period.lstrip(", "), "policy", policy.id))
        entry.update(product_name=name, insured_value_minor=policy.insured_value_minor, currency=policy.currency,
                     effective_date=policy.effective_date.isoformat() if policy.effective_date else None,
                     expiry_date=policy.expiry_date.isoformat() if policy.expiry_date else None)
    elif coverage["status"] == "pending":
        name = product_name(coverage["product_id"]) if coverage["product_id"] else "a policy"
        state = (coverage["policy_status"] or "application in progress").replace("_", " ")
        out.sentences.append(f"Coverage for {card['name']} is pending: {name} ({state}). It is not active yet.")
        record = ("policy", coverage["policy_id"]) if coverage["policy_id"] else ("animal", card["id"])
        out.facts.append(_fact("Pending coverage", f"{name} ({state})", *record))
        entry["product_name"] = name
    else:
        out.sentences.append(f"{card['name']} has no active coverage.")
        out.facts.append(_fact("Coverage", "none", "animal", card["id"]))
        out.miss("active_policy")
    out.records["coverage"].append(entry)


def _alerts(out: _Answer, session: Session, farm_id: str, card: dict | None) -> None:
    rows = alert_rules.list_alerts(session, farm_id, status="open", animal_id=card["id"] if card else None)
    views = alert_rules.views(session, farm_id, rows)
    out.records["alerts"] += views
    for view in views:
        label = "Reduced movement" if view["kind"] == "reduced_movement" else "Observation quality warning"
        out.facts.append(_fact(f"Open alert · {view['animal_name'] or view['track_key'] or 'track'}",
                               f"{label} on {view['camera_name']}", "alert", view["id"]))
    if card is not None:
        if not views:
            out.sentences.append(f"{_label(card)} has no open alerts.")
            return
        plural = "s" if len(views) > 1 else ""
        out.sentences.append(f"{_label(card)} has {len(views)} open alert{plural}: "
                             + " ".join(view["summary"] for view in views))
        return
    by_animal: dict[str, list[dict]] = {}
    unidentified = [view for view in views if view["animal_id"] is None]
    for view in views:
        if view["animal_id"]:
            by_animal.setdefault(view["animal_id"], []).append(view)
    if not views:
        out.sentences.append("No animals have open alerts.")
        return
    if by_animal:
        parts = []
        for animal_id, items in by_animal.items():
            kinds = ", ".join(sorted({("reduced movement" if v["kind"] == "reduced_movement"
                                       else "observation quality") for v in items}))
            parts.append(f"{items[0]['animal_name']} ({animal_id}): {len(items)} open ({kinds})")
        noun = "animal has" if len(by_animal) == 1 else "animals have"
        out.sentences.append(f"{len(by_animal)} {noun} open alerts: " + "; ".join(parts) + ".")
    else:
        out.sentences.append("No animals have open alerts.")
    if unidentified:
        tracks = ", ".join(sorted({v["track_key"] or v["track_id"] for v in unidentified}))
        out.sentences.append(f"{len(unidentified)} open warning{'s' if len(unidentified) > 1 else ''} "
                             f"concern{'' if len(unidentified) > 1 else 's'} an unidentified camera track ({tracks}), "
                             f"not a registered animal.")


def resolve(session: Session, farm_id: str, parsed: ParsedQuery, *, now: datetime | None = None,
            utc_offset_minutes: int | None = None) -> dict:
    now = now or clock.now()
    zone = _zone(utc_offset_minutes)
    intent = parsed.intent
    out = _Answer()
    for ref in parsed.unmatched_refs:
        out.sentences.append(f"I couldn't find an animal matching '{ref}' in this farm.")
    if parsed.dropped_refs and not parsed.unmatched_refs:
        out.sentences.append("I couldn't find a matching animal in this farm.")
    cards = {card["id"]: card for card in list_herd(session, farm_id)["items"]}
    cameras = dict(session.execute(select(Camera.id, Camera.name).where(Camera.farm_id == farm_id)).all())
    targets = [cards[ref] for ref in intent.animal_refs if ref in cards]
    wants = [w for w in WANT_ORDER if w in intent.wants]
    if intent.intent == "unknown" or not wants:
        if not parsed.has_unmatched:
            out.sentences.append(FALLBACK_ANSWER)
    elif not targets:
        if parsed.has_unmatched:
            pass
        elif "alerts" in wants:
            _alerts(out, session, farm_id, None)
        elif "coverage" in wants:
            for card in cards.values():
                _coverage(out, session, farm_id, card)
        elif "location" in wants:
            for card in cards.values():
                _location(out, session, farm_id, card, cameras, now, zone)
        else:
            out.sentences.append("Which animal do you mean? Name it or give its tag id, e.g. animal-demo-002.")
    for card in targets:
        out.records["animals"].append({"id": card["id"], "name": card["name"], "breed": card["breed"],
                                       "sex": card["sex"], "identity_status": card["identity_status"]})
        for want in wants:
            if want == "passport":
                _passport(out, card)
            elif want == "location":
                _location(out, session, farm_id, card, cameras, now, zone)
            elif want == "coverage":
                _coverage(out, session, farm_id, card)
            else:
                _alerts(out, session, farm_id, card)
    return {"intent": intent.intent, "parsed_by": parsed.parsed_by, "answer": " ".join(out.sentences),
            "facts": out.facts, "records": out.records, "missing": out.missing,
            "fallback_reason": parsed.fallback_reason}


def farm_animals(session: Session, farm_id: str) -> list[dict]:
    rows = session.execute(select(Animal.id, Animal.name).where(Animal.farm_id == farm_id).order_by(Animal.id)).all()
    return [{"id": animal_id, "name": name} for animal_id, name in rows]


def ask(settings: Settings, farm_id: str, text: str, *, client: Any | None = None,
        utc_offset_minutes: int | None = None) -> dict:
    """Parse, then resolve in a fresh read snapshot: no transaction stays open across the model call."""
    with read_session() as session:
        animals = farm_animals(session, farm_id)
    parsed = parse(settings, text, animals, client=client)
    with read_session() as session:
        return resolve(session, farm_id, parsed, utc_offset_minutes=utc_offset_minutes)
