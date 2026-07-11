import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252

STANDARD_PERIODS = ["YTD", "1Y", "3Y", "5Y", "10Y", "Max"]

STRESS_PERIODS = {
    "COVID Crash (Feb-Mar 2020)": ("2020-02-19", "2020-03-23"),
    "2022 Bear Market": ("2022-01-03", "2022-10-12"),
}


def normalize_weights(weights):
    total = sum(weights.values())
    return {symbol: weight / total for symbol, weight in weights.items()}


def slice_period(data, period):
    """Slices a DataFrame or Series (date index) to a trailing window ending at its last date."""
    end = data.index.max()
    if period == "YTD":
        start = pd.Timestamp(year=end.year, month=1, day=1)
    elif period == "1Y":
        start = end - pd.DateOffset(years=1)
    elif period == "3Y":
        start = end - pd.DateOffset(years=3)
    elif period == "5Y":
        start = end - pd.DateOffset(years=5)
    elif period == "10Y":
        start = end - pd.DateOffset(years=10)
    elif period == "Max":
        return data
    else:
        raise ValueError(f"Unknown period: {period}")

    sliced = data[data.index >= start]
    return sliced if len(sliced) > 1 else data


def _rebalance_dates(dates, freq):
    if freq == "none":
        return set()
    freq_map = {"monthly": "M", "quarterly": "Q", "annual": "Y"}
    idx = pd.DatetimeIndex(dates)
    period = pd.Series(idx.to_period(freq_map[freq]).values, index=idx)
    changed = period != period.shift(1)
    return set(idx[changed.values])


def portfolio_growth(price_df, weights, rebalance_freq="annual"):
    """Growth of $1 invested per `weights` (symbol -> weight), rebalanced at the given frequency."""
    weights = normalize_weights(weights)
    symbols = list(weights.keys())
    returns = price_df[symbols].pct_change().fillna(0)
    dates = returns.index
    rebal_dates = _rebalance_dates(dates, rebalance_freq)

    holdings = dict(weights)
    values = []
    for i, current_date in enumerate(dates):
        if i > 0:
            for symbol in symbols:
                holdings[symbol] *= 1 + returns.loc[current_date, symbol]
        total = sum(holdings.values())
        values.append(total)
        if current_date in rebal_dates and i > 0:
            for symbol in symbols:
                holdings[symbol] = weights[symbol] * total

    return pd.Series(values, index=dates, name="portfolio")


def cumulative_return(series):
    return series.iloc[-1] / series.iloc[0] - 1


def cagr(series):
    years = (series.index[-1] - series.index[0]).days / 365.25
    if years <= 0:
        return np.nan
    return (series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1


def annualized_volatility(returns):
    return returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)


def sharpe_ratio(returns, risk_free_annual):
    ann_return = returns.mean() * TRADING_DAYS_PER_YEAR
    ann_vol = annualized_volatility(returns)
    if not ann_vol:
        return np.nan
    return (ann_return - risk_free_annual) / ann_vol


def sortino_ratio(returns, risk_free_annual):
    downside = returns[returns < 0]
    if downside.empty:
        return np.nan
    downside_dev = np.sqrt((downside ** 2).mean()) * np.sqrt(TRADING_DAYS_PER_YEAR)
    ann_return = returns.mean() * TRADING_DAYS_PER_YEAR
    if not downside_dev:
        return np.nan
    return (ann_return - risk_free_annual) / downside_dev


def max_drawdown(series):
    running_max = series.cummax()
    drawdown = series / running_max - 1
    return drawdown.min(), drawdown


def beta(port_returns, bench_returns):
    aligned = pd.concat([port_returns, bench_returns], axis=1).dropna()
    if len(aligned) < 2:
        return np.nan
    cov = aligned.cov().iloc[0, 1]
    var = aligned.iloc[:, 1].var()
    return cov / var if var else np.nan


def _capture_ratio(port_returns, bench_returns, side):
    aligned = pd.concat([port_returns, bench_returns], axis=1, keys=["p", "b"]).dropna()
    subset = aligned[aligned["b"] < 0] if side == "down" else aligned[aligned["b"] > 0]
    if subset.empty or subset["b"].mean() == 0:
        return np.nan
    return (subset["p"].mean() / subset["b"].mean()) * 100


def downside_capture(port_returns, bench_returns):
    return _capture_ratio(port_returns, bench_returns, "down")


def upside_capture(port_returns, bench_returns):
    return _capture_ratio(port_returns, bench_returns, "up")


def calendar_year_returns(series):
    returns = {}
    for year, group in series.groupby(series.index.year):
        returns[year] = group.iloc[-1] / group.iloc[0] - 1
    return pd.Series(returns)


def stress_test(price_df, weights, rebalance_freq):
    """Cumulative return of the portfolio through known historical drawdown windows present in the data."""
    results = {}
    for label, (start, end) in STRESS_PERIODS.items():
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        if start_ts < price_df.index.min() or end_ts > price_df.index.max():
            continue
        window = price_df[(price_df.index >= start_ts) & (price_df.index <= end_ts)]
        if len(window) < 2:
            continue
        growth = portfolio_growth(window, weights, rebalance_freq)
        results[label] = cumulative_return(growth)
    return results
