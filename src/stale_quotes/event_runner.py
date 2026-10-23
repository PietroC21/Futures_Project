"""Run the Issue 4 detector on cached ES MBP-1 data."""

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from . import config
from .events import (
    EventConfig,
    add_tick_observation_window,
    detect_events,
    load_futures_sample,
    single_update_events,
)


def run_days(dates, raw_dir=None, processed_dir=None, gap_ns=None, include_unfiltered=True):
    raw_dir = Path(raw_dir or config.RAW_DIR)
    processed_dir = Path(processed_dir or config.PROCESSED_DIR) / "events"
    processed_dir.mkdir(parents=True, exist_ok=True)

    settings = EventConfig(
        cluster_gap_ns=config.CLUSTER_GAP_NS if gap_ns is None else gap_ns
    )
    variants = [("baseline", settings)]
    if include_unfiltered and settings.cluster_gap_ns:
        variants.append(("unfiltered", EventConfig(cluster_gap_ns=0)))

    summaries = []
    for day in dates:
        sample = load_futures_sample(day, raw_dir)
        print(f"{day}: loaded {len(sample.quotes):,} records", flush=True)
        daily = processed_dir / f"{day:%Y%m%d}"
        daily.mkdir(parents=True, exist_ok=True)

        for label, cfg in variants:
            result = detect_events(sample.quotes, cfg)

            # These are counts from successive stages, not interchangeable totals.
            selected_cluster_count = len(result.events)
            single_move_cluster_count = int(result.events["n_price_moves"].eq(1).sum())
            excluded_multi_move_clusters = (
                selected_cluster_count - single_move_cluster_count
            )

            chosen = single_update_events(result, cfg)
            single_update_count = len(chosen)
            excluded_after_single_move = (
                single_move_cluster_count - single_update_count
            )

            # Keep the existing event/window generation unchanged.
            chosen = add_tick_observation_window(chosen, result.candidates, cfg)
            final_event_count = len(chosen)
            excluded_after_window = single_update_count - final_event_count

            if min(
                excluded_multi_move_clusters,
                excluded_after_single_move,
                excluded_after_window,
            ) < 0:
                raise ValueError("Event filtering counts are inconsistent")

            output_name = (
                "events.parquet" if label == "baseline" else "events_unfiltered.parquet"
            )
            chosen.to_parquet(daily / output_name, index=False, compression="zstd")

            counts = chosen["size_class"].value_counts().to_dict()
            print(
                f"  {label}: {final_event_count:,} events "
                f"from {selected_cluster_count:,} selected clusters "
                f"({excluded_multi_move_clusters:,} multi-move clusters excluded) "
                f"{counts}",
                flush=True,
            )

            breakdown = {
                "selected_cluster_count": selected_cluster_count,
                "single_move_cluster_count": single_move_cluster_count,
                "excluded_multi_move_clusters": excluded_multi_move_clusters,
                "single_update_count": single_update_count,
                "excluded_after_single_move": excluded_after_single_move,
                "excluded_after_window": excluded_after_window,
                "final_event_count": final_event_count,
            }
            diagnostics = dict(result.diagnostics)
            diagnostics["filtering_breakdown"] = breakdown
            (daily / f"diagnostics_{label}.json").write_text(
                json.dumps(diagnostics, indent=2, default=str), encoding="utf-8"
            )

            summaries.append(
                {
                    "date": day.isoformat(),
                    "variant": label,
                    "source_records": len(sample.quotes),
                    "candidate_count": len(result.candidates),
                    **breakdown,
                    "event_count": final_event_count,
                    "sub_tick": counts.get("sub_tick", 0),
                    "single_tick": counts.get("single_tick", 0),
                    "multi_tick": counts.get("multi_tick", 0),
                    "raw_window_truncated": int(
                        (chosen["observation_end_reason"] == "next_price_move").sum()
                    ),
                    "tick_window_truncated": int(
                        (chosen["observation_end_tick_reason"] == "next_tick_move").sum()
                    ),
                }
            )

    return pd.DataFrame(summaries)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate ES event tables from Issue 3 MBP-1 cache"
    )
    parser.add_argument(
        "--dates", nargs="+", default=[d.isoformat() for d in config.STUDY_DATES]
    )
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--processed-dir", type=Path)
    parser.add_argument("--cluster-gap-ns", type=int, default=None)
    parser.add_argument("--no-unfiltered", action="store_true")
    args = parser.parse_args(argv)

    summary = run_days(
        [date.fromisoformat(x) for x in args.dates],
        args.raw_dir,
        args.processed_dir,
        args.cluster_gap_ns,
        not args.no_unfiltered,
    )
    root = Path(__file__).resolve().parents[2]
    folder = root / "issue4_report"
    folder.mkdir(exist_ok=True)
    summary.to_csv(folder / "event_counts.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
