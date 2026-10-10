"""On-chain description of a Morpho market oracle (read-only eth_call).

Recognises the three kinds met on Pendle PT markets:
  * Steakhouse MetaOracleDeviationTimelock: a primary and a backup oracle, a deviation
    threshold, and a permissionless challenge that switches to the backup after a timelock;
  * MorphoChainlinkOracleV2: price = base feeds / quote feeds (+ optional ERC4626 vaults);
  * feeds: Chainlink-style aggregators, or Pendle linear-discount feeds whose price only
    depends on time to maturity (they never look at the market).
Selectors were computed with `cast sig` and checked against the live contracts.
"""
from . import sources

SEL = {
    "primaryOracle": "bd8f238e", "backupOracle": "836efd31", "currentOracle": "2289445e",
    "isChallenged": "9df4d0fe", "primaryPrice": "362a07ae", "backupPrice": "ad891006",
    "getDeviation": "89ab3532", "deviationThreshold": "d94ad837",
    "challengeTimelockDuration": "498e8b6e", "healingTimelockDuration": "d83ed440",
    "BASE_FEED_1": "f50a4718", "BASE_FEED_2": "dc53858c",
    "QUOTE_FEED_1": "56095e11", "QUOTE_FEED_2": "acfbd39e",
    "BASE_VAULT": "eaa2d7b4", "QUOTE_VAULT": "2e6f20a6",
    "baseDiscountPerYear": "598e5451", "maturity": "204f83f9",
    "description": "7284e416", "price": "a035b1fe",
}
FEEDS = ("BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2")


def _call(to, sel):
    r = sources.live_call(to, "0x" + sel)
    return r.get("result")


def _uint(res):
    return int(res, 16) if res and res != "0x" else None


def _addr(res):
    return "0x" + res[-40:] if res and res != "0x" and int(res, 16) else None


def _text(res):
    if not res or len(res) < 130:
        return None
    n = int(res[66:130], 16)
    return bytes.fromhex(res[130:130 + n * 2]).decode(errors="ignore")


def describe_feed(address):
    """What a price feed is: a linear-discount PT feed, or a described aggregator."""
    discount = _uint(_call(address, SEL["baseDiscountPerYear"]))
    if discount is not None:
        return {"address": address, "kind": "linear_discount",
                "description": f"Linear discount {discount / 1e16:.1f}%/yr to maturity (ignores the market)",
                "discount_per_year": discount / 1e18, "maturity": _uint(_call(address, SEL["maturity"])),
                "market_sensitive": False}
    desc = _text(_call(address, SEL["description"]))
    if desc and desc.lower().startswith("dummy"):
        return {"address": address, "kind": "scaling", "description": desc, "market_sensitive": False}
    return {"address": address, "kind": "aggregator", "description": desc or "unlabelled feed",
            "market_sensitive": True}


def _chainlink_v2(address):
    feeds = {}
    for name in FEEDS:
        a = _addr(_call(address, SEL[name]))
        if a:
            feeds[name] = describe_feed(a)
    for name in ("BASE_VAULT", "QUOTE_VAULT"):
        a = _addr(_call(address, SEL[name]))
        if a:
            feeds[name] = {"address": a, "kind": "erc4626_vault", "description": "ERC4626 vault rate",
                           "market_sensitive": False}
    return feeds


def describe(address, loan_decimals=6, collateral_decimals=18):
    """Plain dict describing a Morpho oracle and every feed it reads."""
    scale = 10 ** (36 + loan_decimals - collateral_decimals)
    primary = _addr(_call(address, SEL["primaryOracle"]))
    backup = _addr(_call(address, SEL["backupOracle"]))
    if primary and backup:
        pf, bf = _chainlink_v2(primary), _chainlink_v2(backup)
        names = lambda fs: [f["description"] for f in fs.values()]
        return {
            "pattern": "MetaOracleDeviationTimelock (primary/backup)",
            "primary": primary, "backup": backup,
            "active": "primary" if _addr(_call(address, SEL["currentOracle"])) == primary else "backup",
            "challenged": _uint(_call(address, SEL["isChallenged"])) == 1,
            "price": _uint(_call(address, SEL["price"])) / scale,
            "primary_price": _uint(_call(address, SEL["primaryPrice"])) / scale,
            "backup_price": _uint(_call(address, SEL["backupPrice"])) / scale,
            "deviation": _uint(_call(address, SEL["getDeviation"])) / 1e18,
            "threshold": _uint(_call(address, SEL["deviationThreshold"])) / 1e18,
            "timelock_hours": _uint(_call(address, SEL["challengeTimelockDuration"])) / 3600,
            "healing_hours": _uint(_call(address, SEL["healingTimelockDuration"])) / 3600,
            "primary_feeds": pf, "backup_feeds": bf,
            "primary_market_sensitive": any(f["market_sensitive"] for f in pf.values()),
            "backup_market_sensitive": any(f["market_sensitive"] for f in bf.values()),
            "primary_reads": names(pf), "backup_reads": names(bf),
        }
    feeds = _chainlink_v2(address)
    if feeds:
        return {"pattern": "MorphoChainlinkOracleV2", "price": (_uint(_call(address, SEL["price"])) or 0) / scale,
                "feeds": feeds, "market_sensitive": any(f["market_sensitive"] for f in feeds.values()),
                "reads": [f["description"] for f in feeds.values()]}
    return {"pattern": "unknown", "price": (_uint(_call(address, SEL["price"])) or 0) / scale}
