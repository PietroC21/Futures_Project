import pandas as pd
import numpy as np
from stale_quotes.mbo_analysis import normalize_mbo, normalize_stale, reconstruct_and_classify, markouts_from_bbo

BASE = pd.Timestamp('2026-10-07T14:00:00Z')
def stamp(us):return BASE+pd.Timedelta(microseconds=us)
def mbo_row(us,action,oid=7,size=2,price=12.5,flags=0):
    return dict(ts_event=stamp(us),instrument_id=10,order_id=oid,side='A',action=action,price=price,size=size,flags=flags,sequence=us)
def stale_row():
    return dict(event_id=1,instrument_id=10,status='stale',side='ask',ask=12.5,bid=12.4,start=stamp(10),window_end=stamp(100),resolution=pd.NaT,censored=True)

def test_price_fields_and_timestamp_ns():
    out=normalize_mbo(pd.DataFrame([mbo_row(0,'A')]))
    assert int(out.event_ns.iloc[0])==stamp(0).value if 'event_ns' in out else int(out._ns.iloc[0])==stamp(0).value

def test_window_excludes_action_at_stop():
    data=pd.DataFrame([mbo_row(0,'R',oid=0),mbo_row(1,'A'),mbo_row(100,'C')])
    result,_,_=reconstruct_and_classify(data,pd.DataFrame([stale_row()]))
    assert result.iloc[0].resolution_class=='unclassified'

def test_fill_and_mechanical_cancel_not_double_counted():
    data=pd.DataFrame([mbo_row(0,'R',oid=0),mbo_row(1,'A'),mbo_row(20,'F',size=2),mbo_row(20,'C',size=2)])
    result,actions,fills=reconstruct_and_classify(data,pd.DataFrame([stale_row()]))
    assert result.iloc[0].resolution_class=='filled'
    assert result.iloc[0].cancelled_qty==0
    assert len(fills)==1

def test_independent_cancel():
    data=pd.DataFrame([mbo_row(0,'R',oid=0),mbo_row(1,'A'),mbo_row(21,'C')])
    r,_,_=reconstruct_and_classify(data,pd.DataFrame([stale_row()]))
    assert r.iloc[0].resolution_class=='cancelled'

def test_prestart_order_without_initial_book_is_unclassified():
    data=pd.DataFrame([mbo_row(1,'A'),mbo_row(21,'F')])
    r,_,_=reconstruct_and_classify(data,pd.DataFrame([stale_row()]))
    assert r.iloc[0].reason=='incomplete_initial_book'

def test_not_stale_does_not_get_classified():
    row=stale_row();row['status']='not_stale'
    r,_,_=reconstruct_and_classify(pd.DataFrame([mbo_row(1,'A')]),pd.DataFrame([row]))
    assert r.empty

def test_markout_sign_and_missing_horizon():
    fills=pd.DataFrame([dict(event_id=1,instrument_id=10,order_id=7,fill_ns=stamp(20).value,fill_price=12.5,fill_size=1,stale_side='ask')])
    bbo=pd.DataFrame([dict(instrument_id=10,ts_event=stamp(20)+pd.Timedelta(milliseconds=1),bid=12.6,ask=12.8)])
    out=markouts_from_bbo(fills,bbo)
    assert abs(out.iloc[0].markout_points-0.2)<1e-8
    assert np.isnan(out.iloc[-1].markout_points)

def test_partial_cancel_does_not_claim_full_quote_removed():
    data=pd.DataFrame([mbo_row(0,'R',oid=0),mbo_row(1,'A',size=5),mbo_row(30,'C',size=1)])
    res,_,_=reconstruct_and_classify(data,pd.DataFrame([stale_row()]))
    assert res.iloc[0].reason=='partial_activity_only'


def test_overlap_keeps_correct_starting_order_state():
    r1=stale_row();r2=stale_row();r2['event_id']=2;r2['start']=stamp(15);r2['window_end']=stamp(80)
    data=pd.DataFrame([mbo_row(0,'R',oid=0),mbo_row(1,'A'),mbo_row(20,'C')])
    res,_,_=reconstruct_and_classify(data,pd.DataFrame([r1,r2]))
    assert len(res)==2
    assert list(res.resolution_class)==['cancelled','cancelled']
