from datetime import date

import pandas as pd
import pytest

from stale_quotes.instruments import (
    InstrumentsUnavailable,
    lead_future_symbol,
    nearest_strikes,
    roll_date,
    select_instruments,
    third_friday,
)

DAY = date(2026, 10, 7)  # Wednesday: E1C options expire, underlying ESZ6
ESZ6_ID = 10252


def _ts(text, tz="America/Chicago"):
    return pd.Timestamp(text, tz=tz).tz_convert("UTC")


def _row(instrument_id, raw_symbol, instrument_class, **kwargs):
    row = {
        "ts_recv": _ts("2026-10-07 00:00", tz="UTC"),
        "instrument_id": instrument_id,
        "raw_symbol": raw_symbol,
        "instrument_class": instrument_class,
        "security_update_action": "A",
        "asset": "ES",
        "underlying": "",
        "underlying_id": 0,
        "strike_price": float("nan"),
        "expiration": _ts("2026-12-18 08:30"),
        "unit_of_measure_qty": 50.0,
        "display_factor": 0.01,
    }
    row.update(kwargs)
    return row


def _option_chain(asset, expiration, strikes, underlying="ESZ6", underlying_id=ESZ6_ID, first_id=1000):
    rows = []
    for i, strike in enumerate(strikes):
        for j, cls in enumerate("CP"):
            rows.append(_row(
                first_id + 2 * i + j, f"{asset}V6 {cls}{strike:g}", cls,
                asset=asset, underlying=underlying, underlying_id=underlying_id,
                strike_price=float(strike), expiration=_ts(expiration),
            ))
    return rows


def _definitions(*chains):
    rows = [
        _row(ESZ6_ID, "ESZ6", "F", asset="ES", expiration=_ts("2026-12-18 08:30")),
        _row(20000, "ESH7", "F", asset="ES", expiration=_ts("2027-03-19 08:30")),
        _row(30000, "ESZ6-ESH7", "S", asset="ES"),
    ]
    for chain in chains:
        rows += chain
    return pd.DataFrame(rows).set_index("ts_recv")


STRIKES = range(6900, 7105, 5)
TODAY = _option_chain("E1C", "2026-10-07 15:00", STRIKES)


def test_third_friday_and_roll():
    assert third_friday(2026, 12) == date(2026, 12, 18)
    assert third_friday(2026, 5) == date(2026, 5, 15)  # month starting on a Friday
    assert roll_date(2026, 12) == date(2026, 12, 10)


@pytest.mark.parametrize("trading_date, symbol", [
    (date(2026, 10, 7), "ESZ6"),
    (date(2026, 9, 9), "ESU6"),   # day before the September roll
    (date(2026, 9, 10), "ESZ6"),  # roll date
    (date(2026, 12, 9), "ESZ6"),
    (date(2026, 12, 10), "ESH7"),  # December roll crosses the year
    (date(2026, 12, 31), "ESH7"),
    (date(2027, 1, 4), "ESH7"),
])
def test_lead_future(trading_date, symbol):
    assert lead_future_symbol(trading_date) == symbol


def test_nearest_strikes_symmetric_and_deterministic():
    strikes = range(6900, 7105, 5)
    assert nearest_strikes(strikes, 7001.0, 10) == list(range(6980, 7030, 5))
    assert nearest_strikes(strikes, 7002.5, 1) == [7000]  # tie goes to lower strike
    assert nearest_strikes([6990, 7000], 7000.0, 10) == [6990, 7000]


def test_select_instruments():
    sel = select_instruments(_definitions(TODAY), DAY, 7001.0, n_strikes=10)
    assert sel.underlying["raw_symbol"] == "ESZ6"
    assert sel.underlying_is_lead
    assert sel.series == "E1C"
    assert sel.expiration == _ts("2026-10-07 15:00")
    assert sel.atm_strike == 7000
    assert sel.strikes == list(range(6980, 7030, 5))
    assert len(sel.options) == 20
    assert (sel.options.groupby("strike_price")["instrument_class"].apply(set) == {"C", "P"}).all()
    assert sel.instrument_ids[0] == ESZ6_ID and len(sel.instrument_ids) == 21


def test_reference_price_callable_receives_underlying():
    seen = []
    sel = select_instruments(_definitions(TODAY), DAY, lambda s: seen.append(s) or 6950.0)
    assert seen == ["ESZ6"]
    assert sel.atm_strike == 6950


def test_ignores_am_quarterly_and_other_expiries():
    am_quarterly = _option_chain("ES", "2026-10-07 08:30", STRIKES, first_id=5000)
    tomorrow = _option_chain("E1D", "2026-10-08 15:00", STRIKES, first_id=6000)
    sel = select_instruments(_definitions(am_quarterly, TODAY, tomorrow), DAY, 7000.0)
    assert set(sel.options["asset"]) == {"E1C"}


def test_only_strikes_with_call_and_put():
    chain = [r for r in TODAY if not (r["strike_price"] == 7000 and r["instrument_class"] == "P")]
    sel = select_instruments(_definitions(chain), DAY, 7000.0, n_strikes=3)
    assert sel.strikes == [6990, 6995, 7005]
    assert sel.atm_strike == 6995


def test_latest_definition_wins_and_deletes_dropped():
    defs = _definitions(TODAY).reset_index()
    later = defs[defs["raw_symbol"] == "E1CV6 C7000"].copy()
    later["ts_recv"] = _ts("2026-10-07 12:00", tz="UTC")
    later["security_update_action"] = "D"
    defs = pd.concat([defs, later]).set_index("ts_recv")
    sel = select_instruments(defs, DAY, 7000.0)
    assert 7000 not in sel.strikes  # its call was deleted, so no pair remains


def test_no_zero_dte_series():
    tomorrow = _option_chain("E1D", "2026-10-08 15:00", STRIKES)
    with pytest.raises(InstrumentsUnavailable, match="no PM-settled"):
        select_instruments(_definitions(tomorrow), DAY, 7000.0)


def test_missing_underlying_definition():
    chain = _option_chain("E1C", "2026-10-07 15:00", STRIKES, underlying="ESH7", underlying_id=99)
    with pytest.raises(InstrumentsUnavailable, match="underlying future"):
        select_instruments(_definitions(chain), DAY, 7000.0)


def test_metadata_frame_and_request_params():
    sel = select_instruments(_definitions(TODAY), DAY, 7001.0)
    frame = sel.to_frame()
    assert list(frame["role"]).count("underlying") == 1
    assert list(frame["role"]).count("call") == 10 == list(frame["role"]).count("put")
    for col in ["instrument_id", "raw_symbol", "strike_price", "expiration", "underlying_id",
                "unit_of_measure_qty", "display_factor", "reference_price", "atm_strike", "series"]:
        assert col in frame.columns

    params = sel.request_params()
    assert params["dataset"] == "GLBX.MDP3"
    assert params["stype_in"] == "instrument_id"
    assert params["symbols"] == sel.instrument_ids
    assert params["start"] == pd.Timestamp("2026-10-07 09:30", tz="America/New_York")
    assert params["end"] == pd.Timestamp("2026-10-07 16:00", tz="America/New_York")
