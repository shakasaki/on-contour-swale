"""Build every OhmPi cache the browser needs, in one shot.

The caches are gitignored, so a fresh checkout has none of them and
`ohmpi_browser.py` fails to load. Run this once after cloning:

    conda activate swale
    python ohmpi/scripts/build_all.py

Builds (skipping any that already exist; pass --force to rebuild all):
    ohmpi/cache/r_table.parquet      <- build_r_table.py
    ohmpi/cache/waveforms/<...>      <- build_waveform_cache.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE.parent / "cache"

# (script, output path used to detect "already built")
STEPS = [
    ("build_r_table.py", CACHE_DIR / "r_table.parquet"),
    ("build_waveform_cache.py", CACHE_DIR / "waveforms"),
]


def main(force: bool) -> None:
    for script, out in STEPS:
        if out.exists() and not force:
            print(f"skip {script}: {out.name} already present (use --force to rebuild)")
            continue
        print(f"=== running {script} ===", flush=True)
        subprocess.run([sys.executable, str(HERE / script)], check=True)


if __name__ == "__main__":
    main(force="--force" in sys.argv[1:])
