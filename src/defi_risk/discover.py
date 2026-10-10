"""Build the dependency graph of a Pendle PT position from live public data."""
from . import sources
from .graph import Graph, Node

CHAIN_NAMES = {1: "Ethereum"}

# Hand-curated: Pendle market name -> issuer protocol (DefiLlama slug).
# Pendle's API does not expose the issuer, so this is the one non-automatic link.
ISSUERS = {"sUSDe": ("ethena", "Ethena")}


def _pt_address(market):
    return market["pt"].split("-", 1)[1]


def find_market(name, expiry_prefix=None, chain_id=1):
    candidates = [m for m in sources.pendle_active_markets(chain_id) if m["name"] == name]
    if expiry_prefix:
        candidates = [m for m in candidates if m["expiry"].startswith(expiry_prefix)]
    if not candidates:
        raise LookupError(f"no active Pendle market {name} {expiry_prefix or ''}")
    return max(candidates, key=lambda m: m["details"]["liquidity"])


def discover(name, expiry_prefix=None, chain_id=1):
    market = find_market(name, expiry_prefix, chain_id)
    data = sources.pendle_market_data(market["address"], chain_id)
    pt = _pt_address(market)
    g = Graph()

    pos = f"pt:{pt}"
    g.add_node(Node(pos, "position", f"PT-{name} ({market['expiry'][:10]})", {"pt": pt}))

    chain = f"chain:{chain_id}"
    g.add_node(Node(chain, "chain", CHAIN_NAMES.get(chain_id, str(chain_id))))
    g.add_edge(pos, chain, "settles_on")

    amm = f"amm:{market['address']}"
    g.add_node(Node(amm, "amm", "Pendle PT market", {
        "liquidity_usd": data["liquidity"]["usd"],
        "total_pt": data["totalPt"],
        "total_sy": data["totalSy"],
        "pt_discount": data["ptDiscount"],
        "implied_apy": data["impliedApy"],
        "volume_24h_usd": data["tradingVolume"]["usd"],
    }))
    g.add_edge(pos, amm, "exits_through", data["liquidity"]["usd"])

    asset = f"asset:{market['underlyingAsset']}"
    g.add_node(Node(asset, "asset", name, {"underlying_apy": data["underlyingApy"]}))
    g.add_edge(pos, asset, "redeems_into")

    if name in ISSUERS:
        slug, label = ISSUERS[name]
        proto = sources.llama_protocol(slug)
        issuer = f"issuer:{slug}"
        g.add_node(Node(issuer, "issuer", label, {
            "tvl_by_chain": proto.get("currentChainTvls", {}),
        }))
        g.add_edge(asset, issuer, "issued_by")
        g.add_edge(issuer, chain, "settles_on")

    for m in sources.morpho_markets_by_collateral(pt, chain_id):
        lend = f"lending:morpho:{m['marketId']}"
        st = m["state"]
        g.add_node(Node(lend, "lending", f"Morpho {m['collateralAsset']['symbol']}/{m['loanAsset']['symbol']}", {
            "lltv": int(m["lltv"]) / 1e18,
            "collateral_usd": st["collateralAssetsUsd"],
            "borrow_usd": st["borrowAssetsUsd"],
            "utilization": st["utilization"],
        }))
        # The lending market holds the PT as collateral: its liquidations hit the AMM.
        g.add_edge(lend, pos, "holds_as_collateral", st["collateralAssetsUsd"])
        g.add_edge(lend, amm, "liquidates_through", st["collateralAssetsUsd"])
        oracle = f"oracle:{m['oracle']['address'].lower()}"
        g.add_node(Node(oracle, "oracle", m["oracle"]["address"], {"type": m["oracle"]["type"]}))
        g.add_edge(lend, oracle, "priced_by")

    return g
