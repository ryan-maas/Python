# Portfolio Analyzer

A Streamlit app for building model portfolios of mutual funds/ETFs and
analyzing their historical returns, risk, and downside protection. Reads
prices directly from [Fund Tracker](../Fund%20Tracker)'s `fund_tracker.db` —
it never fetches or writes price data itself.

## Setup

**Requirements:** Python 3.10+, and [Fund Tracker](../Fund%20Tracker) set up
with at least some symbols tracked.

```bash
cd "Portfolio Analyzer"
pip install -r requirements.txt
streamlit run app.py
```

If you build a portfolio or pick a benchmark that references a symbol not
yet tracked, the app will tell you which `python update.py --add SYMBOL`
command to run in Fund Tracker first.

## Usage

1. **Build a portfolio** in the sidebar: select symbols from what's tracked
   in Fund Tracker, set a weight % for each (must sum to 100%), choose a
   rebalancing frequency, name it, and hit **Save**. Saved portfolios can be
   reloaded from the dropdown at the top of the sidebar.
2. **Pick benchmarks** to compare against (e.g. `SPY` for US large-cap,
   `AGG`/`BND` for bonds, or a blended benchmark built as its own saved
   portfolio).
3. **Growth & Returns tab** — growth-of-$10,000 chart, a returns table across
   YTD/1Y/3Y/5Y/10Y/Max, and calendar-year returns.
4. **Risk tab** — annualized volatility, Sharpe, Sortino, max drawdown, beta,
   and upside/downside capture ratios vs. each benchmark, plus a drawdown
   (underwater) chart. Downside capture is the clearest single number for
   "how much of the benchmark's losses did this portfolio avoid."
5. **Diversification tab** — correlation heatmap across your holdings.
6. **Stress Test tab** — how this exact portfolio mix performed through the
   COVID crash (Feb–Mar 2020) and the 2022 bear market, if those dates fall
   within your tracked history.

## Rebalancing

- `none` — buy and hold; weights drift with relative performance over time.
- `monthly` / `quarterly` / `annual` — periodically sold back to target
  weights. `annual` is a reasonable default for most model portfolios.

## Project Structure

```
Portfolio Analyzer/
├── app.py            # Streamlit UI
├── data.py           # reads price series from Fund Tracker's db (read-only)
├── analytics.py       # returns, volatility, Sharpe/Sortino, drawdown, beta, capture ratios
├── portfolios_db.py  # SQLite schema + CRUD for saved portfolios
├── requirements.txt
└── portfolios.db      # created on first save (gitignored)
```
