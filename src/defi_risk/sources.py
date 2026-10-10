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


def morpho_markets_by_collateral(token_address, chain_id=1):
    query = (
        '{ markets(first: 50, where: { collateralAssetAddress_in: ["%s"], chainId_in: [%d] }) '
        "{ items { marketId lltv loanAsset { symbol } collateralAsset { symbol } "
        "oracle { address type } "
        "state { supplyAssetsUsd borrowAssetsUsd collateralAssetsUsd utilization } } } }"
    ) % (token_address, chain_id)
    return _request(MORPHO, {"query": query})["data"]["markets"]["items"]
