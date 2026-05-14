"""Cross-check our SMS01-16 metadata against Widmer (2024) Table 6 (p. 32).

Widmer's thesis numbers sensors 1-16 by (side, location, depth). Our
Metadata.xlsx uses SMS01-16 with `tag` labels (slope/mount/step/down/far
for swale; top/middle/bottom for control). The mapping is by
(treatment, tag→Widmer-location, depth), with two known gotchas:

* Widmer's sensor 3 sits at the swale Step at 0.1 m; our metadata has
  no Step 0.1 m sensor (only SMS10 = Step 0.4 m). Our SMS03 instead
  sits at -10 cm "on top of mound" — i.e., above ground. Either the
  site was reconfigured after Widmer's deployment or one of the two
  records is wrong. Flagged.
* Widmer treats swale "Bottom slope 1" (sensors 6/7) and "Bottom slope 2"
  (sensors 8/9) as physically distinct. Our `tag` column distinguishes
  `down` (SwE) from `far` (SwF). The assumption here is that
  Widmer 1 ↔ down, Widmer 2 ↔ far, but this is not certain.

Output: plots/sensor_mapping_widmer.csv with one row per our SMS sensor
and the matched Widmer sensor number (or null if no match). Run from
project root with PYTHONPATH=src.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import polars as pl

from swale.metadata import parse_metadata

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "plots" / "sensor_mapping_widmer.csv"


# Widmer (2024) Table 6, p. 32. (treatment, widmer_location, depth_m).
# Indexed by Widmer's sensor number 1..16.
WIDMER_TABLE_6: dict[int, tuple[str, str, float]] = {
    1:  ("swale",   "Top slope",      0.1),
    2:  ("swale",   "Top slope",      0.4),
    3:  ("swale",   "Step",           0.1),
    4:  ("swale",   "Mound",          0.1),
    5:  ("swale",   "Mound",          0.4),
    6:  ("swale",   "Bottom slope 1", 0.1),
    7:  ("swale",   "Bottom slope 1", 0.4),
    8:  ("swale",   "Bottom slope 2", 0.1),
    9:  ("swale",   "Bottom slope 2", 0.4),
    10: ("swale",   "Step",           0.4),
    11: ("control", "Top slope",      0.1),
    12: ("control", "Top slope",      0.4),
    13: ("control", "Mid slope",      0.1),
    14: ("control", "Mid slope",      0.4),
    15: ("control", "Bottom slope",   0.1),
    16: ("control", "Bottom slope",   0.4),
}

# Our `tag` value -> Widmer's location string. Best-guess mapping based on
# the descriptive labels in Metadata.xlsx Serials. Note `down`->Bottom slope 1
# vs `far`->Bottom slope 2 is a presumption (could be the reverse).
TAG_TO_WIDMER_LOC: dict[tuple[str, str], str] = {
    ("swale",   "slope"):  "Top slope",
    ("swale",   "mount"):  "Mound",
    ("swale",   "step"):   "Step",
    ("swale",   "down"):   "Bottom slope 1",
    ("swale",   "far"):    "Bottom slope 2",
    ("control", "top"):    "Top slope",
    ("control", "middle"): "Mid slope",
    ("control", "bottom"): "Bottom slope",
}


def build_mapping(sensors: pl.DataFrame) -> pl.DataFrame:
    """Join our SMS metadata to Widmer's Table 6 by (treatment, tag, depth)."""
    rows: list[dict] = []
    used_widmer: set[int] = set()

    for row in sensors.iter_rows(named=True):
        sid = row["sensor_id"]
        treatment = row["treatment"]
        tag = row["tag"]
        depth_cm = row["depth_cm"]

        widmer_loc = TAG_TO_WIDMER_LOC.get((treatment, tag)) if treatment and tag else None

        widmer_num: int | None = None
        match_quality = "no_match"

        if widmer_loc is not None and depth_cm is not None:
            depth_m = depth_cm / 100.0
            for num, (w_treat, w_loc, w_depth) in WIDMER_TABLE_6.items():
                if (w_treat == treatment and w_loc == widmer_loc
                        and abs(w_depth - depth_m) < 1e-6):
                    widmer_num = num
                    match_quality = "ok"
                    used_widmer.add(num)
                    break

        if widmer_num is None and (depth_cm == -10):
            match_quality = "no_widmer_slot_above_ground"
        elif widmer_num is None and widmer_loc is None:
            match_quality = "tag_unmapped"
        elif widmer_num is None:
            match_quality = "no_widmer_slot"

        rows.append({
            "sensor_id":         sid,
            "our_location":      row["location"],
            "our_tag":           tag,
            "treatment":         treatment,
            "depth_cm":          depth_cm,
            "widmer_location":   widmer_loc,
            "widmer_sensor":     widmer_num,
            "match_quality":     match_quality,
        })

    mapped = pl.DataFrame(rows)

    # Append any Widmer slots that nothing in ours matched.
    missing = sorted(set(WIDMER_TABLE_6) - used_widmer)
    for num in missing:
        w_treat, w_loc, w_depth = WIDMER_TABLE_6[num]
        mapped = mapped.vstack(pl.DataFrame([{
            "sensor_id":       None,
            "our_location":    None,
            "our_tag":         None,
            "treatment":       w_treat,
            "depth_cm":        int(w_depth * 100),
            "widmer_location": w_loc,
            "widmer_sensor":   num,
            "match_quality":   "missing_from_our_metadata",
        }], schema=mapped.schema))

    return mapped.sort(["treatment", "widmer_sensor", "sensor_id"], nulls_last=True)


def main() -> None:
    warnings.filterwarnings("ignore")
    sensors, _ = parse_metadata(ROOT / "data" / "Metadata.xlsx")
    mapped = build_mapping(
        sensors.filter(pl.col("sensor_id").str.starts_with("SMS"))
    )

    OUT_CSV.parent.mkdir(exist_ok=True)
    mapped.write_csv(OUT_CSV)
    print(f"wrote {OUT_CSV.relative_to(ROOT)}\n")

    with pl.Config(tbl_rows=30, tbl_cols=12, fmt_str_lengths=30):
        print(mapped)

    # Summary
    by_q = mapped.group_by("match_quality").agg(pl.len().alias("n")).sort("n", descending=True)
    print("\nMatch-quality summary:")
    print(by_q)


if __name__ == "__main__":
    main()
