from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass
class ClusterConfig:
    window_days: int = 10
    min_unique_insiders: int = 3
    require_open_market_purchase: bool = True
    min_value_usd: float = 100_000.0  # Per person conviction filter (optional usage)
    min_ownership_delta_pct: float = 0.20  # 20%
    min_total_cluster_value_usd: float = 500_000.0

    # Expiry settings
    expiry_days_trading: int = 60
    no_follow_through_days: int = 20


@dataclass
class InsiderBuy:
    ticker: str
    insider_id: str
    insider_name: str
    trade_date: date
    tx_code: str
    shares: float
    price: float
    value_usd: float
    insider_title: str
    is_entity: bool
    accession_number: str
    ownership_delta_pct: Optional[float] = None


@dataclass
class ClusterEvent:
    ticker: str
    window_start: date
    window_end: date
    signal_date: date
    unique_insiders: int
    total_value_usd: float
    buys: List[InsiderBuy]
    conviction_score: float
    expiry_date: date
    status: str = "active"


def save_events_to_db(events: List[ClusterEvent], engine: Engine):
    """
    Persist events to Postgres.
    Attempts to avoid duplicates if (ticker, signal_date) already exists.
    """
    if not events:
        return

    # In a real system, we might want to UPSERT or check existence more carefully.
    # For now, we'll insert if not exists.

    with engine.begin() as conn:  # Transaction
        for evt in events:
            # Check existence
            exists = conn.execute(
                text(
                    "SELECT cluster_id FROM cluster_events WHERE ticker = :ticker AND signal_date = :date"
                ),
                {"ticker": evt.ticker, "date": evt.signal_date},
            ).fetchone()

            if exists:
                cluster_id = exists[0]
                # Update?
                continue

            # Insert Cluster
            res = conn.execute(
                text("""
                INSERT INTO cluster_events (
                    ticker, window_start, window_end, signal_date,
                    unique_insiders, total_value_usd, conviction_score,
                    expiry_date, status
                ) VALUES (
                    :ticker, :w_start, :w_end, :sig_date,
                    :u_ins, :val, :score,
                    :expiry, :status
                ) RETURNING cluster_id
            """),
                {
                    "ticker": evt.ticker,
                    "w_start": evt.window_start,
                    "w_end": evt.window_end,
                    "sig_date": evt.signal_date,
                    "u_ins": evt.unique_insiders,
                    "val": evt.total_value_usd,
                    "score": evt.conviction_score,
                    "expiry": evt.expiry_date,
                    "status": evt.status,
                },
            )
            cluster_id = res.fetchone()[0]

            # Insert Members
            # Group buys by (insider, date) to avoid PK violation if same person bought twice same day
            # Though our PK is (cluster_id, insider_id, trade_date).
            # If same person bought twice on same day, we should sum it or insert one record.

            # Let's aggregate member buys per day
            member_map = {}
            for b in evt.buys:
                key = (b.insider_id, b.trade_date)
                if key not in member_map:
                    member_map[key] = {
                        "insider_name": b.insider_name,
                        "insider_title": b.insider_title,
                        "tx_code": b.tx_code,
                        "shares": 0.0,
                        "value": 0.0,
                        "price_sum": 0.0,
                        "count": 0,
                    }
                m = member_map[key]
                m["shares"] += b.shares
                m["value"] += b.value_usd
                m["price_sum"] += b.price * b.shares  # Weighted avg later
                m["count"] += 1

            for (ins_id, t_date), data in member_map.items():
                avg_price = data["price_sum"] / data["shares"] if data["shares"] else 0
                conn.execute(
                    text("""
                    INSERT INTO cluster_event_members (
                        cluster_id, insider_id, insider_name, insider_title,
                        trade_date, transaction_code, shares, price, value_usd
                    ) VALUES (
                        :cid, :iid, :iname, :ititle,
                        :tdate, :tx, :shares, :price, :val
                    ) ON CONFLICT DO NOTHING
                """),
                    {
                        "cid": cluster_id,
                        "iid": ins_id,
                        "iname": data["insider_name"],
                        "ititle": data["insider_title"],
                        "tdate": t_date,
                        "tx": data["tx_code"],
                        "shares": data["shares"],
                        "price": avg_price,
                        "val": data["value"],
                    },
                )
