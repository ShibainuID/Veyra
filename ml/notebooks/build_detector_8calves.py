import json
import sys
from pathlib import Path
from uuid import uuid4

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(__file__).parent / "detector_8calves.ipynb"
HR  = "---"

def md(source: str) -> dict:
    return {"cell_type": "markdown", "id": uuid4().hex[:8], "metadata": {}, "source": source}

def code(source: str) -> dict:
    return {
        "cell_type": "code", "execution_count": None, "id": uuid4().hex[:8],
        "metadata": {}, "outputs": [], "source": source,
    }

def section(title: str, anchor: str) -> dict:
    return md(
        f"{HR}\n\n"
        f"# {title} <a name=\"{anchor}\"></a>\n\n"
        f"{HR}"
    )

cells = []

# ---------------------------------------------------------------------------
# Banner (3 cells) + TOC
# ---------------------------------------------------------------------------
cells.append(md(
    f"{HR}\n\n"
    "# Veyra: Barn CCTV Cattle Detector\n\n"
    "*Fine-tuning the CCTV detector that feeds Veyra's tracker, so that identities handed over in the scan "
    "zone are not lost whenever an animal is missed for a few frames.*"
))

cells.append(md(
    f"{HR}\n\n"
    "## Team Veyra\n\n"
    "- Member 1 (Vision and data)\n"
    "- Member 2\n"
    "- Member 3\n"
    "- Member 4"
))

cells.append(md(
    f"{HR}\n\n"
    "## Table of Contents\n\n"
    "1. [**Introduction**](#1)\n"
    "2. [**Initialization**](#2)\n"
    "3. [**Data Check**](#3)\n"
    "4. [**Zero-Shot Baseline**](#4)\n"
    "5. [**Fine-Tuning**](#5)\n"
    "6. [**Evaluation**](#6)\n"
    "7. [**Export**](#7)\n"
))

# ---------------------------------------------------------------------------
# Section 1: Introduction
# ---------------------------------------------------------------------------
cells.append(section("Introduction", "1"))

cells.append(md(
    "## Overview\n\n"
    "*Veyra links a cow's identity, confirmed by a muzzle scan in a marked scan zone, to its track on a barn "
    "camera. A track only keeps that identity while the detector keeps seeing the animal: every missed "
    "detection can end the track, and a new track starts without an identity.*\n\n"
    "*On ten minutes of real barn footage, the COCO-pretrained YOLOv8m detector found only about 40% of the "
    "calves, which left almost no identities intact after the hand-over. The tracker was not the bottleneck: "
    "ByteTrack and BoT-SORT produced nearly the same results.*"
))

cells.append(md(
    "## Aim\n\n"
    "*Fine-tune a single-class cattle detector on hand-labelled barn frames and raise detection recall on "
    "held-out days well above the zero-shot baseline, while keeping precision high, so that tracks stay "
    "continuous enough to carry identities.*"
))

cells.append(md(
    "## Metric\n\n"
    "***Recall at IoU 0.5** is the share of labelled calves that the detector finds. It is the primary metric "
    "here because a missed calf breaks its track and drops its identity. **Precision** guards against false "
    "detections, and **mAP@0.5** and **mAP@0.5:0.95** summarise the precision-recall trade-off.*\n\n"
    "$$\\text{Recall} = \\frac{TP}{TP + FN} \\qquad \\text{Precision} = \\frac{TP}{TP + FP}$$"
))

cells.append(md(
    "## Dataset\n\n"
    "*Data sourced from Hugging Face, 8-Calves (Fang et al., 2025, CC BY 4.0) at: "
    "https://huggingface.co/datasets/tonyFang04/8-calves*\n\n"
    "*The split follows the authors' benchmark and is separated by recording day: 500 frames for training "
    "(morning feed on 2-3 March, afternoon feed on 1-3 March) and 100 frames for validation (morning feed on "
    "4 March). Frames from the afternoon feed of 4 March are excluded, because the tracking test video comes "
    "from that session.*\n\n"
    "*The dataset is used to adapt the detector to an angled barn camera, straw bedding, and crowded calves.*\n\n"
    "```\n"
    "eight_calves_yolo/\n"
    "+-- data.yaml\n"
    "+-- train/\n"
    "|   +-- images/   (500 PNG frames, 800 x 600)\n"
    "|   +-- labels/   (YOLO txt, class 0 = calf)\n"
    "+-- val/\n"
    "     +-- images/   (100 PNG frames)\n"
    "     +-- labels/\n"
    "```"
))

cells.append(md(
    "## Approach: Fine-Tuned YOLOv8m\n\n"
    "*YOLOv8m is a one-stage detector pretrained on COCO, which already contains a cow class. Fine-tuning "
    "keeps its general features and adapts the head to calves seen from a high, angled camera.*\n\n"
    "*Training uses both T4 GPUs with distributed data parallelism, an 800-pixel input to keep small calves "
    "visible, and augmentation suited to an overhead view: flips in both directions, small rotations, and "
    "brightness changes.*\n\n"
    "```\n"
    "Barn frame [800 x 600]\n"
    "    |\n"
    "    +-- YOLOv8m backbone + neck (COCO pretrained)\n"
    "         |\n"
    "    Detection head -> calf boxes + confidence\n"
    "         |\n"
    "    Tracker (BoT-SORT) -> tracks that carry hand-over identities\n"
    "```\n\n"
    "*The zero-shot COCO model is scored on the same validation frames first, so the gain from fine-tuning "
    "is measured rather than assumed.*"
))

# ---------------------------------------------------------------------------
# Section 2: Initialization
# ---------------------------------------------------------------------------
cells.append(section("Initialization", "2"))

cells.append(md(
    "## Environment Setup\n\n"
    "To reproduce results without re-running training, assign `Settings.RUN_NAME` to `'INFERENCE'` and then "
    "run all cells. The notebook targets Kaggle with the GPU T4 x2 accelerator."
))

cells.append(code("!nvidia-smi || echo 'No NVIDIA GPU detected'"))

cells.append(md("The following cell installs all libraries used in this notebook."))

cells.append(code("%pip install -q ultralytics pandas matplotlib"))

cells.append(md("## Import Libraries"))

cells.append(code(
    "import json\n"
    "import os\n"
    "import random\n"
    "import shutil\n"
    "from pathlib import Path\n"
    "\n"
    "import matplotlib.pyplot as plt\n"
    "import numpy as np\n"
    "import pandas as pd\n"
    "import torch\n"
    "import yaml\n"
    "from PIL import Image\n"
    "from ultralytics import YOLO"
))

cells.append(md("## Seed Everything"))

cells.append(code(
    "def seed_everything(seed: int = 42):\n"
    "    random.seed(seed)\n"
    "    os.environ['PYTHONHASHSEED'] = str(seed)\n"
    "    np.random.seed(seed)\n"
    "    torch.manual_seed(seed)\n"
    "    torch.cuda.manual_seed_all(seed)\n"
    "\n"
    "seed_everything(42)"
))

cells.append(md(
    "## Settings\n\n"
    "All paths, hyperparameters, and environment flags are centralised here. The dataset is located by "
    "searching `/kaggle/input` for the split's `data.yaml`, so the notebook does not depend on Kaggle's "
    "mount path."
))

cells.append(code(
    "class Settings:\n"
    "    SEED       = 42\n"
    "    RUN_NAME   = 'yolov8m_8calves_v1'\n"
    "    _ON_KAGGLE = Path('/kaggle/input').exists()\n"
    "\n"
    "    INPUT_DIR  = Path('/kaggle/input') if _ON_KAGGLE else Path('../data/processed')\n"
    "    OUTPUT_DIR = Path('/kaggle/working') if _ON_KAGGLE else Path('../runs/detector_8calves')\n"
    "\n"
    "    BASE_MODEL   = 'yolov8m.pt'\n"
    "    IMG_SIZE     = 800\n"
    "    EPOCHS       = 120\n"
    "    PATIENCE     = 30\n"
    "    N_GPUS       = torch.cuda.device_count()\n"
    "    BATCH_SIZE   = 8 * max(1, N_GPUS)\n"
    "    _LOCAL       = 'mps' if torch.backends.mps.is_available() else 'cpu'\n"
    "    DEVICE       = list(range(N_GPUS)) if N_GPUS > 1 else (0 if N_GPUS == 1 else _LOCAL)\n"
    "    EVAL_DEVICE  = 0 if N_GPUS else _LOCAL\n"
    "    CONF         = 0.25\n"
    "    MATCH_IOU    = 0.5\n"
    "    COCO_ANIMALS = list(range(15, 24))\n"
    "\n"
    "CFG = Settings()\n"
    "CFG.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)\n"
    "print(f'GPUs: {CFG.N_GPUS}  Device: {CFG.DEVICE}  Batch: {CFG.BATCH_SIZE}  Run: {CFG.RUN_NAME}')"
))

cells.append(md(
    "## Load Dataset\n\n"
    "The split's `data.yaml` uses a relative path, so a copy with the absolute dataset root is written to the "
    "working directory for Ultralytics."
))

cells.append(code(
    "source_yaml = next(CFG.INPUT_DIR.rglob('eight_calves_yolo/data.yaml'))\n"
    "DATA_ROOT = source_yaml.parent\n"
    "data_cfg = yaml.safe_load(source_yaml.read_text())\n"
    "data_cfg['path'] = str(DATA_ROOT)\n"
    "DATA_YAML = CFG.OUTPUT_DIR / 'data.yaml'\n"
    "DATA_YAML.write_text(yaml.safe_dump(data_cfg))\n"
    "\n"
    "splits = {s: sorted((DATA_ROOT / s / 'images').glob('*.png')) for s in ('train', 'val')}\n"
    "print(f'Dataset root: {DATA_ROOT}')\n"
    "print({s: len(v) for s, v in splits.items()})"
))

# ---------------------------------------------------------------------------
# Section 3: Data Check
# ---------------------------------------------------------------------------
cells.append(section("Data Check", "3"))

cells.append(md(
    "Box counts and sizes per split confirm that training and validation describe the same scene, and a few "
    "labelled frames show how crowded and occluded the calves are."
))

cells.append(code(
    "def read_labels(image_path: Path) -> np.ndarray:\n"
    "    txt = image_path.parent.parent / 'labels' / (image_path.stem + '.txt')\n"
    "    rows = [list(map(float, l.split())) for l in txt.read_text().splitlines() if l.strip()]\n"
    "    return np.array(rows).reshape(-1, 5)\n"
    "\n"
    "\n"
    "rows = []\n"
    "for split, images in splits.items():\n"
    "    for p in images:\n"
    "        labels = read_labels(p)\n"
    "        rows.append({'split': split, 'boxes': len(labels),\n"
    "                     'mean_w': labels[:, 3].mean() if len(labels) else np.nan,\n"
    "                     'mean_h': labels[:, 4].mean() if len(labels) else np.nan})\n"
    "stats = pd.DataFrame(rows)\n"
    "stats.groupby('split').agg(frames=('boxes', 'size'), boxes=('boxes', 'sum'),\n"
    "                           boxes_per_frame=('boxes', 'mean'), mean_w=('mean_w', 'mean'), mean_h=('mean_h', 'mean')).round(3)"
))

cells.append(code(
    "def draw(ax, image_path: Path, boxes_xyxy: np.ndarray, color: str, title: str) -> None:\n"
    "    ax.imshow(Image.open(image_path))\n"
    "    for x0, y0, x1, y1 in boxes_xyxy:\n"
    "        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, color=color, lw=1.5))\n"
    "    ax.set_title(title, fontsize=9)\n"
    "    ax.axis('off')\n"
    "\n"
    "\n"
    "def yolo_to_xyxy(labels: np.ndarray, w: int, h: int) -> np.ndarray:\n"
    "    cx, cy, bw, bh = labels[:, 1] * w, labels[:, 2] * h, labels[:, 3] * w, labels[:, 4] * h\n"
    "    return np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)\n"
    "\n"
    "\n"
    "fig, axes = plt.subplots(1, 3, figsize=(15, 4))\n"
    "for ax, p in zip(axes, random.Random(CFG.SEED).sample(splits['val'], 3)):\n"
    "    w, h = Image.open(p).size\n"
    "    draw(ax, p, yolo_to_xyxy(read_labels(p), w, h), 'lime', p.name)\n"
    "plt.tight_layout()\n"
    "plt.savefig(CFG.OUTPUT_DIR / 'val_samples.png', dpi=110)\n"
    "plt.show()"
))

# ---------------------------------------------------------------------------
# Section 4: Zero-Shot Baseline
# ---------------------------------------------------------------------------
cells.append(section("Zero-Shot Baseline", "4"))

cells.append(md(
    "The COCO model has no calf class, so any of its animal classes counts as a calf detection. Predictions "
    "are matched one-to-one to labels at IoU 0.5, and the same function scores the fine-tuned model later."
))

cells.append(code(
    "def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:\n"
    "    if len(a) == 0 or len(b) == 0:\n"
    "        return np.zeros((len(a), len(b)))\n"
    "    x0 = np.maximum(a[:, None, 0], b[None, :, 0])\n"
    "    y0 = np.maximum(a[:, None, 1], b[None, :, 1])\n"
    "    x1 = np.minimum(a[:, None, 2], b[None, :, 2])\n"
    "    y1 = np.minimum(a[:, None, 3], b[None, :, 3])\n"
    "    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)\n"
    "    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])\n"
    "    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])\n"
    "    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)\n"
    "\n"
    "\n"
    "def precision_recall(model: YOLO, images: list[Path], classes: list[int] | None) -> dict:\n"
    "    tp = fp = fn = 0\n"
    "    for p in images:\n"
    "        r = model.predict(str(p), imgsz=CFG.IMG_SIZE, conf=CFG.CONF, classes=classes, verbose=False)[0]\n"
    "        pred = r.boxes.xyxy.cpu().numpy()\n"
    "        w, h = Image.open(p).size\n"
    "        gt = yolo_to_xyxy(read_labels(p), w, h)\n"
    "        ious = iou_matrix(gt, pred)\n"
    "        used = set()\n"
    "        for i in np.argsort(-ious.max(1)) if ious.size else []:\n"
    "            j = next((j for j in np.argsort(-ious[i]) if ious[i, j] >= CFG.MATCH_IOU and j not in used), None)\n"
    "            if j is not None:\n"
    "                used.add(j)\n"
    "        tp += len(used)\n"
    "        fn += len(gt) - len(used)\n"
    "        fp += len(pred) - len(used)\n"
    "    return {'precision': tp / max(tp + fp, 1), 'recall': tp / max(tp + fn, 1), 'tp': tp, 'fp': fp, 'fn': fn}\n"
    "\n"
    "\n"
    "results = {'zero_shot_coco': precision_recall(YOLO(CFG.BASE_MODEL), splits['val'], CFG.COCO_ANIMALS)}\n"
    "results['zero_shot_coco']"
))

# ---------------------------------------------------------------------------
# Section 5: Fine-Tuning
# ---------------------------------------------------------------------------
cells.append(section("Fine-Tuning", "5"))

cells.append(md(
    "The detector is trained as a single class on both GPUs. Mosaic stays on because it multiplies the "
    "crowded configurations the tracker struggles with, and vertical flips are allowed because the camera "
    "looks down on the pen. Early stopping watches validation mAP."
))

cells.append(code(
    "if CFG.RUN_NAME != 'INFERENCE':\n"
    "    model = YOLO(CFG.BASE_MODEL)\n"
    "    model.train(\n"
    "        data=str(DATA_YAML), epochs=CFG.EPOCHS, patience=CFG.PATIENCE, imgsz=CFG.IMG_SIZE,\n"
    "        batch=CFG.BATCH_SIZE, device=CFG.DEVICE, workers=4, single_cls=True, seed=CFG.SEED,\n"
    "        cos_lr=True, fliplr=0.5, flipud=0.5, degrees=10.0, hsv_v=0.3, hsv_s=0.3, mosaic=1.0,\n"
    "        close_mosaic=15, project=str(CFG.OUTPUT_DIR), name=CFG.RUN_NAME, exist_ok=True, plots=True,\n"
    "    )\n"
    "\n"
    "WEIGHTS = CFG.OUTPUT_DIR / CFG.RUN_NAME / 'weights' / 'best.pt'\n"
    "print(f'Best weights: {WEIGHTS} ({WEIGHTS.stat().st_size / 1e6:.1f} MB)')"
))

cells.append(md(
    "The training curves show whether validation mAP is still rising when training stops, which would mean "
    "more epochs could help."
))

cells.append(code(
    "history = pd.read_csv(CFG.OUTPUT_DIR / CFG.RUN_NAME / 'results.csv')\n"
    "history.columns = [c.strip() for c in history.columns]\n"
    "fig, axes = plt.subplots(1, 2, figsize=(12, 3.5))\n"
    "axes[0].plot(history['epoch'], history['train/box_loss'], label='train box loss')\n"
    "axes[0].plot(history['epoch'], history['val/box_loss'], label='val box loss')\n"
    "axes[0].set(title='Box loss', xlabel='Epoch')\n"
    "axes[0].legend()\n"
    "for col in ('metrics/precision(B)', 'metrics/recall(B)', 'metrics/mAP50(B)', 'metrics/mAP50-95(B)'):\n"
    "    axes[1].plot(history['epoch'], history[col], label=col.split('/')[1])\n"
    "axes[1].set(title='Validation metrics', xlabel='Epoch', ylim=(0, 1))\n"
    "axes[1].legend()\n"
    "plt.tight_layout()\n"
    "plt.savefig(CFG.OUTPUT_DIR / 'training_curves.png', dpi=110)\n"
    "plt.show()"
))

# ---------------------------------------------------------------------------
# Section 6: Evaluation
# ---------------------------------------------------------------------------
cells.append(section("Evaluation", "6"))

cells.append(md(
    "The best checkpoint is scored on the validation day with Ultralytics' standard metrics and with the "
    "same matching function as the zero-shot baseline, so the two rows of the comparison are directly "
    "comparable."
))

cells.append(code(
    "best = YOLO(str(WEIGHTS))\n"
    "val = best.val(data=str(DATA_YAML), imgsz=CFG.IMG_SIZE, single_cls=True, device=CFG.EVAL_DEVICE, plots=False,\n"
    "               verbose=False)\n"
    "results['fine_tuned'] = {\n"
    "    **precision_recall(best, splits['val'], None),\n"
    "    'map50': float(val.box.map50),\n"
    "    'map50_95': float(val.box.map),\n"
    "}\n"
    "comparison = pd.DataFrame(results).T[['precision', 'recall', 'tp', 'fp', 'fn', 'map50', 'map50_95']]\n"
    "comparison"
))

cells.append(md(
    "Predictions on held-out frames, drawn next to the labels, show which situations still cause misses."
))

cells.append(code(
    "fig, axes = plt.subplots(2, 3, figsize=(15, 8))\n"
    "for col, p in enumerate(random.Random(CFG.SEED + 1).sample(splits['val'], 3)):\n"
    "    w, h = Image.open(p).size\n"
    "    draw(axes[0, col], p, yolo_to_xyxy(read_labels(p), w, h), 'lime', f'labels: {p.name}')\n"
    "    pred = best.predict(str(p), imgsz=CFG.IMG_SIZE, conf=CFG.CONF, verbose=False)[0].boxes.xyxy.cpu().numpy()\n"
    "    draw(axes[1, col], p, pred, 'red', f'fine-tuned predictions ({len(pred)})')\n"
    "plt.tight_layout()\n"
    "plt.savefig(CFG.OUTPUT_DIR / 'val_predictions.png', dpi=110)\n"
    "plt.show()"
))

# ---------------------------------------------------------------------------
# Section 7: Export
# ---------------------------------------------------------------------------
cells.append(section("Export", "7"))

cells.append(md(
    "The best weights and the comparison table are copied to the output root, where the local tracking "
    "evaluation picks them up."
))

cells.append(code(
    "shutil.copy(WEIGHTS, CFG.OUTPUT_DIR / 'calf_detector_v1.pt')\n"
    "(CFG.OUTPUT_DIR / 'detector_results.json').write_text(json.dumps(results, indent=1))\n"
    "print(json.dumps(results, indent=1))"
))

# ---------------------------------------------------------------------------
# Notebook writer
# ---------------------------------------------------------------------------
nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12.0"},
    },
    "cells": cells,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {len(cells)} cells -> {OUT}")
