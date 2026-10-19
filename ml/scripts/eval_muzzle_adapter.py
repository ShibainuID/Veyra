"""Check that the muzzle identity adapter (ONNX + SIFT) reproduces the hybrid results on the test animals.

usage: python scripts/eval_muzzle_adapter.py [group]   # group = test (default) or val
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api"))
from adapters.muzzle import Gallery, MuzzleIdentifier  # noqa: E402

IMAGES = ROOT / "ml/data/raw/li2022_muzzle/BeefCattle_Muzzle_Individualized"
group_name = sys.argv[1] if len(sys.argv) > 1 else "test"
group = json.loads((ROOT / "ml/splits/muzzle_v1.json").read_text())[group_name]

ident = MuzzleIdentifier()
t0 = time.time()
gallery = Gallery()
for animal, imgs in group["gallery"].items():
    for rel in imgs:
        ref = ident.reference(rel, cv2.imread(str(IMAGES / rel)))
        if ref is not None:
            gallery.add(animal, ref)

with ThreadPoolExecutor() as ex:
    results = list(ex.map(lambda q: ident.identify(cv2.imread(str(IMAGES / q["image"])), gallery), group["queries"]))

reg = [(q, r) for q, r in zip(group["queries"], results) if q["registered"]]
unk = [(q, r) for q, r in zip(group["queries"], results) if not q["registered"]]
summary = {
    "group": group_name,
    "registered_queries": len(reg),
    "unknown_queries": len(unk),
    "correct_candidate": sum(r["outcome"] == "candidate" and r["animal_id"] == q["animal"] for q, r in reg) / len(reg),
    "wrong_candidate_registered": sum(r["outcome"] == "candidate" and r["animal_id"] != q["animal"] for q, r in reg) / len(reg),
    "uncertain_registered": sum(r["outcome"] == "uncertain" for _, r in reg) / len(reg),
    "unknown_false_candidate": sum(r["outcome"] == "candidate" for _, r in unk) / len(unk),
    "unknown_uncertain": sum(r["outcome"] == "uncertain" for _, r in unk) / len(unk),
    "unknown_new": sum(r["outcome"] == "new" for _, r in unk) / len(unk),
    "seconds": round(time.time() - t0),
}
print(json.dumps(summary, indent=1))
(ROOT / f"ml/results/muzzle_adapter_{group_name}.json").write_text(json.dumps(summary, indent=1))
