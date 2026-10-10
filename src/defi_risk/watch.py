"""Live watch of the signals the fork simulations identified (read-only, Ethereum mainnet).

Usage:
  python -m defi_risk.watch            # one check, prints and writes dashboard/status.json
  python -m defi_risk.watch --loop 60  # every 60 seconds

Each signal maps to a simulated outcome:
  * PT-sUSDe: the oracle deviation between primary and backup. Above the 0.75% threshold anyone
    can start the 16 h challenge; when it is accepted, liquidations make the position unsellable.
  * PT-reUSD: re.xyz's share price. A 2% write-down saturated the pool within one 15-minute TWAP.
  * PT-sUSDS: Smokehouse USDT's money in the PT-sUSDS/USDT market. A run on that vault took the
    market to 100% utilisation and the borrow rate from 4% to 18%.
  * Both Morpho markets: the largest borrowers' distance to liquidation.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import sources

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "dashboard" / "status.json"
STATE = ROOT / "data" / "watch_state.json"

SUSDE_ORACLE = "0xF8b29e7E9c00CE531434775f7923CC9fbCa01b08"
SUSDS_ORACLE = "0x3464a61A68C486241FE07201C913F055Bdce35BF"
SUSDS_OJO = "0x16bdf4c1a1fbd0d3a181dcee4141bb106e22b002"
USDE_FEED = "0xa569d910839Ae8865Da8F8e70FfFb0cBA869F961"
REUSD_SHARE_PRICE = "0xd1D104a7515989ac82F1AFDa15a23650411b05B8"
SMOKEHOUSE_USDT = "0xa0804346780b4c2e3be118ac957d1db82f9d7484"
MARKETS = {
    "PT-sUSDe/USDC": "0x5613b170ded221c588b6e9637b910f49e5508680ceede207f44aa72e5c46cb05",
    "PT-reUSD/USDC": "0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64",
    "PT-sUSDS/USDT": "0x0367161b7cb23dfd03747dd3815d1c445b0437b648a6d50346249c6e7b92ff1b",
}
SEL = {"getDeviation": "89ab3532", "deviationThreshold": "d94ad837", "isChallenged": "9df4d0fe",
       "challengeExpiresAt": "ccc1b9cd", "currentOracle": "2289445e", "primaryOracle": "bd8f238e",
       "latestRoundData": "feaf968c", "getSharePrice": "5b1dac60",
       "FEED_1": "d84bd024", "FEED_2": "41299f94"}


def _call(to, sel):
    r = sources._request(sources.rpc_url(), {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                             "params": [{"to": to, "data": "0x" + sel}, "latest"]})
    if "result" not in r:
        raise RuntimeError(f"eth_call {to} {sel}: {r.get('error')}")
    return r["result"]


def _uint(to, sel, word=0):
    res = _call(to, SEL[sel])[2:]
    return int(res[64 * word:64 * (word + 1)], 16)


def _signal(name, level, value, meaning, action):
    return {"name": name, "level": level, "value": value, "meaning": meaning, "action": action}


def susde_signals():
    dev = _uint(SUSDE_ORACLE, "getDeviation") / 1e18
    thr = _uint(SUSDE_ORACLE, "deviationThreshold") / 1e18
    usde = _uint(USDE_FEED, "latestRoundData", 1) / 1e8
    challenged = _uint(SUSDE_ORACLE, "isChallenged") == 1
    on_backup = _call(SUSDE_ORACLE, SEL["currentOracle"])[-40:] != _call(SUSDE_ORACLE, SEL["primaryOracle"])[-40:]
    if on_backup:
        lvl, act = "red", "Oracle already on backup: liquidations are live, the pool may be saturated. Exit if anything is left."
    elif challenged:
        left = (_uint(SUSDE_ORACLE, "challengeExpiresAt") - time.time()) / 3600
        lvl, act = "red", f"Challenge running, {max(left, 0):.1f} h before the switch. Exit now, inside the window."
    elif dev > thr:
        lvl, act = "red", "Deviation above threshold: anyone can start the 16 h challenge. Prepare to exit."
    elif dev > thr / 2:
        lvl, act = "amber", "Deviation above half the threshold: watch closely."
    else:
        lvl, act = "green", "No action."
    return [_signal("PT-sUSDe oracle deviation", lvl,
                    f"{dev:.3%} (threshold {thr:.2%}), USDe ${usde:.4f}",
                    "Primary vs backup oracle. The backup reads Chainlink USDe/USD; the primary does not.", act)]


def susds_signals():
    dev = _uint(SUSDS_ORACLE, "getDeviation") / 1e18
    thr = _uint(SUSDS_ORACLE, "deviationThreshold") / 1e18
    challenged = _uint(SUSDS_ORACLE, "isChallenged") == 1
    if challenged or dev > thr:
        lvl, act = "red", "USDS deviation above threshold or challenge running: on the fork a 2% USDS depeg made the position unsellable. Exit inside the 16 h."
    elif dev > thr / 2:
        lvl, act = "amber", "Deviation above half the threshold: watch closely."
    else:
        lvl, act = "green", "No action."
    out = [_signal("PT-sUSDS oracle deviation", lvl, f"{dev:.3%} (threshold {thr:.2%})",
                   "Primary vs backup; the backup adds Chainlink USDS/USD.", act)]
    # Ojo returns min(Pendle TWAP, conservative feed): the gap is the cushion against market panic.
    f1 = "0x" + _call(SUSDS_OJO, SEL["FEED_1"])[-40:]
    f2 = "0x" + _call(SUSDS_OJO, SEL["FEED_2"])[-40:]
    twap, floor = _uint(f1, "latestRoundData", 1) / 1e18, _uint(f2, "latestRoundData", 1) / 1e18
    gap = twap / floor - 1
    lvl = "green" if gap > 0.005 else "amber" if gap > 0 else "red"
    out.append(_signal("PT-sUSDS market cushion", lvl, f"pool TWAP {twap:.4f} vs floor {floor:.4f} ({gap:+.2%})",
                       "The oracle only follows the market once the TWAP falls below the floor.",
                       "No action." if lvl == "green" else "Market price at the floor: the next sell-off reaches Morpho."))
    return out


def reusd_signals(state):
    price = _uint(REUSD_SHARE_PRICE, "getSharePrice") / 1e18
    peak = max(state.get("reusd_peak", 0.0), price)
    state["reusd_peak"] = peak
    drop = 1 - price / peak if peak else 0.0
    if drop >= 0.01:
        lvl, act = "red", "Write-down of 1% or more: a 2% cut saturated the pool on the fork. Automated exit within 15 min."
    elif drop > 0.001:
        lvl, act = "amber", "The share price fell: check re.xyz announcements."
    else:
        lvl, act = "green", "No action."
    return [_signal("PT-reUSD issuer share price", lvl, f"{price:.6f} ({drop:.3%} below the highest seen)",
                    "re.xyz's own NAV feed, read by the SY exchange rate and passed to the oracle.", act)]


def lender_signals():
    out = []
    q = ('{ vaultByAddress(address: "%s", chainId: 1) { state { totalAssetsUsd allocation { supplyAssetsUsd '
         'market { marketId } } } } }') % SMOKEHOUSE_USDT
    v = sources._request(sources.MORPHO, {"query": q})["data"]["vaultByAddress"]["state"]
    alloc = next((a["supplyAssetsUsd"] for a in v["allocation"] if a["market"]["marketId"] == MARKETS["PT-sUSDS/USDT"]), 0)
    q = ('{ markets(where: { uniqueKey_in: ["%s"] }) { items { state { utilization borrowApy } } } }'
         % MARKETS["PT-sUSDS/USDT"])
    try:
        st = sources._request(sources.MORPHO, {"query": q})["data"]["markets"]["items"][0]["state"]
    except Exception:
        q = q.replace("uniqueKey_in", "marketId_in")
        st = None
    util = st["utilization"] if st else None
    lvl = "green"
    act = "No action."
    if util is not None and util > 0.99:
        lvl, act = "red", "Market at 100%: lenders are locked, PT-sUSDS borrowers face a rate spike and may dump PT."
    elif util is not None and util > 0.95:
        lvl, act = "amber", "Utilisation above 95%: close to the vault-run state simulated on the fork."
    out.append(_signal("PT-sUSDS lender concentration", lvl,
                       f"Smokehouse USDT ${alloc / 1e6:.2f}M in PT-sUSDS/USDT" + (f", utilisation {util:.1%}" if util is not None else ""),
                       "Same vault lends to PT-reUSD: a reUSD loss can trigger a run that drains this market.", act))
    return out


def borrower_signals():
    out = []
    for name, mid in MARKETS.items():
        q = ('{ marketPositions(first: 5, orderBy: BorrowShares, orderDirection: Desc, where: {marketUniqueKey_in: ["%s"], '
             'borrowShares_gte: 1}) { items { healthFactor state { borrowAssetsUsd } } } }') % mid
        try:
            items = sources._request(sources.MORPHO, {"query": q})["data"]["marketPositions"]["items"]
        except Exception:
            items = sources.morpho_positions(mid)
        items = [i for i in items if i["healthFactor"]]
        if not items:
            continue
        worst = min(items, key=lambda i: i["healthFactor"])
        dist = 1 - 1 / worst["healthFactor"]
        lvl = "red" if dist < 0.005 else "amber" if dist < 0.02 else "green"
        out.append(_signal(f"{name} largest borrowers", lvl,
                           f"${worst['state']['borrowAssetsUsd'] / 1e6:.2f}M debt {dist:.2%} from liquidation",
                           "Closest large borrower to liquidation: the first domino of a cascade.",
                           "Small move can start liquidations." if lvl != "green" else "No action."))
    return out


def check():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    signals = []
    for fn in (susde_signals, susds_signals, lambda: reusd_signals(state), lender_signals, borrower_signals):
        try:
            signals += fn()
        except Exception as e:  # one broken source must not hide the others
            signals.append(_signal(getattr(fn, "__name__", "signal"), "unknown", "-", f"read failed: {e}", "Check manually."))
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state))
    status = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "signals": signals}
    STATUS.write_text(json.dumps(status, indent=1))
    return status


def main():
    loop = int(sys.argv[sys.argv.index("--loop") + 1]) if "--loop" in sys.argv else 0
    while True:
        s = check()
        print(f"\n{s['checked_at']}")
        for x in s["signals"]:
            print(f"  [{x['level'].upper():7}] {x['name']}: {x['value']}\n            -> {x['action']}")
        if not loop:
            break
        time.sleep(loop)


if __name__ == "__main__":
    main()
