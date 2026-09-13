#!/usr/bin/env python3
# -----------------2026.09.13--------------------
# Standalone helper: extract CQC sample zips into per-zip subfolders.
#
# Layout: CQC_sample/<batch_gen>/<Bxx-N>/<serial>.zip  (one zip per sensor dir)
# Each <name>.zip is extracted into a subfolder named after the zip:
#   <Bxx-N>/<serial>.zip + <Bxx-N>/<serial>/*.csv
# The .zip file itself is always kept untouched. Idempotent: skipped if the
# target subfolder already has content.
#
# Usage:
#   python3 unzip_cqc.py                 # scan CQC_sample/ near this script
#   python3 unzip_cqc.py <dir>           # scan a custom directory (recursive)

import sys
import zipfile
from pathlib import Path


def default_cqc_dir() -> Path:
    """Walk upwards from this script and use the first dir containing CQC_sample/."""
    for p in Path(__file__).resolve().parents:
        if (p / "CQC_sample").is_dir():
            return p / "CQC_sample"
    return Path("CQC_sample")


def extract_in_place(zf_path: Path):
    target = zf_path.parent / zf_path.stem
    if target.exists() and any(target.iterdir()):
        print(f"  [skip] {zf_path.name}: {target.name}/ already has content")
        return
    with zipfile.ZipFile(zf_path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if not names:
            print(f"  [skip] {zf_path.name}: empty archive")
            return
        # strip a single common leading folder, if the archive has one
        tops = {n.split("/")[0] for n in names if "/" in n}
        prefix = ""
        if len(tops) == 1 and all("/" in n for n in names):
            prefix = names[0].split("/")[0] + "/"
        target.mkdir(parents=True, exist_ok=True)
        n_files = 0
        for n in names:
            if prefix and not n.startswith(prefix):
                print(f"  [warn] {zf_path.name}: mixed layout, skipping entry {n}")
                continue
            out = target / n[len(prefix):]
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(out, "wb") as dst:
                dst.write(src.read())
            n_files += 1
    print(f"  [ok] {zf_path.name}: {n_files} files -> {target}/ (zip kept)")


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else default_cqc_dir()
    if not root.exists():
        print(f"directory not found: {root}")
        sys.exit(1)
    zips = sorted(root.rglob("*.zip"))
    if not zips:
        print(f"no zip files under {root}")
        return
    print(f"Found {len(zips)} zip file(s) under {root}")
    for zf in zips:
        extract_in_place(zf)


if __name__ == "__main__":
    main()
