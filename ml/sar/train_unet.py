"""Train a Sentinel-1 SAR flood-water segmentation U-Net (Phase 1 model C).

Real-data mode only — no synthetic data anywhere in the pipeline:

  Train on real Sen1Floods11 tiles extracted by ``download_sen1floods11.py``
  (run on Colab T4, or locally on CPU). Produces the actual IoU numbers for
  the reviewer. The mode flag is gone: this script only trains ``sen1floods11``.

Writes to ml/artifacts/sar_unet/{model.pt, meta.json}. meta.json carries the
architecture config (so a later wrapper can rebuild the model) plus measured
validation IoU/Dice — the "how it was trained / how it was tested" record.
"""
import argparse
import hashlib
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
def _fold(name: str, val_frac: float = 0.15) -> int:
    """Deterministic 0..99 bucket of a chip filename (stable across runs/VMs)."""
    return int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16) % 100


class Sen1Floods11(Dataset):
    """Real tiles from the canonical GCS layout (download_sen1floods11.py).

    Two pools are fetched per event:
      WeakLabeled/  - auto Otsu water labels (train pool, per dataset metadata)
      HandLabeled/  - human QC water labels (val pool, per dataset metadata)

    S1 imagery is 2-band float32 dB (VV/VH); labels are int16 with the
    canonical Sen1Floods11 encoding: 1 = water, -1 = no data (masked out of
    the loss via the returned weight), 0 = not water. ``partition`` selects
    the pool: "train" -> WeakLabeled, "val" -> HandLabeled. This is the
    dataset's own geographic split (no chip-id overlap), so validation is
    genuinely held-out. If the two-pool layout is absent it falls back to a
    deterministic 85/15 chip-id hash split.
    """

    SPLIT_VAL_FRAC = 0.15

    def __init__(self, data_dir, size=256, seed=0, augment=False, partition="all"):
        import rasterio

        self.size, self.rng = size, random.Random(seed)
        self.augment = augment
        data_dir = Path(data_dir)
        self.split_note = ""

        def collect(base):
            pairs = []
            for tif in sorted(base.glob("**/S1Hand_*.tif")):
                cands = [
                    tif.with_name(tif.name.replace("S1Hand", "Label")),
                    tif.with_name("Label" + tif.name[len("S1Hand_"):]),
                    tif.with_name(tif.name.replace("S1", "Label")),
                ]
                lab = next((p for p in cands if p.exists()), None)
                if lab is not None:
                    pairs.append((str(tif), str(lab)))
            return pairs

        weak_dir = data_dir / "WeakLabeled"
        hand_dir = data_dir / "HandLabeled"
        weak_pairs = collect(weak_dir)
        hand_pairs = collect(hand_dir)
        if weak_pairs and hand_pairs:
            # canonical dataset split: train on weak labels, val on hand labels
            self.split_note = "canonical split (train=WeakLabeled, val=HandLabeled)"
            if partition == "train":
                self.pairs = weak_pairs
            elif partition == "val":
                self.pairs = hand_pairs
            else:
                self.pairs = weak_pairs + hand_pairs
        else:
            # fallback: 85/15 hash split over everything
            self.split_note = "85/15 chip-id hash split (fallback)"
            pairs = collect(data_dir)
            if partition == "train":
                thresh = self.SPLIT_VAL_FRAC * 100
                pairs = [p for p in pairs if _fold(Path(p[0]).name) >= thresh]
            elif partition == "val":
                thresh = self.SPLIT_VAL_FRAC * 100
                pairs = [p for p in pairs if _fold(Path(p[0]).name) < thresh]
            self.pairs = pairs
        self.rasterio = rasterio
        assert self.pairs, f"no S1Hand/Label pairs for partition='{partition}' under {data_dir}"

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, i):
        img_path, lab_path = self.pairs[i]
        size = self.size
        with self.rasterio.open(img_path) as src:
            arr = src.read(out_shape=(2, size, size)).astype(np.float32)
        # Some Sen1Floods11 tiles carry NaN/Inf nodata pixels in the imagery;
        # they would poison the percentile normalisation and push the whole
        # network to NaN. Replace them with the per-band median.
        if not np.isfinite(arr).all():
            for b in range(arr.shape[0]):
                band = arr[b]
                med = float(np.nanmedian(band))
                band[~np.isfinite(band)] = med if np.isfinite(med) else 0.0
            if not getattr(self, "_warned_nonfinite", False):
                self._warned_nonfinite = True
                print(f"  [warn] non-finite pixels replaced in {Path(img_path).name}")
        with self.rasterio.open(lab_path) as src:
            lab = src.read(1, out_shape=(size, size)).astype(np.float32)
        # Canonical Sen1Floods11 encoding: 1 = water, -1 = no data (excluded
        # from the loss via the weight), 0 = not water.
        mask = (lab == 1).astype(np.float32)
        weight = (lab != -1).astype(np.float32)
        # normalise per-band percentile
        for b in range(arr.shape[0]):
            lo, hi = np.percentile(arr[b], 1), np.percentile(arr[b], 99)
            arr[b] = np.clip((arr[b] - lo) / max(hi - lo, 1e-6), 0, 1)
        if self.augment:
            if self.rng.random() < 0.5:
                arr = arr[:, :, ::-1].copy()
                mask = mask[:, ::-1].copy()
                weight = weight[:, ::-1].copy()
            if self.rng.random() < 0.5:
                arr = arr[:, ::-1, :].copy()
                mask = mask[:, ::-1].copy()
                weight = weight[:, ::-1].copy()
        return torch.tensor(arr), torch.tensor(mask).unsqueeze(0), torch.tensor(weight).unsqueeze(0)


def make_model(encoder: str, in_channels: int, pretrained: bool):
    weights = "imagenet" if pretrained else None
    return smp.Unet(
        encoder_name=encoder,
        encoder_weights=weights,
        in_channels=in_channels,
        classes=1,
    )


def iou_dice(pred: torch.Tensor, target: torch.Tensor, weight: torch.Tensor = None, eps: float = 1e-6):
    pred = (pred > 0.5).float()
    if weight is not None:
        pred = (pred * weight).float()
        target = target * weight
    inter = (pred * target).sum(dim=(1, 2, 3))
    union = pred.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    iou = (inter + eps) / (union - inter + eps)
    dice = (2 * inter + eps) / (union + eps)
    return iou.mean().item(), dice.mean().item()


def evaluate(model, loader, device):
    model.eval()
    ious, dices = [], []
    with torch.no_grad():
        for x, y, w in loader:
            x, y, w = x.to(device), y.to(device), w.to(device)
            logits = model(x)
            lo, do = iou_dice(torch.sigmoid(logits), y, w)
            ious.append(lo)
            dices.append(do)
    model.train()
    return float(np.mean(ious)), float(np.mean(dices))


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    train_ds = Sen1Floods11(args.data_dir, size=args.size, seed=1, augment=True, partition="train")
    val_ds = Sen1Floods11(args.data_dir, size=args.size, seed=2, augment=False, partition="val")
    print(f"sen1floods11 tiles: train={len(train_ds)} val={len(val_ds)}")
    print(f"  split: {train_ds.split_note}")
    pretrained = True

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    model = make_model(args.encoder, args.in_channels, pretrained).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    best_iou, best_dice, best_state = 0.0, 0.0, None
    diverged = False
    started = time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        run_loss, steps = 0.0, 0
        for x, y, w in train_loader:
            x, y, w = x.to(device), y.to(device), w.to(device)
            opt.zero_grad()
            # weighted BCE-with-logits: weight 0 pixels (Sen1Floods11 -1
            # no-data) contribute nothing; pos_weight up-weights the sparse
            # water class (weak Otsu labels are ~1% water) so the model does
            # not collapse to all-background
            loss = F.binary_cross_entropy_with_logits(
                model(x), y, pos_weight=torch.tensor([args.pos_weight], device=device),
                reduction="none") * w
            loss = loss.sum() / w.sum().clamp(min=1.0)
            if not torch.isfinite(loss):
                # divergent run: abort before it can overwrite good artifacts
                print(f"\n  [diverged] non-finite loss at epoch {epoch} step {steps + 1} — aborting run")
                diverged = True
                break
            loss.backward()
            if args.grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            opt.step()
            run_loss += loss.item()
            steps += 1
        if diverged:
            break
        val_iou, val_dice = evaluate(model, val_loader, device)
        if val_iou > best_iou:
            best_iou, best_dice = val_iou, val_dice
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        print(f"epoch {epoch}/{args.epochs}  loss={run_loss / max(steps, 1):.4f}  val_iou={val_iou:.4f}  val_dice={val_dice:.4f}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "mode": "sen1floods11",
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
            "trained on real Sen1Floods11 India Sentinel-1 chips; "
            "labels encoded 1=water, -1=no-data masked from loss; "
            "split: " + train_ds.split_note
        ),
    }
    if diverged:
        # fail-soft: leave any existing good artifacts (model.pt + meta.json)
        # untouched; record the failure in a sidecar log instead
        (out / "diverged.log").write_text(
            json.dumps({"diverged": True, "mode": "sen1floods11",
                        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2),
            encoding="utf-8",
        )
        print(f"\n  FAILED train diverged (non-finite loss); good artifacts at {out} preserved")
        return
    torch.save(best_state or model.state_dict(), out / "model.pt")
    with open(out / "meta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    print(f"\nbest val_iou={best_iou:.4f}  ->  {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="/content/sen1floods11",
                    help="Sen1Floods11 root (created by download_sen1floods11.py)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--encoder", default="resnet18")
    ap.add_argument("--in-channels", type=int, default=2)
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--grad-clip", type=float, default=0.0,
                    help="max gradient norm (0 = off). Recommended 1.0 for real-data runs")
    ap.add_argument("--pos-weight", type=float, default=1.0,
                    help="BCE positive-class weight (water is about 1%% of weak labels; 1.0 = plain BCE)")
    args = ap.parse_args()
    train(args)


if __name__ == "__main__":
    main()