import json
import subprocess
from datetime import date
from types import SimpleNamespace

import pytest

from stale_quotes import config, download
from stale_quotes.download import confirm, plan_requests, run

from test_instruments import DAY, TODAY, _definitions
from stale_quotes.instruments import select_instruments


class FakeClient:
    """Stands in for `databento.Historical`, recording every call."""

    def __init__(self, cost=1.5):
        self.cost = cost
        self.downloads = []
        self.metadata = SimpleNamespace(
            get_cost=lambda **kw: self.cost,
            get_billable_size=lambda **kw: 2_000_000,
        )
        self.timeseries = SimpleNamespace(get_range=self._get_range)

    def _get_range(self, path, **params):
        self.downloads.append(params)
        path.write_bytes(b"dbn")


@pytest.fixture
def selection():
    return select_instruments(_definitions(TODAY), DAY, 7001.0)


@pytest.fixture
def patched(monkeypatch, selection, tmp_path):
    monkeypatch.setattr(download, "select_many", lambda dates, client, **kw: ([selection], {date(2026, 10, 10): "weekend"}))
    monkeypatch.setattr(download, "save_selections", lambda sels: tmp_path / "instruments.parquet")
    return tmp_path / "raw"


def test_plan_splits_futures_and_options(selection, tmp_path):
    reqs = plan_requests([selection], ["mbp-1", "mbo"], tmp_path)
    assert [(r.params["schema"], r.kind) for r in reqs] == [
        ("mbp-1", "futures"), ("mbp-1", "options"), ("mbo", "futures"), ("mbo", "options"),
    ]
    futures, options = reqs[:2]
    assert futures.params["symbols"] == [selection.instrument_ids[0]]
    assert options.params["symbols"] == selection.instrument_ids[1:]
    assert futures.path == tmp_path / "mbp-1" / "20261007" / "futures.dbn.zst"
    assert options.raw_symbols[0] == "E1CV6 C6980"


@pytest.mark.parametrize("answer, expected", [("y", True), ("YES", True), ("", False), ("n", False)])
def test_confirm(answer, expected):
    assert confirm(1.0, lambda prompt: answer) is expected


def test_shows_cost_and_downloads_after_confirmation(patched, capsys):
    client, prompts = FakeClient(), []
    paths = run([DAY], raw_dir=patched, client=client, ask=lambda p: prompts.append(p) or "y")

    out = capsys.readouterr().out
    assert "total: $3.00" in out
    assert "2026-10-10: skipped, weekend" in out
    assert prompts and "$3.00" in prompts[0]
    assert len(client.downloads) == 2 and all(p.exists() for p in paths)
    manifest = json.loads(paths[1].with_name("options.json").read_text())
    assert manifest["stype_in"] == "instrument_id" and len(manifest["raw_symbols"]) == 20
    assert not list(patched.rglob("*.partial"))


def test_declining_downloads_nothing(patched):
    client = FakeClient()
    assert run([DAY], raw_dir=patched, client=client, ask=lambda p: "n") == []
    assert client.downloads == []


def test_dry_run_downloads_nothing(patched, capsys):
    client = FakeClient()
    run([DAY], raw_dir=patched, client=client, dry_run=True, ask=pytest.fail)
    assert client.downloads == []
    assert "total: $3.00" in capsys.readouterr().out


def test_cached_files_are_not_requested_again(patched):
    client = FakeClient()
    run([DAY], raw_dir=patched, client=client, assume_yes=True)
    client.downloads.clear()
    assert run([DAY], raw_dir=patched, client=client, ask=pytest.fail) == []
    assert client.downloads == []


def test_raw_data_is_git_ignored():
    ignored = subprocess.run(
        ["git", "check-ignore", "data/raw/mbp-1/20261007/options.dbn.zst", "data/processed/instruments.parquet"],
        cwd=config.ROOT_DIR, capture_output=True, text=True,
    )
    assert len(ignored.stdout.split()) == 2
