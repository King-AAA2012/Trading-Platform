"""Portfolio construction and risk analytics.

- Daily returns of all candidates are aligned on a common calendar (markets in different countries trade different
  days; gaps are forward-filled).
- Covariance uses Ledoit-Wolf shrinkage toward a scaled identity, so 30+ stocks with one year of data still give a
  well-conditioned, stable matrix.
- Weights maximise a mean-variance objective under box limits (per-position cap, per-trade risk cap from the ATR
  stop), a gross-exposure budget (1 - cash reserve) and sector/market caps, by projected gradient ascent. The chosen
  objective (max Sharpe, min volatility, max return, risk parity, balanced) decides the risk aversion / target.
- The result is scaled to the user's target volatility and checked against the drawdown limit.
- Analytics: expected return/vol/Sharpe, historical VaR & CVaR, a one-year backtest of the weights, a bootstrapped
  Monte Carlo of the next year, diversification ratio, effective positions, average correlation, beta and each
  holding's share of total risk.
"""
from __future__ import annotations

import math

import numpy as np

RF = 0.03


def align(hists: dict[str, dict], symbols: list[str], days: int = 252) -> tuple[np.ndarray, list[str], np.ndarray]:
    series = [(s, hists[s]) for s in symbols if s in hists and len(hists[s]["c"]) > 60]
    if not series:
        return np.zeros((0, 0)), [], np.zeros(0)
    alld = np.unique(np.concatenate([h["t"][-days - 60:] // 86400 for _, h in series]))
    cnt = np.zeros(len(alld))
    for _, h in series:
        cnt += np.isin(alld, h["t"] // 86400)
    grid = alld[cnt >= max(1, 0.3 * len(series))][-(days + 1):]
    cols = []
    for _, h in series:
        d = h["t"] // 86400
        pos = np.searchsorted(d, grid, side="right") - 1
        px = np.where(pos >= 0, h["c"][np.maximum(pos, 0)], np.nan)
        first = np.flatnonzero(np.isfinite(px))
        if len(first):
            px[: first[0]] = px[first[0]]
        cols.append(px)
    P = np.column_stack(cols)
    R = np.diff(np.log(np.maximum(P, 1e-12)), axis=0)
    R = np.nan_to_num(R)
    R = np.clip(R, -0.5, 0.5)
    return R, [s for s, _ in series], grid[1:]


def ledoit_wolf(R: np.ndarray) -> np.ndarray:
    T, N = R.shape
    X = R - R.mean(0)
    S = X.T @ X / T
    mu = np.trace(S) / N
    F = mu * np.eye(N)
    d2 = np.sum((S - F) ** 2)
    b_bar2 = (np.sum(np.sum(X ** 2, axis=1) ** 2) - T * np.sum(S ** 2)) / T ** 2
    shrink = float(np.clip(min(b_bar2, d2) / d2, 0, 1)) if d2 > 0 else 1.0
    return shrink * F + (1 - shrink) * S


def _project(w, lo, hi, budget, groups=()):
    """Project onto {lo <= w <= hi, sum|w| <= budget, sum|w_g| <= cap_g for each group} (each asset has a fixed sign domain).
    Group caps are enforced by proportional shrinking, which keeps the point feasible without zeroing anyone out."""
    w = _project_box_budget(w, lo, hi, budget)
    for idx, cap in groups:
        tot = np.abs(w[idx]).sum()
        if tot > cap:
            w[idx] *= cap / tot
    return w


def _project_box_budget(w, lo, hi, budget):
    w = np.clip(w, lo, hi)
    if np.abs(w).sum() <= budget:
        return w
    sgn = np.where(hi > 0, 1.0, -1.0)
    cap = np.maximum(np.abs(np.where(sgn > 0, hi, lo)), 0)
    a = np.abs(w)
    t_lo, t_hi = 0.0, a.max()
    for _ in range(60):
        t = (t_lo + t_hi) / 2
        if np.clip(a - t, 0, cap).sum() > budget:
            t_lo = t
        else:
            t_hi = t
    return sgn * np.clip(a - t_hi, 0, cap)


def mean_variance(mu, S, lo, hi, budget, gamma, iters=600, groups=()):
    N = len(mu)
    w = _project(np.full(N, budget / N) * np.where(hi > 0, 1, np.where(lo < 0, -1, 0)), lo, hi, budget, groups)
    L = float(np.linalg.eigvalsh(S).max()) * gamma + 1e-9
    step = 1.0 / L
    for _ in range(iters):
        w_new = _project(w + step * (mu - gamma * S @ w), lo, hi, budget, groups)
        if np.abs(w_new - w).max() < 1e-7:
            w = w_new
            break
        w = w_new
    return w


def risk_parity(S, lo, hi, budget, iters=200, groups=()):
    sd = np.sqrt(np.maximum(np.diag(S), 1e-12))
    ok = hi > 0
    if not ok.any():
        return np.zeros(len(sd))
    w = np.where(ok, 1 / sd, 0)
    w = w / w.sum() * budget
    for _ in range(iters):
        rc = w * (S @ w)
        w = np.where(ok, w * np.sqrt(np.mean(rc[ok]) / np.maximum(rc, 1e-16)), 0)
        w = _project(w / max(w.sum(), 1e-12) * budget, np.maximum(lo, 0), np.maximum(hi, 0), budget, groups)
    return w


def port_stats(w, mu, S):
    er = float(mu @ w)
    vol = float(math.sqrt(max(w @ S @ w, 1e-16)))
    return er, vol, (er - RF * np.abs(w).sum()) / vol


def optimise(mu, S, lo, hi, budget, objective, target_vol, groups=()):
    if objective == "parity":
        w = risk_parity(S, lo, hi, budget, groups=groups)
    elif objective == "minvol":
        w = mean_variance(np.full(len(mu), 1e-4) + 0.1 * mu, S, lo, hi, budget, gamma=60, groups=groups)
    elif objective == "return":
        w = mean_variance(mu, S, lo, hi, budget, gamma=1.5, groups=groups)
    else:
        best, w = -1e9, None
        for g in (1, 2, 4, 8, 16, 32, 64):
            c = mean_variance(mu, S, lo, hi, budget, g, groups=groups)
            sh = port_stats(c, mu, S)[2] if np.abs(c).sum() > 1e-6 else -1e9
            if sh > best:
                best, w = sh, c
        if objective == "balanced":
            w = 0.5 * w + 0.5 * risk_parity(S, lo, hi, budget, groups=groups)
    # volatility targeting: scale the whole book (cash absorbs the rest)
    _, vol, _ = port_stats(w, mu, S)
    if vol > 0:
        scale = min(target_vol / vol, budget / max(np.abs(w).sum(), 1e-9))
        w = _project(np.clip(w * scale, lo, hi), lo, hi, budget, groups)   # re-apply sector/market caps after scaling
    return w


def analytics(w: np.ndarray, R: np.ndarray, mu: np.ndarray, S: np.ndarray, bench_r: np.ndarray | None, horizon_days: int,
              max_dd: float, seed: int = 7) -> dict:
    if len(w) == 0 or not np.abs(w).sum():
        return {"empty": True}
    er, vol, sharpe = port_stats(w, mu, S * 252)
    pr = R @ w                                   # daily portfolio returns (cash earns 0)
    eq = np.cumprod(1 + pr)
    dd = float(np.min(eq / np.maximum.accumulate(eq) - 1))
    var95 = float(-np.percentile(pr, 5))
    cvar95 = float(-pr[pr <= np.percentile(pr, 5)].mean()) if len(pr) > 20 else var95
    # Monte Carlo: bootstrap history in 5-day blocks, re-centred on the committee's expected return (no hindsight drift)
    rng = np.random.default_rng(seed)
    T, H, sims = len(pr), 252, 2000
    centred = pr - pr.mean() + er / 252
    starts = rng.integers(0, max(T - 5, 1), size=(sims, H // 5 + 1))
    paths = centred[(starts[:, :, None] + np.arange(5)).reshape(sims, -1)[:, :H] % T]
    cum = np.cumprod(1 + paths, axis=1)
    term = cum[:, -1] - 1
    mdd = np.min(cum / np.maximum.accumulate(cum, axis=1) - 1, axis=1)
    sd = np.sqrt(np.maximum(np.diag(S), 1e-16))
    pvar = float(w @ S @ w)
    rc = w * (S @ w) / pvar if pvar > 0 else np.zeros_like(w)
    wn = np.abs(w) / np.abs(w).sum()
    C = S / np.outer(sd, sd)
    iu = np.triu_indices(len(w), 1)
    avg_corr = float(np.average(C[iu], weights=(wn[:, None] * wn[None, :])[iu])) if len(w) > 1 else 1.0
    beta = None
    if bench_r is not None and len(bench_r) == len(pr) and np.var(bench_r) > 0:
        beta = float(np.cov(pr, bench_r)[0, 1] / np.var(bench_r))
    step = max(1, len(eq) // 250)
    pcts = [5, 25, 50, 75, 95]
    fan = {str(p): np.percentile(cum[:, ::5], p, axis=0).round(4).tolist() for p in pcts}
    return {
        "expReturn": er, "vol": vol, "sharpe": float(sharpe), "var95": var95, "cvar95": cvar95,
        "varH": var95 * math.sqrt(horizon_days), "backtestReturn": float(eq[-1] - 1), "backtestMaxDD": dd,
        "curve": np.round(eq[::step], 4).tolist(),
        "mc": {"p": {str(p): float(np.percentile(term, p)) for p in pcts}, "probLoss": float((term < 0).mean()),
               "probDDBreach": float((mdd < -max_dd).mean()), "medianMaxDD": float(np.median(mdd)), "fan": fan},
        "divRatio": float((wn * sd).sum() / math.sqrt(max(wn @ S @ wn, 1e-16))), "effN": float(1 / (wn ** 2).sum()),
        "avgCorr": avg_corr, "beta": beta, "riskContrib": rc.tolist(),
    }
