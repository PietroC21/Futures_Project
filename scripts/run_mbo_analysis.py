"""Run the Issue 8 MBO audit on existing Issue 3/6 local caches."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for package_path in (ROOT / 'src', ROOT.parent / 'src'):
    if package_path.exists(): sys.path.insert(0,str(package_path))
from stale_quotes.mbo_analysis import reconstruct_and_classify, markouts_from_bbo, summarize


def main(argv=None):
    ap=argparse.ArgumentParser(description='Classify stale option resting orders using MBO')
    ap.add_argument('--date',default='2026-10-07')
    ap.add_argument('--repo-root',type=Path,default=ROOT)
    ap.add_argument('--stale',type=Path,default=None)
    ap.add_argument('--mbo',type=Path,default=None)
    ap.add_argument('--events',type=Path,default=None,help='Issue 4 events.parquet for move-size splits')
    ap.add_argument('--option-mbp',type=Path,default=None)
    ap.add_argument('--output-dir',type=Path,default=None)
    ap.add_argument('--fill-cancel-tolerance-ns',type=int,default=0)
    ap.add_argument('--start-et',default=None,help='optional HH:MM start, New York time')
    ap.add_argument('--end-et',default=None,help='optional HH:MM end, New York time')
    args=ap.parse_args(argv)
    root=args.repo_root.expanduser().resolve()
    day=args.date.replace('-','')
    stale_path=args.stale or root/'data'/'processed'/'stale'/f'{day}.parquet'
    mbo_path=args.mbo or root/'data'/'raw'/'mbo'/day/'options.dbn.zst'
    mbp_path=args.option_mbp or root/'data'/'raw'/'mbp-1'/day/'options.dbn.zst'
    out=args.output_dir or root/'data'/'processed'/'mbo'/day
    for name,path in [('Issue 6 stale pairs',stale_path),('option MBO',mbo_path),('option MBP-1',mbp_path)]:
        if not path.is_file(): raise FileNotFoundError(f'{name} not found: {path}')
    import databento as db
    from stale_quotes.staleness import option_bbo
    stale=pd.read_parquet(stale_path)
    if args.start_et or args.end_et:
        utc_times=pd.to_datetime(stale['start'],utc=True)
        ny_times=utc_times.dt.tz_convert('America/New_York')
        if args.start_et:stale=stale.loc[ny_times.dt.strftime('%H:%M').ge(args.start_et)].copy()
        if args.end_et:stale=stale.loc[ny_times.dt.strftime('%H:%M').lt(args.end_et)].copy()
    print(f'Loaded {len(stale):,} Issue 6 pairs; {int((stale.status=="stale").sum()):,} stale')
    # Combine original MBO and additional non-overlapping instrument batches.
    batch_dir=mbo_path.parent
    mbo_files=[mbo_path]+sorted(p for p in batch_dir.glob('options_extra_*.dbn.zst') if p!=mbo_path)
    frames=[]; ids_seen=set()
    for file in mbo_files:
        manifest=file.with_suffix('').with_suffix('.json')
        if not manifest.is_file():raise FileNotFoundError(f'Missing manifest for {file}: {manifest}')
        import json
        meta=json.loads(manifest.read_text())
        symbols=set(map(int,meta['symbols']))
        overlap=ids_seen & symbols
        if overlap:raise ValueError(f'Duplicate instrument IDs across MBO batches: {sorted(overlap)} in {file.name}')
        ids_seen.update(symbols)
        chunk=db.DBNStore.from_file(file).to_df()
        frames.append(chunk.reset_index() if 'ts_event' not in chunk.columns else chunk)
        print(f'Loaded {len(chunk):,} MBO records from {file.name} ({len(symbols)} instruments)')
    mbo=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    print(f'Combined {len(mbo):,} MBO records; {len(ids_seen)} instrument IDs in manifests')
    resolutions,order_actions,fills=reconstruct_and_classify(mbo,stale,tolerance_ns=args.fill_cancel_tolerance_ns)
    options=db.DBNStore.from_file(mbp_path).to_df()
    bbo=option_bbo(options)
    markouts=markouts_from_bbo(fills,bbo)
    resolution_summary,mark_summary,quality=summarize(resolutions,markouts)
    out.mkdir(parents=True,exist_ok=True)
    for name,frame in [('quote_resolutions',resolutions),('order_outcomes',order_actions),('fill_markouts',markouts)]:
        if len(frame):frame.to_parquet(out/f'{name}.parquet',index=False,compression='zstd')
    report=root/'issue8_report';report.mkdir(parents=True,exist_ok=True)
    resolution_summary.to_csv(report/f'resolution_summary_{day}.csv',index=False)
    mark_summary.to_csv(report/f'markout_summary_{day}.csv',index=False)
    quality.to_csv(report/f'data_quality_{day}.csv',index=False)
    if args.events and args.events.is_file() and not resolutions.empty:
        ev=pd.read_parquet(args.events)
        if {'event_id','move_ticks'}.issubset(ev.columns):
            merged=resolutions.merge(ev[['event_id','move_ticks']].drop_duplicates('event_id'),on='event_id',how='left')
            merged['move_group']=pd.cut(merged.move_ticks.abs(),bins=[-0.001,0.999,1.001,float('inf')],labels=['sub_tick','single_tick','multi_tick'])
            split=merged.groupby(['move_group','resolution_class'],observed=True).size().rename('count').reset_index()
            split.to_csv(report/f'resolution_by_move_{day}.csv',index=False)
    _write_report(report,day,stale,resolutions,resolution_summary,mark_summary,quality)

    print('\nResolution classes\n',resolution_summary.to_string(index=False))
    print('\nBook coverage:',resolutions.book_initialized.value_counts(dropna=False).to_dict() if not resolutions.empty and 'book_initialized' in resolutions else 'no pairs')
    print(f'Local detail: {out}\nSmall tables: {report}')

def _write_report(folder,day,stale,resolutions,counts,mark,quality):
    n=len(resolutions)
    parts=[f'# Issue 8 — MBO order-level analysis ({day})','',
           '## Sample',f'- Total Issue 6 pairs: {len(stale):,}',
           f'- Pairs marked stale: {n:,}',
           '', '## Resolution classes',
           'Classifications are based on observed MBO order actions; unclassified includes missing book state and incomplete observation windows.',
           '', '| Class | Count | Share |','|---|---:|---:|']
    for row in counts.itertuples(index=False):parts.append(f'| {row.classification} | {row.count:,} | {row.share:.2%} |')
    parts += ['','## Post-fill markouts','Taker-signed against the first available option midpoint at or after each horizon. These are not realized trading profits.','','| Horizon | Valid fills | Mean ($) | Median ($) |','|---|---:|---:|---:|']
    for row in mark.itertuples(index=False):parts.append(f'| +{row.horizon_ms} ms | {row.valid:,} | {row.mean_usd:.4f} | {row.median_usd:.4f} |')
    parts += ['','## Limitations',
              '- An MBO file starting at the cash open may not include all resting orders. Without a reliable book initialization, quote-level outcomes remain unclassified.',
              '- F and C messages from the same fill are paired to avoid double counting. Unclear matches remain unclassified.',
              '- Futures and option timestamps come from different engines; near-boundary classifications are conditional on clock comparability.',
              '- Partial actions and unresolved/censored windows should not be interpreted as completed quote removals.',
              '- Markouts are indicative, not executable exit P&L.','']
    (folder/f'summary_{day}.md').write_text('\n'.join(parts),encoding='utf-8')

if __name__=='__main__':main()
