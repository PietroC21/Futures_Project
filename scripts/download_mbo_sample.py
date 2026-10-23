"""Fetch a limited option MBO sample with enough prehistory to initialize the book.

Requires Issue 3's existing options MBP-1 manifest to choose instrument IDs.
Shows cost and billable size; never overwrites an existing MBO cache.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description='Download option MBO including UTC-midnight snapshot history')
    p.add_argument('--repo-root',type=Path,default=ROOT)
    p.add_argument('--date',default='2026-10-07')
    p.add_argument('--n-options',type=int,default=4)
    p.add_argument('--end-et',default='10:30',help='end of market sample in New York local time')
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--yes',action='store_true')
    args=p.parse_args()
    root=args.repo_root.expanduser().resolve(); day=args.date.replace('-','')
    mbp_manifest=root/'data'/'raw'/'mbp-1'/day/'options.json'
    if not mbp_manifest.exists():raise FileNotFoundError(f'Missing Issue 3 manifest: {mbp_manifest}')
    meta=json.loads(mbp_manifest.read_text())
    all_ids=[int(x) for x in meta['symbols']]
    if args.n_options<1:raise ValueError('n-options must be positive')
    # Choose central IDs from Issue 3 strike-sorted list, usually near ATM.
    n=min(args.n_options,len(all_ids));offset=max(0,(len(all_ids)-n)//2)
    selected=all_ids[offset:offset+n]
    h,m=map(int,args.end_et.split(':'))
    local_end=datetime.fromisoformat(args.date).replace(hour=h,minute=m,tzinfo=ZoneInfo('America/New_York'))
    # MBO historical daily snapshot is generated at UTC midnight, if provided.
    # Start at UTC midnight rather than 09:30 ET to obtain pre-session state.
    utc_start=datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc)
    if local_end.astimezone(timezone.utc)<=utc_start:raise ValueError('end must be later than UTC midnight')
    params=dict(dataset='GLBX.MDP3',schema='mbo',symbols=selected,stype_in='instrument_id',start=utc_start.isoformat(),end=local_end.isoformat())
    dest=root/'data'/'raw'/'mbo'/day/'options.dbn.zst'
    if dest.exists():
        print('Already exists; will not overwrite:',dest)
        print('Check options.json to verify interval and symbols before using it.')
        return
    import databento as db
    key=os.environ.get('DATABENTO_API_KEY') or os.environ.get('DATABENTO_KEY')
    if not key:raise RuntimeError('Set DATABENTO_API_KEY or DATABENTO_KEY in your environment')
    client=db.Historical(key)
    cost=float(client.metadata.get_cost(**params));size=float(client.metadata.get_billable_size(**params))/1e6
    print(f'MBO estimate: ${cost:.2f}, {size:,.1f} billable MB, {len(selected)} option IDs')
    print('Request window:',params['start'],'through',params['end'])
    if args.dry_run:return
    if not args.yes and input('Proceed with download? [y/N] ').strip().lower() not in {'y','yes'}:
        print('Cancelled');return
    dest.parent.mkdir(parents=True,exist_ok=True)
    partial=dest.with_name('options.partial')
    client.timeseries.get_range(**params,path=partial)
    partial.replace(dest)
    (dest.parent/'options.json').write_text(json.dumps({'trading_date':args.date,'kind':'options',**params,'origin':'issue8_mbo_snapshot_sample'},indent=2),encoding='utf-8')
    print('Saved:',dest)

if __name__=='__main__':main()
