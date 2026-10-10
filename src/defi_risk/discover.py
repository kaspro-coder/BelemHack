"""Build the dependency graph of one or several Pendle PT positions from live public data.

Node ids are global (an address or a protocol name), so graphs of several positions merge
naturally: a node reached from two positions is a shared dependency.
"""
from collections import deque

from . import oracle as oracle_mod
from . import sources
from .graph import Graph, Node

CHAIN_NAMES = {1: "Ethereum"}


def _pt_address(market):
    return market["pt"].split("-", 1)[1]


def find_market(name, expiry_prefix=None, chain_id=1):
    candidates = [m for m in sources.pendle_active_markets(chain_id) if m["name"] == name]
    if expiry_prefix:
        candidates = [m for m in candidates if m["expiry"].startswith(expiry_prefix)]
    if not candidates:
        raise LookupError(f"no active Pendle market {name} {expiry_prefix or ''}")
    return max(candidates, key=lambda m: m["details"]["liquidity"])


DOCS = "docs.ethena.fi hedging-system/managing-risk-from-dependencies"
# Ethena names Bybit as an example CeFi venue. Binance/OKX come from a third-party
# research note of unknown date, so they are kept at lower confidence. No per-venue
# split is published, so we do not invent exposure numbers.
HEDGE_VENUES = {"Bybit": "documented", "Binance": "unverified", "OKX": "unverified",
                "Hyperliquid": "unverified"}
DOCUMENTED_INFRA = [
    ("oes:copper", "oes", "Copper (off-exchange settlement)"),
    ("feed:pyth", "price_feed", "Pyth (Ethena hedging price feed)"),
    ("feed:redstone", "price_feed", "Redstone (Ethena hedging price feed)"),
    ("infra:aws", "infra", "AWS (hedging system hosting)"),
]


def _add_ethena_hedge(g, issuer):
    supply = sources.usde_supply_usd()
    funding = sources.eth_funding_annualized()
    g.nodes[issuer].data["usde_supply_usd"] = supply
    for venue, conf in HEDGE_VENUES.items():
        vid = f"venue:{venue.lower()}"
        g.add_node(Node(vid, "perp_venue", venue, {"eth_funding_annualized": funding.get(venue)}))
        g.add_edge(issuer, vid, "hedges_short_perps_on", confidence=conf,
                   src=DOCS if conf == "documented" else "third-party note (4pillars), undated")
    for nid, kind, label in DOCUMENTED_INFRA:
        g.add_node(Node(nid, kind, label))
        g.add_edge(issuer, nid, "depends_on", confidence="documented", src=DOCS)


def _add_issuer(g, info, asset, chain):
    name = info.get("protocol")
    if not name:
        return
    slug = sources.llama_slug(name)
    issuer = f"issuer:{(slug or name).lower()}"
    if issuer not in g.nodes:
        data = {"pendle_protocol": name, "defillama_slug": slug}
        if slug:
            proto = sources.llama_protocol(slug)
            data["tvl_by_chain"] = {k: v for k, v in proto.get("currentChainTvls", {}).items()
                                    if "-" not in k and k not in ("borrowed", "staking", "pool2")}
        g.add_node(Node(issuer, "issuer", name, data))
        g.add_edge(issuer, chain, "settles_on", src="DefiLlama")
        if name.lower() == "ethena":
            _add_ethena_hedge(g, issuer)
    g.add_edge(asset, issuer, "issued_by", src="Pendle market metadata")


def _add_feeds(g, oracle_id, feeds, relation):
    for f in feeds.values():
        if f["kind"] == "scaling":
            continue  # a decimals adapter, not a source of price
        fid = f"feed:{f['address'].lower()}"
        g.add_node(Node(fid, "price_feed", f["description"], {k: v for k, v in f.items() if k != "address"}))
        g.add_edge(oracle_id, fid, relation, src="on-chain read")


def _add_lending(g, m, pos, amm):
    lend = f"lending:morpho:{m['marketId']}"
    st = m["state"]
    g.add_node(Node(lend, "lending", f"Morpho {m['collateralAsset']['symbol']}/{m['loanAsset']['symbol']}", {
        "lltv": int(m["lltv"]) / 1e18,
        "collateral_usd": st["collateralAssetsUsd"],
        "borrow_usd": st["borrowAssetsUsd"],
        "utilization": st["utilization"],
        "market_id": m["marketId"],
    }))
    g.add_edge(lend, pos, "holds_as_collateral", st["collateralAssetsUsd"])
    g.add_edge(lend, amm, "liquidates_through", st["collateralAssetsUsd"])
    g.add_node(Node("protocol:morpho-blue", "protocol", "Morpho Blue"))
    g.add_edge(lend, "protocol:morpho-blue", "runs_on")

    loan = f"stable:{m['loanAsset']['address'].lower()}"
    g.add_node(Node(loan, "stablecoin", m["loanAsset"]["symbol"]))
    g.add_edge(lend, loan, "lends")

    # Morpho lists every vault allowed to supply; keep only those with money actually in.
    market_supply = st["supplyAssetsUsd"] or 0
    for v in m.get("supplyingVaults") or []:
        vault = sources.morpho_vault(v["address"])
        alloc = next((a["supplyAssetsUsd"] or 0 for a in vault["state"]["allocation"]
                      if a["market"]["marketId"] == m["marketId"]), 0)
        if alloc < 10_000:
            continue
        vid = f"vault:{v['address'].lower()}"
        if vid not in g.nodes:
            g.add_node(Node(vid, "vault", v["name"], {"total_assets_usd": vault["state"]["totalAssetsUsd"],
                                                      "allocations": {}}))
        g.nodes[vid].data["allocations"][m["marketId"]] = {
            "market": g.nodes[lend].label, "usd": alloc,
            "share_of_vault": alloc / (vault["state"]["totalAssetsUsd"] or 1),
            "share_of_market_supply": alloc / market_supply if market_supply else None,
        }
        g.add_edge(vid, lend, "lends_into", alloc, src="Morpho vault allocation")

    oid = f"oracle:{m['oracle']['address'].lower()}"
    if oid not in g.nodes:
        d = oracle_mod.describe(m["oracle"]["address"], m["loanAsset"]["decimals"], m["collateralAsset"]["decimals"])
        label = {"MetaOracleDeviationTimelock (primary/backup)": "Oracle: primary/backup + challenge",
                 "MorphoChainlinkOracleV2": "Oracle: Morpho Chainlink V2"}.get(d["pattern"], "Oracle: unknown type")
        g.add_node(Node(oid, "oracle", label, {"address": m["oracle"]["address"], "morpho_type": m["oracle"]["type"],
                                               **{k: v for k, v in d.items() if not k.endswith("feeds") and k != "feeds"}}))
        if "primary_feeds" in d:
            _add_feeds(g, oid, d["primary_feeds"], "primary_reads")
            _add_feeds(g, oid, d["backup_feeds"], "backup_reads")
        elif "feeds" in d:
            _add_feeds(g, oid, d["feeds"], "reads")
    g.add_edge(lend, oid, "priced_by")


def discover(name, expiry_prefix=None, chain_id=1, g=None):
    """Add one PT position and everything it depends on to `g` (a new graph if None)."""
    g = g if g is not None else Graph()
    market = find_market(name, expiry_prefix, chain_id)
    data = sources.pendle_market_data(market["address"], chain_id)
    info = sources.pendle_market_info(market["address"], chain_id)
    pt = _pt_address(market)

    pos = f"pt:{pt}"
    g.add_node(Node(pos, "position", f"PT-{name} ({market['expiry'][:10]})", {"pt": pt, "market": market["address"]}))

    chain = f"chain:{chain_id}"
    g.add_node(Node(chain, "chain", CHAIN_NAMES.get(chain_id, str(chain_id))))
    g.add_edge(pos, chain, "settles_on")

    amm = f"amm:{market['address']}"
    g.add_node(Node(amm, "amm", f"Pendle pool PT-{name}", {
        "liquidity_usd": data["liquidity"]["usd"],
        "total_pt": data["totalPt"],
        "total_sy": data["totalSy"],
        "pt_discount": data["ptDiscount"],
        "implied_apy": data["impliedApy"],
        "volume_24h_usd": data["tradingVolume"]["usd"],
    }))
    g.add_edge(pos, amm, "exits_through", data["liquidity"]["usd"])
    g.add_node(Node("protocol:pendle", "protocol", "Pendle"))
    g.add_edge(amm, "protocol:pendle", "runs_on")
    # Pendle quotes also fill off-chain limit orders that market makers can pull at any time.
    g.add_node(Node("liquidity:pendle-limit-orders", "offchain", "Pendle limit orders (off-chain makers)"))
    g.add_edge(pos, "liquidity:pendle-limit-orders", "exits_through", confidence="measured",
               src="Pendle swap quote used 8 limit-order fills on PT-sUSDe")

    asset = f"asset:{market['underlyingAsset']}"
    g.add_node(Node(asset, "asset", info["underlyingAsset"]["symbol"], {"underlying_apy": data["underlyingApy"]}))
    g.add_edge(pos, asset, "redeems_into")
    _add_issuer(g, info, asset, chain)

    for m in sources.morpho_markets_by_collateral(pt, chain_id):
        if (m["state"]["collateralAssetsUsd"] or 0) < 10_000:
            continue  # empty markets add noise, not risk
        _add_lending(g, m, pos, amm)
    return g


def discover_many(positions, chain_id=1):
    """positions: [(name, expiry_prefix), ...] -> one merged graph."""
    g = Graph()
    for name, expiry in positions:
        discover(name, expiry, chain_id, g)
    return g


# Edges that point from a dependent INTO the position side: a lending market holds the PT,
# a vault lends into the market. Walking them backwards reaches what can hurt the position.
REVERSE = {"holds_as_collateral", "lends_into"}


def reach(g, start):
    seen, todo = {start}, deque([start])
    while todo:
        n = todo.popleft()
        for e in g.edges:
            nxt = e.target if e.source == n and e.relation not in REVERSE else (
                e.source if e.target == n and e.relation in REVERSE else None)
            if nxt and nxt not in seen and g.nodes[nxt].kind != "position":
                seen.add(nxt)
                todo.append(nxt)
    return seen - {start}


def contagion_paths(g):
    """Vaults that lend into the lending markets of two or more positions.

    A loss in one market hits the vault's depositors; if they withdraw, the vault pulls
    its supply from the other markets, which can drain their liquidity.
    """
    owner = {e.source: e.target for e in g.edges if e.relation == "holds_as_collateral"}
    out = []
    for v in (n for n in g.nodes.values() if n.kind == "vault"):
        legs = [{"market_id": mid, "position": g.nodes[owner[f"lending:morpho:{mid}"]].label, **a}
                for mid, a in v.data["allocations"].items() if f"lending:morpho:{mid}" in owner]
        if len({l["position"] for l in legs}) > 1:
            out.append({"vault": v.label, "total_assets_usd": v.data["total_assets_usd"], "legs": legs})
    return out


def shared_dependencies(g):
    """{node_id: [position ids]} for every node that two or more positions depend on."""
    positions = [n.id for n in g.nodes.values() if n.kind == "position"]
    hits = {}
    for p in positions:
        for n in reach(g, p):
            hits.setdefault(n, []).append(p)
    return {n: ps for n, ps in hits.items() if len(ps) > 1}
