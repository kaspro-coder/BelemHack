"""Base rate of material hacks on the largest perp exchanges, from DefiLlama's hacks database.

Cohort: the 25 largest derivatives exchanges by open interest today (CoinGecko). An exchange
counts from max(year established, 2019). An incident is a CEX hack of at least MIN_LOSS.

Biases: the cohort is chosen by today's size, so exchanges that died or were drained
(e.g. FTX) are missing, which understates risk. The database records hacks, not freezes or
outages, which understates it further. Both push the true rate UP.
"""
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

from . import sources
from .cohort import poisson_ci

MIN_LOSS = 10e6
FIRST_YEAR = 2019
# Name patterns that tie a CoinGecko exchange to its DefiLlama incident entries.
PATTERNS = {
    "Binance": r"^Binance", "Hyperliquid": r"Hyperliquid", "Bybit": r"^Bybit", "Gate": r"^Gate$",
    "MEXC": r"MEXC", "WEEX": r"WEEX", "CoinW": r"CoinW", "Tapbit": r"Tapbit", "Bitget": r"Bitget",
    "OKX": r"^OKX$|^OKEx", "XT": r"^XT", "OrangeX": r"OrangeX", "Toobit": r"Toobit",
    "CoinUp": r"CoinUp", "WhiteBIT": r"WhiteBIT", "LBank": r"LBank", "KuCoin": r"^KuCoin",
    "HTX": r"^HTX|^Huobi", "BingX": r"BingX", "Aster": r"Aster", "Deribit": r"Deribit",
    "Phemex": r"Phemex", "Ourbit": r"Ourbit", "BTSE": r"BTSE", "Variational": r"Variational",
}


def _top_exchanges(n=25):
    url = f"https://api.coingecko.com/api/v3/derivatives/exchanges?order=open_interest_btc_desc&per_page={n}"
    req = urllib.request.Request(url, headers={"User-Agent": "defi-risk/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def incident_rate(window_days):
    """Hack rate per exchange-year, and P(at least n venues hit) over the holding window."""
    hacks = [h for h in sources.llama_hacks() if h.get("targetType") == "CEX" and (h.get("amount") or 0) >= MIN_LOSS]
    now = datetime.now(timezone.utc)
    now_year = now.year + (now.timetuple().tm_yday - 1) / 365
    years = incidents = 0
    hits = []
    for e in _top_exchanges():
        key = next((k for k in PATTERNS if e["name"].startswith(k)), None)
        est = max(int(e.get("year_established") or FIRST_YEAR), FIRST_YEAR)
        start = datetime(est, 1, 1, tzinfo=timezone.utc).timestamp()
        mine = [h for h in hacks if key and re.search(PATTERNS[key], h["name"]) and h["date"] >= start]
        years += now_year - est
        incidents += len(mine)
        hits += [(h["name"], datetime.fromtimestamp(h["date"], timezone.utc).year, h["amount"]) for h in mine]
    lo, hi = poisson_ci(incidents)
    return {"incidents": incidents, "exchange_years": years, "per_year": incidents / years,
            "lo": lo / years, "hi": hi / years, "hits": hits, "window_days": window_days}


def prob_any(rate_per_year, n_venues, window_days):
    return 1 - (1 - min(1.0, rate_per_year * window_days / 365)) ** n_venues


# Observed once on a venue Ethena used: Bybit, Feb 2025. USDe dipped below $0.96 for about
# a day, then recovered, with no bad debt reported (Cointelegraph, Chaos Labs / Aave governance;
# secondary sources, not verified on-chain here).
PRECEDENT_DEPEG = 0.04
