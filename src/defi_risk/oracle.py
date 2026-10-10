"""On-chain analysis of a Morpho market oracle (read-only eth_call).

Handles the primary/backup oracle pattern: two Morpho price oracles, a challenge
timelock, and automatic failover. Selectors were resolved from the contract bytecode
against the public signature database, then checked by calling them.
"""
from . import sources

RPC = "https://ethereum-rpc.publicnode.com"
SEL = {
    "primaryOracle": "bd8f238e", "backupOracle": "836efd31", "currentOracle": "2289445e",
    "isChallenged": "9df4d0fe", "primaryPrice": "362a07ae", "backupPrice": "ad891006",
    "getDeviation": "89ab3532", "challengeTimelockDuration": "498e8b6e",
    "BASE_FEED_1": "f50a4718", "BASE_FEED_2": "dc53858c",
    "QUOTE_FEED_1": "56095e11", "QUOTE_FEED_2": "acfbd39e",
}
DESCRIPTION = "7284e416"
FEEDS = ("BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2")


def _call(to, sel):
    r = sources._request(RPC, {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                               "params": [{"to": to, "data": "0x" + sel}, "latest"]})
    return r.get("result")


def _addr(res):
    return "0x" + res[-40:] if res and int(res, 16) else None


def _text(res):
    if not res or len(res) < 130:
        return None
    n = int(res[66:130], 16)
    return bytes.fromhex(res[130:130 + n * 2]).decode(errors="ignore")


def _feeds(oracle):
    out = {}
    for name in FEEDS:
        a = _addr(_call(oracle, SEL[name]))
        if a:
            out[name] = {"address": a, "description": _text(_call(a, DESCRIPTION))}
    return out


def analyse(oracle, loan_decimals=6, collateral_decimals=18):
    """Return a plain dict describing the oracle, or None if it is not primary/backup."""
    primary = _addr(_call(oracle, SEL["primaryOracle"]))
    backup = _addr(_call(oracle, SEL["backupOracle"]))
    if not primary or not backup:
        return None
    scale = 10 ** (36 + loan_decimals - collateral_decimals)
    price = lambda s: int(_call(oracle, SEL[s]), 16) / scale
    pf, bf = _feeds(primary), _feeds(backup)
    return {
        "pattern": "primary/backup with challenge timelock",
        "primary": primary, "backup": backup,
        "active": "primary" if _addr(_call(oracle, SEL["currentOracle"])) == primary else "backup",
        "challenged": int(_call(oracle, SEL["isChallenged"]), 16) == 1,
        "primary_price": price("primaryPrice"), "backup_price": price("backupPrice"),
        "deviation": int(_call(oracle, SEL["getDeviation"]), 16) / 1e18,
        "timelock_hours": int(_call(oracle, SEL["challengeTimelockDuration"]), 16) / 3600,
        "primary_feeds": pf, "backup_feeds": bf,
        # The primary reads fewer feeds: it has no USDe/USD leg, so it cannot see a USDe depeg.
        "primary_sees_depeg": any("USDe" in (f["description"] or "") for f in pf.values()),
        "backup_sees_depeg": any("USDe" in (f["description"] or "") for f in bf.values()),
    }
