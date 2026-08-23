"""Pre-apply the deterministic preprocessing once, so training is GPU-bound.

Why
---
Raw APTOS images are ~2000x1500. Retina-cropping and resizing each one on every
epoch makes the data loader the bottleneck: on a laptop the GPU sits near 0%
while six CPU workers decode PNGs. Measured cost was ~238s/epoch.

The crop and resize are *deterministic* — identical every epoch — so doing them
once and caching the result is exactly equivalent, and cuts epoch time by an
order of magnitude. Augmentation still runs per-epoch on the cached image,
because in the original pipeline augmentation is applied *after* the resize.

The cache uses the same `crop_to_retina` / `resize` functions the server uses, so
train/serve parity is preserved.

Usage:
    python -m datasets.cache_preprocessed --data-dir data/aptos --output data/aptos_224
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasets.retinal_dataset import (  # noqa: E402
    CLASS_NAMES,
    class_distribution,
    crop_to_retina,
    discover_samples,
    resize,
)


def _process(job: tuple[str, str, int]) -> tuple[bool, str]:
    """Returns (ok, reason). The reason is reported rather than swallowed —
    silently dropping training images skews the class balance and invalidates
    any comparison against a differently-cached run."""
    source, destination, size = job
    try:
        with Image.open(source) as handle:
            rgb = np.asarray(handle.convert("RGB"), dtype=np.uint8)
        cropped, _ = crop_to_retina(rgb)
        resized = resize(cropped, (size, size))
        # PNG keeps the cache lossless; re-compressing to JPEG would introduce
        # artefacts the served model never sees.
        Image.fromarray(resized).save(destination, format="PNG", compress_level=1)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache preprocessed retinal images.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    samples = discover_samples(args.data_dir)
    print(f"Source: {len(samples)} images from {args.data_dir}")
    print(f"  distribution: {class_distribution(samples)}")

    output = Path(args.output).resolve()
    for name in CLASS_NAMES:
        (output / name).mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[str, str, int]] = []
    for index, sample in enumerate(samples):
        target = output / CLASS_NAMES[sample.label] / f"{sample.path.stem}_{index}.png"
        if target.exists():
            continue
        jobs.append((str(sample.path), str(target), args.image_size))

    if not jobs:
        print("  cache already complete")
    else:
        print(f"\nPreprocessing {len(jobs)} images at {args.image_size}px "
              f"across {args.workers} workers…")
        started = time.time()
        reasons: list[str] = []
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for done, (ok, reason) in enumerate(
                pool.map(_process, jobs, chunksize=16), start=1
            ):
                if not ok:
                    reasons.append(reason)
                if done % 250 == 0 or done == len(jobs):
                    rate = done / max(time.time() - started, 1e-6)
                    remaining = (len(jobs) - done) / max(rate, 1e-6)
                    print(f"  {done}/{len(jobs)}  ({rate:.0f} img/s, ~{remaining:.0f}s left)")

        elapsed = time.time() - started
        print(f"\n  finished in {elapsed:.0f}s")
        if reasons:
            print(f"  {len(reasons)} images could not be processed. Causes:")
            for cause, count in Counter(reasons).most_common(5):
                print(f"    {count:>4}x  {cause[:110]}")

    cached = discover_samples(output)
    print(f"\nCache: {len(cached)} images at {output}")
    print(f"  distribution: {class_distribution(cached)}")

    if len(cached) != len(samples):
        # Exit non-zero so a scripted pipeline halts here. An incomplete cache
        # skews the class balance and invalidates any comparison against a
        # differently-cached run — this warning was previously easy to scroll
        # past and train on regardless.
        raise SystemExit(
            f"\n  INCOMPLETE CACHE: {len(cached)} images cached, {len(samples)} in "
            f"the source ({len(samples) - len(cached)} missing).\n"
            "  Re-run with fewer --workers; failures here are usually memory\n"
            "  pressure rather than unreadable files. Do not train on this cache."
        )

    print("\nTrain on the cache:")
    print(f"  python -m training.train --data-dir {args.output} --epochs 25")


if __name__ == "__main__":
    main()
