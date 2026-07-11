import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analytics as an
import data
import portfolios_db as pdb

st.set_page_config(page_title="Portfolio Analyzer", layout="wide")
pdb.init_db()
conn = pdb.get_db()

REBALANCE_OPTIONS = ["none", "monthly", "quarterly", "annual"]

# ---------- Sidebar: portfolio builder ----------
st.sidebar.title("Portfolios")

portfolios = pdb.list_portfolios(conn)
portfolio_names = [p["name"] for p in portfolios]
choice = st.sidebar.selectbox("Load portfolio", ["+ New Portfolio"] + portfolio_names)

if choice == "+ New Portfolio":
    loaded_id, default_name, default_symbols, default_weights, default_rebalance = (
        None, "", [], {}, "annual",
    )
else:
    loaded = next(p for p in portfolios if p["name"] == choice)
    loaded_id = loaded["id"]
    holdings_rows = pdb.get_holdings(conn, loaded_id)
    default_name = loaded["name"]
    default_symbols = [h["symbol"] for h in holdings_rows]
    default_weights = {h["symbol"]: h["weight_pct"] for h in holdings_rows}
    default_rebalance = loaded["rebalance_freq"]

tracked_symbols = [s for s, _ in data.get_tracked_symbols()]

st.sidebar.subheader("Holdings")
selected_symbols = st.sidebar.multiselect("Symbols", tracked_symbols, default=default_symbols)

weights = {}
for symbol in selected_symbols:
    weights[symbol] = st.sidebar.number_input(
        f"{symbol} weight %", min_value=0.0, max_value=100.0,
        value=float(default_weights.get(symbol, 0.0)), step=1.0, key=f"weight_{symbol}",
    )
total_weight = sum(weights.values())

if selected_symbols:
    if abs(total_weight - 100) > 0.01:
        st.sidebar.warning(f"Weights sum to {total_weight:.1f}%, not 100%.")
    else:
        st.sidebar.success("Weights sum to 100%")

rebalance_freq = st.sidebar.selectbox(
    "Rebalancing", REBALANCE_OPTIONS, index=REBALANCE_OPTIONS.index(default_rebalance)
)
name = st.sidebar.text_input("Portfolio name", value=default_name)

save_col, delete_col = st.sidebar.columns(2)
if save_col.button("Save"):
    if not name:
        st.sidebar.error("Enter a name first.")
    elif abs(total_weight - 100) > 0.01:
        st.sidebar.error("Weights must sum to 100% before saving.")
    else:
        pdb.save_portfolio(conn, name, rebalance_freq, weights)
        st.sidebar.success(f"Saved '{name}'")
        st.rerun()

if loaded_id is not None and delete_col.button("Delete"):
    pdb.delete_portfolio(conn, loaded_id)
    st.sidebar.success(f"Deleted '{choice}'")
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Benchmarks")
default_benchmarks = [s for s in ["SPY"] if s in tracked_symbols]
benchmark_symbols = st.sidebar.multiselect("Compare against", tracked_symbols, default=default_benchmarks)

st.sidebar.subheader("Settings")
chart_period = st.sidebar.selectbox("Chart / risk window", an.STANDARD_PERIODS, index=4)
risk_free_pct = st.sidebar.number_input("Risk-free rate (annual %)", value=4.0, step=0.25)
risk_free = risk_free_pct / 100

# ---------- Main area ----------
st.title("Portfolio Analyzer")

if not selected_symbols or abs(total_weight - 100) > 0.01:
    st.info("Build a portfolio in the sidebar — pick symbols and set weights that sum to 100% — to see analysis.")
    st.stop()

all_symbols = list(dict.fromkeys(selected_symbols + benchmark_symbols))
try:
    full_price_df = data.load_price_series(all_symbols)
except ValueError as e:
    st.error(str(e))
    st.stop()

st.caption(
    f"Price history available: {full_price_df.index.min().date()} to "
    f"{full_price_df.index.max().date()} ({len(full_price_df)} trading days, "
    "truncated to the shortest common history across your selected symbols)"
)

pie_col, table_col = st.columns([1, 1])
with pie_col:
    fig_pie = px.pie(
        pd.DataFrame({"Symbol": list(weights.keys()), "Weight": list(weights.values())}),
        names="Symbol", values="Weight", title=f"{name or '(unsaved)'} composition",
    )
    st.plotly_chart(fig_pie, use_container_width=True)
with table_col:
    st.write("Holdings")
    st.dataframe(
        pd.DataFrame({"Symbol": list(weights.keys()), "Weight %": list(weights.values())}).set_index("Symbol")
    )

chart_df = an.slice_period(full_price_df, chart_period)
port_growth = an.portfolio_growth(chart_df, weights, rebalance_freq)
port_returns = port_growth.pct_change().dropna()

bench_growth = {b: an.portfolio_growth(chart_df, {b: 100}, "none") for b in benchmark_symbols}
bench_returns = {b: g.pct_change().dropna() for b, g in bench_growth.items()}

tab_returns, tab_risk, tab_diversification, tab_stress = st.tabs(
    ["Growth & Returns", "Risk", "Diversification", "Stress Test"]
)

with tab_returns:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=port_growth.index, y=port_growth * 10000, name="Portfolio"))
    for b, g in bench_growth.items():
        fig.add_trace(go.Scatter(x=g.index, y=g * 10000, name=b))
    fig.update_layout(title=f"Growth of $10,000 ({chart_period})", yaxis_title="Value ($)")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Returns across time periods")
    rows = []
    series_map = {"Portfolio": (weights, rebalance_freq)}
    for b in benchmark_symbols:
        series_map[b] = ({b: 100}, "none")

    for label, (w, rf) in series_map.items():
        row = {"Name": label}
        for period_label in an.STANDARD_PERIODS:
            window = an.slice_period(full_price_df, period_label)
            if len(window) < 2:
                row[period_label] = None
                continue
            g = an.portfolio_growth(window, w, rf)
            row[period_label] = an.cumulative_return(g)
        row["CAGR (Max)"] = an.cagr(an.portfolio_growth(full_price_df, w, rf))
        rows.append(row)

    returns_df = pd.DataFrame(rows).set_index("Name")
    st.dataframe(returns_df.style.format("{:.1%}"))

    st.subheader("Calendar year returns")
    cal_map = {"Portfolio": an.calendar_year_returns(an.portfolio_growth(full_price_df, weights, rebalance_freq))}
    for b in benchmark_symbols:
        cal_map[b] = an.calendar_year_returns(an.portfolio_growth(full_price_df, {b: 100}, "none"))
    cal_df = pd.DataFrame(cal_map)
    fig_cal = px.bar(cal_df, barmode="group", title="Calendar Year Returns")
    fig_cal.update_layout(yaxis_tickformat=".0%", xaxis_title="Year", yaxis_title="Return")
    st.plotly_chart(fig_cal, use_container_width=True)

with tab_risk:
    st.subheader(f"Risk metrics ({chart_period})")
    risk_rows = [{
        "Name": "Portfolio",
        "Ann. Volatility": an.annualized_volatility(port_returns),
        "Sharpe": an.sharpe_ratio(port_returns, risk_free),
        "Sortino": an.sortino_ratio(port_returns, risk_free),
        "Max Drawdown": an.max_drawdown(port_growth)[0],
    }]
    for b, br in bench_returns.items():
        risk_rows.append({
            "Name": b,
            "Ann. Volatility": an.annualized_volatility(br),
            "Sharpe": an.sharpe_ratio(br, risk_free),
            "Sortino": an.sortino_ratio(br, risk_free),
            "Max Drawdown": an.max_drawdown(bench_growth[b])[0],
        })
    risk_df = pd.DataFrame(risk_rows).set_index("Name")
    st.dataframe(risk_df.style.format({
        "Ann. Volatility": "{:.1%}", "Sharpe": "{:.2f}", "Sortino": "{:.2f}", "Max Drawdown": "{:.1%}",
    }))

    if benchmark_symbols:
        st.subheader("Vs. benchmark")
        capture_rows = [{
            "Benchmark": b,
            "Beta": an.beta(port_returns, br),
            "Upside Capture %": an.upside_capture(port_returns, br),
            "Downside Capture %": an.downside_capture(port_returns, br),
        } for b, br in bench_returns.items()]
        st.dataframe(pd.DataFrame(capture_rows).set_index("Benchmark").style.format({
            "Beta": "{:.2f}", "Upside Capture %": "{:.1f}", "Downside Capture %": "{:.1f}",
        }))
        st.caption(
            "Downside capture < 100% means the portfolio lost less than the benchmark on the "
            "benchmark's down days — the clearest single number for downside protection."
        )

    st.subheader("Drawdown")
    fig_dd = go.Figure()
    _, port_dd = an.max_drawdown(port_growth)
    fig_dd.add_trace(go.Scatter(x=port_dd.index, y=port_dd * 100, fill="tozeroy", name="Portfolio"))
    for b, g in bench_growth.items():
        _, bdd = an.max_drawdown(g)
        fig_dd.add_trace(go.Scatter(x=bdd.index, y=bdd * 100, name=b))
    fig_dd.update_layout(title=f"Drawdown ({chart_period})", yaxis_title="% from peak")
    st.plotly_chart(fig_dd, use_container_width=True)

with tab_diversification:
    st.subheader("Correlation between holdings")
    if len(selected_symbols) < 2:
        st.info("Add at least 2 holdings to see a correlation matrix.")
    else:
        holdings_returns = chart_df[selected_symbols].pct_change().dropna()
        corr = holdings_returns.corr()
        fig_corr = px.imshow(
            corr, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
            title=f"Holdings Correlation ({chart_period})",
        )
        st.plotly_chart(fig_corr, use_container_width=True)
        st.caption("Lower/negative correlations between holdings mean more diversification benefit.")

with tab_stress:
    st.subheader("Historical stress tests")
    port_stress = an.stress_test(full_price_df, weights, rebalance_freq)
    if not port_stress:
        st.info("None of the known stress-test windows fall within your tracked price history.")
    else:
        stress_rows = []
        for label, port_ret in port_stress.items():
            row = {"Period": label, "Portfolio": port_ret}
            for b in benchmark_symbols:
                b_stress = an.stress_test(full_price_df, {b: 100}, "none")
                row[b] = b_stress.get(label)
            stress_rows.append(row)
        st.dataframe(pd.DataFrame(stress_rows).set_index("Period").style.format("{:.1%}"))
        st.caption("Cumulative return of this exact portfolio mix through known historical drawdown windows.")
