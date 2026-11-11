import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

DATABASE_URL = os.environ["DATABASE_URL"]
STATIC = Path(__file__).parent / "static"

SEEDS = [
    ("trend-pullback", "Trend Continuation Pullback", "ES / MES", "ACTIVE", "15M trend → 5M support/retest → 1M trigger", [
        ["Is 15M market structure clearly directional?", "If structure is mixed, reject the setup.", True],
        ["Is price aligned with session VWAP and 5M 9/21 EMAs?", "Misalignment reduces confidence; avoid countertrend entries.", True],
        ["Did price retest a pre-drawn 5M level or trendline?", "Do not redraw levels to justify entry.", True],
        ["Is the 1M confirmation candle complete?", "Unconfirmed triggers cause premature entries.", True],
        ["Does structural stop allow ≥2R before opposing liquidity?", "If not, pass; never tighten stop merely to improve RR.", True],
        ["Are spread, ATR, and news restrictions acceptable?", "High-impact announcements and fast markets can overwhelm stop assumptions.", True],
    ]),
    ("opening-range", "Opening Range Breakout + Retest", "ES / MES, NQ / MNQ", "PAPER", "15M opening range → breakout close → retest → confirmation", [
        ["Is the first 15M opening range fully formed?", "No entries before 9:45 ET.", True],
        ["Did a completed 5M candle close beyond the range?", "Wicks alone are not breakout confirmation.", True],
        ["Did price retest the breakout boundary successfully?", "Reject if a 5M candle closes back inside the range.", True],
        ["Is there meaningful room before next higher-timeframe level?", "Crowded targets reduce achievable reward.", True],
        ["Does a structure-based stop fit max planned dollar risk?", "Oversized stops mean zero contracts, not oversized risk.", True],
        ["Are volume and economic calendar conditions acceptable?", "Breakouts around news can suffer abnormal slippage.", True],
    ]),
    ("liquidity-sweep", "Liquidity Sweep + Reclaim", "GC / MGC", "PAPER", "Prior session extreme → sweep → 5M reclaim → 1M trigger", [
        ["Is the targeted prior-session high/low marked in advance?", "Retrospective level selection adds hindsight bias.", True],
        ["Did price sweep the level then close back through it on 5M?", "Avoid blindly fading a genuine trend breakout.", True],
        ["Is a clear 1M reversal structure confirmed?", "No confirmation means no entry.", True],
        ["Is the stop beyond the actual sweep extreme?", "Do not hide the stop inside the liquidity pool.", True],
        ["Is the next opposing level ≥2R away?", "Gold can reverse sharply; target must be realistic.", True],
        ["Are CPI, PCE, NFP, FOMC and major USD releases clear?", "High news sensitivity and slippage risk.", True],
    ]),
    ("vwap-reclaim", "VWAP Reclaim + Hold", "ES / MES", "PAPER", "VWAP acceptance → retest → trend confirmation", [
        ["Was price accepted back above/below VWAP on completed 5M candles?", "Single wick cross is insufficient.", True],
        ["Did price hold VWAP on retest?", "Choppy VWAP crossings are no-trade conditions.", True],
        ["Does the 15M trend support the direction?", "Countertrend VWAP reclaims require separate evidence.", True],
        ["Is the structural invalidation point objectively defined?", "A vaguely placed stop is not a hardened rule.", True],
        ["Is the reward path clear and ≥2R?", "Avoid nearby opposing range boundaries.", True],
        ["Is this outside the news/volatility blacklist?", "Price dislocations invalidate ordinary VWAP assumptions.", True],
    ]),
]


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def bootstrap():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS setups (
          id text PRIMARY KEY, name text NOT NULL, markets text NOT NULL,
          status text NOT NULL DEFAULT 'PAPER', description text NOT NULL DEFAULT '',
          questions jsonb NOT NULL DEFAULT '[]'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS trades (
          id uuid PRIMARY KEY, trade_date date NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          setup_id text REFERENCES setups(id), market text NOT NULL, direction text NOT NULL,
          entry_price numeric, stop_price numeric, target_price numeric,
          contracts integer NOT NULL DEFAULT 0, planned_risk numeric NOT NULL DEFAULT 0,
          gross_pnl numeric NOT NULL DEFAULT 0, fees numeric NOT NULL DEFAULT 0,
          status text NOT NULL DEFAULT 'PLANNED', score integer NOT NULL DEFAULT 0,
          rule_compliant boolean NOT NULL DEFAULT false, answers jsonb NOT NULL DEFAULT '{}'::jsonb,
          risk_notes text NOT NULL DEFAULT '', review_notes text NOT NULL DEFAULT '',
          tags text NOT NULL DEFAULT ''
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS trades_day_idx ON trades(trade_date DESC)")
        for slug, name, markets, status, desc, questions in SEEDS:
            qs = [{"id": f"q{i+1}", "text": x[0], "risk_note": x[1], "required": x[2]} for i,x in enumerate(questions)]
            conn.execute("""INSERT INTO setups(id,name,markets,status,description,questions) VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT(id) DO NOTHING""", (slug, name, markets, status, desc, json.dumps(qs)))


@asynccontextmanager
async def lifespan(app):
    bootstrap()
    yield

app = FastAPI(title="Case Capital Local Trading Journal", lifespan=lifespan, docs_url=None, redoc_url=None)

class SetupInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    markets: str = Field(default="MES", max_length=100)
    description: str = Field(default="", max_length=500)
    questions: list[dict[str, Any]] = Field(default_factory=list, max_length=20)

class TradeInput(BaseModel):
    trade_date: date
    setup_id: str
    market: str = Field(min_length=1, max_length=12)
    direction: str = Field(pattern="^(LONG|SHORT)$")
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    contracts: int = Field(ge=0, le=100)
    planned_risk: float = Field(ge=0, le=1000000)
    gross_pnl: float = Field(ge=-1000000, le=1000000)
    fees: float = Field(ge=0, le=100000)
    status: str = Field(pattern="^(PLANNED|EXECUTED|SKIPPED|CANCELLED)$")
    score: int = Field(ge=0, le=100)
    rule_compliant: bool
    answers: dict[str, Any] = Field(default_factory=dict)
    risk_notes: str = Field(default="", max_length=15000)
    review_notes: str = Field(default="", max_length=15000)
    tags: str = Field(default="", max_length=500)

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")

@app.get("/health")
def health():
    with db() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"ok": True, "storage": "postgresql"}

@app.get("/api/setups")
def list_setups():
    with db() as conn:
        return conn.execute("SELECT id,name,markets,status,description,questions FROM setups ORDER BY created_at,id").fetchall()

@app.post("/api/setups", status_code=201)
def create_setup(data: SetupInput):
    slug = "custom-" + uuid.uuid4().hex[:12]
    qs=[]
    for i, q in enumerate(data.questions):
        qt = str(q.get("text", "")).strip()
        if not qt: continue
        qs.append({"id":f"q{i+1}","text":qt[:350],"risk_note":str(q.get("risk_note", ""))[:1000],"required":bool(q.get("required", True))})
    with db() as conn:
        conn.execute("INSERT INTO setups(id,name,markets,status,description,questions) VALUES (%s,%s,%s,'PAPER',%s,%s)",
                     (slug,data.name,data.markets,data.description,json.dumps(qs)))
    return {"id":slug}

@app.get("/api/trades")
def list_trades():
    with db() as conn:
        rows = conn.execute("""SELECT id::text AS id,trade_date::text AS trade_date,setup_id,market,direction,
        entry_price,stop_price,target_price,contracts,planned_risk,gross_pnl,fees,status,score,
        rule_compliant,answers,risk_notes,review_notes,tags,created_at::text AS created_at
        FROM trades ORDER BY trade_date DESC,created_at DESC LIMIT 5000""").fetchall()
    for row in rows:
        for field in ("entry_price","stop_price","target_price","planned_risk","gross_pnl","fees"):
            if row[field] is not None: row[field]=float(row[field])
    return rows

@app.post("/api/trades", status_code=201)
def create_trade(data: TradeInput):
    obj = data.model_dump()
    obj["answers"] = json.dumps(obj["answers"])
    columns = list(obj)
    vals = [obj[k] for k in columns]
    ident = str(uuid.uuid4())
    with db() as conn:
        found=conn.execute("SELECT 1 FROM setups WHERE id=%s",(data.setup_id,)).fetchone()
        if not found: raise HTTPException(400,"Unknown setup")
        conn.execute(f"INSERT INTO trades(id,{','.join(columns)}) VALUES (%s,{','.join(['%s']*len(columns))})", [ident,*vals])
    return {"id":ident}

@app.put("/api/trades/{trade_id}")
def update_trade(trade_id: uuid.UUID, data: TradeInput):
    obj=data.model_dump()
    obj["answers"]=json.dumps(obj["answers"])
    with db() as conn:
        found=conn.execute("SELECT 1 FROM setups WHERE id=%s",(data.setup_id,)).fetchone()
        if not found: raise HTTPException(400,"Unknown setup")
        changes=", ".join(f"{k}=%s" for k in obj)
        result=conn.execute(f"UPDATE trades SET {changes} WHERE id=%s", [*obj.values(),str(trade_id)])
        if result.rowcount==0: raise HTTPException(404,"Trade not found")
    return {"ok":True}

@app.delete("/api/trades/{trade_id}")
def delete_trade(trade_id: uuid.UUID):
    with db() as conn:
        result=conn.execute("DELETE FROM trades WHERE id=%s", (str(trade_id),))
        if result.rowcount==0: raise HTTPException(404,"Trade not found")
    return {"ok":True}