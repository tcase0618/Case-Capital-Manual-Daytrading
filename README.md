# Case Capital Futures Desk — Local PostgreSQL Edition

A **local-only**, manual futures trading research dashboard. Trade qualification, risk notes and journal records are persisted in PostgreSQL. The web browser talks to a small Python/FastAPI server; it never holds PostgreSQL credentials.

## Requirements
- Docker Desktop / Docker Engine with Docker Compose
- A web browser

## Startup
1. Extract the ZIP.
2. Copy `.env.example` to `.env`.
3. Replace the example `POSTGRES_PASSWORD` with a long, unique password (avoid `@`, `:`, `/`, `?`, `#` or `%` in the password unless URL-encoded).
4. Open a terminal in the `case_capital_local` directory and run:

```bash
docker compose up --build -d
```

5. Open **http://localhost:8765** in your browser.

Stop app without deleting saved data:

```bash
docker compose down
```

**IMPORTANT:** Do not run `docker compose down -v` unless you intend to delete the PostgreSQL data volume permanently. Back up journal records using the CSV and JSON export buttons. These are exports, not automated backups.

## What's included
- Setup library: trend pullback, opening range breakout, gold liquidity sweep, VWAP reclaim
- Custom setup creation, each with its own qualifying questions and tailored risk warnings
- Per-question YES / NO / N/A answers and individual note fields
- Manual trade qualification with risk warnings and explicit PAPER/ACTIVE separation
- Risk sizing for ES/MES, NQ/MNQ, GC/MGC with $50 max initial risk
- PostgreSQL-backed journal with create/edit/delete, P&L, notes, rule compliance and full questionnaire snapshots
- CSV and full JSON export

## Architecture and security
- Docker PostgreSQL 16 is internal to the Docker network (no published database port).
- FastAPI UI/API binds only to **127.0.0.1:8765** on the host.
- Local access only; **no login/authentication is provided**, so do not expose it to the internet or a shared network.
- This is a single-user prototype. A future VPS/multi-user deployment needs authentication, HTTPS, CSRF protection, role-based permissions, stronger audit history, and managed backups.
- The app runs no trades and is not connected to TradingView, Tradovate, Tradeify, or broker APIs.
- Questions are starter research checklists, not verified indicators of profitable setups.

## Data
Trades have per-question responses with free-form notes, an overall risk note, post-trade review, optional prices, contracts, planned risk, P&L and fees. Updating a setup does not retroactively alter existing questionnaire snapshots. Custom setups start in PAPER status.

## Review before evaluation use
Confirm current Tradeify account specifications, activity rules, trading hours, platform connectivity and payout restrictions yourself. This dashboard enforces **no real order controls**.

## Source distribution
The complete application is packaged under `releases/case_capital_futures_desk_postgres.zip` until the extracted source files are checked in. The earlier standalone HTML is under `legacy/`.
