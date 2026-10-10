"""Thin clients for the public data sources (no API key needed)."""
import json
import urllib.request

PENDLE = "https://api-v2.pendle.finance"
LLAMA = "https://api.llama.fi"
MORPHO = "https://blue-api.morpho.org/graphql"


def _request(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "User-Agent": "defi-risk/0.1"}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def pendle_active_markets(chain_id=1):
    return _request(f"{PENDLE}/core/v1/{chain_id}/markets/active")["markets"]


def pendle_market_data(market, chain_id=1):
    return _request(f"{PENDLE}/core/v2/{chain_id}/markets/{market}/data")


def llama_protocol(slug):
    return _request(f"{LLAMA}/protocol/{slug}")


def llama_hacks():
    return _request(f"{LLAMA}/hacks")


def usde_supply_usd():
    for a in _request("https://stablecoins.llama.fi/stablecoins?includePrices=true")["peggedAssets"]:
        if a["symbol"] == "USDe":
            return a["circulating"]["peggedUSD"]


def eth_funding_annualized():
    """Current ETH perp funding per venue, annualized (positive = longs pay shorts)."""
    out = {}
    hl = _request("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
    for u, c in zip(hl[0]["universe"], hl[1]):
        if u["name"] == "ETH":
            out["Hyperliquid"] = float(c["funding"]) * 24 * 365
    r = _request("https://api.bybit.com/v5/market/funding/history?category=linear&symbol=ETHUSDT&limit=1")
    out["Bybit"] = float(r["result"]["list"][0]["fundingRate"]) * 3 * 365
    r = _request("https://www.okx.com/api/v5/public/funding-rate?instId=ETH-USDT-SWAP")
    out["OKX"] = float(r["data"][0]["fundingRate"]) * 3 * 365
    r = _request("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT")
    out["Binance"] = float(r["lastFundingRate"]) * 3 * 365
    return out


def morpho_markets_by_collateral(token_address, chain_id=1):
    query = (
        '{ markets(first: 50, where: { collateralAssetAddress_in: ["%s"], chainId_in: [%d] }) '
        "{ items { marketId lltv loanAsset { symbol } collateralAsset { symbol } "
        "oracle { address type } "
        "state { supplyAssetsUsd borrowAssetsUsd collateralAssetsUsd utilization } } } }"
    ) % (token_address, chain_id)
    return _request(MORPHO, {"query": query})["data"]["markets"]["items"]


def morpho_positions(market_id):
    """Active borrowers of a Morpho market: health factor, debt and collateral in USD."""
    rows, skip = [], 0
    while True:
        query = (
            '{ marketPositions(first: 100, skip: %d, where: {marketUniqueKey_in: ["%s"], borrowShares_gte: 1}) '
            "{ items { healthFactor state { borrowAssetsUsd collateralUsd } } } }"
        ) % (skip, market_id)
        items = _request(MORPHO, {"query": query})["data"]["marketPositions"]["items"]
        rows += [r for r in items if r["state"]["borrowAssetsUsd"]]
        if len(items) < 100:
            return rows
        skip += 100


def usde_price_history(days=1100):
    """Daily USDe/USD prices [(unix_ts, price)], oldest first (DefiLlama, 400-day chunks)."""
    import time
    coin = "ethereum:0x4c9EDD5852cd905f086C759E8383e09bff1E68B3"
    now, pts = int(time.time()), {}
    for k in range(-(-days // 400)):
        start = now - (k + 1) * 400 * 86400
        data = _request(f"https://coins.llama.fi/chart/{coin}?start={start}&span=400&period=1d")
        for p in data["coins"][coin]["prices"]:
            pts[p["timestamp"]] = p["price"]
    return sorted(pts.items())
