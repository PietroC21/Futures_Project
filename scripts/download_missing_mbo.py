"""Download only missing option instrument IDs, never overwriting existing MBO.

Example: python scripts/download_missing_mbo.py --date 2026-10-07 --start-et 10:00 --end-et 10:30 --dry-run
Requires an existing options MBO manifest and Issue 6 stale parquet.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def atomic_json(path, obj):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2), encoding='utf8')
    tmp.replace(path)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo-root',type=Path,default=ROOT)
    ap.add_argument('--date',default='2026-10-07')
    ap.add_argument('--start-et',default='10:00')
    ap.add_argument('--end-et',default='10:30')
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--yes',action='store_true')
    args=ap.parse_args()
    root=args.repo_root.expanduser().resolve()
    day=args.date.replace('-','')
    folder=root/'data'/'raw'/'mbo'/day
    stale_file=root/'data'/'processed'/'stale'/f'{day}.parquet'
    if not stale_file.is_file():raise FileNotFoundError(stale_file)
    stale=pd.read_parquet(stale_file)
    required={'status','start','instrument_id'}
    if not required.issubset(stale.columns):raise ValueError(f'Missing stale columns: {required-set(stale.columns)}')
    start=pd.Timestamp(f'{args.date} {args.start_et}',tz='America/New_York').tz_convert('UTC')
    end=pd.Timestamp(f'{args.date} {args.end_et}',tz='America/New_York').tz_convert('UTC')
    if not start < end:raise ValueError('start-et must precede end-et')
    timestamps=pd.to_datetime(stale['start'],utc=True)
    wanted=set(map(int,stale.loc[stale['status'].eq('stale') & timestamps.ge(start) & timestamps.lt(end),'instrument_id'].unique()))
    if not wanted:raise RuntimeError('No stale instruments in the specified analysis interval.')
    # Read all existing manifests; reject an unmanifested file because coverage cannot be verified.
    known_files=list(folder.glob('*.dbn.zst')) if folder.exists() else []
    if (folder/'options.dbn.zst').is_file() and not (folder/'options.json').is_file():
        raise RuntimeError('Existing options.dbn.zst has no options.json; cannot safely determine covered symbols.')
    covered=set(); previously=[]
    manifests=sorted(folder.glob('*.json')) if folder.exists() else []
    for manifest in manifests:
        try: obj=json.loads(manifest.read_text())
        except Exception as exc: raise RuntimeError(f'Bad MBO manifest: {manifest}') from exc
        if obj.get('schema')!='mbo':continue
        file=folder/(manifest.stem+'.dbn.zst')
        if not file.is_file():raise RuntimeError(f'Manifest exists without data file: {file}')
        if obj.get('dataset')!='GLBX.MDP3':raise RuntimeError(f'Unexpected dataset in {manifest}')
        if obj.get('stype_in')!='instrument_id':raise RuntimeError(f'Unexpected stype_in in {manifest}')
        s=pd.Timestamp(obj['start']).tz_convert('UTC')
        e=pd.Timestamp(obj['end']).tz_convert('UTC')
        if s > pd.Timestamp(f'{args.date}T00:00:00Z') or e < end:
            print(f'WARNING: existing batch does not cover target [midnight, {end}] and will NOT count as covered: {manifest.name}')
            continue
        ids=set(map(int,obj.get('symbols',[])))
        covered|=ids
        previously.append((manifest.name,len(ids),sorted(ids)))
    unmanifested=[f.name for f in known_files if not (folder/(f.stem.replace('.dbn','')+'.json')).is_file()]
    if unmanifested:raise RuntimeError(f'MBO data without matching JSON manifest: {unmanifested}')
    missing=sorted(wanted-covered)
    print('Wanted stale instruments:',len(wanted), sorted(wanted))
    print('Already covered in complete-window manifests:',len(wanted & covered),sorted(wanted & covered))
    print('Missing instruments:',len(missing),missing)
    print('Existing valid batches:',[(name,n) for name,n,_ in previously])
    if not missing:
        print('All required IDs already covered. No download needed.');return
    # Cost quotation and download use same exact params. Keep prehistory to UTC midnight.
    from datetime import date
    import databento as db
    key=os.getenv('DATABENTO_API_KEY') or os.getenv('DATABENTO_KEY')
    if not key:raise RuntimeError('Set DATABENTO_API_KEY or DATABENTO_KEY')
    client=db.Historical(key)
    params=dict(dataset='GLBX.MDP3',schema='mbo',symbols=missing,stype_in='instrument_id',
                start=f'{args.date}T00:00:00+00:00',end=end.isoformat())
    cost=float(client.metadata.get_cost(**params))
    size=float(client.metadata.get_billable_size(**params))/1e6
    print(f'Additional MBO estimate: ${cost:.2f}; {size:.1f} billable MB')
    if args.dry_run:
        print('DRY RUN: no files written.');return
    if not args.yes and input('Download these MISSING IDs only? [y/N] ').strip().lower() not in {'y','yes'}:
        print('Cancelled');return
    folder.mkdir(parents=True,exist_ok=True)
    suffix='_'.join(map(str,missing))
    # Stable batch identity means repeat invocations are no-ops after success.
    import hashlib
    digest=hashlib.sha256((args.date+'|'+end.isoformat()+'|'+suffix).encode()).hexdigest()[:12]
    base=f'options_extra_{digest}'
    target=folder/f'{base}.dbn.zst'
    manifest=folder/f'{base}.json'
    if target.exists() or manifest.exists():
        raise FileExistsError(f'Batch already exists or incomplete: {target} / {manifest}; inspect before retry.')
    tmp=folder/f'{base}.partial'
    if tmp.exists():raise FileExistsError(f'Incomplete prior batch: {tmp}; inspect before retrying.')
    try:
        client.timeseries.get_range(**params,path=tmp)
        if not tmp.is_file() or not tmp.stat().st_size:raise RuntimeError('Download is empty')
        tmp.replace(target)
        atomic_json(manifest,{'trading_date':args.date,'kind':'options',**params,'origin':'issue8_missing_instruments'})
    except Exception:
        print('If a .partial file exists, check it before retrying. Existing original file is untouched.')
        raise
    print('Saved',target)
    print('Saved',manifest)

if __name__=='__main__':main()
