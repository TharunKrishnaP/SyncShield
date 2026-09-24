"""Train a Sentinel-1 SAR flood-water segmentation U-Net (Phase 1 model C).

Two modes:

  --mode synthetic   Generate synthetic SAR-like chips on the fly (no GPU, no
                     downloads). A few epochs across 2-3 real train cycles that
                     end-to-end certify train -> save -> load -> infer ->
                     polygonise on any machine. This is a *pipeline smoke test*,
                     NOT a production model.

  --mode sen1floods11  Train on real Sen1Floods11 tiles extracted by
                     ``download_sen1floods11.py`` (run on Colab T4). Produces
                     the actual IoU numbers for the reviewer.

Writes to ml/artifacts/sar_unet/{model.pt, meta.json}. meta.json carries the
architecture config (so a later wrapper can rebuild the model) plus measured
validation IoU/Dice — the "how it was trained / how it was tested" record.
"""
import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

import segmentation_models_pytorch as smp

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "artifacts" / "sar_unet"


# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------
class SyntheticSAR(Dataset):
    """SAR-like chips: speckled background + darker water blobs + mask."""

    def __init__(self, n=160, size=128, seed=0):
        self.n, self.size = n, size
        self.rng = random.Random(seed)

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        size = self.size
        rng = self.rng
        # Vectorised numpy RNG derived from the python RNG so per-chip
        # reproducibility is kept while per-pixel draws stay fast.
        nprng = np.random.default_rng(rng.randrange(2**32))
        # Two SAR bands VV/VH in dB-ish scale.
        img = np.zeros((2, size, size), dtype=np.float32)
        mask = np.zeros((size, size), dtype=np.float32)
        base = -16.0 + rng.uniform(-2, 2)
        for b in range(2):
            noise = rng.uniform(0.8, 3.0)
            # per-pixel speckle (matches real SAR texture AND the demo scene
            # generator ml/sar/make_synthetic_scene.py)
            img[b] = base + nprng.normal(0.0, noise, (size, size))
        for _ in range(rng.randint(1, 4)):
            cx, cy = rng.randint(0, size - 1), rng.randint(0, size - 1)
            # wide range incl. large elongated ellipses (the demo scene's
            # blob is rx~0.6*size) so blob scale is in-distribution
            rx = rng.randint(10, max(11, int(size * 0.6)))
            ry = rng.randint(6, max(7, size // 5))
            rot = rng.uniform(0, 3.1415)
            y, x = np.mgrid[0:size, 0:size]
            dx = (x - cx) * np.cos(rot) + (y - cy) * np.sin(rot)
            dy = -(x - cx) * np.sin(rot) + (y - cy) * np.cos(rot)
            blob = ((dx / rx) ** 2 + (dy / ry) ** 2) <= 1.0
            mask[blob] = 1.0
            for b in range(2):
                img[b][blob] += rng.uniform(-6, -2)  # water = darker backscatter
        # Same per-band percentile normalisation as inference
        # (ml/sar/infer.py load_scene_array) so the model sees the exact
        # distribution it will be fed on real scenes.
        for b in range(2):
            band = img[b]
            lo, hi = np.percentile(band, 1), np.percentile(band, 99)
            img[b] = np.clip((band - lo) / max(hi - lo, 1e-6), 0, 1)
        return torch.tensor(img), torch.tensor(mask).unsqueeze(0)


class Sen1Floods11(Dataset):
    """Real tiles from the extracted Sen1Floods11 directory.

    Uses S1Hand (VV/VH) + Label .tif pairs. Label: 2 = water -> mask 1.
    """

    def __init__(self, data_dir, size=256, seed=0, augment=False):
        import rasterio

        self.size, self.rng = size, random.Random(seed)
        self.augment = augment
        self.pairs = []
        data_dir = Path(data_dir)
        for tif in sorted(data_dir.glob("**/S1Hand_*.tif")):
            cands = [
                tif.with_name(tif.name.replace("S1Hand", "Label")),
                tif.with_name("Label" + tif.name[len("S1Hand_"):]),
                tif.with_name(tif.name.replace("S1", "Label")),
            ]
            lab = next((p for p in cands if p.exists()), None)
            if lab is not None:
                self.pairs.append((str(tif), str(lab)))
        self.rasterio = rasterio
        assert self.pairs, f"no S1Hand/Label pairs found under {data_dir}"

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, i):
        img_path, lab_path = self.pairs[i]
        size = self.size
        with self.rasterio.open(img_path) as src:
            arr = src.read(out_shape=(2, size, size)).astype(np.float32)
        with self.rasterio.open(lab_path) as src:
            lab = src.read(1, out_shape=(size, size)).astype(np.float32)
        mask = (lab == 2).astype(np.float32)
        # normalise per-band percentile
        for b in range(arr.shape[0]):
            lo, hi = np.percentile(arr[b], 1), np.percentile(arr[b], 99)
            arr[b] = np.clip((arr[b] - lo) / max(hi - lo, 1e-6), 0, 1)
        if self.augment:
            if self.rng.random() < 0.5:
                arr = arr[:, :, ::-1].copy()
                mask = mask[:, ::-1].copy()
            if self.rng.random() < 0.5:
                arr = arr[:, ::-1, :].copy()
                mask = mask[:, ::-1].copy()
        return torch.tensor(arr), torch.tensor(mask).unsqueeze(0)


def make_model(encoder: str, in_channels: int, pretrained: bool):
    weights = "imagenet" if pretrained else None
    return smp.Unet(
        encoder_name=encoder,
        encoder_weights=weights,
        in_channels=in_channels,
        classes=1,
    )


def iou_dice(pred: torch.Tensor, target: torch.Tensor, eps: float = 1e-6):
    pred = (pred > 0.5).float()
    inter = (pred * target).sum(dim=(1, 2, 3))
    union = pred.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    iou = (inter + eps) / (union - inter + eps)
    dice = (2 * inter + eps) / (union + eps)
    return iou.mean().item(), dice.mean().item()


def evaluate(model, loader, device):
    model.eval()
    ious, dices = [], []
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            lo, do = iou_dice(torch.sigmoid(logits), y)
            ious.append(lo)
            dices.append(do)
    model.train()
    return float(np.mean(ious)), float(np.mean(dices))


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    if args.mode == "synthetic":
        train_ds = SyntheticSAR(n=args.train_samples, size=args.size, seed=1)
        val_ds = SyntheticSAR(n=args.val_samples, size=args.size, seed=2)
        pretrained = False
    else:
        train_ds = Sen1Floods11(args.data_dir, size=args.size, seed=1, augment=True)
        val_ds = Sen1Floods11(args.data_dir, size=args.size, seed=2, augment=False)
        n_val = max(int(len(val_ds) * 0.15), 4)
        val_ds.pairs = val_ds.pairs[:n_val]
        pretrained = True
        print(f"sen1floods11 tiles: train={len(train_ds)} val={len(val_ds)}")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    model = make_model(args.encoder, args.in_channels, pretrained).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = torch.nn.BCEWithLogitsLoss()

    best_iou, best_dice, best_state = 0.0, 0.0, None
    started = time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        run_loss, steps = 0.0, 0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            opt.step()
            run_loss += loss.item()
            steps += 1
        val_iou, val_dice = evaluate(model, val_loader, device)
        if val_iou > best_iou:
            best_iou, best_dice = val_iou, val_dice
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        print(f"epoch {epoch}/{args.epochs}  loss={run_loss / max(steps, 1):.4f}  val_iou={val_iou:.4f}  val_dice={val_dice:.4f}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    torch.save(best_state or model.state_dict(), out / "model.pt")
    meta = {
        "mode": args.mode,
        "encoder": args.encoder,
        "in_channels": args.in_channels,
        "size": args.size,
        "epochs": args.epochs,
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "val_iou": round(best_iou, 4),
        "val_dice": round(best_dice, 4),
        "elapsed_sec": round(time.time() - started, 1),
        "device": str(device),
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": (
            "synthetic mode = pipeline certification only, NOT a production model; "
            "run --mode sen1floods11 on Colab for the real model + IoU"
            if args.mode == "synthetic"
            else "trained on Sen1Floods11 via ml/sar/train_colab.ipynb"
        ),
    }
    with open(out / "meta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    print(f"\nbest val_iou={best_iou:.4f}  ->  {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["synthetic", "sen1floods11"], default="synthetic")
    ap.add_argument("--data-dir", default="/content/sen1floods11")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--encoder", default="resnet18")
    ap.add_argument("--in-channels", type=int, default=2)
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--train-samples", type=int, default=160)
    ap.add_argument("--val-samples", type=int, default=32)
    args = ap.parse_args()
    train(args)


if __name__ == "__main__":
    main()