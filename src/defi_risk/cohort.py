"""Base rate of persistent stablecoin depegs, measured on every USD stablecoin we can price.

Prices are weekly (DefiLlama caps a request at 500 points, so weekly lets us batch 3 coins).
A persistent depeg is a run of at least MIN_RUN consecutive weekly prices at or below 1-d.
Short wobbles are excluded on purpose: a holder to maturity only loses if the depeg lasts,
and single-day dips in obscure coins are often bad price data.

Known biases (both push the true risk UP, not down):
  * dead coins missing from DefiLlama's list are not counted (survivorship);
  * only coins with a CoinGecko id and daily prices are used.
"""
import json
import math
import time
import urllib.error
from pathlib import Path

from . import sources

CACHE = Path(__file__).resolve().parents[2] / "data" / "cohort_prices.json"
PERIOD_DAYS = 7
MIN_RUN = 2  # two weekly samples in a row: the depeg lasted at least a week


def _get(url, tries=6):
    """GET with backoff on rate limiting. Raises after the last try, never fails silently."""
    for i in range(tries):
        try:
            return sources._request(url)
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(2 ** i)


def _histories(gecko_ids, days=1100, batch=3):
    """Weekly prices for many coins, batched to stay under DefiLlama's limits."""
    now, pts = int(time.time()), {g: {} for g in gecko_ids}
    span = days // PERIOD_DAYS
    for i in range(0, len(gecko_ids), batch):
        keys = [f"coingecko:{g}" for g in gecko_ids[i:i + batch]]
        start = now - days * 86400
        data = _get(f"https://coins.llama.fi/chart/{','.join(keys)}?start={start}&span={span}&period={PERIOD_DAYS}d")
        for key in keys:
            for p in data["coins"].get(key, {}).get("prices", []):
                pts[key.split(":", 1)[1]][p["timestamp"]] = p["price"]
        time.sleep(1.2)
    return {g: [p for _, p in sorted(v.items())] for g, v in pts.items()}


def load_prices(refresh=False):
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text())
    coins = [a for a in _get("https://stablecoins.llama.fi/stablecoins?includePrices=false")["peggedAssets"]
             if a.get("pegType") == "peggedUSD" and a.get("gecko_id")]
    hist = _histories([a["gecko_id"] for a in coins])
    out = [{"symbol": a["symbol"], "mechanism": a.get("pegMechanism"),
            "circulating": a["circulating"].get("peggedUSD") or 0, "prices": hist[a["gecko_id"]]}
           for a in coins if len(hist[a["gecko_id"]]) >= 30]
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(out))
    return out


def episodes(prices, d, min_run=MIN_RUN):
    n = run = 0
    for p in prices:
        run = run + 1 if p <= 1 - d else 0
        if run == min_run:
            n += 1  # count each persistent episode once
    return n


def _poisson_cdf(k, lam):
    if lam == 0:
        return 1.0
    return sum(math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1)) for i in range(k + 1))


def poisson_ci(k, alpha=0.1):
    """Exact (Garwood) interval for a Poisson count, 90% by default.

    Lower bound: P(X >= k | lo) = alpha/2, i.e. cdf(k-1, lo) = 1 - alpha/2.
    Upper bound: P(X <= k | hi) = alpha/2, i.e. cdf(k, hi) = alpha/2.
    """
    def solve(target, increasing, k=k):
        lo, hi = 0.0, k + 10 * math.sqrt(k + 1) + 20
        for _ in range(80):
            mid = (lo + hi) / 2
            v = _poisson_cdf(k, mid)
            (lo, hi) = (mid, hi) if (v > target) == increasing else (lo, mid)
        return lo
    low = 0.0 if k == 0 else solve(1 - alpha / 2, True, k - 1)
    high = solve(alpha / 2, True, k)
    return low, high


def base_rate(cohort, d, window_days, mechanism_filter=None, min_circulating=0):
    """Probability that a coin starts a persistent depeg of size d within one holding window."""
    coins = [c for c in cohort if (mechanism_filter is None or mechanism_filter(c["mechanism"]))
             and c.get("circulating", 0) >= min_circulating]
    n_ep = sum(episodes(c["prices"], d) for c in coins)
    exposure = sum(len(c["prices"]) for c in coins) * PERIOD_DAYS / window_days  # independent windows
    if exposure == 0:
        return {"coins": len(coins), "episodes": 0, "windows": 0, "p": 0.0, "lo": 0.0, "hi": float("nan")}
    lo, hi = poisson_ci(n_ep)
    return {"coins": len(coins), "episodes": n_ep, "windows": exposure,
            "p": n_ep / exposure, "lo": lo / exposure, "hi": hi / exposure}


def estimate_p3(window_days, d=0.03, min_circulating=1e8):
    """Data-driven P(persistent depeg >= d within the holding window) with a 90% range.

    Cohort: non-fiat-backed USD stablecoins above `min_circulating` today, the size class
    USDe belongs to. Size is measured today, so survivors are over-represented: treat the
    low end of the range with caution.
    """
    r = base_rate(load_prices(), d, window_days, lambda m: m != "fiat-backed", min_circulating)
    return {"p": r["p"], "lo": r["lo"], "hi": r["hi"], "coins": r["coins"], "episodes": r["episodes"]}
