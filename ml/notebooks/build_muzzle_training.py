import json
import sys
from pathlib import Path
from uuid import uuid4

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(__file__).parent / "muzzle_training.ipynb"
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
    "# Veyra: Cattle Muzzle Identification\n\n"
    "*Training and open-set evaluation of the muzzle model that tells Veyra which registered animal "
    "a capture belongs to, or that it belongs to none of them.*"
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
    "3. [**Data Profiling**](#3)\n"
    "4. [**Animal-Level Splits**](#4)\n"
    "5. [**Evaluation Protocol**](#5)\n"
    "6. [**Baseline: SIFT and RANSAC**](#6)\n"
    "7. [**Zero-Shot Foundation Models**](#7)\n"
    "8. [**DINOv3 and ArcFace Fine-Tuning**](#8)\n"
    "9. [**Hybrid: Embedding Retrieval and SIFT Verification**](#9)\n"
    "10. [**Results Comparison**](#10)\n"
    "11. [**Export to ONNX**](#11)\n"
))

# ---------------------------------------------------------------------------
# Section 1: Introduction
# ---------------------------------------------------------------------------
cells.append(section("Introduction", "1"))

cells.append(md(
    "## Overview\n\n"
    "*Veyra turns smallholder cattle into evidence records that a bank can review as potential "
    "collateral. The first question every record must answer is which animal it describes, and the "
    "cattle muzzle carries a ridge-and-bead pattern that is distinctive for each individual.*\n\n"
    "*The task is individual identification rather than species classification. A new capture is "
    "compared against a gallery of registered animals, and the system must either name a candidate "
    "for a human verifier or report that no registered animal matches.*"
))

cells.append(md(
    "## Aim\n\n"
    "*Build a muzzle retrieval model that ranks the correct registered animal first and keeps the "
    "false-match rate on unregistered animals at or below 5%, then compare it against a classical "
    "SIFT baseline and zero-shot DINOv2 and DINOv3 baselines on the same held-out animals.*"
))

cells.append(md(
    "## Metric\n\n"
    "***Correct match at the operating threshold** is the share of queries from registered animals "
    "whose top candidate is correct and scores above the threshold. The threshold is the score that "
    "allows at most 5% of validation queries from unknown animals to match anything. It is "
    "appropriate here because Veyra must reject animals that are not in the registry, so closed-set "
    "accuracy alone would overstate performance.*\n\n"
    "$$\\text{Correct match} = \\frac{|\\{q \\in Q_{reg} : \\hat{a}(q) = a(q) \\wedge s(q) > \\tau\\}|}{|Q_{reg}|}"
    "\\qquad \\text{FMR}_{unk} = \\frac{|\\{q \\in Q_{unk} : s(q) > \\tau\\}|}{|Q_{unk}|}$$\n\n"
    "*Rank-1 and top-5 retrieval rates are reported alongside as closed-set diagnostics.*"
))

cells.append(md(
    "## Dataset\n\n"
    "*Data sourced from Zenodo, Beef Cattle Muzzle/Noseprint database (Li, Erickson, and Xiong, 2022, "
    "CC BY 4.0) at: https://zenodo.org/records/6324361*\n\n"
    "*The dataset contains 4,923 cropped muzzle images of 268 US feedlot cattle, with one folder per "
    "animal and roughly 18 images per animal on average.*\n\n"
    "*The dataset is used to train the embedding model on one group of animals and to measure "
    "retrieval and unknown-animal rejection on animals the model has never seen.*\n\n"
    "```\n"
    "li2022_muzzle/\n"
    "└── <image_root>/\n"
    "     ├── <animal_id_1>/\n"
    "     |    ├── <image>.jpg\n"
    "     |    └── ...\n"
    "     └── <animal_id_268>/\n"
    "```"
))

cells.append(md(
    "## Approach: DINOv3 with ArcFace Metric Learning\n\n"
    "*DINOv3 is a self-supervised Vision Transformer distilled from a 7B-parameter teacher trained on "
    "1.7 billion images. Its patch-level features stay sharp, which suits the fine ridge texture of a "
    "muzzle. DINOv2 is evaluated alongside it in the zero-shot stage, so the backbone choice rests on "
    "measured results. ArcFace adds an angular margin between identities during training, which pulls "
    "images of the same animal together on a hypersphere and pushes different animals apart.*\n\n"
    "*At inference time the classification head is discarded. Each image becomes a normalised "
    "embedding, and identification is a cosine-similarity search against the gallery, so a new animal "
    "is registered by adding its embedding without retraining.*\n\n"
    "```\n"
    "Muzzle crop [224 x 224]\n"
    "    |\n"
    "    +-- DINOv3 ViT-S/16 backbone (last blocks fine-tuned) [384]\n"
    "         |\n"
    "    Projection + L2 normalisation [512]\n"
    "         |\n"
    "    Training: ArcFace head over training animals\n"
    "    Inference: cosine similarity against the gallery -> ranked candidates\n"
    "```\n\n"
    "*Animals, never images, are assigned to train, validation, and test groups. Validation and test "
    "each hold registered animals and unknown animals that never enter the gallery, following the "
    "evaluation protocol in Section 4.3 of the Veyra PRD.*"
))

# ---------------------------------------------------------------------------
# Section 2: Initialization
# ---------------------------------------------------------------------------
cells.append(section("Initialization", "2"))

cells.append(md(
    "## Environment Setup\n\n"
    "To reproduce results without re-running training, assign `Settings.RUN_NAME` to `'INFERENCE'` "
    "and then run all cells. The notebook targets Kaggle with the GPU T4 x2 accelerator and also runs "
    "locally on Apple Silicon (MPS). On Kaggle, every attached dataset under `/kaggle/input` is searched "
    "for animal folders."
))

cells.append(code("!nvidia-smi || echo 'No NVIDIA GPU detected'"))

cells.append(md("The following cell installs all libraries used in this notebook."))

cells.append(code(
    "%pip install -q numpy pandas matplotlib pillow tqdm tabulate opencv-contrib-python-headless "
    "torch torchvision timm onnx onnxruntime"
))

cells.append(md("## Import Libraries"))

cells.append(code(
    "import json\n"
    "import math\n"
    "import os\n"
    "import random\n"
    "import time\n"
    "from collections import Counter, defaultdict\n"
    "from concurrent.futures import ThreadPoolExecutor\n"
    "from pathlib import Path\n"
    "\n"
    "import cv2\n"
    "import matplotlib.pyplot as plt\n"
    "import numpy as np\n"
    "import onnxruntime as ort\n"
    "import pandas as pd\n"
    "import timm\n"
    "import torch\n"
    "import torch.nn as nn\n"
    "import torch.nn.functional as F\n"
    "from PIL import Image\n"
    "from torch.utils.data import DataLoader, Dataset\n"
    "from torchvision import transforms as T\n"
    "from tqdm.auto import tqdm"
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
    "All paths, hyperparameters, and environment flags are centralised here. Switching between Kaggle "
    "and local execution requires no changes outside this class. `IMAGE_ROOT` is the folder whose "
    "subfolders are individual animals."
))

cells.append(code(
    "class Settings:\n"
    "    SEED       = 42\n"
    "    RUN_NAME   = 'dinov3_arcface_v1'\n"
    "    _ON_KAGGLE = Path('/kaggle/input').exists()\n"
    "\n"
    "    DATA_DIR   = (\n"
    "        Path('/kaggle/input')\n"
    "        if _ON_KAGGLE else Path('../data/raw/li2022_muzzle')\n"
    "    )\n"
    "    IMAGE_ROOT = None\n"
    "    OUTPUT_DIR = Path('/kaggle/working') if _ON_KAGGLE else Path('../runs')\n"
    "    RUN_DIR    = OUTPUT_DIR / RUN_NAME\n"
    "    FIG_DIR    = RUN_DIR / 'figures'\n"
    "    SPLIT_PATH = Path('/kaggle/working/muzzle_v1.json') if _ON_KAGGLE else Path('../splits/muzzle_v1.json')\n"
    "    RESULT_DIR = Path('/kaggle/working') if _ON_KAGGLE else Path('../results')\n"
    "    EXPORT_DIR = Path('/kaggle/working') if _ON_KAGGLE else Path('../../vision/models')\n"
    "\n"
    "    TRAIN_FRACTION     = 0.50\n"
    "    VAL_FRACTION       = 0.20\n"
    "    UNKNOWN_FRACTION   = 0.25\n"
    "    GALLERY_PER_ANIMAL = 1\n"
    "    TARGET_UNKNOWN_FMR = 0.05\n"
    "\n"
    "    SIFT_MAX_SIDE   = 480\n"
    "    SIFT_FEATURES   = 800\n"
    "    SIFT_RATIO      = 0.75\n"
    "    SIFT_SHORTLIST  = 10\n"
    "    SIFT_MIN_MATCH  = 8\n"
    "    HYBRID_TOP_K    = 5\n"
    "\n"
    "    BACKBONE        = 'vit_small_patch16_dinov3.lvd1689m'\n"
    "    ZERO_SHOT_BACKBONES = ['vit_small_patch14_dinov2.lvd142m', 'vit_small_patch16_dinov3.lvd1689m']\n"
    "    IMG_SIZE        = 224\n"
    "    EMBED_DIM       = 512\n"
    "    TRAINABLE_BLOCKS = 4\n"
    "    ARC_SCALE       = 30.0\n"
    "    ARC_MARGIN      = 0.30\n"
    "    EPOCHS          = 20\n"
    "    N_GPUS          = torch.cuda.device_count()\n"
    "    BATCH_SIZE      = 32 * max(1, N_GPUS)\n"
    "    LR_BACKBONE     = 2e-5\n"
    "    LR_HEAD         = 1e-3\n"
    "    WEIGHT_DECAY    = 0.05\n"
    "    WARMUP_EPOCHS   = 1\n"
    "    NUM_WORKERS     = 4 if _ON_KAGGLE else 0\n"
    "\n"
    "    DEVICE = (\n"
    "        'cuda' if torch.cuda.is_available()\n"
    "        else 'mps' if torch.backends.mps.is_available() else 'cpu'\n"
    "    )\n"
    "\n"
    "CFG = Settings()\n"
    "for d in (CFG.RUN_DIR, CFG.FIG_DIR, CFG.SPLIT_PATH.parent, CFG.RESULT_DIR, CFG.EXPORT_DIR):\n"
    "    d.mkdir(parents=True, exist_ok=True)\n"
    "print(f'Device: {CFG.DEVICE}  GPUs: {CFG.N_GPUS}  Batch size: {CFG.BATCH_SIZE}  Run: {CFG.RUN_NAME}')"
))

cells.append(md(
    "## Load Dataset\n\n"
    "Every folder that directly contains images is treated as one animal, and its name becomes the "
    "animal ID. This works whether the archive was extracted with or without an extra top-level folder."
))

cells.append(code(
    "IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp'}\n"
    "\n"
    "image_paths = sorted(p for p in CFG.DATA_DIR.rglob('*') if p.suffix.lower() in IMAGE_EXTS)\n"
    "CFG.IMAGE_ROOT = Path(os.path.commonpath([p.parent.parent for p in image_paths]))\n"
    "\n"
    "df = pd.DataFrame({\n"
    "    'image':  [str(p.relative_to(CFG.IMAGE_ROOT)) for p in image_paths],\n"
    "    'animal': [p.parent.name for p in image_paths],\n"
    "})\n"
    "animals = df.groupby('animal')['image'].apply(sorted).to_dict()\n"
    "print(f'Image root: {CFG.IMAGE_ROOT}')\n"
    "print(f'Images: {len(df)}  Animals: {len(animals)}')"
))

# ---------------------------------------------------------------------------
# Section 3: Data Profiling
# ---------------------------------------------------------------------------
cells.append(section("Data Profiling", "3"))

cells.append(md(
    "The number of images per animal decides how many query images remain after one image per "
    "registered animal goes into the gallery, and the image resolution decides how much muzzle detail "
    "survives resizing to 224 pixels. Both are checked before any split is made."
))

cells.append(code(
    "counts = df.groupby('animal').size()\n"
    "sizes = pd.DataFrame(\n"
    "    [Image.open(CFG.IMAGE_ROOT / p).size for p in df['image']],\n"
    "    columns=['width', 'height'],\n"
    ")\n"
    "\n"
    "print('Images per animal')\n"
    "print(counts.describe().round(1).to_string())\n"
    "print('\\nImage size (pixels)')\n"
    "print(sizes.describe().round(0).to_string())\n"
    "\n"
    "fig, axes = plt.subplots(1, 2, figsize=(12, 3.5))\n"
    "axes[0].hist(counts, bins=30, color='#4C72B0')\n"
    "axes[0].set(title='Images per animal', xlabel='Images', ylabel='Animals')\n"
    "axes[1].scatter(sizes['width'], sizes['height'], s=4, alpha=0.4, color='#4C72B0')\n"
    "axes[1].set(title='Image size', xlabel='Width (px)', ylabel='Height (px)')\n"
    "plt.tight_layout()\n"
    "plt.savefig(CFG.FIG_DIR / 'profile.png', dpi=120)\n"
    "plt.show()"
))

cells.append(md(
    "A grid of four images from each of four random animals shows how much the same muzzle varies "
    "across captures, which is the variation the model must tolerate."
))

cells.append(code(
    "rng = random.Random(CFG.SEED)\n"
    "sample_animals = rng.sample(sorted(animals), 4)\n"
    "\n"
    "fig, axes = plt.subplots(4, 4, figsize=(10, 10))\n"
    "for r, a in enumerate(sample_animals):\n"
    "    for c, rel in enumerate(rng.sample(animals[a], min(4, len(animals[a])))):\n"
    "        axes[r, c].imshow(Image.open(CFG.IMAGE_ROOT / rel).convert('RGB'))\n"
    "        axes[r, c].set_title(a if c == 0 else '', fontsize=9, loc='left')\n"
    "for ax in axes.flat:\n"
    "    ax.axis('off')\n"
    "plt.tight_layout()\n"
    "plt.savefig(CFG.FIG_DIR / 'samples.png', dpi=120)\n"
    "plt.show()"
))

# ---------------------------------------------------------------------------
# Section 4: Animal-Level Splits
# ---------------------------------------------------------------------------
cells.append(section("Animal-Level Splits", "4"))

cells.append(md(
    "Animals are assigned to train, validation, and test groups so that no animal contributes images "
    "to more than one group. Within validation and test, a quarter of the animals are held out as "
    "unknown animals that never enter the gallery. The split is saved once and reloaded on later runs, "
    "so every method is scored on exactly the same animals."
))

cells.append(code(
    "def split_group(ids: list[str], rng: random.Random) -> dict:\n"
    "    ids = sorted(ids)\n"
    "    rng.shuffle(ids)\n"
    "    n_unknown = round(len(ids) * CFG.UNKNOWN_FRACTION)\n"
    "    unknown, registered = ids[:n_unknown], ids[n_unknown:]\n"
    "    gallery, queries = {}, []\n"
    "    for a in registered:\n"
    "        imgs = animals[a][:]\n"
    "        rng.shuffle(imgs)\n"
    "        gallery[a] = imgs[:CFG.GALLERY_PER_ANIMAL]\n"
    "        queries += [{'image': i, 'animal': a, 'registered': True} for i in imgs[CFG.GALLERY_PER_ANIMAL:]]\n"
    "    for a in unknown:\n"
    "        queries += [{'image': i, 'animal': a, 'registered': False} for i in animals[a]]\n"
    "    return {'registered': sorted(registered), 'unknown': sorted(unknown), 'gallery': gallery, 'queries': queries}\n"
    "\n"
    "\n"
    "def make_split() -> dict:\n"
    "    rng = random.Random(CFG.SEED)\n"
    "    usable = sorted(a for a, imgs in animals.items() if len(imgs) > CFG.GALLERY_PER_ANIMAL)\n"
    "    rng.shuffle(usable)\n"
    "    n_train = round(len(usable) * CFG.TRAIN_FRACTION)\n"
    "    n_val = round(len(usable) * CFG.VAL_FRACTION)\n"
    "    return {\n"
    "        'dataset': 'li2022_muzzle',\n"
    "        'seed': CFG.SEED,\n"
    "        'train': sorted(usable[:n_train]),\n"
    "        'val': split_group(usable[n_train:n_train + n_val], rng),\n"
    "        'test': split_group(usable[n_train + n_val:], rng),\n"
    "    }\n"
    "\n"
    "\n"
    "if CFG.SPLIT_PATH.exists():\n"
    "    split = json.loads(CFG.SPLIT_PATH.read_text())\n"
    "    print(f'Loaded existing split: {CFG.SPLIT_PATH}')\n"
    "else:\n"
    "    split = make_split()\n"
    "    CFG.SPLIT_PATH.write_text(json.dumps(split, indent=1))\n"
    "    print(f'Created split: {CFG.SPLIT_PATH}')\n"
    "\n"
    "train_animals = split['train']\n"
    "assert not set(train_animals) & set(split['val']['registered'] + split['val']['unknown'])\n"
    "assert not set(train_animals) & set(split['test']['registered'] + split['test']['unknown'])\n"
    "\n"
    "summary = pd.DataFrame([\n"
    "    {'group': 'train', 'animals': len(train_animals),\n"
    "     'images': sum(len(animals[a]) for a in train_animals)},\n"
    "    *[{'group': g, 'animals': len(split[g]['registered']) + len(split[g]['unknown']),\n"
    "       'registered': len(split[g]['registered']), 'unknown': len(split[g]['unknown']),\n"
    "       'gallery images': sum(len(v) for v in split[g]['gallery'].values()),\n"
    "       'registered queries': sum(q['registered'] for q in split[g]['queries']),\n"
    "       'unknown queries': sum(not q['registered'] for q in split[g]['queries'])}\n"
    "      for g in ('val', 'test')],\n"
    "]).fillna('-')\n"
    "summary"
))

# ---------------------------------------------------------------------------
# Section 5: Evaluation Protocol
# ---------------------------------------------------------------------------
cells.append(section("Evaluation Protocol", "5"))

cells.append(md(
    "Every method produces a score matrix with one row per query and one column per gallery animal, "
    "where a higher score means more similar. The same functions then rank candidates, choose the "
    "threshold on validation unknown animals, and compute the metrics, so the methods differ only in "
    "how they score a pair of images."
))

cells.append(code(
    "def top_candidates(scores: np.ndarray, gallery_animals: list[str]) -> tuple[np.ndarray, np.ndarray]:\n"
    "    order = np.argsort(-scores, axis=1)\n"
    "    return np.array(gallery_animals)[order], np.take_along_axis(scores, order, axis=1)\n"
    "\n"
    "\n"
    "def pick_threshold(scores: np.ndarray, group: dict) -> float:\n"
    "    unknown = np.array([not q['registered'] for q in group['queries']])\n"
    "    top_unknown = scores[unknown].max(axis=1)\n"
    "    return float(np.quantile(top_unknown, 1 - CFG.TARGET_UNKNOWN_FMR))\n"
    "\n"
    "\n"
    "def compute_metrics(scores: np.ndarray, group: dict, threshold: float) -> dict:\n"
    "    gallery_animals = list(group['gallery'])\n"
    "    ranked, ranked_scores = top_candidates(scores, gallery_animals)\n"
    "    truth = np.array([q['animal'] for q in group['queries']])\n"
    "    registered = np.array([q['registered'] for q in group['queries']])\n"
    "    top1, top1_score = ranked[:, 0], ranked_scores[:, 0]\n"
    "    accepted = top1_score > threshold\n"
    "    reg, unk = registered, ~registered\n"
    "    return {\n"
    "        'rank1': (top1[reg] == truth[reg]).mean(),\n"
    "        'top5': np.mean([t in r[:5] for t, r in zip(truth[reg], ranked[reg])]),\n"
    "        'correct_match': ((top1[reg] == truth[reg]) & accepted[reg]).mean(),\n"
    "        'wrong_match_registered': ((top1[reg] != truth[reg]) & accepted[reg]).mean(),\n"
    "        'unknown_fmr': accepted[unk].mean(),\n"
    "        'threshold': threshold,\n"
    "    }\n"
    "\n"
    "\n"
    "results = {}\n"
    "score_store = {}\n"
    "\n"
    "\n"
    "def record(method: str, val_scores: np.ndarray, test_scores: np.ndarray) -> pd.DataFrame:\n"
    "    threshold = pick_threshold(val_scores, split['val'])\n"
    "    results[method] = {\n"
    "        'val': compute_metrics(val_scores, split['val'], threshold),\n"
    "        'test': compute_metrics(test_scores, split['test'], threshold),\n"
    "    }\n"
    "    score_store[method] = {'val': val_scores, 'test': test_scores}\n"
    "    return pd.DataFrame(results[method]).T.round(4)"
))

# ---------------------------------------------------------------------------
# Section 6: Baseline: SIFT and RANSAC
# ---------------------------------------------------------------------------
cells.append(section("Baseline: SIFT and RANSAC", "6"))

cells.append(md(
    "The classical baseline needs no training. SIFT keypoints are extracted after contrast "
    "equalisation, a FLANN index over all gallery descriptors shortlists the most-voted gallery "
    "images, and RANSAC keeps only matches that agree on one geometric transform. The score is the "
    "number of RANSAC inliers, which a verifier can inspect directly."
))

cells.append(code(
    "def sift_features(rel: str):\n"
    "    img = cv2.imread(str(CFG.IMAGE_ROOT / rel), cv2.IMREAD_GRAYSCALE)\n"
    "    scale = CFG.SIFT_MAX_SIDE / max(img.shape)\n"
    "    if scale < 1:\n"
    "        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)\n"
    "    img = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(img)\n"
    "    kps, desc = cv2.SIFT_create(nfeatures=CFG.SIFT_FEATURES).detectAndCompute(img, None)\n"
    "    if desc is None or len(kps) < CFG.SIFT_MIN_MATCH:\n"
    "        return None\n"
    "    return np.float32([k.pt for k in kps]), desc\n"
    "\n"
    "\n"
    "def ransac_inliers(a, b) -> int:\n"
    "    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(a[1], b[1], k=2)\n"
    "    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < CFG.SIFT_RATIO * n.distance]\n"
    "    if len(good) < CFG.SIFT_MIN_MATCH:\n"
    "        return 0\n"
    "    src = a[0][[m.queryIdx for m in good]]\n"
    "    dst = b[0][[m.trainIdx for m in good]]\n"
    "    _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)\n"
    "    return 0 if mask is None else int(mask.sum())\n"
    "\n"
    "\n"
    "def sift_scores(group: dict, feats: dict) -> np.ndarray:\n"
    "    gallery_animals = list(group['gallery'])\n"
    "    gallery = [(ai, img) for ai, a in enumerate(gallery_animals) for img in group['gallery'][a] if feats[img]]\n"
    "    index = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=64))\n"
    "    for _, img in gallery:\n"
    "        index.add([feats[img][1]])\n"
    "    index.train()\n"
    "\n"
    "    def score_query(q: dict) -> np.ndarray:\n"
    "        row = np.zeros(len(gallery_animals))\n"
    "        f = feats[q['image']]\n"
    "        if f is None:\n"
    "            return row\n"
    "        votes = Counter(m[0].imgIdx for m in index.knnMatch(f[1], k=1) if m)\n"
    "        for gi, _ in votes.most_common(CFG.SIFT_SHORTLIST):\n"
    "            ai, img = gallery[gi]\n"
    "            row[ai] = max(row[ai], ransac_inliers(f, feats[img]))\n"
    "        return row\n"
    "\n"
    "    return np.stack([score_query(q) for q in tqdm(group['queries'], desc='SIFT queries')])"
))

cells.append(md(
    "Features are extracted once for every validation and test image in parallel threads, because "
    "OpenCV releases the Python interpreter lock during extraction."
))

cells.append(code(
    "eval_images = sorted({\n"
    "    img for g in ('val', 'test')\n"
    "    for img in [i for v in split[g]['gallery'].values() for i in v] + [q['image'] for q in split[g]['queries']]\n"
    "})\n"
    "\n"
    "t0 = time.time()\n"
    "with ThreadPoolExecutor() as ex:\n"
    "    sift_feats = dict(zip(eval_images, ex.map(sift_features, eval_images)))\n"
    "print(f'SIFT features for {len(eval_images)} images in {time.time() - t0:.0f}s, '\n"
    "      f'{sum(v is None for v in sift_feats.values())} with too few keypoints')\n"
    "\n"
    "sift_val = sift_scores(split['val'], sift_feats)\n"
    "sift_test = sift_scores(split['test'], sift_feats)\n"
    "record('sift_ransac', sift_val, sift_test)"
))

# ---------------------------------------------------------------------------
# Section 7: Zero-Shot Foundation Models
# ---------------------------------------------------------------------------
cells.append(section("Zero-Shot Foundation Models", "7"))

cells.append(md(
    "Before any fine-tuning, DINOv2 and DINOv3 are used exactly as released. Each image becomes the "
    "backbone's pooled embedding, each registered animal is represented by the mean of its gallery "
    "embeddings, and the score is cosine similarity. This measures how much muzzle identity the "
    "pretrained features already carry and decides which backbone to fine-tune."
))

cells.append(code(
    "class ImageDataset(Dataset):\n"
    "    def __init__(self, items: list[str], labels: list[int] | None, transform):\n"
    "        self.items, self.labels, self.transform = items, labels, transform\n"
    "\n"
    "    def __len__(self):\n"
    "        return len(self.items)\n"
    "\n"
    "    def __getitem__(self, i):\n"
    "        img = self.transform(Image.open(CFG.IMAGE_ROOT / self.items[i]).convert('RGB'))\n"
    "        return img, (self.labels[i] if self.labels is not None else -1)\n"
    "\n"
    "\n"
    "def create_backbone(name: str) -> nn.Module:\n"
    "    return timm.create_model(name, pretrained=True, num_classes=0, img_size=CFG.IMG_SIZE)\n"
    "\n"
    "\n"
    "def eval_transform(backbone: nn.Module):\n"
    "    cfg = timm.data.resolve_data_config({}, model=backbone)\n"
    "    return T.Compose([\n"
    "        T.Resize((CFG.IMG_SIZE, CFG.IMG_SIZE)),\n"
    "        T.ToTensor(),\n"
    "        T.Normalize(cfg['mean'], cfg['std']),\n"
    "    ])\n"
    "\n"
    "\n"
    "@torch.no_grad()\n"
    "def embed(model: nn.Module, images: list[str], transform) -> dict[str, np.ndarray]:\n"
    "    model.eval()\n"
    "    loader = DataLoader(ImageDataset(images, None, transform), batch_size=64,\n"
    "                        num_workers=CFG.NUM_WORKERS, shuffle=False)\n"
    "    out = []\n"
    "    for x, _ in tqdm(loader, desc='embed', leave=False):\n"
    "        out.append(F.normalize(model(x.to(CFG.DEVICE)).float(), dim=1).cpu().numpy())\n"
    "    return dict(zip(images, np.concatenate(out)))\n"
    "\n"
    "\n"
    "def cosine_scores(group: dict, emb: dict[str, np.ndarray]) -> np.ndarray:\n"
    "    gallery = np.stack([np.mean([emb[i] for i in imgs], axis=0) for imgs in group['gallery'].values()])\n"
    "    gallery /= np.linalg.norm(gallery, axis=1, keepdims=True)\n"
    "    queries = np.stack([emb[q['image']] for q in group['queries']])\n"
    "    return queries @ gallery.T"
))

cells.append(md(
    "Both backbones are scored on the same validation and test animals as the SIFT baseline."
))

cells.append(code(
    "for name in CFG.ZERO_SHOT_BACKBONES:\n"
    "    backbone = create_backbone(name).to(CFG.DEVICE)\n"
    "    emb = embed(backbone, eval_images, eval_transform(backbone))\n"
    "    method = 'zeroshot_' + name.split('.')[0]\n"
    "    display(record(method, cosine_scores(split['val'], emb), cosine_scores(split['test'], emb)))\n"
    "    del backbone\n"
    "\n"
    "pd.DataFrame({m: r['val'] for m, r in results.items()}).T.round(4)"
))

# ---------------------------------------------------------------------------
# Section 8: DINOv3 and ArcFace Fine-Tuning
# ---------------------------------------------------------------------------
cells.append(section("DINOv3 and ArcFace Fine-Tuning", "8"))

cells.append(md(
    "Fine-tuning uses only the training animals. The backbone's early blocks stay frozen to keep the "
    "general features learned during pretraining, and only the last blocks, a projection layer, and "
    "the ArcFace head are trained. After every epoch the model is evaluated on validation animals with "
    "the same open-set protocol, and the checkpoint with the best correct-match rate is kept."
))

cells.append(md(
    "## Training Data and Augmentation\n\n"
    "Augmentation imitates frames from a handheld phone video: small changes of crop, rotation, light, "
    "and focus. Horizontal flips are excluded, because a mirrored muzzle is a different ridge pattern "
    "rather than the same animal."
))

cells.append(code(
    "train_items = [img for a in train_animals for img in animals[a]]\n"
    "label_of = {a: i for i, a in enumerate(train_animals)}\n"
    "train_labels = [label_of[a] for a in train_animals for _ in animals[a]]\n"
    "\n"
    "data_cfg = timm.data.resolve_data_config({}, model=create_backbone(CFG.BACKBONE))\n"
    "train_transform = T.Compose([\n"
    "    T.RandomResizedCrop(CFG.IMG_SIZE, scale=(0.7, 1.0), ratio=(0.85, 1.18)),\n"
    "    T.RandomRotation(15),\n"
    "    T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2),\n"
    "    T.RandomApply([T.GaussianBlur(5, sigma=(0.1, 1.5))], p=0.3),\n"
    "    T.ToTensor(),\n"
    "    T.Normalize(data_cfg['mean'], data_cfg['std']),\n"
    "])\n"
    "test_transform = T.Compose([\n"
    "    T.Resize((CFG.IMG_SIZE, CFG.IMG_SIZE)),\n"
    "    T.ToTensor(),\n"
    "    T.Normalize(data_cfg['mean'], data_cfg['std']),\n"
    "])\n"
    "\n"
    "train_loader = DataLoader(\n"
    "    ImageDataset(train_items, train_labels, train_transform),\n"
    "    batch_size=CFG.BATCH_SIZE, shuffle=True, drop_last=True, num_workers=CFG.NUM_WORKERS,\n"
    ")\n"
    "print(f'Training animals: {len(train_animals)}  images: {len(train_items)}  batches/epoch: {len(train_loader)}')"
))

cells.append(md(
    "## Model\n\n"
    "The embedding model maps an image to a unit-length 512-dimensional vector. ArcFace compares that "
    "vector with one learned direction per training animal and adds an angular margin to the correct "
    "animal's angle, so the model must separate identities by more than the margin."
))

cells.append(code(
    "class MuzzleEmbedder(nn.Module):\n"
    "    def __init__(self, backbone_name: str):\n"
    "        super().__init__()\n"
    "        self.backbone = create_backbone(backbone_name)\n"
    "        self.proj = nn.Sequential(\n"
    "            nn.Linear(self.backbone.num_features, CFG.EMBED_DIM),\n"
    "            nn.BatchNorm1d(CFG.EMBED_DIM),\n"
    "        )\n"
    "\n"
    "    def forward(self, x):\n"
    "        return F.normalize(self.proj(self.backbone(x)), dim=1)\n"
    "\n"
    "\n"
    "class ArcFaceHead(nn.Module):\n"
    "    def __init__(self, n_classes: int):\n"
    "        super().__init__()\n"
    "        self.weight = nn.Parameter(torch.empty(n_classes, CFG.EMBED_DIM))\n"
    "        nn.init.xavier_uniform_(self.weight)\n"
    "        self.cos_m, self.sin_m = math.cos(CFG.ARC_MARGIN), math.sin(CFG.ARC_MARGIN)\n"
    "        self.th = math.cos(math.pi - CFG.ARC_MARGIN)\n"
    "        self.mm = math.sin(math.pi - CFG.ARC_MARGIN) * CFG.ARC_MARGIN\n"
    "\n"
    "    def forward(self, emb, labels):\n"
    "        cos = emb @ F.normalize(self.weight, dim=1).T\n"
    "        sin = torch.sqrt((1.0 - cos ** 2).clamp(1e-7, 1.0))\n"
    "        # cos(theta + m) = cos(theta)cos(m) - sin(theta)sin(m)\n"
    "        cos_margin = cos * self.cos_m - sin * self.sin_m\n"
    "        cos_margin = torch.where(cos > self.th, cos_margin, cos - self.mm)\n"
    "        one_hot = F.one_hot(labels, cos.shape[1]).bool()\n"
    "        return torch.where(one_hot, cos_margin, cos) * CFG.ARC_SCALE\n"
    "\n"
    "\n"
    "def freeze_early_blocks(model: MuzzleEmbedder) -> None:\n"
    "    for p in model.backbone.parameters():\n"
    "        p.requires_grad = False\n"
    "    for block in model.backbone.blocks[-CFG.TRAINABLE_BLOCKS:]:\n"
    "        for p in block.parameters():\n"
    "            p.requires_grad = True\n"
    "    for p in model.backbone.norm.parameters():\n"
    "        p.requires_grad = True\n"
    "\n"
    "\n"
    "model = MuzzleEmbedder(CFG.BACKBONE).to(CFG.DEVICE)\n"
    "head = ArcFaceHead(len(train_animals)).to(CFG.DEVICE)\n"
    "freeze_early_blocks(model)\n"
    "train_model = nn.DataParallel(model) if CFG.N_GPUS > 1 else model\n"
    "n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)\n"
    "print(f'Trainable backbone + projection parameters: {n_trainable / 1e6:.1f}M  GPUs used: {max(1, CFG.N_GPUS)}')"
))

cells.append(md(
    "## Training Loop\n\n"
    "The backbone and the new layers use separate learning rates, with a linear warmup followed by "
    "cosine decay. On Kaggle's T4 x2 machine the batch is split across both GPUs with `DataParallel`, "
    "and mixed precision is used on CUDA only. Validation after each epoch reuses the "
    "evaluation protocol from Section 5, so the selected checkpoint is optimised for open-set "
    "identification rather than training accuracy."
))

cells.append(code(
    "def validate(model: nn.Module) -> dict:\n"
    "    group = split['val']\n"
    "    images = [i for v in group['gallery'].values() for i in v] + [q['image'] for q in group['queries']]\n"
    "    scores = cosine_scores(group, embed(model, images, test_transform))\n"
    "    return compute_metrics(scores, group, pick_threshold(scores, group))\n"
    "\n"
    "\n"
    "def train() -> pd.DataFrame:\n"
    "    optimizer = torch.optim.AdamW([\n"
    "        {'params': [p for p in model.backbone.parameters() if p.requires_grad], 'lr': CFG.LR_BACKBONE},\n"
    "        {'params': list(model.proj.parameters()) + list(head.parameters()), 'lr': CFG.LR_HEAD},\n"
    "    ], weight_decay=CFG.WEIGHT_DECAY)\n"
    "    total = CFG.EPOCHS * len(train_loader)\n"
    "    warmup = CFG.WARMUP_EPOCHS * len(train_loader)\n"
    "    scheduler = torch.optim.lr_scheduler.LambdaLR(\n"
    "        optimizer,\n"
    "        lambda s: (s + 1) / warmup if s < warmup else 0.5 * (1 + math.cos(math.pi * (s - warmup) / max(1, total - warmup))),\n"
    "    )\n"
    "    use_amp = CFG.DEVICE == 'cuda'\n"
    "    scaler = torch.amp.GradScaler(enabled=use_amp)\n"
    "\n"
    "    history, best = [], -1.0\n"
    "    for epoch in range(1, CFG.EPOCHS + 1):\n"
    "        train_model.train()\n"
    "        head.train()\n"
    "        losses, t0 = [], time.time()\n"
    "        for x, y in tqdm(train_loader, desc=f'epoch {epoch}', leave=False):\n"
    "            x, y = x.to(CFG.DEVICE), y.to(CFG.DEVICE)\n"
    "            with torch.autocast('cuda', enabled=use_amp):\n"
    "                loss = F.cross_entropy(head(train_model(x), y), y)\n"
    "            optimizer.zero_grad(set_to_none=True)\n"
    "            scaler.scale(loss).backward()\n"
    "            scaler.step(optimizer)\n"
    "            scaler.update()\n"
    "            scheduler.step()\n"
    "            losses.append(loss.item())\n"
    "        m = validate(model)\n"
    "        history.append({'epoch': epoch, 'loss': np.mean(losses), **m, 'seconds': time.time() - t0})\n"
    "        flag = ''\n"
    "        if m['correct_match'] > best:\n"
    "            best = m['correct_match']\n"
    "            torch.save(model.state_dict(), CFG.RUN_DIR / 'best.pt')\n"
    "            flag = '  <- best'\n"
    "        print(f\"epoch {epoch:2d}  loss {np.mean(losses):.3f}  val rank1 {m['rank1']:.3f}  \"\n"
    "              f\"correct {m['correct_match']:.3f}  unk_fmr {m['unknown_fmr']:.3f}{flag}\")\n"
    "    history = pd.DataFrame(history)\n"
    "    history.to_csv(CFG.RUN_DIR / 'history.csv', index=False)\n"
    "    return history\n"
    "\n"
    "\n"
    "if CFG.RUN_NAME == 'INFERENCE':\n"
    "    history = None\n"
    "else:\n"
    "    history = train()"
))

cells.append(md(
    "The loss and the validation metrics are plotted per epoch to check that open-set performance "
    "improves together with the training loss rather than overfitting the training animals."
))

cells.append(code(
    "if history is not None:\n"
    "    fig, axes = plt.subplots(1, 2, figsize=(12, 3.5))\n"
    "    axes[0].plot(history['epoch'], history['loss'], marker='o')\n"
    "    axes[0].set(title='ArcFace training loss', xlabel='Epoch', ylabel='Loss')\n"
    "    for col in ('rank1', 'correct_match', 'unknown_fmr'):\n"
    "        axes[1].plot(history['epoch'], history[col], marker='o', label=col)\n"
    "    axes[1].set(title='Validation (open set)', xlabel='Epoch', ylim=(0, 1))\n"
    "    axes[1].legend()\n"
    "    plt.tight_layout()\n"
    "    plt.savefig(CFG.FIG_DIR / 'training.png', dpi=120)\n"
    "    plt.show()"
))

cells.append(md(
    "The best checkpoint is reloaded and scored once on validation and test animals with the shared "
    "protocol. The test animals were not used to choose the checkpoint or the threshold."
))

cells.append(code(
    "model.load_state_dict(torch.load(CFG.RUN_DIR / 'best.pt', map_location=CFG.DEVICE))\n"
    "ft_emb = embed(model, eval_images, test_transform)\n"
    "record('dinov3_arcface', cosine_scores(split['val'], ft_emb), cosine_scores(split['test'], ft_emb))"
))

# ---------------------------------------------------------------------------
# Section 9: Hybrid: Embedding Retrieval and SIFT Verification
# ---------------------------------------------------------------------------
cells.append(section("Hybrid: Embedding Retrieval and SIFT Verification", "9"))

cells.append(md(
    "Cosine similarity ranks candidates well, but a cosine threshold chosen on validation animals "
    "does not transfer reliably: its meaning shifts with gallery size and with the few unknown animals "
    "available for calibration. A RANSAC inlier count measures geometric agreement between two specific "
    "muzzle patterns, so its threshold keeps the same meaning across galleries. The hybrid uses the "
    "fine-tuned embedding to shortlist the top candidates and SIFT with RANSAC to verify them."
))

cells.append(code(
    "def hybrid_scores(group: dict, emb: dict[str, np.ndarray]) -> np.ndarray:\n"
    "    gallery_animals = list(group['gallery'])\n"
    "    cos = cosine_scores(group, emb)\n"
    "    shortlist = np.argsort(-cos, axis=1)[:, :CFG.HYBRID_TOP_K]\n"
    "\n"
    "    def verify(qi: int) -> np.ndarray:\n"
    "        # Cosine only breaks ties between candidates with equal inlier counts (it adds less than 0.001).\n"
    "        row = (cos[qi] + 1) / 2 * 1e-3\n"
    "        f = sift_feats[group['queries'][qi]['image']]\n"
    "        if f is None:\n"
    "            return row\n"
    "        for ai in shortlist[qi]:\n"
    "            imgs = group['gallery'][gallery_animals[ai]]\n"
    "            row[ai] += max(ransac_inliers(f, sift_feats[i]) for i in imgs if sift_feats[i] is not None)\n"
    "        return row\n"
    "\n"
    "    with ThreadPoolExecutor() as ex:\n"
    "        return np.stack(list(tqdm(ex.map(verify, range(len(group['queries']))),\n"
    "                                  total=len(group['queries']), desc='verify')))\n"
    "\n"
    "\n"
    "record('hybrid_dinov3_sift', hybrid_scores(split['val'], ft_emb), hybrid_scores(split['test'], ft_emb))"
))

# ---------------------------------------------------------------------------
# Section 10: Results Comparison
# ---------------------------------------------------------------------------
cells.append(section("Results Comparison", "10"))

cells.append(md(
    "All methods are compared on the test animals with thresholds chosen on validation animals. "
    "A method qualifies only if its validation threshold still holds on test, meaning the unknown-animal "
    "false-match rate stays within twice the 5% target. Qualifying methods are then ranked by "
    "`correct_match`."
))

cells.append(code(
    "leaderboard = pd.DataFrame({m: r['test'] for m, r in results.items()}).T\n"
    "leaderboard['threshold_holds'] = leaderboard['unknown_fmr'] <= 2 * CFG.TARGET_UNKNOWN_FMR\n"
    "leaderboard = leaderboard.sort_values(['threshold_holds', 'correct_match'], ascending=False).round(4)\n"
    "best_method = leaderboard.index[0]\n"
    "\n"
    "(CFG.RESULT_DIR / 'muzzle_leaderboard.json').write_text(json.dumps(\n"
    "    {m: {s: {k: float(v) for k, v in r[s].items()} for s in r} for m, r in results.items()}, indent=1))\n"
    "(CFG.RESULT_DIR / 'muzzle_leaderboard.md').write_text(\n"
    "    f'# Muzzle leaderboard (test animals, split {CFG.SPLIT_PATH.name})\\n\\n' + leaderboard.to_markdown() + '\\n')\n"
    "print(f'Best method on test: {best_method}')\n"
    "leaderboard"
))

cells.append(md(
    "The score distributions of the best method show how far apart correct matches and unknown "
    "animals sit. A wide gap means the threshold is robust; overlap means more cases will be sent to "
    "the verifier."
))

cells.append(code(
    "group = split['test']\n"
    "scores = score_store[best_method]['test']\n"
    "ranked, ranked_scores = top_candidates(scores, list(group['gallery']))\n"
    "truth = np.array([q['animal'] for q in group['queries']])\n"
    "reg = np.array([q['registered'] for q in group['queries']])\n"
    "correct = reg & (ranked[:, 0] == truth)\n"
    "wrong = reg & (ranked[:, 0] != truth)\n"
    "threshold = results[best_method]['test']['threshold']\n"
    "\n"
    "plt.figure(figsize=(9, 3.5))\n"
    "bins = np.linspace(ranked_scores[:, 0].min(), ranked_scores[:, 0].max(), 50)\n"
    "plt.hist(ranked_scores[correct, 0], bins=bins, alpha=0.6, label='registered, correct top-1')\n"
    "plt.hist(ranked_scores[wrong, 0], bins=bins, alpha=0.6, label='registered, wrong top-1')\n"
    "plt.hist(ranked_scores[~reg, 0], bins=bins, alpha=0.6, label='unknown animal')\n"
    "plt.axvline(threshold, color='black', linestyle='--', label='threshold (from val)')\n"
    "plt.title(f'Top-1 score distribution on test animals: {best_method}')\n"
    "plt.xlabel('Score')\n"
    "plt.ylabel('Queries')\n"
    "plt.legend()\n"
    "plt.tight_layout()\n"
    "plt.savefig(CFG.FIG_DIR / 'score_distribution.png', dpi=120)\n"
    "plt.show()"
))

# ---------------------------------------------------------------------------
# Section 11: Export to ONNX
# ---------------------------------------------------------------------------
cells.append(section("Export to ONNX", "11"))

cells.append(md(
    "The fine-tuned embedder is exported to ONNX so the Veyra vision service can run it with "
    "`onnxruntime` and no PyTorch dependency. The ArcFace head is not exported, because inference only "
    "needs embeddings. The exported model is checked against the PyTorch model on real images, and a "
    "model card records the data, split, metrics, and limits."
))

cells.append(code(
    "export_model = MuzzleEmbedder(CFG.BACKBONE)\n"
    "export_model.load_state_dict(torch.load(CFG.RUN_DIR / 'best.pt', map_location='cpu'))\n"
    "export_model.eval()\n"
    "\n"
    "onnx_path = CFG.EXPORT_DIR / 'muzzle_embed_v1.onnx'\n"
    "dummy = torch.randn(1, 3, CFG.IMG_SIZE, CFG.IMG_SIZE)\n"
    "torch.onnx.export(\n"
    "    export_model, dummy, onnx_path,\n"
    "    input_names=['image'], output_names=['embedding'],\n"
    "    dynamic_axes={'image': {0: 'batch'}, 'embedding': {0: 'batch'}},\n"
    "    opset_version=17, dynamo=False,\n"
    ")\n"
    "\n"
    "check_images = eval_images[:16]\n"
    "batch = torch.stack([test_transform(Image.open(CFG.IMAGE_ROOT / i).convert('RGB')) for i in check_images])\n"
    "with torch.no_grad():\n"
    "    torch_out = export_model(batch).numpy()\n"
    "onnx_out = ort.InferenceSession(str(onnx_path)).run(None, {'image': batch.numpy()})[0]\n"
    "print(f'ONNX file: {onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB)')\n"
    "print(f'Max abs difference vs PyTorch: {np.abs(torch_out - onnx_out).max():.2e}')"
))

cells.append(md(
    "The model card is written next to the ONNX file so that anyone deploying the model sees its "
    "evidence and its limits together."
))

cells.append(code(
    "r = results['hybrid_dinov3_sift']\n"
    "card = f'''# muzzle_embed_v1\n"
    "\n"
    "- Task: open-set individual cattle identification from muzzle crops (retrieval, not classification).\n"
    "- Backbone: {CFG.BACKBONE} (DINOv3 License), last {CFG.TRAINABLE_BLOCKS} blocks fine-tuned with ArcFace.\n"
    "- Input: RGB {CFG.IMG_SIZE}x{CFG.IMG_SIZE}, normalised with mean {data_cfg['mean']} and std {data_cfg['std']}.\n"
    "- Output: L2-normalised {CFG.EMBED_DIM}-d embedding used to shortlist the top {CFG.HYBRID_TOP_K} gallery animals by cosine similarity.\n"
    "- Verification: SIFT + ratio test + RANSAC on the shortlist (max side {CFG.SIFT_MAX_SIDE}px, CLAHE); score = inlier count.\n"
    "- Accept a match when inliers > {r['test']['threshold']:.0f} (chosen on validation animals for unknown false-match rate <= {CFG.TARGET_UNKNOWN_FMR:.0%}). Cosine alone is not used for acceptance: its validation threshold did not transfer to test.\n"
    "- Data: Beef Cattle Muzzle database, Li et al. 2022, Zenodo 6324361, CC BY 4.0. Split {CFG.SPLIT_PATH.name}, by animal.\n"
    "\n"
    "## Test animals, hybrid pipeline (never used for training, checkpoint, or threshold)\n"
    "\n"
    "| Metric | Value |\n"
    "| --- | --- |\n"
    "| Correct match at threshold | {r['test']['correct_match']:.3f} |\n"
    "| Unknown-animal false-match rate | {r['test']['unknown_fmr']:.3f} |\n"
    "| Rank-1 | {r['test']['rank1']:.3f} |\n"
    "| Top-5 | {r['test']['top5']:.3f} |\n"
    "\n"
    "## Limits\n"
    "\n"
    "- US feedlot cattle and cropped still photographs; not Chinese breeds and not phone video frames.\n"
    "- Images come from one collection period; identification across months is untested.\n"
    "- Scores are similarities, not calibrated probabilities. A match is a candidate for human verification.\n"
    "'''\n"
    "(CFG.EXPORT_DIR / 'MODEL_CARD.md').write_text(card)\n"
    "print(card)"
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
