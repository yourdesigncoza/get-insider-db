Below is a **clean, production-ready way to define and detect a “Cluster Buy” as an event**, not just a label you apply after the fact.

---

## 1. Think in Terms of an **Event Window**, Not a Day

A cluster buy is **not** “3 insiders bought on the same day”.
That’s too brittle and misses real signals.

Instead, define a **rolling detection window**.

### Recommended windows (pick one for V1):

* **Primary window:** 10 trading days
* **Secondary window:** 30 calendar days

> Real-time rule:
> Every new insider BUY updates the rolling window for that ticker.

---

## 2. Hard Minimum Criteria (Non-Negotiable)

A cluster buy **exists** if *all* of the following are true **within the window**:

### A. Multiple Independent Insiders

* **Minimum:** 3 unique insiders
* Must be **natural persons** (exclude funds, trusts, entities)
* Must be **distinct roles** where possible (not all directors from the same committee)

```text
COUNT(DISTINCT insider_id) ≥ 3
```

---

### B. Same Direction, Same Intent

* **BUY only**
* **Open market transactions only**
* SEC Form 4 code: `P`
* Explicitly exclude:

  * `M` (option exercise)
  * `A` (grant)
  * `F`, `S`, etc.

This keeps intent *clean*.

---

### C. Temporal Clustering

All qualifying buys must fall within the same rolling window:

```text
MAX(trade_date) - MIN(trade_date) ≤ window_days
```

This is what makes it a **cluster**, not coincidence.

---

## 3. Conviction Filters (This Is Where Signal Emerges)

This is the difference between “interesting” and “actionable”.

### A. Meaningful Capital at Risk

Per insider (pick one):

* **Absolute:** ≥ $100k (minimum), $200k+ preferred
* **Relative:** ≥ 20% increase in prior holdings

Best systems allow **either** to qualify:

```text
(dollar_value ≥ 100,000) OR (ownership_delta ≥ 20%)
```

---

### B. Aggregate Commitment (Company-Level)

Add a *cluster-level* threshold:

* Total cluster value ≥ **$500k – $1M**
* OR cumulative shares ≥ X% of average daily volume

This avoids “3 insiders buying $30k each”.

---

## 4. Role Weighting (Not All Clusters Are Equal)

Not required to *detect* a cluster, but critical for **ranking**.

Example weighting:

| Role            | Weight |
| --------------- | ------ |
| CFO             | 1.3    |
| General Counsel | 1.2    |
| COO / VP        | 1.1    |
| CEO             | 1.0    |
| Director        | 0.7    |

You can compute a **Cluster Conviction Score**:

```text
Σ (insider_weight × normalized_buy_size)
```

This lets you say:

> “This is a **Tier-A cluster buy**, not just a cluster buy.”

---

## 5. Real-Time Detection Logic (How It Actually Triggers)

Here’s the key insight:

> **A cluster buy is confirmed at the moment the Nth qualifying insider buy enters the window.**

### Example (10-day window):

* Day 1: CFO buys → no cluster
* Day 4: Director buys → no cluster
* Day 7: COO buys → ✅ **Cluster detected**

That timestamp is your **signal time**, not the first trade.

---

## 6. Avoiding False Positives (Critical)

Before confirming the cluster, auto-exclude if:

* > 50% of insiders are **newly appointed** (<90 days tenure)
* All buys are:

  * Identical sizes
  * Same date
  * Same price
    → likely compensation-related or coordinated optics
* Insider is historically a **serial bad timer**

---

## 7. Final “Cluster Buy” Definition (System-Ready)

> A **Cluster Buy** is a real-time detected event where **three or more independent corporate insiders** execute **open-market purchases** of their company’s stock **within a defined rolling window (10–30 days)**, involving **material personal capital**, indicating **shared internal conviction** that the company is undervalued.

---

## 8. Optional: Cluster Strength Tiers (Highly Recommended)

| Tier       | Definition                               |
| ---------- | ---------------------------------------- |
| **Tier A** | ≥4 insiders, ≥$1M total, includes CFO/GC |
| **Tier B** | 3 insiders, ≥$500k total                 |
| **Tier C** | Bare minimum cluster                     |

This maps perfectly to alerts, dashboards, and backtests.

---

## 9. Why This Works for Backtesting *and* Live Trading

* No hindsight bias
* Signal is timestamped
* Windowed logic is deterministic
* Can be replayed historically exactly as detected live

Which aligns perfectly with your earlier point:

> *“I want to evaluate outcomes as if we didn’t know the future.”*

---


* Translate this **directly into SQL / Python logic**


Here’s a simple, reference-style Python outline you can drop next to your current implementation. It’s written like “logic scaffolding” (not full app code), so you can wire it into your DB + pipeline.

```python
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Dict, List, Set, Tuple, Optional


# ----------------------------
# Data shape you already have
# ----------------------------
@dataclass(frozen=True)
class InsiderBuy:
    ticker: str
    insider_id: str            # unique natural person id (NOT fund/entity)
    trade_date: date
    tx_code: str               # SEC code (want 'P' for open market purchase)
    shares: float
    price: float
    value_usd: float
    insider_title: str         # e.g. CEO/CFO/Director/GC/VP
    is_entity: bool            # True for funds/trusts/etc.
    ownership_delta_pct: Optional[float] = None  # if you have it


# ----------------------------
# Config knobs (V1 defaults)
# ----------------------------
@dataclass(frozen=True)
class ClusterConfig:
    window_days: int = 10                 # rolling window
    min_unique_insiders: int = 3
    require_open_market_purchase: bool = True

    # conviction filters (either per-insider condition can qualify)
    min_value_usd: float = 100_000.0
    min_ownership_delta_pct: float = 20.0  # if available

    # optional company-level filter
    min_total_cluster_value_usd: float = 500_000.0

    # optional role weighting (for scoring/ranking)
    role_weights: Dict[str, float] = None


DEFAULT_ROLE_WEIGHTS = {
    "CFO": 1.3,
    "GENERAL COUNSEL": 1.2,
    "GC": 1.2,
    "COO": 1.1,
    "VP": 1.1,
    "CEO": 1.0,
    "DIRECTOR": 0.7,
}


# ----------------------------
# 1) Filtering: keep only "real" buys
# ----------------------------
def is_qualifying_buy(b: InsiderBuy, cfg: ClusterConfig) -> bool:
    if b.is_entity:
        return False

    if cfg.require_open_market_purchase and b.tx_code.upper() != "P":
        return False

    # conviction (either $ size OR holdings delta)
    by_value = b.value_usd >= cfg.min_value_usd
    by_delta = (
        b.ownership_delta_pct is not None
        and b.ownership_delta_pct >= cfg.min_ownership_delta_pct
    )
    return by_value or by_delta


# ----------------------------
# 2) Rolling-window cluster detection (per ticker)
#    Trigger moment = when Nth unique insider appears in window
# ----------------------------
@dataclass
class ClusterEvent:
    ticker: str
    window_start: date
    window_end: date
    signal_date: date                 # when cluster becomes "confirmed"
    unique_insiders: int
    total_value_usd: float
    buys: List[InsiderBuy]
    conviction_score: float           # optional


def detect_clusters_for_ticker(
    buys: List[InsiderBuy],
    cfg: ClusterConfig
) -> List[ClusterEvent]:
    """
    Input buys should already be filtered to a single ticker (or do that outside),
    sorted by trade_date ascending.
    """
    if cfg.role_weights is None:
        cfg = ClusterConfig(**{**cfg.__dict__, "role_weights": DEFAULT_ROLE_WEIGHTS})

    # Keep only qualifying buys
    q = [b for b in buys if is_qualifying_buy(b, cfg)]
    q.sort(key=lambda x: x.trade_date)

    events: List[ClusterEvent] = []
    left = 0

    # Sliding window over dates
    for right in range(len(q)):
        window_end = q[right].trade_date
        window_start = window_end - timedelta(days=cfg.window_days)

        # Move left pointer to keep within rolling window
        while left < right and q[left].trade_date < window_start:
            left += 1

        window_buys = q[left:right+1]

        # Unique insiders in window
        insiders: Set[str] = {b.insider_id for b in window_buys}
        if len(insiders) < cfg.min_unique_insiders:
            continue

        # Optional company-level threshold
        total_value = sum(b.value_usd for b in window_buys)
        if total_value < cfg.min_total_cluster_value_usd:
            continue

        # Optional scoring (simple + readable)
        score = 0.0
        for b in window_buys:
            w = cfg.role_weights.get(b.insider_title.upper(), 1.0)
            # normalize buy size lightly to avoid huge buys dominating completely
            score += w * (b.value_usd ** 0.5)

        # "Signal date" is the moment this condition becomes true (current window_end)
        events.append(
            ClusterEvent(
                ticker=window_buys[-1].ticker,
                window_start=min(b.trade_date for b in window_buys),
                window_end=max(b.trade_date for b in window_buys),
                signal_date=window_end,
                unique_insiders=len(insiders),
                total_value_usd=total_value,
                buys=window_buys,
                conviction_score=score,
            )
        )

    # Optional: de-dupe overlapping events (keep first signal in overlapping windows)
    return dedupe_overlapping_cluster_events(events)


def dedupe_overlapping_cluster_events(events: List[ClusterEvent]) -> List[ClusterEvent]:
    """
    Simple heuristic: if events overlap heavily, keep the earliest signal_date.
    You can replace with your own grouping logic.
    """
    events.sort(key=lambda e: (e.ticker, e.signal_date))
    out: List[ClusterEvent] = []
    last_by_ticker: Dict[str, ClusterEvent] = {}

    for e in events:
        prev = last_by_ticker.get(e.ticker)
        if prev and e.window_start <= prev.window_end:
            # overlap -> keep the earlier signal (prev), unless this one has meaningfully more insiders/value
            if (e.unique_insiders > prev.unique_insiders) or (e.total_value_usd > prev.total_value_usd * 1.5):
                last_by_ticker[e.ticker] = e
                out[-1] = e
            continue

        last_by_ticker[e.ticker] = e
        out.append(e)

    return out


# ----------------------------
# 3) Real-time usage pattern
# ----------------------------
def on_new_form4_buy(new_buy: InsiderBuy, cfg: ClusterConfig):
    """
    Pseudocode: called whenever you ingest a new filing row.
    """
    # 1) store raw buy in DB
    # db.insert(new_buy)

    # 2) query DB for this ticker in the last window_days (plus a little buffer)
    # recent_buys = db.fetch_buys(ticker=new_buy.ticker, since=today - window_days - buffer)

    # 3) run detection
    # events = detect_clusters_for_ticker(recent_buys, cfg)

    # 4) if the latest event has signal_date == new_buy.trade_date -> trigger alert
    # if events and events[-1].signal_date == new_buy.trade_date:
    #     notify_cluster_buy(events[-1])
    pass
```

---


Define “cluster decay” (when a cluster expires)


Great question — this is **where most insider systems quietly break**, so defining it explicitly is a big deal 👍
Think of **cluster decay** as answering:

> *“At what point is this cluster no longer an active signal?”*

Below is a **clean, deterministic definition** you can use both live and in backtests.

---

## 1. What “Cluster Decay” Actually Means

A **cluster buy is an event**, not a permanent state.

**Cluster decay** is the moment when:

* The **information edge** implied by insider consensus has likely been absorbed by the market **or**
* The original **conditions that created the signal are no longer valid**

So decay should be **time-based and rule-based**, not price-based (price-based decay introduces hindsight bias).

---

## 2. Primary Decay Rule (Use This as V1)

### ✅ **Time-Based Expiry After Signal Confirmation**

> A cluster buy **expires N days after the signal date**, regardless of price action.

**Recommended defaults:**

| Horizon            | Expiry               |
| ------------------ | -------------------- |
| Short-term trading | 20–30 trading days   |
| Swing / position   | 60 trading days      |
| Long-term thesis   | 90–120 calendar days |

For your use case (evaluation + buy-side only):

```text
cluster_expiry_date = signal_date + 60 trading days
```

This is clean, replayable, and backtest-safe.

---

## 3. Secondary Decay Rule (Momentum Exhaustion)

This avoids clusters hanging around forever when nothing follows.

### ✅ **No Follow-Through Decay**

If **no additional insider buys** occur after confirmation:

```text
expire if (today - signal_date) ≥ no_follow_through_days
```

Suggested:

* `no_follow_through_days = 15–20 trading days`

This captures:

> “Consensus was there briefly, but didn’t strengthen.”

---

## 4. Negative Information Override (Hard Invalidation)

Some events should **instantly kill** a cluster.

### ❌ Immediate Decay Triggers

Expire the cluster immediately if **any** of the following occur:

* **Cluster selling** by the *same insiders*
* **CFO or CEO sells** within the active window
* Insider buy is **reclassified** (e.g. corrected filing → not open market)
* Discovery that buyers are **entities / funds** (data correction)

This isn’t “decay” — it’s **signal invalidation**.

---

## 5. Optional: Soft Decay (Signal Strength Fade)

Instead of on/off, you can **degrade confidence over time**.

Example:

```text
decay_factor = max(0, 1 - (days_since_signal / max_life_days))
```

So your conviction score becomes:

```text
effective_score = raw_cluster_score × decay_factor
```

This is extremely useful for:

* Ranking active clusters
* Comparing fresh vs stale signals
* Dashboards

---

## 6. Formal Definition (System-Ready)

> A **cluster buy decays** when it exceeds its predefined active lifespan from the signal date **without reinforcement**, or when invalidated by contradictory insider behavior, after which it is no longer considered actionable.

---

## 7. Suggested DB Fields (You’ll Thank Yourself Later)

```sql
cluster_signal_date
cluster_expiry_date
cluster_status        -- active | decayed | invalidated
decay_reason          -- time_expiry | no_follow_through | insider_sell | data_correction
last_reinforcement_at
```

---

## 8. Why This Matters for Backtesting

This lets you:

* Measure returns **only during active signal life**
* Avoid lookahead bias
* Compare:

  * Entry at signal
  * Entry at +5 days
  * Entry at mid-life
* Kill dead signals cleanly

Which ties perfectly back to your earlier goal:

> *“There’s no need to test 5 years if 6 months already shows nothing.”*

---

## 9. Simple Mental Model

* **Detection** = consensus appears
* **Signal date** = moment consensus is confirmed
* **Active life** = market hasn’t fully priced it yet
* **Decay** = edge likely gone
* **Invalidation** = insiders contradict themselves

---


Here’s a **backtest-ready event schema** that makes cluster detection + decay + evaluation dead simple (and avoids lookahead bias).

## 1) Core tables

### A) `cluster_events` (one row = one cluster signal)

```sql
CREATE TABLE cluster_events (
  cluster_id            BIGSERIAL PRIMARY KEY,

  ticker                TEXT NOT NULL,

  -- detection window used to form the cluster (what you “saw”)
  window_start          DATE NOT NULL,
  window_end            DATE NOT NULL,

  -- signal moment (when the Nth unique insider buy appears)
  signal_date           DATE NOT NULL,

  -- decay / lifecycle
  status                TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','decayed','invalidated')),
  expiry_date           DATE NOT NULL,
  last_reinforcement_at DATE,
  decay_reason          TEXT,  -- time_expiry | no_follow_through | insider_sell | data_correction | etc.

  -- cluster composition
  unique_insiders       INT NOT NULL,
  total_value_usd       NUMERIC(18,2) NOT NULL,
  conviction_score      NUMERIC(18,6),

  -- provenance
  detector_version      TEXT NOT NULL DEFAULT 'v1',
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cluster_events_ticker_signal
  ON cluster_events (ticker, signal_date);

CREATE INDEX idx_cluster_events_active
  ON cluster_events (status, expiry_date);
```

### B) `cluster_event_members` (who/what formed the cluster)

```sql
CREATE TABLE cluster_event_members (
  cluster_id      BIGINT NOT NULL REFERENCES cluster_events(cluster_id) ON DELETE CASCADE,

  insider_id      TEXT NOT NULL,
  insider_name    TEXT,
  insider_title   TEXT,

  trade_date      DATE NOT NULL,
  tx_code         TEXT NOT NULL,          -- should be 'P'
  shares          NUMERIC(18,4),
  price           NUMERIC(18,6),
  value_usd       NUMERIC(18,2) NOT NULL,

  ownership_delta_pct NUMERIC(10,4),

  PRIMARY KEY (cluster_id, insider_id, trade_date)
);

CREATE INDEX idx_cluster_members_cluster
  ON cluster_event_members (cluster_id);

CREATE INDEX idx_cluster_members_ticker_date
  ON cluster_event_members (trade_date);
```

---

## 2) Optional but powerful tables (evaluation + replay)

### C) `cluster_event_evals` (store your backtest results per horizon)

This is where you store “what happened after signal” for multiple scenarios (open next day, 5d, 20d, etc.).

```sql
CREATE TABLE cluster_event_evals (
  cluster_id        BIGINT NOT NULL REFERENCES cluster_events(cluster_id) ON DELETE CASCADE,
  eval_name         TEXT NOT NULL,           -- e.g. 'open_next_day', 'close_5d', 'max_20d', 'stop_tp_20d'

  entry_date        DATE NOT NULL,
  entry_price       NUMERIC(18,6) NOT NULL,

  exit_date         DATE,
  exit_price        NUMERIC(18,6),

  return_pct        NUMERIC(12,6),
  max_runup_pct     NUMERIC(12,6),
  max_drawdown_pct  NUMERIC(12,6),

  meta              JSONB,                   -- store stop/tp params, notes, etc.
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (cluster_id, eval_name)
);

CREATE INDEX idx_cluster_evals_name
  ON cluster_event_evals (eval_name);
```

---

## 3) How this supports “cluster decay”

Your detector writes:

* `signal_date` = when cluster confirmed
* `expiry_date` = `signal_date + N trading days` (or calendar, your choice)
* `status` flips to `decayed` when `today > expiry_date`
* `last_reinforcement_at` updates when more qualifying buys come in **before expiry**

If something invalidates:

* set `status='invalidated'`
* set `decay_reason='insider_sell'` (etc.)
* set `expiry_date = invalidation_date` (so the “active window” ends exactly there)

That makes backtests super clean: *only evaluate performance between signal and expiry.*

---

## 4) The single most useful view for backtests

“Give me all clusters that were active on a date (no lookahead).”

```sql
CREATE VIEW cluster_events_active_window AS
SELECT
  cluster_id, ticker, signal_date, expiry_date, status,
  unique_insiders, total_value_usd, conviction_score
FROM cluster_events
WHERE status IN ('active','decayed','invalidated');
```

Then in your backtest, you filter by:

* `signal_date <= as_of_date`
* `expiry_date >= as_of_date` (if you want “active signals only”)

---

## 5) Minimal “event creation contract” (what your detector must output)

When a new cluster is detected, insert:

* `ticker`
* `window_start`, `window_end`
* `signal_date`
* `unique_insiders`
* `total_value_usd`
* `conviction_score`
* `expiry_date`
* members rows in `cluster_event_members`

That’s it — everything else (ranking, evals, dashboards) becomes easy.

If you tell me which price source you’re using for backtests (Alpha Vantage? Polygon? cached OHLCV table?), I’ll give you the exact SQL/Python pattern to populate `cluster_event_evals` for:

* **Open next day**
* **Close +5 / +20**
* **Max runup within active life**
* **7% rule / stop-loss / TP ladders** (your style)


Cool — Alpha Vantage makes this clean because you can reliably pull **EOD daily bars** per ticker from their **`TIME_SERIES_DAILY_ADJUSTED`** endpoint. ([Alpha Vantage][1])

Below is a backtest-ready mapping that plugs straight into the `cluster_events` / `cluster_event_evals` structure we just designed.

---

## 1) Price cache table (don’t backtest by calling Alpha Vantage live every time)

```sql
CREATE TABLE price_bars_daily (
  ticker      TEXT NOT NULL,
  bar_date    DATE NOT NULL,
  open        NUMERIC(18,6),
  high        NUMERIC(18,6),
  low         NUMERIC(18,6),
  close       NUMERIC(18,6),
  adj_open    NUMERIC(18,6),
  adj_high    NUMERIC(18,6),
  adj_low     NUMERIC(18,6),
  adj_close   NUMERIC(18,6),
  volume      BIGINT,
  PRIMARY KEY (ticker, bar_date)
);

CREATE INDEX idx_price_bars_date ON price_bars_daily (bar_date);
```

Alpha Vantage’s EOD endpoint returns daily price series (including adjusted fields depending on params/response). ([Alpha Vantage][1])

---

## 2) Minimal Alpha Vantage fetcher (Python outline)

This uses plain `requests` so you’re not coupled to a library. ([Alpha Vantage Documentation][2])

```python
import requests
from datetime import date
from typing import List, Dict, Any, Optional

ALPHAVANTAGE_EOD_URL = "https://www.alphavantage.co/query"

def alphavantage_fetch_eod(
    api_key: str,
    ticker: str,
    start: date,
    end: Optional[date] = None,
    use_adjusted: bool = True,
) -> List[Dict[str, Any]]:
    """
    Alpha Vantage EOD daily prices.
    Docs + examples show TIME_SERIES_DAILY_ADJUSTED with symbol and outputsize params. :contentReference[oaicite:3]{index=3}
    """
    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": ticker,
        "apikey": api_key,
        "outputsize": "full",
    }
    # Alpha Vantage returns all data for full outputsize, filtering by date needs to be done post-fetch

    headers = {"Content-Type": "application/json"}
    url = ALPHAVANTAGE_EOD_URL
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    
    # Parse and filter Alpha Vantage response
    time_series_data = data.get("Time Series (Daily)", {}) or data.get("Daily Adjusted Time Series", {})
    if not time_series_data:
        return []

    cleaned_data = []
    for date_str, values in time_series_data.items():
        current_date = date.fromisoformat(date_str)
        if start <= current_date and (end is None or current_date <= end):
            cleaned_data.append({
                'date': current_date,
                'open': float(values['1. open']),
                'high': float(values['2. high']),
                'low': float(values['3. low']),
                'close': float(values['4. close']),
                'adjOpen': float(values['1. open'] if not use_adjusted else values['5. adjusted close']),
                'adjHigh': float(values['2. high'] if not use_adjusted else values['5. adjusted close']),
                'adjLow': float(values['3. low'] if not use_adjusted else values['5. adjusted close']),
                'adjClose': float(values['5. adjusted close']),
                'volume': int(values['6. volume'])
            })
    return sorted(cleaned_data, key=lambda x: x['date'])
```

---

## 3) Backtest eval generator (event → entry/exit metrics)

Key idea: **evals are derived from your cached `price_bars_daily`**, not from Alpha Vantage at backtest time.

### Common evals you said you care about

* **Open next day**
* **Close +5d / +20d**
* **Max runup / drawdown during active life** (signal_date → expiry_date)

Python outline:

```python
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

@dataclass
class Bar:
    d: date
    o: float
    h: float
    l: float
    c: float

def next_trading_bar(bars: List[Bar], after: date) -> Optional[Bar]:
    for b in bars:
        if b.d > after:
            return b
    return None

def bar_at_offset(bars: List[Bar], start_idx: int, offset: int) -> Optional[Bar]:
    idx = start_idx + offset
    if 0 <= idx < len(bars):
        return bars[idx]
    return None

def max_runup_drawdown(bars: List[Bar], entry_price: float) -> Tuple[float, float]:
    """
    Returns (max_runup_pct, max_drawdown_pct) using highs/lows after entry.
    """
    max_runup = float("-inf")
    max_dd = float("inf")
    for b in bars:
        runup = (b.h - entry_price) / entry_price
        dd = (b.l - entry_price) / entry_price
        max_runup = max(max_runup, runup)
        max_dd = min(max_dd, dd)
    return max_runup, max_dd

def eval_event_open_next_day(
    bars: List[Bar],
    signal_date: date,
    expiry_date: date,
    exit_offset_days: int = 20,   # e.g. close +20 bars
):
    # bars must be sorted ascending and cover signal->expiry and beyond
    entry_bar = next_trading_bar(bars, after=signal_date)
    if not entry_bar:
        return None

    entry_idx = bars.index(entry_bar)

    exit_bar = bar_at_offset(bars, entry_idx, exit_offset_days)
    if not exit_bar:
        return None

    entry_price = entry_bar.o
    exit_price = exit_bar.c
    ret = (exit_price - entry_price) / entry_price

    # active-life window (cap to expiry_date)
    active_bars = [b for b in bars if entry_bar.d <= b.d <= expiry_date]
    runup, dd = max_runup_drawdown(active_bars, entry_price)

    return {
        "entry_date": entry_bar.d,
        "entry_price": entry_price,
        "exit_date": exit_bar.d,
        "exit_price": exit_price,
        "return_pct": ret,
        "max_runup_pct": runup,
        "max_drawdown_pct": dd,
    }
```

---

## 4) Practical wiring into your DB tables

### Load bars into `price_bars_daily`

* During ingestion: fetch missing date ranges from Alpha Vantage, upsert rows.

### When a new `cluster_events` row is created

* Immediately compute evals into `cluster_event_evals` using cached bars:

  * `eval_name='open_next_day_close_20b'`
  * `eval_name='open_next_day_close_5b'`
  * `eval_name='active_life_max_runup_dd'` (derived while computing others)

---

## 5) One important Alpha Vantage reality for your design

Alpha Vantage EOD is **per ticker** (you’ll iterate tickers you need). So your “price cache” is the performance unlock. ([Alpha Vantage][3])

---

If you paste your **existing price fetch code** (or tell me whether you’re using `alphavantage-python` vs raw requests), I’ll adapt the outline into *your exact style* (async, retries, DB upserts, and a single `compute_event_evals(cluster_id)` function that populates `cluster_event_evals`).

[1]: https://www.alphavantage.co/documentation/ "Alpha Vantage API Documentation"
[2]: https://www.alphavantage.co/documentation/ "Alpha Vantage Python Client documentation"
[3]: https://www.alphavantage.co/documentation/ "The Fastest Method to Ingest Alpha Vantage End-of-Day Stock API ..."
