from stale_quotes.events import *
from stale_quotes.event_runner import main
"""Offline tests for quote states, tick classification and event windows."""
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
BASE = pd.Timestamp('2026-10-07T13:30:00Z')
CFG = EventConfig(cluster_gap_ns=100000, max_cluster_span_ns=1000000, reaction_window_ns=5000000)

def quotes(bids, times=None, **extra):
    if times is None:
        times = [0, *range(1000, 1000 * (len(bids) - 1), 1000), 20000] if len(bids) > 1 else [0]
    d = pd.DataFrame({'ts_event': [BASE + pd.Timedelta(t * 1000, unit='ns') for t in times], 'instrument_id': 10252, 'bid_px_00': np.array(bids, dtype=float), 'ask_px_00': np.array(bids, dtype=float) + 0.25, 'bid_sz_00': 10.0, 'ask_sz_00': 10.0, 'action': 'A', 'flags': 0})
    for k, v in extra.items():
        d[k] = v
    return d

def test_single_tick_and_required_fields():
    r = detect_events(quotes([7000, 7000.25, 7000.25]), CFG)
    e = r.events.iloc[0]
    assert e.t0 == BASE + pd.Timedelta(1000000, unit='ns')
    assert e.price_before == 7000.125 and e.price_after == 7000.375
    assert e.direction == 'up' and e.move_points == 0.25 and (e.move_ticks == 1)
    assert e.size_class == 'single_tick' and e.horizon_complete

@pytest.mark.parametrize('move,direction,size', [(0.5, 'up', 'multi_tick'), (-0.75, 'down', 'multi_tick'), (-0.25, 'down', 'single_tick')])
def test_move_size(move, direction, size):
    e = detect_events(quotes([7000, 7000 + move, 7000 + move]), CFG).events.iloc[0]
    assert e.direction == direction and e.size_class == size and (e.move_ticks == move / 0.25)

def test_half_tick_midpoint_not_rounded():
    d = quotes([7000] * 3)
    d.loc[1:, 'ask_px_00'] = 7000.5
    e = detect_events(d, CFG).events.iloc[0]
    assert e.move_points == 0.125 and e.move_ticks == 0.5 and (e.size_class == 'sub_tick')

def test_same_timestamp_size_update_does_not_erase_price_move():
    d = quotes([7000, 7000.25, 7000.25, 7000.25], [0, 1000, 1000, 20000])
    d.loc[2, 'bid_sz_00'] = 20
    r = detect_events(d, CFG)
    assert r.events.move_ticks.tolist() == [1]
    assert r.diagnostics['same_timestamp_records_collapsed'] == 1

def test_same_timestamp_round_trip_has_no_final_price_change():
    r = detect_events(quotes([7000, 7000.25, 7000, 7000], [0, 1000, 1000, 20000]), CFG)
    assert r.candidates.empty and r.events.empty

def test_size_only_updates_are_not_candidates():
    assert detect_events(quotes([7000] * 3, bid_sz_00=[10, 20, 30]), CFG).candidates.empty

def test_trade_prints_do_not_change_quote_state():
    d = quotes([7000, 7100, 7000], [0, 1000, 20000], action=['A', 'T', 'A'])
    r = detect_events(d, CFG)
    assert r.candidates.empty and r.diagnostics['trade_records_ignored'] == 1

def test_trade_after_quote_at_same_time_cannot_roll_back_quote():
    d = quotes([7000, 7000.25, 7000, 7000.25], [0, 1000, 1000, 20000], action=['A', 'A', 'T', 'A'])
    assert detect_events(d, CFG).events.move_ticks.tolist() == [1]

@pytest.mark.parametrize('column,value', [('bid_sz_00', 0), ('bid_px_00', np.nan), ('ask_px_00', 6999), ('ask_px_00', 7000), ('flags', 8), ('flags', 32), ('flags', np.nan), ('bid_px_00', 7000.01), ('ask_px_00', 9220000000.0), ('bid_sz_00', np.inf), ('ts_event', pd.NaT), ('action', 'R')])
def test_invalid_state_resets_comparison(column, value):
    d = quotes([7000, 7000.25, 7000.5, 7000.5], [0, 1000, 2000, 20000])
    d.loc[1, column] = value
    assert detect_events(d, CFG).candidates.empty

def test_final_invalid_same_timestamp_resets():
    d = quotes([7000, 7000.25, 7000.25, 7000.5, 7000.5], [0, 1000, 1000, 2000, 20000])
    d.loc[2, 'bid_sz_00'] = 0
    assert detect_events(d, CFG).events.empty

def test_large_data_gap_reinitializes():
    d = quotes([7000, 7001, 7001], [0, 2000000, 2020000])
    assert detect_events(d, CFG).candidates.empty

def test_missing_required_fields_raise():
    with pytest.raises(ValueError, match='Missing columns'):
        detect_events(quotes([7000]).drop(columns='ask_sz_00'))

def test_reordered_input_is_not_silently_sorted():
    with pytest.raises(ValueError, match='decreases'):
        detect_events(quotes([7000, 7000.25, 7000.5], [0, 2000, 1000]))

def test_multiple_futures_rejected():
    d = quotes([7000] * 3)
    d.loc[1, 'instrument_id'] = 99
    with pytest.raises(ValueError, match='one selected'):
        detect_events(d)

def test_cluster_t0_is_final_update_not_start():
    r = detect_events(quotes([7000, 7000.25, 7000.5, 7000.5], [0, 1000, 1050, 20000]), CFG)
    e = r.events.iloc[0]
    assert len(r.candidates) == 2 and len(r.events) == 1
    assert e.cluster_start == BASE + pd.Timedelta(1000000, unit='ns')
    assert e.t0 == BASE + pd.Timedelta(1050000, unit='ns') and e.move_ticks == 2
    assert e.confirmed_at == BASE + pd.Timedelta(1150000, unit='ns')
    assert r.candidates.cluster_id.nunique() == 1

def test_round_trip_suppressed_but_audited():
    r = detect_events(quotes([7000, 7000.25, 7000, 7000], [0, 1000, 1050, 20000]), CFG)
    assert r.events.empty and r.clusters.is_round_trip.iloc[0]
    assert 'round_trip' in r.clusters.exclusion_reason.iloc[0]

def test_partial_reversal_filter_can_be_disabled():
    d = quotes([7000, 7000.5, 7000.25, 7000.25], [0, 1000, 1050, 20000])
    assert detect_events(d, CFG).events.empty
    e = detect_events(d, replace(CFG, drop_reversals=False)).events.iloc[0]
    assert e.move_ticks == 1 and e.gross_move_ticks == 3 and e.has_reversal

def test_span_cap_does_not_make_artificial_independent_events():
    d = quotes([7000, 7000.25, 7000.5, 7000.75, 7001, 7001], [0, 1000, 1090, 1180, 1270, 20000])
    r = detect_events(d, replace(CFG, max_cluster_span_ns=150000))
    assert len(r.clusters) == 2 and r.events.empty
    assert r.clusters.exclusion_reason.str.contains('span_cap_split').all()

def test_singleton_option_excludes_aggregates():
    d = quotes([7000, 7000.25, 7000.5, 7000.5], [0, 1000, 1050, 20000])
    assert detect_events(d, replace(CFG, singleton_only=True)).events.empty

def test_observation_window_stops_at_next_raw_move_even_if_suppressed():
    d = quotes([7000, 7000.25, 7000.5, 7000.25, 7000.25], [0, 1000, 3000, 3050, 20000])
    r = detect_events(d, CFG)
    assert len(r.events) == 1
    e = r.events.iloc[0]
    assert e.observation_end == BASE + pd.Timedelta(3000000, unit='ns')
    assert e.observation_end_reason == 'next_price_move' and e.overlap_within_horizon
    assert not e.horizon_complete

def test_drop_overlap_policy():
    d = quotes([7000, 7000.25, 7000.5, 7000.5], [0, 1000, 3000, 20000])
    r = detect_events(d, replace(CFG, overlap_policy='drop'))
    assert r.events.move_ticks.tolist() == [1] and r.events.t0.iloc[0] == BASE + pd.Timedelta(3000000, unit='ns')
    assert 'overlap' in r.clusters.exclusion_reason.iloc[0]

def test_windows_are_non_overlapping():
    d = quotes([7000, 7000.25, 7000.5, 7000.75, 7000.75], [0, 1000, 3000, 5000, 20000])
    e = detect_events(d, CFG).events
    assert len(e) == 3
    assert (e.observation_end.iloc[:-1].reset_index(drop=True) <= e.t0.iloc[1:].reset_index(drop=True)).all()

def test_unconfirmed_tail_excluded():
    r = detect_events(quotes([7000, 7000.25], [0, 1000]), CFG)
    assert r.events.empty and r.clusters.right_context_missing.iloc[0]

def test_missing_left_context_excluded():
    r = detect_events(quotes([7000, 7000.25, 7000.25], [0, 50, 20000]), CFG)
    assert r.events.empty and r.clusters.left_context_missing.iloc[0]

def test_truncated_sample_horizon_is_disclosed():
    e = detect_events(quotes([7000, 7000.25, 7000.25], [0, 1000, 2000]), CFG).events.iloc[0]
    assert e.observation_end_reason == 'segment_end' and (not e.horizon_complete)

def test_spread_change_without_midpoint_move_is_audited():
    d = quotes([7000] * 3)
    d.loc[1:, 'bid_px_00'] = 6999.75
    d.loc[1:, 'ask_px_00'] = 7000.5
    r = detect_events(d, CFG)
    assert len(r.candidates) == 1 and r.events.empty
    assert r.candidates.direction.iloc[0] == 'flat'
    e = detect_events(d, replace(CFG, price_basis='ask')).events.iloc[0]
    assert e.move_ticks == 1 and e.direction == 'up'

def test_empty_and_no_moves_have_stable_columns():
    for d in [quotes([7000]).iloc[:0], quotes([7000] * 3)]:
        r = detect_events(d, CFG)
        assert r.events.empty and r.candidates.empty
        assert {'t0', 'price_before', 'price_after', 'move_ticks', 'direction'} <= set(r.events)

@pytest.mark.parametrize('kw', [{'cluster_gap_ns': -1}, {'tick_size': 0}, {'reaction_window_ns': float('nan')}, {'max_cluster_span_ns': 50, 'cluster_gap_ns': 100}, {'price_basis': 'trade'}, {'overlap_policy': 'unknown'}])
def test_bad_configuration(kw):
    with pytest.raises(ValueError):
        EventConfig(**kw)

def test_nanosecond_separation_preserved():
    d = quotes([7000, 7000.25, 7000.5, 7000.5], [0, 1000, 1001, 20000])
    d.loc[2, 'ts_event'] = d.loc[1, 'ts_event'] + pd.Timedelta(123, unit='ns')
    r = detect_events(d, replace(CFG, cluster_gap_ns=0))
    assert r.events.t0.iloc[1].value - r.events.t0.iloc[0].value == 123

def test_clear_followed_by_quote_at_same_timestamp_resets():
    d = quotes([7000, 7000, 7001, 7001], [0, 1000, 1000, 20000], action=['A', 'R', 'A', 'A'])
    assert detect_events(d, CFG).events.empty
'Manifest integration and a native compressed DBN round trip, without an API.'
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import pandas as pd
import pytest
DAY = date(2026, 10, 7)

@pytest.fixture
def native_sample(tmp_path):
    import databento as db
    import databento_dbn as dbn
    folder = tmp_path / 'raw' / 'mbp-1' / '20261007'
    folder.mkdir(parents=True)
    manifest = dict(trading_date='2026-10-07', kind='futures', dataset='GLBX.MDP3', schema='mbp-1', stype_in='instrument_id', symbols=[10252], raw_symbols=['ESZ6'], start=BASE.isoformat(), end=(BASE + pd.Timedelta(1, unit='s')).isoformat())
    (folder / 'futures.json').write_text(json.dumps(manifest), encoding='utf-8')
    metadata = dbn.Metadata(dataset='GLBX.MDP3', start=BASE.value, stype_in=dbn.SType('instrument_id'), stype_out=dbn.SType('instrument_id'), schema=dbn.Schema('mbp-1'))
    records = []
    for row in quotes([7000, 7000.25, 7000.25]).itertuples():
        records.append(dbn.MBP1Msg(publisher_id=1, instrument_id=10252, ts_event=row.ts_event.value, ts_recv=row.ts_event.value + 10000, price=int(row.bid_px_00 * 1000000000.0), size=10, action=dbn.Action('A'), side=dbn.Side('B'), depth=0, levels=dbn.BidAskPair(bid_px=int(row.bid_px_00 * 1000000000.0), ask_px=int(row.ask_px_00 * 1000000000.0), bid_sz=10, ask_sz=10)))
    uncompressed = tmp_path / 'synthetic.dbn'
    uncompressed.write_bytes(bytes(metadata) + b''.join((bytes(r) for r in records)))
    db.DBNStore.from_file(uncompressed).to_file(folder / 'futures.dbn.zst', compression='zstd')
    return (tmp_path / 'raw', folder, manifest)

def test_real_dbn_decoder_and_parquet_roundtrip(native_sample, tmp_path):
    raw, folder, _ = native_sample
    sample = load_futures_sample(DAY, raw)
    assert sample.quotes.bid_px_00.iloc[0] == 7000
    assert sample.manifest['raw_symbols'] == ['ESZ6']
    result = detect_events(sample.quotes, CFG)
    assert result.events.move_ticks.tolist() == [1]
    paths = write_event_result(result, tmp_path / 'out', {'kind': 'synthetic_fixture'})
    recovered = pd.read_parquet(paths['events'])
    assert recovered.t0.iloc[0].value == result.events.t0.iloc[0].value
    assert recovered.price_before.iloc[0] == 7000.125
    assert json.loads(paths['diagnostics'].read_text())['source']['kind'] == 'synthetic_fixture'

def test_preserves_selected_future_during_roll(native_sample):
    raw, folder, m = native_sample
    m['raw_symbols'] = ['ESU6']
    (folder / 'futures.json').write_text(json.dumps(m))
    assert load_futures_sample(DAY, raw).manifest['raw_symbols'] == ['ESU6']

@pytest.mark.parametrize('field,value', [('schema', 'mbo'), ('kind', 'options'), ('dataset', 'OTHER'), ('trading_date', '2026-10-08'), ('stype_in', 'raw_symbol'), ('symbols', [999]), ('symbols', [10252, 99]), ('raw_symbols', ['MESZ6']), ('start', 'bad'), ('end', '2026-10-07T00:00:00Z')])
def test_bad_manifest_rejected(native_sample, field, value):
    raw, folder, m = native_sample
    m[field] = value
    (folder / 'futures.json').write_text(json.dumps(m))
    with pytest.raises(ValueError):
        load_futures_sample(DAY, raw)

def test_missing_data_gives_download_instruction(tmp_path):
    with pytest.raises(FileNotFoundError, match='scripts/download.py'):
        load_futures_sample(DAY, tmp_path)

def test_runner_real_file_path_uses_local_sample(native_sample, tmp_path):
    from stale_quotes.event_runner import run_days
    raw, _, _ = native_sample
    summary = run_days([DAY], raw_dir=raw, processed_dir=tmp_path / 'processed', include_unfiltered=False)
    assert (tmp_path/'processed/events/20261007/events.parquet').exists()
    assert summary.event_count.iloc[0] >= 0

def test_integer_nanosecond_parameters():
    with pytest.raises(ValueError, match='integer'):
        EventConfig(cluster_gap_ns=0.5)
    with pytest.raises(ValueError, match='integer'):
        EventConfig(reaction_window_ns=True)


def test_exact_nanosecond_boundary():
    d=quotes([7000,7000.25,7000.5,7000.5],[0,1000,1001,20_000])
    d.loc[2,'ts_event']=d.loc[1,'ts_event']+pd.Timedelta(123,unit='ns')
    r=detect_events(d,replace(CFG,cluster_gap_ns=123))
    assert len(r.events)==1 and r.events.cluster_duration_ns.iloc[0]==123
    assert r.events.t0_ns.iloc[0]==d.ts_event.iloc[2].value
    r=detect_events(d,replace(CFG,cluster_gap_ns=122))
    assert len(r.events)==2


def test_single_update_uses_actual_price_change_timestamp():
    d=quotes([7000,7000,7000,7000],[0,1000,1050,20_000])
    d.loc[1:,'ask_px_00']=7000.75
    d.loc[2:,'bid_px_00']=6999.75
    d.loc[2:,'ask_px_00']=7001.0  # spread changes, midpoint unchanged
    r=detect_events(d,CFG)
    s=single_update_events(r,CFG)
    assert len(s)==1
    assert s.t0.iloc[0]==BASE+pd.Timedelta(1_000_000,unit='ns')
    assert s.cluster_end.iloc[0]==BASE+pd.Timedelta(1_050_000,unit='ns')
    assert s.move_points.iloc[0]==.25


def test_selected_windows_remain_non_overlapping_in_ns():
    r=detect_events(quotes([7000,7000.25,7000.5,7000.5],[0,1000,3000,20_000]),CFG)
    s=single_update_events(r,CFG)
    assert (s.observation_end_ns.iloc[:-1].reset_index(drop=True)<=s.t0_ns.iloc[1:].reset_index(drop=True)).all()


def test_tick_window_ignores_half_tick_flicker():
    d=quotes([7000,7000.25,7000.25,7000.5,7000.5],[0,1000,3000,5000,20000])
    d.loc[2:, 'ask_px_00'] += .25  # midpoint half-tick at t=3000us
    d.loc[3:, 'ask_px_00'] += .25  # another larger move
    cfg=replace(CFG,cluster_gap_ns=0)
    res=detect_events(d,cfg)
    primary=single_update_events(res,cfg)
    enriched=add_tick_observation_window(primary,res.candidates,cfg)
    assert {'observation_end_tick','next_tick_move','observation_end_tick_reason'} <= set(enriched.columns)
    assert (enriched.observation_end_tick>=enriched.observation_end).all()

def test_unfiltered_zero_gap():
    r=detect_events(quotes([7000,7000.25,7000,7000.5],[0,1000,1100,20000]),replace(CFG,cluster_gap_ns=0))
    s=single_update_events(r,replace(CFG,cluster_gap_ns=0))
    assert not s.empty
