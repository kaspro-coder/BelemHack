"""Cost of unwinding a PT position, from live Pendle swap quotes.

Quotes are read-only (nothing is executed). They reflect the pool as it is right now,
so they describe calm-market exit cost, not stressed-market exit cost.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from . import sources

DUMMY_RECEIVER = "0x000000000000000000000000000000000000dEaD"


def _quote(market, pt, token_out, pt_amount, chain_id=1):
    params = urllib.parse.urlencode({
        "receiver": DUMMY_RECEIVER, "slippage": 0.01, "enableAggregator": "false",
        "tokenIn": pt, "tokenOut": token_out, "amountIn": int(pt_amount * 10**18),
    })
    url = f"{sources.PENDLE}/core/v2/sdk/{chain_id}/markets/{market}/swap?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "defi-risk/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["data"]
    except urllib.error.HTTPError as e:
        if "MarketProportionTooHigh" in e.read().decode():
            return None  # pool refuses a trade this large
        raise


class ExitCurve:
    def __init__(self, market, chain_id=1):
        info = _get(f"{sources.PENDLE}/core/v1/{chain_id}/markets/{market}")
        self.market, self.chain_id = market, chain_id
        self.pt = info["pt"]["address"] if "address" in info["pt"] else info["pt"]["id"].split("-")[1]
        self.token_out = info["underlyingAsset"]["address"]
        self.pt_usd = info["pt"]["price"]["usd"]

    def cost(self, usd):
        """Fractional loss (price impact + fee) to sell `usd` of PT, or None if the pool refuses."""
        q = _quote(self.market, self.pt, self.token_out, usd / self.pt_usd, self.chain_id)
        if q is None:
            return None
        impact = -q["priceImpact"]
        fee = q["fee"]["usd"] / usd
        return impact + fee

    def capacity_usd(self, lo=1e5, hi=5e7, tol=0.02):
        """Largest single sale the pool accepts (bisection)."""
        if self.cost(lo) is None:
            return 0.0
        while hi / lo > 1 + tol:
            mid = (lo * hi) ** 0.5
            lo, hi = (mid, hi) if self.cost(mid) is not None else (lo, mid)
        return lo


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "defi-risk/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)
