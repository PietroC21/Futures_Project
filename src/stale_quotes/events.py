"""ES MBP-1 event detection and manifest-based local loading.

The detector keeps nanosecond timestamps and retains raw candidates for audit.
"""
from . import config

"""ES quote-state changes, bounded clusters and non-overlapping study windows.

The public detector accepts point-denominated MBP-1 DataFrames and has no API
or filesystem side effects. The event definition is documented above.
"""
from dataclasses import asdict, dataclass
import math
import numpy as np
import pandas as pd
BBO = ['bid_px_00', 'ask_px_00', 'bid_sz_00', 'ask_sz_00']
CANDIDATE_COLUMNS = ['candidate_id', 'instrument_id', 'segment_id', 't0', 'price_before', 'price_after', 'move_points', 'move_ticks', 'direction', 'size_class', 'bid_before', 'bid_after', 'ask_before', 'ask_after', 'bid_move_ticks', 'ask_move_ticks', 'mid_before', 'mid_after', 'is_price_move', 'cluster_id']
CLUSTER_COLUMNS = ['cluster_id', 'instrument_id', 'segment_id', 'cluster_start', 'cluster_end', 't0', 'confirmed_at', 'price_before', 'price_after', 'move_points', 'move_ticks', 'abs_move_ticks', 'direction', 'size_class', 'n_updates', 'n_price_moves', 'gross_move_ticks', 'has_reversal', 'is_round_trip', 'left_linked', 'right_linked', 'left_context_missing', 'right_context_missing', 'next_price_move', 'segment_end', 'observation_end', 'observation_end_reason', 'overlap_within_horizon', 'horizon_complete', 'selected', 'exclusion_reason']

@dataclass(frozen=True)
class EventConfig:
    price_basis: str = 'midpoint'
    tick_size: float = config.ES_FUTURES_TICK_SIZE
    cluster_gap_ns: int = config.CLUSTER_GAP_NS
    max_cluster_span_ns: int = config.MAX_CLUSTER_SPAN_NS
    reaction_window_ns: int = config.REACTION_WINDOW_NS
    max_quote_gap_ns: int = config.MAX_QUOTE_GAP_NS
    drop_reversals: bool = True
    singleton_only: bool = False
    overlap_policy: str = 'truncate'

    def __post_init__(self):
        if self.price_basis not in {'midpoint', 'bid', 'ask'}:
            raise ValueError('price_basis must be midpoint, bid or ask')
        if self.overlap_policy not in {'truncate', 'drop'}:
            raise ValueError('overlap_policy must be truncate or drop')
        if not math.isfinite(self.tick_size) or self.tick_size <= 0:
            raise ValueError('tick_size must be finite and positive')
        for name in ('cluster_gap_ns', 'max_cluster_span_ns', 'reaction_window_ns', 'max_quote_gap_ns'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise ValueError(f'{name} must be an integer number of nanoseconds')
            minimum = 0 if name == 'cluster_gap_ns' else 1
            if value < minimum or value > pd.Timedelta.max.value:
                raise ValueError(f'{name} is outside the supported range')
        if self.max_cluster_span_ns < self.cluster_gap_ns:
            raise ValueError('max_cluster_span_ns must be at least cluster_gap_ns')

@dataclass
class EventResult:
    quotes: pd.DataFrame
    candidates: pd.DataFrame
    clusters: pd.DataFrame
    events: pd.DataFrame
    diagnostics: dict

def _labels(ticks):
    a = np.abs(np.asarray(ticks, dtype=float))
    return np.select([a == 0, a < 1, a == 1], ['flat', 'sub_tick', 'single_tick'], default='multi_tick')

def _utc_ns(values):
    return pd.to_datetime(values, utc=True, errors='coerce').astype('datetime64[ns, UTC]')

def prepare_quotes(frame: pd.DataFrame, settings: EventConfig=EventConfig()) -> tuple[pd.DataFrame, dict]:
    """Normalize BBO states without bridging invalid records or session gaps.

    Trade records carry a pre-trade BBO in MBP-1; they cannot establish a new
    post-trade quote state. An unchanged trade print therefore creates no event.
    Input order is the source arrival order; decreasing exchange times raise.
    """
    d = frame.copy()
    if 'ts_event' not in d and d.index.name == 'ts_event':
        d = d.reset_index()
    required = {'ts_event', 'instrument_id', *BBO}
    missing = required - set(d.columns)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}')
    d = d.reset_index(drop=True)
    d['_arrival'] = np.arange(len(d))
    d['ts_event'] = _utc_ns(d.ts_event)
    ids = pd.to_numeric(d.instrument_id, errors='coerce')
    if ids.isna().any() or not np.isfinite(ids).all() or (ids % 1 != 0).any():
        raise ValueError('instrument_id must contain finite integer identifiers')
    d['instrument_id'] = ids.astype('int64')
    if d.instrument_id.nunique() > 1:
        raise ValueError('Pass one selected underlying future at a time; do not mix contracts')
    for column in BBO:
        d[column] = pd.to_numeric(d[column], errors='coerce')
    action = d.get('action', pd.Series('A', index=d.index)).map(lambda x: x.decode() if isinstance(x, bytes) else str(getattr(x, 'value', x)))
    n_trade = int(action.eq('T').sum())
    d['_reset_action'] = action.eq('R')
    if (d.ts_event.dropna().diff() < pd.Timedelta(0)).any():
        raise ValueError('ts_event decreases in arrival order; validate upstream ordering before detection')
    d = d.loc[~action.eq('T')].copy()
    if not d.empty:
        reset_in_group = d.groupby(['instrument_id', 'ts_event'], dropna=False)['_reset_action'].transform('any')
        d['_reset_action'] = reset_in_group
    duplicates = d.ts_event.notna() & d.duplicated(['instrument_id', 'ts_event'], keep='last')
    n_duplicates = int(duplicates.sum())
    d = d.loc[~duplicates].reset_index(drop=True)
    flags = pd.to_numeric(d.get('flags', pd.Series(0, index=d.index)), errors='coerce')
    flags_valid = flags.notna() & np.isfinite(flags) & flags.ge(0) & flags.le(255) & flags.mod(1).eq(0)
    safe_flags = flags.where(flags_valid, 0).astype('int64')
    on_grid = pd.Series(True, index=d.index)
    for column in ['bid_px_00', 'ask_px_00']:
        ticks = d[column] / settings.tick_size
        on_grid &= np.isfinite(ticks) & (ticks - ticks.round()).abs().le(1e-07)
    positive_sizes = np.isfinite(d.bid_sz_00) & np.isfinite(d.ask_sz_00) & d.bid_sz_00.gt(0) & d.ask_sz_00.gt(0)
    valid = d.ts_event.notna() & flags_valid & (safe_flags & 40).eq(0) & ~d._reset_action & on_grid & positive_sizes & d.bid_px_00.gt(0) & d.ask_px_00.lt(100000000.0) & d.ask_px_00.gt(d.bid_px_00)
    d['valid'] = valid
    d['midpoint'] = (d.bid_px_00 + d.ask_px_00) / 2
    d['price'] = d[{'midpoint': 'midpoint', 'bid': 'bid_px_00', 'ask': 'ask_px_00'}[settings.price_basis]]
    gaps = d.ts_event.diff() > pd.Timedelta(settings.max_quote_gap_ns, unit='ns')
    starts = valid & (~valid.shift(fill_value=False) | gaps)
    d['segment_id'] = starts.cumsum().astype('int64')
    d['comparable'] = valid & valid.shift(fill_value=False) & ~gaps
    d['price_before'] = d.price.shift()
    d['bid_before'] = d.bid_px_00.shift()
    d['ask_before'] = d.ask_px_00.shift()
    d['mid_before'] = d.midpoint.shift()
    diagnostics = dict(input_records=len(frame), trade_records_ignored=n_trade, same_timestamp_records_collapsed=n_duplicates, quote_states=len(d), invalid_states=int((~valid).sum()), missing_event_timestamps=int(d.ts_event.isna().sum()), continuity_segments=int(starts.sum()), price_basis=settings.price_basis)
    return (d, diagnostics)

def detect_events(frame: pd.DataFrame, settings: EventConfig=EventConfig()) -> EventResult:
    """Return quote states, all BBO price-change candidates and selected clusters."""
    quotes, diagnostics = prepare_quotes(frame, settings)
    changed = quotes.bid_px_00.ne(quotes.bid_before) | quotes.ask_px_00.ne(quotes.ask_before)
    q = quotes.loc[quotes.comparable & changed].copy()
    candidates = pd.DataFrame({'candidate_id': np.arange(len(q)), 'instrument_id': q.instrument_id.to_numpy(), 'segment_id': q.segment_id.to_numpy(), 't0': q.ts_event.to_numpy(), 'price_before': q.price_before.to_numpy(), 'price_after': q.price.to_numpy(), 'bid_before': q.bid_before.to_numpy(), 'bid_after': q.bid_px_00.to_numpy(), 'ask_before': q.ask_before.to_numpy(), 'ask_after': q.ask_px_00.to_numpy(), 'mid_before': q.mid_before.to_numpy(), 'mid_after': q.midpoint.to_numpy()})
    for prefix in ['bid', 'ask']:
        candidates[f'{prefix}_move_ticks'] = (candidates[f'{prefix}_after'] - candidates[f'{prefix}_before']) / settings.tick_size
    candidates['move_points'] = candidates.price_after - candidates.price_before
    candidates['move_ticks'] = candidates.move_points / settings.tick_size
    candidates['direction'] = np.select([candidates.move_ticks > 0, candidates.move_ticks < 0], ['up', 'down'], default='flat')
    candidates['size_class'] = _labels(candidates.move_ticks)
    candidates['is_price_move'] = candidates.move_ticks.ne(0)
    candidates['cluster_id'] = pd.Series(index=candidates.index, dtype='int64')
    cluster_frame = _cluster_candidates(candidates, quotes, settings)
    candidates = candidates.reindex(columns=CANDIDATE_COLUMNS)
    candidates['cluster_id'] = candidates.cluster_id.astype('int64')
    selected = cluster_frame.loc[cluster_frame.selected.astype(bool)].copy()
    selected.insert(0, 'event_id', selected.cluster_id)
    diagnostics.update(settings=asdict(settings), bbo_price_change_candidates=len(candidates), directional_candidates=int(candidates.is_price_move.sum()), clusters=len(cluster_frame), selected_events=len(selected), round_trip_clusters=int(cluster_frame.is_round_trip.sum()), reversal_clusters=int(cluster_frame.has_reversal.sum()), excluded_clusters=int((~cluster_frame.selected.astype(bool)).sum()))
    for table in (candidates, cluster_frame, selected):
        for column in ('t0', 'cluster_start', 'cluster_end', 'confirmed_at', 'observation_end'):
            if column in table:
                ts = pd.to_datetime(table[column], utc=True).astype('datetime64[ns, UTC]')
                values = ts.astype('int64').astype('Int64')
                table[column + '_ns'] = values.mask(ts.isna())
        if 'cluster_end_ns' in table:
            table['cluster_duration_ns'] = table.cluster_end_ns - table.cluster_start_ns
            table['confirmation_delay_ns'] = table.confirmed_at_ns - table.t0_ns
            table['observation_duration_ns'] = table.observation_end_ns - table.t0_ns
    return EventResult(quotes, candidates, cluster_frame, selected.reset_index(drop=True), diagnostics)


def _cluster_candidates(candidates, quotes, settings):
    """Build bounded clusters using integer ns and array reductions."""
    if candidates.empty:
        candidates['cluster_id'] = pd.Series(dtype='int64')
        return pd.DataFrame(columns=CLUSTER_COLUMNS)
    t = candidates.t0.astype('int64').to_numpy()
    seg = candidates.segment_id.to_numpy()
    start = np.zeros(len(t), dtype=bool)
    start[0] = True
    anchor = 0
    for j in range(1, len(t)):
        if (seg[j] != seg[j-1] or t[j]-t[j-1] > settings.cluster_gap_ns
                or t[j]-t[anchor] > settings.max_cluster_span_ns):
            start[j] = True
            anchor = j
    a = np.flatnonzero(start)
    b = np.r_[a[1:], len(t)]
    cid = np.cumsum(start)-1
    candidates['cluster_id'] = cid
    m = candidates.move_ticks.to_numpy()
    directional = m != 0
    count = np.add.reduceat(directional.astype('int64'), a)
    positive = np.add.reduceat((m > 0).astype('int64'), a)
    negative = np.add.reduceat((m < 0).astype('int64'), a)
    before = candidates.price_before.to_numpy()[a]
    after = candidates.price_after.to_numpy()[b-1]
    net = after-before
    ticks = net/settings.tick_size
    first, last = t[a], t[b-1]
    ids = seg[a]
    bounds = quotes.loc[quotes.valid].groupby('segment_id').ts_event.agg(['min','max'])
    left_bound = bounds['min'].astype('int64').reindex(ids).to_numpy()
    right_bound = bounds['max'].astype('int64').reindex(ids).to_numpy()
    left_linked = np.zeros(len(a), dtype=bool)
    right_linked = np.zeros(len(a), dtype=bool)
    if len(a)>1:
        linked = (ids[1:]==ids[:-1]) & (first[1:]-last[:-1]<=settings.cluster_gap_ns)
        left_linked[1:] = linked
        right_linked[:-1] = linked
    # Search within each continuity segment; a later segment is never a successor.
    sentinel = np.iinfo('int64').max
    next_move = np.full(len(a), sentinel, dtype='int64')
    dt = t[directional]
    ds = seg[directional]
    pos = np.searchsorted(dt, last, side='right')
    valid_pos = np.flatnonzero(pos<len(dt))
    valid_pos = valid_pos[ds[pos[valid_pos]]==ids[valid_pos]]
    next_move[valid_pos] = dt[pos[valid_pos]]
    desired = last+settings.reaction_window_ns
    limits = np.column_stack([desired,right_bound,next_move])
    which = limits.argmin(axis=1)
    end = limits[np.arange(len(a)),which]
    overlap = next_move<desired
    reversal = (positive>0)&(negative>0)
    round_trip = (count>0)&(ticks==0)
    left_missing = first-left_bound<settings.cluster_gap_ns
    right_missing = right_bound<last+settings.cluster_gap_ns
    reasons = np.full(len(a),'',dtype=object)
    def add(mask,label):
        idx=np.flatnonzero(mask)
        reasons[idx]=[str(reasons[i])+(';' if reasons[i] else '')+label for i in idx]
    add(count==0,'no_price_change')
    add(round_trip,'round_trip')
    if settings.drop_reversals:add(reversal,'reversal')
    add(left_linked|right_linked,'span_cap_split')
    add(left_missing,'missing_left_context')
    add(right_missing,'missing_right_context')
    if settings.singleton_only:add(count!=1,'not_singleton')
    if settings.overlap_policy=='drop':
        add(overlap,'overlap')
        add(right_bound<desired,'incomplete_horizon')
    add(end<=last,'empty_observation_window')
    def utc(x):return pd.to_datetime(x,utc=True,unit='ns')
    # Avoid float conversion of epoch ns when inserting NaT.
    next_ts=pd.to_datetime(np.where(next_move==sentinel,np.iinfo('int64').min,next_move),utc=True,unit='ns')
    return pd.DataFrame(dict(cluster_id=np.arange(len(a)),
        instrument_id=candidates.instrument_id.to_numpy()[a],segment_id=ids,
        cluster_start=utc(first),cluster_end=utc(last),t0=utc(last),
        confirmed_at=utc(last+settings.cluster_gap_ns),price_before=before,
        price_after=after,move_points=net,move_ticks=ticks,abs_move_ticks=np.abs(ticks),
        direction=np.select([ticks>0,ticks<0],['up','down'],default='flat'),
        size_class=_labels(ticks),n_updates=b-a,n_price_moves=count,
        gross_move_ticks=np.add.reduceat(np.abs(m),a),has_reversal=reversal,
        is_round_trip=round_trip,left_linked=left_linked,right_linked=right_linked,
        left_context_missing=left_missing,right_context_missing=right_missing,
        next_price_move=next_ts,segment_end=utc(right_bound),observation_end=utc(end),
        observation_end_reason=np.array(['horizon','segment_end','next_price_move'])[which],
        overlap_within_horizon=overlap,horizon_complete=end==desired,
        selected=reasons=='',exclusion_reason=reasons),columns=CLUSTER_COLUMNS)

def single_update_events(result: EventResult, settings: EventConfig) -> pd.DataFrame:
    """Return isolated single midpoint changes at their actual exchange time."""
    table=result.events.loc[result.events.n_price_moves.eq(1)].copy()
    if table.empty:
        table['event_kind']='single_price_update'
        return table.reset_index(drop=True)
    raw=result.candidates.loc[result.candidates.is_price_move].copy()
    raw=raw.loc[raw.cluster_id.isin(table.cluster_id)].set_index('cluster_id')
    members=raw.reindex(table.cluster_id)
    t=members.t0.astype('int64').to_numpy()
    desired=t+settings.reaction_window_ns
    next_ts=table.next_price_move.astype('int64').to_numpy()
    next_ns=np.where(table.next_price_move.isna(),np.iinfo('int64').max,next_ts)
    limits=np.column_stack([desired,table.segment_end.astype('int64').to_numpy(),next_ns])
    which=limits.argmin(axis=1)
    end=limits[np.arange(len(t)),which]
    table['t0']=pd.to_datetime(t,utc=True,unit='ns')
    table['t0_ns']=pd.array(t,dtype='Int64')
    table['price_before']=members.price_before.to_numpy()
    table['price_after']=members.price_after.to_numpy()
    table['observation_end']=pd.to_datetime(end,utc=True,unit='ns')
    table['observation_end_ns']=pd.array(end,dtype='Int64')
    table['observation_end_reason']=np.array(['horizon','segment_end','next_price_move'])[which]
    table['overlap_within_horizon']=next_ns<desired
    table['horizon_complete']=end==desired
    table['confirmation_delay_ns']=pd.array(table.confirmed_at.astype('int64').to_numpy()-t,dtype='Int64')
    table['observation_duration_ns']=pd.array(end-t,dtype='Int64')
    keep=end>t
    if settings.overlap_policy=='drop':keep &= (end==desired)&(next_ns>=desired)
    table=table.loc[keep].copy()
    table['event_kind']='single_price_update'
    return table.reset_index(drop=True)

"""Read Issue #3's local futures cache and write Issue #4 outputs."""
from dataclasses import dataclass
from datetime import date
import inspect
import json
from pathlib import Path
import re
import pandas as pd

@dataclass
class FuturesSample:
    quotes: pd.DataFrame
    manifest: dict
    path: Path

def load_futures_sample(trading_date: date, raw_dir: Path=config.RAW_DIR) -> FuturesSample:
    """Load the manifest-selected underlying, never a recomputed lead future.

    Only MBP-1 futures are decoded; options and MBO files are not read. Chunked
    conversion reduces peak memory from unused DBN fields, but the selected
    futures BBO columns for this date must still fit in memory.
    """
    folder = Path(raw_dir) / 'mbp-1' / f'{trading_date:%Y%m%d}'
    path, manifest_path = (folder / 'futures.dbn.zst', folder / 'futures.json')
    if not path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f'Missing {path} or its futures.json manifest. Run scripts/download.py --dates {trading_date} first.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for name, expected in {'dataset': config.DATASET, 'schema': 'mbp-1', 'kind': 'futures', 'trading_date': trading_date.isoformat(), 'stype_in': 'instrument_id'}.items():
        if manifest.get(name) != expected:
            raise ValueError(f'Invalid futures manifest {name}: expected {expected!r}')
    ids, symbols = (manifest.get('symbols'), manifest.get('raw_symbols'))
    if not isinstance(ids, list) or len(ids) != 1 or (not isinstance(symbols, list)) or (len(symbols) != 1):
        raise ValueError('The manifest must identify exactly one futures instrument and symbol')
    if not re.fullmatch('ES[HMUZ]\\d{1,2}', str(symbols[0])):
        raise ValueError('Manifest symbol is not an outright ES future')
    try:
        expected_id = int(ids[0])
    except (ValueError, TypeError):
        raise ValueError('Manifest instrument ID is not an integer') from None
    if str(expected_id) != str(ids[0]) or expected_id < 0:
        raise ValueError('Manifest instrument ID is not a nonnegative integer')
    start = pd.to_datetime(manifest.get('start'), utc=True, errors='coerce')
    end = pd.to_datetime(manifest.get('end'), utc=True, errors='coerce')
    if pd.isna(start) or pd.isna(end) or start >= end:
        raise ValueError('Manifest needs a valid start/end interval')
    import databento as db
    store = db.DBNStore.from_file(path)
    dbn_schema = getattr(getattr(store, 'metadata', None), 'schema', None)
    if dbn_schema is not None and str(dbn_schema) != 'mbp-1':
        raise ValueError('DBN metadata schema is not mbp-1')
    signature = inspect.signature(store.to_df).parameters
    kwargs = {'pretty_ts': True, 'map_symbols': False}
    if 'price_type' in signature:
        kwargs['price_type'] = 'float'
    else:
        kwargs['pretty_px'] = True
    if 'count' in signature:
        kwargs['count'] = 500000
    converted = store.to_df(**kwargs)
    chunks = [converted] if isinstance(converted, pd.DataFrame) else converted
    columns = ['ts_event', 'ts_recv', 'instrument_id', 'bid_px_00', 'ask_px_00', 'bid_sz_00', 'ask_sz_00', 'flags', 'action', 'sequence']
    frames = []
    for chunk in chunks:
        if chunk.index.name == 'ts_recv' and 'ts_recv' not in chunk:
            chunk = chunk.reset_index()
        if 'instrument_id' not in chunk:
            raise ValueError('DBN data is missing instrument_id')
        if not pd.to_numeric(chunk.instrument_id, errors='coerce').eq(expected_id).all():
            raise ValueError('DBN instrument IDs do not match the selected underlying in futures.json')
        if 'ts_recv' in chunk:
            recv = pd.to_datetime(chunk.ts_recv, utc=True, errors='coerce')
            if (recv.notna() & ((recv < start) | (recv >= end))).any():
                raise ValueError('DBN reception timestamps fall outside the manifest request interval')
        frames.append(chunk.loc[:, [c for c in columns if c in chunk]].copy())
    quotes = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    if quotes.empty:
        raise ValueError('Cached futures file has no records')
    return FuturesSample(quotes, manifest, path)

def write_event_result(result: EventResult, folder: Path, source: dict) -> dict[str, Path]:
    """Write audit tables, selected events and diagnostics to the chosen folder."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for name, frame in {'candidates': result.candidates, 'clusters': result.clusters, 'events': result.events}.items():
        target = folder / f'{name}.parquet'
        partial = target.with_suffix('.partial.parquet')
        frame.to_parquet(partial, index=False)
        partial.replace(target)
        outputs[name] = target
    target = folder / 'diagnostics.json'
    target.write_text(json.dumps({**result.diagnostics, 'source': source}, indent=2, default=str), encoding='utf-8')
    outputs['diagnostics'] = target
    return outputs


def add_tick_observation_window(events: pd.DataFrame, candidates: pd.DataFrame, settings: EventConfig) -> pd.DataFrame:
    """Alternative window ending at the next raw move of at least one ES tick.

    The standard observation_end is left unchanged. A sub-tick change may still
    affect fair value; the longer interval is a sensitivity specification only.
    """
    out = events.copy()
    if out.empty:
        out['next_tick_move'] = pd.Series(dtype='datetime64[ns, UTC]')
        out['observation_end_tick'] = pd.Series(dtype='datetime64[ns, UTC]')
        out['observation_end_tick_ns'] = pd.Series(dtype='Int64')
        out['observation_duration_tick_ns'] = pd.Series(dtype='Int64')
        out['observation_end_tick_reason'] = pd.Series(dtype='object')
        return out
    raw = candidates.loc[candidates.is_price_move & candidates.move_ticks.abs().ge(1), ['segment_id', 't0']].copy()
    ticks_by_segment = {int(seg): np.sort(g.t0.astype('int64').to_numpy()) for seg,g in raw.groupby('segment_id')}
    start = out.t0.astype('int64').to_numpy()
    sentinel = np.iinfo('int64').max
    next_tick = np.full(len(out), sentinel, dtype='int64')
    for seg, positions in out.groupby('segment_id').indices.items():
        clock = ticks_by_segment.get(int(seg))
        if clock is None or len(clock)==0: continue
        index = np.asarray(positions, dtype='int64')
        loc = np.searchsorted(clock, start[index], side='right')
        found = loc < len(clock)
        next_tick[index[found]] = clock[loc[found]]
    horizon = start + settings.reaction_window_ns
    bounds = out.segment_end.astype('int64').to_numpy()
    limits = np.column_stack((horizon, bounds, next_tick))
    reason_index = limits.argmin(axis=1)
    end = limits[np.arange(len(out)),reason_index]
    out['next_tick_move'] = pd.to_datetime(np.where(next_tick==sentinel,np.iinfo('int64').min,next_tick),unit='ns',utc=True)
    out['observation_end_tick'] = pd.to_datetime(end,unit='ns',utc=True)
    out['observation_end_tick_ns'] = pd.array(end,dtype='Int64')
    out['observation_duration_tick_ns'] = pd.array(end-start,dtype='Int64')
    out['observation_end_tick_reason'] = np.array(['horizon','segment_end','next_tick_move'])[reason_index]
    return out
