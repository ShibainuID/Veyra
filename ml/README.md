# Veyra ML

Training and evaluation for cattle muzzle identification and weight estimation. Serving code lives in `vision/`; only evaluated models are exported there.

## Setup

```bash
cd ml
uv venv --python 3.12
uv pip install -r pyproject.toml
```

## Data (not committed)

| Folder | Source | Licence |
| --- | --- | --- |
| `data/raw/li2022_muzzle/` | R9 Beef Cattle Muzzle, [Zenodo 6324361](https://zenodo.org/records/6324361), 643.7 MB, md5 `f2b19d9bab2fc668460a796259944204` | CC BY 4.0 |
| `data/raw/mendeley_weight/` | R11 Cattle side and back view, [Mendeley h2s22wr5py v3](https://data.mendeley.com/datasets/h2s22wr5py) | CC BY 4.0 |

## Muzzle benchmark

The whole pipeline (profiling, animal-level splits, SIFT baseline, DINOv2/DINOv3 zero-shot, DINOv3 + ArcFace fine-tuning, comparison, ONNX export) lives in one notebook generated from a builder script:

```bash
python3 notebooks/build_muzzle_training.py
```

Splits are by animal, never by image (PRD Section 4.3), and `splits/` is committed so every method is scored on the same animals. The match threshold is chosen on validation animals (unknown-animal false-match rate at most 5%) and reported once on test animals.

## Training on Kaggle (GPU T4 x2)

Computer-vision training runs on Kaggle with the `NvidiaTeslaT4` (T4 x2) accelerator. The notebook splits each batch across both GPUs.

Upload R9 once as a private dataset (Kaggle extracts the zip):

```bash
cp data/raw/li2022_muzzle/BeefCattle_Muzzle_database.zip kaggle/dataset_li2022/
kaggle datasets create -p kaggle/dataset_li2022
```

Push and run the training notebook, then fetch its outputs:

```bash
python3 notebooks/build_muzzle_training.py
cp notebooks/muzzle_training.ipynb kaggle/kernel_muzzle/
kaggle kernels push -p kaggle/kernel_muzzle --accelerator NvidiaTeslaT4
kaggle kernels status athillazaidan/veyra-muzzle-training
kaggle kernels output athillazaidan/veyra-muzzle-training -p runs/kaggle_muzzle
```
