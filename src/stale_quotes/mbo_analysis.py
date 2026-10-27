"""Order-level audit of stale ES option quotes using Databento MBO.

Conservative by design: classify direct order actions without inferring a
market maker's identity or treating trade ('T') records as resting fills.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
import numpy as np
import pandas as pd

MARKOUT_MS = (1, 10, 100)
F_SNAPSHOT = 32


def ns(value):
    """UTC nanosecond timestamp as Python int, or None."""
    if value is None or pd.isna(value):
        return None
    return int(pd.Timestamp(value).value) if not isinstance(value, (int, np.integer)) else int(value)


def normalize_mbo(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize DBNStore.to_df output; keep exact UTC nanosecond timestamps."""
    df = frame.reset_index() if 'ts_event' not in frame.columns else frame.copy()
    needed = {'ts_event','instrument_id','order_id','side','action','price','size'}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f'MBO missing fields: {sorted(missing)}')
    if 'sequence' not in df: df['sequence'] = np.arange(len(df), dtype=np.int64)
    if 'flags' not in df: df['flags'] = 0
    df['_ns'] = pd.to_datetime(df.ts_event,utc=True).dt.as_unit('ns').astype('int64')
    # Input order is authoritative for equal timestamps; sequence is used when present.
    df['_position'] = np.arange(len(df))
    return df.sort_values(['_ns','sequence','_position'],kind='stable').reset_index(drop=True)


def normalize_stale(frame: pd.DataFrame) -> pd.DataFrame:
    missing = {'instrument_id','event_id','status','side','start'} - set(frame.columns)
    if missing: raise ValueError(f'Stale table missing fields: {sorted(missing)}')
    out=frame[frame.status.eq('stale')].copy().reset_index(drop=True)
    out['_start_ns'] = out.start.map(ns)
    def stop_time(r):
        values = [v for v in (ns(r.get('resolution')), ns(r.get('window_end'))) if v is not None]
        return min(values) if values else None
    out['_stop_ns'] = out.apply(stop_time, axis=1)
    # On a censored pair, resolution is absent; window_end is the cutoff.
    out['_stale_price'] = np.where(out.side.eq('ask'),out.get('ask',pd.Series(index=out.index,dtype=float)),out.get('bid',pd.Series(index=out.index,dtype=float)))
    return out


def _side(s):
    return {'ask':'A','bid':'B','A':'A','B':'B'}.get(str(s), str(s))


@dataclass
class Resting:
    price: float
    size: int
    side: str
    known: bool = True


def reconstruct_and_classify(mbo: pd.DataFrame, stale: pd.DataFrame, *, tolerance_ns: int = 0):
    """Process selected option instruments in time order.

    Snapshots are used as initial state if present; otherwise missing pre-window
    orders are explicitly reported as incomplete book coverage. F is execution
    evidence; paired F/C removes quantity once (C changes the book, F does not).
    The output is an event audit, not a simulation of queue fills.
    """
    mbo=normalize_mbo(mbo)
    windows=normalize_stale(stale)
    audits=[]; orders_out=[]; fills=[]
    for inst, wgroup in windows.groupby('instrument_id',sort=False):
        data=mbo[mbo.instrument_id.eq(inst)]
        # Build the state for all windows at once, but only collect actions during
        # the matched stale windows. Time boundary policy: [start, stop).
        rows=list(data.rename(columns={'_ns':'event_ns'}).itertuples(index=False,name='Mbo'))
        if not rows:
            for _,w in wgroup.iterrows(): audits.append(_empty(w,'unclassified','no_mbo'))
            continue
        windows_sorted=sorted((w for _,w in wgroup.iterrows()),key=lambda w:w['_start_ns'])
        # One forward replay per instrument, with independent per-window action logs.
        active={}; initialized=False; cursor=0
        for w in windows_sorted:
            start=w['_start_ns']; end=w['_stop_ns']
            if start is None or end is None or end<=start or not np.isfinite(w['_stale_price']):
                audits.append(_empty(w,'unclassified','invalid_window_or_price'));continue
            while cursor<len(rows) and int(rows[cursor].event_ns)<start:
                r=rows[cursor]; _apply(active,r)
                if int(r.flags)&F_SNAPSHOT or str(r.action)=='R': initialized=True
                cursor+=1
            side=_side(w.side); price=float(w['_stale_price'])
            matched={oid:(state.size,state.price) for oid,state in active.items() if state.side==side and np.isclose(state.price,price,atol=1e-8,rtol=0)}
            # State exists even without a snapshot but may be incomplete due to prehistory.
            covered=initialized
            action_log=[]; j=cursor
            while j<len(rows) and int(rows[j].event_ns)<end:
                r=rows[j]; oid=int(r.order_id)
                if oid in matched and str(r.action) in {'F','C','M','R'}:
                    action_log.append({'order_id':oid,'action':str(r.action),'ns':int(r.event_ns),'size':int(r.size),'price':float(r.price),'side':str(r.side), 'sequence':int(r.sequence)})
                j+=1
            # Count fills and de-duplicate F-associated C records using a
            # conservative same order/time tolerance. Ambiguous C -> unclassified.
            fill_by_oid=defaultdict(list)
            for a in action_log:
                if a['action']=='F': fill_by_oid[a['order_id']].append(a)
            matched_c=set(); used_f=set()
            for k,a in enumerate(action_log):
                if a['action']!='C': continue
                candidates=[(abs(a['ns']-f['ns']),fi,f) for fi,f in enumerate(fill_by_oid[a['order_id']])
                            if (a['order_id'],fi) not in used_f and abs(a['ns']-f['ns'])<=tolerance_ns and a['size']==f['size']]
                if candidates:
                    _,fi,_=min(candidates,key=lambda x:x[0]); used_f.add((a['order_id'],fi));matched_c.add(k)
            qty={'filled':0,'cancelled':0,'modified':0}; ambiguous_c=0
            for k,a in enumerate(action_log):
                kind=a['action']
                if kind=='F':
                    qty['filled']+=a['size']
                    fills.append({'event_id':w.event_id,'instrument_id':inst,'order_id':a['order_id'],'fill_ns':a['ns'], 'fill_price':a['price'],'fill_size':a['size'],'stale_side':str(w.side),'trading_date':str(w.get('trading_date',''))})
                elif kind=='C' and k not in matched_c:
                    # Without F_LAST grouping, a C near unmatched fill is ambiguous.
                    if any(abs(a['ns']-f['ns'])<=max(tolerance_ns,1000) for f in fill_by_oid[a['order_id']]): ambiguous_c+=a['size']
                    else: qty['cancelled']+=a['size']
                elif kind=='M': qty['modified']+=a['size']
                orders_out.append({'event_id':w.event_id,'instrument_id':inst,**a,'paired_with_fill':k in matched_c})
            classes=[k for k,v in qty.items() if v>0]
            if not matched: cls='unclassified';reason='no_resting_order_match'
            elif ambiguous_c: cls='unclassified'; reason='ambiguous_fill_cancel'
            elif len(classes)>1: cls='mixed';reason='multiple_actions'
            elif classes: cls=classes[0];reason='observed_order_actions'
            else: cls='unclassified';reason='no_action_before_end'
            if matched and sum(qty.values()) < sum(x[0] for x in matched.values()) and cls!='unclassified':
                cls='unclassified';reason='partial_activity_only'
            if not covered:
                # Preserve observed order evidence; prohibit complete quote-level claims.
                cls='unclassified';reason='incomplete_initial_book'
            audits.append({'event_id':w.event_id,'instrument_id':inst,'trading_date':str(w.get('trading_date','')),
              'stale_side':str(w.side),'stale_price':price,'start_ns':start,'stop_ns':end,
              'censored':bool(w.get('censored',False)),'book_initialized':covered,
              'matched_order_count':len(matched),'initial_matched_size':sum(x[0] for x in matched.values()),
              'filled_qty':qty['filled'],'cancelled_qty':qty['cancelled'],'modified_qty':qty['modified'],
              'ambiguous_cancel_qty':ambiguous_c,'resolution_class':cls,'reason':reason})
            # Keep the replay cursor at start. Later windows may overlap this one.
    return pd.DataFrame(audits),pd.DataFrame(orders_out),pd.DataFrame(fills)


def _empty(w,cls,reason):
    return dict(event_id=w.event_id,instrument_id=w.instrument_id,resolution_class=cls,reason=reason,
                matched_order_count=0,filled_qty=0,cancelled_qty=0,modified_qty=0,censored=bool(w.get('censored',False)))


def _apply(active,r):
    action=str(r.action);oid=int(r.order_id);side=str(r.side)
    if action=='R':active.clear()
    elif action=='A':active[oid]=Resting(float(r.price),int(r.size),side)
    elif action=='M':
        if oid in active:active[oid]=Resting(float(r.price),int(r.size),side)
    elif action=='C':
        if oid in active:
            remain=active[oid].size-int(r.size)
            if remain<=0:active.pop(oid,None)
            else:active[oid].size=remain
    # F / T / N do not update resting-order state.


def markouts_from_bbo(fills:pd.DataFrame,bbo:pd.DataFrame,*,horizons_ms=MARKOUT_MS,multiplier=50.0):
    """Taker-signed, quote-mid markouts. Next quote at/after horizon, not prior."""
    if fills.empty:return pd.DataFrame()
    q=bbo.reset_index() if 'ts_event' not in bbo else bbo.copy()
    if 'mid' not in q:
        if {'bid','ask'}.issubset(q.columns):q['mid']=(q.bid+q.ask)/2
        else:q['mid']=(q.bid_px_00+q.ask_px_00)/2
    q['_ns']=pd.to_datetime(q.ts_event,utc=True).dt.as_unit('ns').astype('int64')
    out=[]
    for inst,part in fills.groupby('instrument_id'):
        qs=q[q.instrument_id.eq(inst)].sort_values('_ns'); times=qs._ns.to_numpy();mids=qs.mid.to_numpy(float)
        for f in part.to_dict('records'):
            sign=1 if str(f['stale_side'])=='ask' else -1
            for h in horizons_ms:
                target=int(f['fill_ns'])+int(h*1_000_000)
                idx=int(np.searchsorted(times,target,side='left'))
                future=float(mids[idx]) if idx<len(times) else np.nan
                price=float(f['fill_price']); point=sign*(future-price) if np.isfinite(future) else np.nan
                out.append({**f,'horizon_ms':h,'target_ns':target,'reference_mid':future,'markout_points':point,'markout_usd':point*multiplier})
    return pd.DataFrame(out)


def summarize(resolutions,markouts):
    if resolutions.empty:return pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
    counts=resolutions.resolution_class.value_counts(dropna=False)
    total=len(resolutions)
    summary=pd.DataFrame({'classification':counts.index,'count':counts.values,'share':counts.values/total})
    if markouts.empty: return summary,pd.DataFrame(),pd.DataFrame([{'metric':'stale_pairs','value':total}])
    mark=markouts.groupby('horizon_ms').agg(fill_observations=('markout_usd','size'),valid=('markout_usd','count'),mean_usd=('markout_usd','mean'),median_usd=('markout_usd','median'),positive_share=('markout_usd',lambda x:float((x.dropna()>0).mean()) if x.notna().any() else np.nan)).reset_index()
    qual=pd.DataFrame([{'metric':'stale_pairs','value':total},{'metric':'unclassified','value':int(counts.get('unclassified',0))},{'metric':'book_incomplete','value':int((resolutions.reason=='incomplete_initial_book').sum())}])
    return summary,mark,qual
