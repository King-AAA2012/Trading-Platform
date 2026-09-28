"""Vectorised technical indicators (numpy). Every function returns an array aligned with its input."""
import numpy as np
from scipy.signal import lfilter


def ema(x: np.ndarray, n: int) -> np.ndarray:
    a = 2.0 / (n + 1)
    y, _ = lfilter([a], [1, a - 1], x[1:], zi=[(1 - a) * x[0]])
    return np.concatenate([[x[0]], y])


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    a = 1.0 / n
    y, _ = lfilter([a], [1, a - 1], x[1:], zi=[(1 - a) * x[0]])
    return np.concatenate([[x[0]], y])


def sma(x: np.ndarray, n: int) -> np.ndarray:
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.full_like(x, np.nan, dtype=float)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    out[:n - 1] = c[1:n] / np.arange(1, n)       # expanding mean for the warm-up
    return out


def rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    m = sma(x, n)
    m2 = sma(x * x, n)
    return np.sqrt(np.maximum(m2 - m * m, 0))


def rolling_max(x: np.ndarray, n: int) -> np.ndarray:
    from numpy.lib.stride_tricks import sliding_window_view
    pad = np.concatenate([np.full(n - 1, x[0]), x])
    return sliding_window_view(pad, n).max(axis=1)


def rolling_min(x: np.ndarray, n: int) -> np.ndarray:
    from numpy.lib.stride_tricks import sliding_window_view
    pad = np.concatenate([np.full(n - 1, x[0]), x])
    return sliding_window_view(pad, n).min(axis=1)


def shift(x: np.ndarray, k: int) -> np.ndarray:
    out = np.empty_like(x)
    out[:k] = x[0]
    out[k:] = x[:-k]
    return out


def rsi(c: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(c, prepend=c[0])
    up, dn = wilder(np.maximum(d, 0), n), wilder(np.maximum(-d, 0), n)
    rs = up / np.where(dn == 0, 1e-12, dn)
    return 100 - 100 / (1 + rs)


def true_range(h, l, c):
    pc = shift(c, 1)
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def atr(h, l, c, n: int = 14) -> np.ndarray:
    tr = true_range(h, l, c)
    # some feeds (e.g. FX, thin markets) may only have closes (h == l == c); fall back to close-to-close moves
    tr = np.where(tr <= 0, np.abs(np.diff(c, prepend=c[0])), tr)
    return np.maximum(wilder(tr, n), c * 1e-4)


def macd(c, fast=12, slow=26, sig=9):
    line = ema(c, fast) - ema(c, slow)
    signal = ema(line, sig)
    return line, signal, line - signal


def adx(h, l, c, n: int = 14):
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(h, l, c, n)
    pdi = 100 * wilder(pdm, n) / a
    ndi = 100 * wilder(ndm, n) / a
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12)
    return wilder(dx, n), pdi, ndi


def bollinger(c, n=20, k=2.0):
    m = sma(c, n)
    s = rolling_std(c, n)
    return m + k * s, m, m - k * s


def obv(c, v):
    return np.cumsum(np.sign(np.diff(c, prepend=c[0])) * v)


def stoch(h, l, c, n=14, d=3):
    hh, ll = rolling_max(h, n), rolling_min(l, n)
    k = 100 * (c - ll) / np.maximum(hh - ll, 1e-12)
    return k, sma(k, d)
