"""Download and cache ES futures and 0DTE option market data from Databento.

For every study date the instruments are chosen by `instruments.select_for_date`,
then one request per (schema, date, futures/options) is planned. Requests whose
file is already in ``data/raw/`` are skipped. The cost of the rest is estimated
and shown, and nothing is downloaded until the user confirms.

Files are stored as Databento's native compressed DBN, with a JSON manifest
next to each one recording exactly what was requested:

    data/raw/<schema>/<YYYYMMDD>/futures.dbn.zst   futures.json
    data/raw/<schema>/<YYYYMMDD>/options.dbn.zst   options.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from stale_quotes import config
from stale_quotes.instruments import (
    InstrumentSelection,
    get_client,
    save_selections,
    select_many,
)


@dataclass
class DownloadRequest:
    trading_date: date
    kind: str  # "futures" or "options"
    params: dict
    raw_symbols: list[str]
    path: Path

    @property
    def cached(self) -> bool:
        return self.path.exists()

    @property
    def label(self) -> str:
        return f"{self.params['schema']} {self.trading_date} {self.kind}"


def plan_requests(
    selections: Iterable[InstrumentSelection],
    schemas: Iterable[str] = config.SCHEMAS,
    raw_dir: Path = config.RAW_DIR,
) -> list[DownloadRequest]:
    """One futures and one options request per selection and schema."""
    requests = []
    for schema in schemas:
        for sel in selections:
            params = sel.request_params(schema)
            folder = raw_dir / schema / f"{sel.trading_date:%Y%m%d}"
            parts = {
                "futures": (sel.instrument_ids[:1], sel.raw_symbols[:1]),
                "options": (sel.instrument_ids[1:], sel.raw_symbols[1:]),
            }
            for kind, (ids, symbols) in parts.items():
                requests.append(DownloadRequest(
                    trading_date=sel.trading_date,
                    kind=kind,
                    params={**params, "symbols": ids},
                    raw_symbols=symbols,
                    path=folder / f"{kind}.dbn.zst",
                ))
    return requests


def estimate(client, requests: Iterable[DownloadRequest]) -> pd.DataFrame:
    """Databento cost (USD) and billable size of each request."""
    rows = []
    for req in requests:
        rows.append({
            "request": req.label,
            "cost_usd": client.metadata.get_cost(**req.params),
            "size_mb": client.metadata.get_billable_size(**req.params) / 1e6,
        })
    return pd.DataFrame(rows, columns=["request", "cost_usd", "size_mb"])


def confirm(total_cost: float, ask: Callable[[str], str] = input) -> bool:
    answer = ask(f"Download for an estimated ${total_cost:,.2f}? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}


def download(client, req: DownloadRequest) -> Path:
    """Fetch one request to its cache path, writing the manifest beside it.

    Data goes to a temporary file first, so an interrupted download is never
    mistaken for a cached one.
    """
    req.path.parent.mkdir(parents=True, exist_ok=True)
    partial = req.path.with_suffix(".partial")
    client.timeseries.get_range(**req.params, path=partial)
    partial.rename(req.path)
    manifest = {
        "trading_date": req.trading_date.isoformat(),
        "kind": req.kind,
        **{k: str(v) if k in ("start", "end") else v for k, v in req.params.items()},
        "raw_symbols": req.raw_symbols,
    }
    req.path.with_name(f"{req.kind}.json").write_text(json.dumps(manifest, indent=2))
    return req.path


def run(
    dates: Iterable[date] = config.STUDY_DATES,
    schemas: Iterable[str] = config.SCHEMAS,
    n_strikes: int = config.N_STRIKES,
    raw_dir: Path = config.RAW_DIR,
    assume_yes: bool = False,
    dry_run: bool = False,
    client=None,
    ask: Callable[[str], str] = input,
) -> list[Path]:
    """Select instruments, show the cost of uncached data, and download it."""
    client = client or get_client()
    selections, skipped = select_many(dates, client, n_strikes=n_strikes)
    for sel in selections:
        print(sel.summary())
    for trading_date, reason in skipped.items():
        print(f"{trading_date}: skipped, {reason}")
    if selections:
        print(f"instrument metadata: {save_selections(selections)}")

    requests = plan_requests(selections, schemas, raw_dir)
    for req in requests:
        if req.cached:
            print(f"cached: {req.path}")
    pending = [req for req in requests if not req.cached]
    if not pending:
        print("nothing to download")
        return []

    costs = estimate(client, pending)
    print()
    print(costs.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    total = costs["cost_usd"].sum()
    print(f"total: ${total:,.2f}, {costs['size_mb'].sum():,.1f} MB")

    if dry_run:
        return []
    if not assume_yes and not confirm(total, ask):
        print("cancelled")
        return []

    paths = []
    for req in pending:
        print(f"downloading {req.label} -> {req.path}")
        paths.append(download(client, req))
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Download ES futures and 0DTE option data from Databento.")
    parser.add_argument("--dates", nargs="+", type=date.fromisoformat, default=config.STUDY_DATES,
                        help="trading dates, YYYY-MM-DD (default: config.STUDY_DATES)")
    parser.add_argument("--schemas", nargs="+", default=config.SCHEMAS, help="Databento schemas (default: mbp-1)")
    parser.add_argument("--n-strikes", type=int, default=config.N_STRIKES, help="strikes around ATM")
    parser.add_argument("--raw-dir", type=Path, default=config.RAW_DIR, help="cache directory")
    parser.add_argument("--dry-run", action="store_true", help="only show the cost estimate")
    parser.add_argument("-y", "--yes", action="store_true", help="download without asking for confirmation")
    args = parser.parse_args(argv)
    run(args.dates, args.schemas, args.n_strikes, args.raw_dir, args.yes, args.dry_run)


if __name__ == "__main__":
    main()
