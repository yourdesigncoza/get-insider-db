from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Set, Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.config import get_engine
from src.insider_classification import normalize_insider_name
from src.insider_roles import ROLE_WEIGHTS  # Canonical source (integer scale)

logger = logging.getLogger(__name__)

# DEPRECATED: Legacy float-scale weights (kept for reference only)
# Use ROLE_WEIGHTS from src.insider_roles instead (integer scale: CFO=4, CEO=2, etc.)
# These float weights were used for a different scoring model and are no longer active.
_LEGACY_ROLE_WEIGHTS_FLOAT = {
    "CFO": 1.3,
    "CHIEF FINANCIAL OFFICER": 1.3,
    "GENERAL COUNSEL": 1.2,
    "CHIEF LEGAL OFFICER": 1.2,
    "GC": 1.2,
    "COO": 1.1,
    "CHIEF OPERATING OFFICER": 1.1,
    "VP": 1.1,
    "VICE PRESIDENT": 1.1,
    "CEO": 1.0,
    "CHIEF EXECUTIVE OFFICER": 1.0,
    "DIRECTOR": 0.7,
}

@dataclass
class ClusterConfig:
    window_days: int = 10
    min_unique_insiders: int = 3
    require_open_market_purchase: bool = True
    min_value_usd: float = 100_000.0  # Per person conviction filter (optional usage)
    min_ownership_delta_pct: float = 0.20 # 20%
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

def get_role_weight(title: str) -> float:
    if not title:
        return 1.0
    title_u = title.upper()
    # Simple keyword matching, prioritized by specific roles
    best_weight = 0.0
    
    for role, weight in ROLE_WEIGHTS.items():
        if role in title_u:
            # We want the max weight found? Or prioritized?
            # E.g. "Director and CEO" -> CEO (1.0) vs Director (0.7).
            # The recap says CFO > GC > COO > CEO > Director.
            # So we should probably take the highest weight found?
            # Actually, CFO (1.3) is highest. So max is correct strategy.
            best_weight = max(best_weight, weight)
            
    if best_weight > 0:
        return best_weight
        
    return 1.0 # Default

def fetch_recent_buys(engine: Engine, lookback_days: int = 120) -> pd.DataFrame:
    """
    Fetch qualifying buys (Open Market 'P') for the last N days.
    """
    query = text("""
        SELECT 
            s.ticker,
            s.insider_name,
            s.insider_title,
            s.transaction_date,
            s.transaction_code,
            s.shares,
            s.price_per_share as price,
            s.total_value,
            s.accession_number,
            s.shares_owned_after
        FROM insider_buy_signals s
        WHERE s.transaction_date >= CURRENT_DATE - INTERVAL :days DAY
          AND s.transaction_code = 'P'
          AND s.ticker IS NOT NULL
        ORDER BY s.ticker, s.transaction_date
    """)
    
    # Note: Interval syntax might vary by DB. Postgres uses 'N day'.
    # The snippet above uses generic param style.
    # Postgres specific:
    query = text("""
        SELECT 
            s.ticker,
            s.insider_name,
            s.insider_title,
            s.transaction_date,
            s.transaction_code,
            s.shares,
            s.price_per_share as price,
            s.total_value,
            s.accession_number,
            s.shares_owned_after
        FROM insider_buy_signals s
        WHERE s.transaction_date >= (CURRENT_DATE - (:days || ' days')::interval)
          AND s.transaction_code = 'P'
          AND s.ticker IS NOT NULL
        ORDER BY s.ticker, s.transaction_date
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"days": lookback_days})
        
    return df

def detect_clusters(buys_df: pd.DataFrame, cfg: ClusterConfig) -> List[ClusterEvent]:
    """
    Implementation of the sliding window logic from cluster-recap.md
    """
    events: List[ClusterEvent] = []
    
    if buys_df.empty:
        return events
        
    # Pre-process buys into objects
    # We need to dedupe or handle multiple rows per filing?
    # The DataFrame has line items.
    # For cluster detection, we care about "Insider X bought on Day Y".
    # If Insider X has 5 rows on Day Y, that's 1 buy event for them.
    
    # Group by Ticker -> then logic
    for ticker, group in buys_df.groupby("ticker"):
        # Sort by date
        group = group.sort_values("transaction_date")
        
        # Convert to objects
        buy_objects: List[InsiderBuy] = []
        for _, row in group.iterrows():
            # Basic entity filtering (simple heuristic for now, can use DB classification later)
            name = row["insider_name"]
            # Exclude obvious funds if not already filtered
            if " LP" in name or " FUND" in name or " TRUST" in name:
                # Ideally use the classification table here.
                # For V1, we trust the input or rely on downstream strictness.
                pass 
                
            # Delta calculation (simplified)
            shares = float(row["shares"] or 0)
            owned_after = float(row["shares_owned_after"] or 0)
            delta = 0.0
            if owned_after > shares: # prior = after - shares
                prior = owned_after - shares
                if prior > 0:
                    delta = shares / prior
            
            obj = InsiderBuy(
                ticker=ticker,
                insider_id=normalize_insider_name(name),
                insider_name=name,
                trade_date=row["transaction_date"], # datetime.date from pandas?
                tx_code=row["transaction_code"],
                shares=shares,
                price=float(row["price"] or 0),
                value_usd=float(row["total_value"] or 0),
                insider_title=str(row["insider_title"] or ""),
                is_entity=False, # Placeholder
                accession_number=row["accession_number"],
                ownership_delta_pct=delta
            )
            buy_objects.append(obj)
            
        # Sliding window
        left = 0
        n = len(buy_objects)
        
        # We need to find the *first* time condition is met.
        # But iterating right pointer means we examine "Window ending at Right".
        
        processed_signals = []
        
        for right in range(n):
            current_buy = buy_objects[right]
            window_end = current_buy.trade_date
            if isinstance(window_end, pd.Timestamp):
                window_end = window_end.date()
                
            window_start_limit = window_end - timedelta(days=cfg.window_days)
            
            # Advance left
            while left < right:
                l_date = buy_objects[left].trade_date
                if isinstance(l_date, pd.Timestamp):
                    l_date = l_date.date()
                if l_date < window_start_limit:
                    left += 1
                else:
                    break
            
            # Current window buys
            window_buys = buy_objects[left : right + 1]
            
            # Check criteria
            unique_insiders = {b.insider_id for b in window_buys}
            
            if len(unique_insiders) >= cfg.min_unique_insiders:
                total_val = sum(b.value_usd for b in window_buys)
                
                if total_val >= cfg.min_total_cluster_value_usd:
                    # FOUND A SIGNAL
                    
                    # Calculate Score
                    score = 0.0
                    for b in window_buys:
                        w = get_role_weight(b.insider_title)
                        # "normalize buy size lightly" - logic from recap: w * (value ** 0.5)
                        score += w * (b.value_usd ** 0.5)
                        
                    # Create Event
                    # Expiry logic: signal_date + 60 trading days (approx 85 calendar days)
                    expiry = window_end + timedelta(days=85) 
                    
                    evt = ClusterEvent(
                        ticker=ticker,
                        window_start=min(b.trade_date for b in window_buys) if not isinstance(min(b.trade_date for b in window_buys), pd.Timestamp) else min(b.trade_date for b in window_buys).date(),
                        window_end=window_end,
                        signal_date=window_end,
                        unique_insiders=len(unique_insiders),
                        total_value_usd=total_val,
                        buys=window_buys,
                        conviction_score=score,
                        expiry_date=expiry
                    )
                    processed_signals.append(evt)
        
        # Dedupe overlap - "Simple heuristic: if events overlap heavily, keep the earliest signal_date"
        # Logic from recap:
        # Sort by signal date.
        # If new event starts <= prev event end, it's an overlap.
        # Keep prev unless new is "meaningfully" better.
        
        deduped = []
        if processed_signals:
            # Sort by signal date
            processed_signals.sort(key=lambda x: x.signal_date)
            
            current_cluster = processed_signals[0]
            
            for next_evt in processed_signals[1:]:
                # Overlap check: does next start before current ends?
                # Actually, recap says: "if events overlap heavily"
                # A simple check: is next_evt.window_start <= current_cluster.window_end?
                if next_evt.window_start <= current_cluster.window_end:
                    # It's an extension or subset.
                    # Recap: "overlap -> keep the earlier signal (prev), unless this one has meaningfully more insiders/value"
                    is_better = (next_evt.unique_insiders > current_cluster.unique_insiders) or \
                                (next_evt.total_value_usd > current_cluster.total_value_usd * 1.5)
                                
                    if is_better:
                        current_cluster = next_evt # Upgrade to the stronger signal
                    else:
                        # Ignore this later, weaker/similar signal
                        pass
                else:
                    # Non-overlapping, save current and move to next
                    deduped.append(current_cluster)
                    current_cluster = next_evt
            
            deduped.append(current_cluster)
            events.extend(deduped)
            
    return events

def save_events_to_db(events: List[ClusterEvent], engine: Engine):
    """
    Persist events to Postgres.
    Attempts to avoid duplicates if (ticker, signal_date) already exists.
    """
    if not events:
        return

    # In a real system, we might want to UPSERT or check existence more carefully.
    # For now, we'll insert if not exists.
    
    with engine.begin() as conn: # Transaction
        for evt in events:
            # Check existence
            exists = conn.execute(text(
                "SELECT cluster_id FROM cluster_events WHERE ticker = :ticker AND signal_date = :date"
            ), {"ticker": evt.ticker, "date": evt.signal_date}).fetchone()
            
            if exists:
                cluster_id = exists[0]
                # Update?
                continue
                
            # Insert Cluster
            res = conn.execute(text("""
                INSERT INTO cluster_events (
                    ticker, window_start, window_end, signal_date, 
                    unique_insiders, total_value_usd, conviction_score, 
                    expiry_date, status
                ) VALUES (
                    :ticker, :w_start, :w_end, :sig_date,
                    :u_ins, :val, :score,
                    :expiry, :status
                ) RETURNING cluster_id
            """), {
                "ticker": evt.ticker,
                "w_start": evt.window_start,
                "w_end": evt.window_end,
                "sig_date": evt.signal_date,
                "u_ins": evt.unique_insiders,
                "val": evt.total_value_usd,
                "score": evt.conviction_score,
                "expiry": evt.expiry_date,
                "status": evt.status
            })
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
                        "count": 0
                    }
                m = member_map[key]
                m["shares"] += b.shares
                m["value"] += b.value_usd
                m["price_sum"] += b.price * b.shares # Weighted avg later
                m["count"] += 1
                
            for (ins_id, t_date), data in member_map.items():
                avg_price = data["price_sum"] / data["shares"] if data["shares"] else 0
                conn.execute(text("""
                    INSERT INTO cluster_event_members (
                        cluster_id, insider_id, insider_name, insider_title,
                        trade_date, transaction_code, shares, price, value_usd
                    ) VALUES (
                        :cid, :iid, :iname, :ititle,
                        :tdate, :tx, :shares, :price, :val
                    ) ON CONFLICT DO NOTHING
                """), {
                    "cid": cluster_id,
                    "iid": ins_id,
                    "iname": data["insider_name"],
                    "ititle": data["insider_title"],
                    "tdate": t_date,
                    "tx": data["tx_code"],
                    "shares": data["shares"],
                    "price": avg_price,
                    "val": data["value"]
                })

def run_backfill(lookback_days: int = 365):
    """
    Main entry point to run detection on history.
    """
    engine = get_engine()
    print(f"Fetching buys for last {lookback_days} days...")
    df = fetch_recent_buys(engine, lookback_days)
    print(f"Found {len(df)} transactions.")
    
    cfg = ClusterConfig(
        min_unique_insiders=3,
        min_total_cluster_value_usd=500_000 # As per recap v1 default
    )
    
    print("Detecting clusters...")
    events = detect_clusters(df, cfg)
    print(f"Detected {len(events)} cluster events.")
    
    print("Saving to DB...")
    save_events_to_db(events, engine)
    print("Done.")

if __name__ == "__main__":
    run_backfill()
