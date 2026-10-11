"""Live state of the LOCAL Anvil fork, for manual demo incidents.

Usage: python -m defi_risk.forkwatch --loop 3
Reads the fork every few seconds and writes dashboard/fork_status.json, which the page shows.
Unlike watch.py (mainnet), this follows whatever you do to the fork with cast commands:
mocked prices, oracle challenges, time warps, liquidations, PT dumps.
"""
import json
import math
import re
import sys
import time
from pathlib import Path

from . import sources

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "fork_status.json"
FORK = __import__("os").environ.get("FORK_RPC", "http://127.0.0.1:8545")
FORK_START = 1791666623  # timestamp of the pinned block, to show how far the demo warped time

TOKENS = [
    {"name": "PT-sUSDe", "pool": "0x47ad2cd1dd15739a7a035b9d3b7828d916fef77e", "pt_decimals": 18,
     "markets": {"USDC": ("0x5613b170ded221c588b6e9637b910f49e5508680ceede207f44aa72e5c46cb05", "sUSDe_USDC")},
     "meta_oracle": "0xF8b29e7E9c00CE531434775f7923CC9fbCa01b08",
     "feed": ("USDe/USD", "0xa569d910839ae8865da8f8e70fffb0cba869f961", "chainlink"),
     "asset_decimals": 18, "asset_priced_by_feed": True},
    {"name": "PT-reUSD", "pool": "0x13285bcbc27f92b47b4edb99d744c07b48c977c0", "pt_decimals": 6,
     "markets": {"USDC": ("0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64", "reUSD_USDC"),
                 "USDT": ("0x6acd18854e43f93f5a90446004c35c72a68af1ad99f08cb247782ce6457914ca", "reUSD_USDT")},
     "meta_oracle": None,
     "feed": ("reUSD share price", "0xd1D104a7515989ac82F1AFDa15a23650411b05B8", "share_price"),
     "asset_decimals": 6, "asset_priced_by_feed": False, "share_price_ref": 1.1061507730636588},
    {"name": "PT-sUSDS", "pool": "0x9c560ebaf78e596cbcc27411d633a74d628dd7dc", "pt_decimals": 18,
     "markets": {"USDC": ("0x22fe4c688161863c73571a2b8db65cc11a4a6bceee4f0dea4aa83e4b784f1bd9", "sUSDS_USDC"),
                 "USDT": ("0x0367161b7cb23dfd03747dd3815d1c445b0437b648a6d50346249c6e7b92ff1b", "sUSDS_USDT"),
                 "USDS": ("0x9a8dab6de1059e6dc66c34b358764b70effb289e514e237f3161ffb09eaaf24f", "sUSDS_USDS")},
     "meta_oracle": "0x3464a61A68C486241FE07201C913F055Bdce35BF",
     "feed": ("USDS/USD", "0xff30586cd0f29ed462364c7e81375fc0c71219b1", "chainlink"),
     "asset_decimals": 18, "asset_priced_by_feed": True},
]
MORPHO = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
FUND = "0x00000000000000000000000000000000000BE1E3"
SELLER = "0x17d9d652E2FD969cDfdb4eC7a71137BDd9aada95"  # DemoSeller as first deployed by Anvil's dev account
FUND_PT = 1_000_000
SEL = {"position": "93c52062", "market": "5c60e39a", "idToMarketParams": "2c3c9157", "price": "a035b1fe",
       "decimals": "313ce567", "_storage": "c3fb90d6", "getDeviation": "89ab3532",
       "deviationThreshold": "d94ad837", "isChallenged": "9df4d0fe", "challengeExpiresAt": "ccc1b9cd",
       "isPrimary": "3682152b", "latestRoundData": "feaf968c", "getSharePrice": "5b1dac60",
       "sell": "6c197ff5", "exchangeRate": "3ba0b9a9", "readTokens": "2c8ce6bc", "paused": "5c975abb",
       "balanceOf": "70a08231", "allowance": "dd62ed3e"}


def _rpc(method, params):
    return sources._request(FORK, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def _call(to, data):
    r = _rpc("eth_call", [{"to": to, "data": data}, "latest"])
    if "result" not in r:
        raise RuntimeError(r.get("error"))
    return r["result"][2:]


def _words(hexdata):
    return [int(hexdata[i:i + 64], 16) for i in range(0, len(hexdata), 64)]


def _borrowers():
    src = (ROOT / "sim" / "src" / "Borrowers.sol").read_text()
    out = {}
    for name, body in re.findall(r"function (\w+)\(\).*?\{(.*?)\n    \}", src, re.S):
        out[name] = re.findall(r"0x[0-9a-fA-F]{40}", body)
    return out


BORROWERS = _borrowers()


def _market(mid, key):
    params = _words(_call(MORPHO, "0x" + SEL["idToMarketParams"] + mid[2:]))
    loan, oracle, lltv = "0x%040x" % params[0], "0x%040x" % params[2], params[4]
    dec = _words(_call(loan, "0x" + SEL["decimals"]))[0]
    tsa, tss, tba, tbs = _words(_call(MORPHO, "0x" + SEL["market"] + mid[2:]))[:4]
    price = _words(_call(oracle, "0x" + SEL["price"]))[0]
    unhealthy, debt_total, debt_risk, worst = 0, 0.0, 0.0, None
    for b in BORROWERS.get(key, []):
        _, shares, coll = _words(_call(MORPHO, "0x" + SEL["position"] + mid[2:] + b[2:].lower().rjust(64, "0")))
        if not shares:
            continue
        debt = (shares * (tba + 1) + (tbs + 10**6) - 1) // (tbs + 10**6)
        max_borrow = coll * price // 10**36 * lltv // 10**18
        hf = max_borrow / debt if debt else math.inf
        debt_usd = debt / 10**dec
        debt_total += debt_usd
        if hf < 1:
            unhealthy += 1
            debt_risk += debt_usd
        dist = 1 - 1 / hf if hf > 0 else -1
        if worst is None or dist < worst:
            worst = dist
    return {"oracle_price": price, "unhealthy": unhealthy, "borrowers": len(BORROWERS.get(key, [])),
            "debt_usd": debt_total, "debt_at_risk_usd": debt_risk, "closest_distance": worst,
            "utilization": tba / tsa if tsa else 0}


def _token(t, now):
    out = {"name": t["name"], "markets": {}}
    label, addr, kind = t["feed"]
    if kind == "chainlink":
        out["feed"] = {"label": label, "value": _words(_call(addr, "0x" + SEL["latestRoundData"]))[1] / 1e8}
    else:
        out["feed"] = {"label": label, "value": _words(_call(addr, "0x" + SEL["getSharePrice"]))[0] / 1e18}
    if t["meta_oracle"]:
        o = t["meta_oracle"]
        expires = _words(_call(o, "0x" + SEL["challengeExpiresAt"]))[0]
        out["oracle"] = {
            "active": "primary" if _words(_call(o, "0x" + SEL["isPrimary"]))[0] else "backup",
            "deviation": _words(_call(o, "0x" + SEL["getDeviation"]))[0] / 1e18,
            "threshold": _words(_call(o, "0x" + SEL["deviationThreshold"]))[0] / 1e18,
            "challenged": bool(_words(_call(o, "0x" + SEL["isChallenged"]))[0]),
            "challenge_hours_left": max(0.0, (expires - now) / 3600) if expires else None,
        }
    for loan, (mid, key) in t["markets"].items():
        out["markets"][loan] = _market(mid, key)
    total_pt, total_sy, ln_rate = _words(_call(t["pool"], "0x" + SEL["_storage"]))[:3]
    out["pool"] = {"implied_apy": math.exp(ln_rate / 1e18) - 1, "pt_reserve": total_pt / 10**t["pt_decimals"],
                   "sy_reserve": total_sy / 1e18}
    return out


def _quote(pool, amount):
    """SY the pool would pay the fund for `amount` PT right now, or None if it refuses.
    An eth_call: the sale is simulated by the node, nothing is executed."""
    data = "0x" + SEL["sell"] + pool[2:].lower().rjust(64, "0") + hex(amount)[2:].rjust(64, "0")
    r = _rpc("eth_call", [{"from": FUND, "to": SELLER, "data": data}, "latest"])
    return int(r["result"], 16) if "result" in r and r["result"] not in ("0x", None) else None


def _book(t, tok, reference):
    """What the incident does to the fund's pocket: sale value now, loss, status, time left."""
    unit = 10 ** t["pt_decimals"]
    tokens = _call(t["pool"], "0x" + SEL["readTokens"])
    sy, pt = "0x" + tokens[24:64], "0x" + tokens[88:128]
    fund_word, seller_word = FUND[2:].lower().rjust(64, "0"), SELLER[2:].lower().rjust(64, "0")
    held = _words(_call(pt, "0x" + SEL["balanceOf"] + fund_word))[0]
    allowed = _words(_call(pt, "0x" + SEL["allowance"] + fund_word + seller_word))[0]
    if held < FUND_PT * unit or allowed < FUND_PT * unit:
        return {"status": "not set up", "time_left": "give the fund its PT and approve the seller (step 0)",
                "position_pt": FUND_PT, "sellable_pt": 0, "stuck_pt": 0, "reference_usd": reference}
    rate = _words(_call(sy, "0x" + SEL["exchangeRate"]))[0]
    price = tok["feed"]["value"] if t["asset_priced_by_feed"] else 1.0
    to_usd = lambda sy_out: sy_out * rate / 1e18 / 10 ** t["asset_decimals"] * price
    full = _quote(t["pool"], FUND_PT * unit)
    sellable = FUND_PT
    value = to_usd(full) if full is not None else None
    if full is None:  # largest part the pool still takes
        sellable = 0
        for frac in (0.75, 0.5, 0.25, 0.1, 0.05):
            q = _quote(t["pool"], int(FUND_PT * frac) * unit)
            if q is not None:
                sellable, value = FUND_PT * frac, to_usd(q)
                break
    paused = _words(_call(sy, "0x" + SEL["paused"]))[0] == 1
    o = tok.get("oracle")
    if paused:  # settlement-layer incident: Pendle governance froze the SY behind the PT
        incident, left = True, "none: Pendle paused the SY, no exit until it is unpaused"
    elif o:
        incident = o["deviation"] > o["threshold"] or o["challenged"] or o["active"] == "backup"
        if o["active"] == "backup":
            pending = sum(m["unhealthy"] for m in tok["markets"].values())
            debt = sum(m["debt_at_risk_usd"] for m in tok["markets"].values())
            left = (f"seconds: oracle switched, {pending} borrowers (${debt / 1e6:.1f}M) can be liquidated now; "
                    f"bots dump their PT into this pool within blocks" if pending
                    else "closed: oracle switched, liquidations are live")
        elif o["challenged"]:
            left = f"{o['challenge_hours_left']:.1f} h before the oracle switches"
        elif incident:
            left = "16 h from the first challenge, which anyone can start now"
        else:
            left = "-"
    else:
        incident = tok["feed"]["value"] < t["share_price_ref"] * 0.999
        left = "at most 15 min: the oracle's TWAP catches up, then liquidations" if incident else "-"
    if sellable == FUND_PT and not incident:
        status = "normal"
    elif sellable == FUND_PT and o and o["active"] == "backup" and any(m["unhealthy"] for m in tok["markets"].values()):
        status = "last moment"  # sellable only until liquidators dump into the pool
    elif sellable == FUND_PT:
        status = "exit still possible"
    elif sellable > 0:
        status = "partly stuck"
    else:
        status = "stuck"
    # price per PT on what can be sold, against the calm price measured on the fork
    per_pt_now = value / sellable if value and sellable else None
    per_pt_ref = reference / FUND_PT if reference else None
    return {"sell_now_usd": value, "sellable_pt": sellable, "stuck_pt": FUND_PT - sellable, "position_pt": FUND_PT,
            "reference_usd": reference,
            "price_vs_reference": (per_pt_now / per_pt_ref - 1) if per_pt_now and per_pt_ref else None,
            "status": status, "time_left": left, "incident": incident, "sy_paused": paused}


def _references():
    """Calm exit value of the fund's pocket, measured by the fork simulations (dashboard/data.json)."""
    try:
        d = json.loads((ROOT / "dashboard" / "data.json").read_text())
        return {p["name"]: p["calm_exit"] for p in d["positions"]}
    except Exception:
        return {}


def check():
    blk = _rpc("eth_getBlockByNumber", ["latest", False])["result"]
    now = int(blk["timestamp"], 16)
    status = {"block": int(blk["number"], 16), "timestamp": now, "hours_since_fork": (now - FORK_START) / 3600,
              "read_at": time.strftime("%H:%M:%S"), "tokens": []}
    refs = _references()
    for t in TOKENS:
        try:
            tok = _token(t, now)
            try:
                tok["book"] = _book(t, tok, refs.get(t["name"]))
            except Exception as e:
                tok["book"] = {"error": str(e)[:160]}
            status["tokens"].append(tok)
        except Exception as e:
            status["tokens"].append({"name": t["name"], "error": str(e)[:200]})
    status["seller"] = SELLER
    OUT.write_text(json.dumps(status, indent=1), encoding="utf-8")
    return status


def main():
    global SELLER
    loop = float(sys.argv[sys.argv.index("--loop") + 1]) if "--loop" in sys.argv else 0
    if "--seller" in sys.argv:
        SELLER = sys.argv[sys.argv.index("--seller") + 1]
    while True:
        try:
            s = check()
        except Exception as e:  # Anvil down or restarting: keep waiting instead of crashing
            print(f"local chain not reachable ({str(e)[:80]}), retrying...", flush=True)
            time.sleep(loop or 3)
            continue
        line = [f"block {s['block']} +{s['hours_since_fork']:.1f}h"]
        for t in s["tokens"]:
            if "error" in t:
                line.append(f"{t['name']}: ERROR")
                continue
            unh = sum(m["unhealthy"] for m in t["markets"].values())
            o = t.get("oracle", {})
            b = t.get("book", {})
            book = (f", book {b['status']}" + (f" ${b['sell_now_usd']:,.0f}" if b.get("sell_now_usd") else "")) if "status" in b else ""
            line.append(f"{t['name']}: {t['feed']['label']} {t['feed']['value']:.4f}"
                        + (f", oracle {o['active']}{' CHALLENGED' if o['challenged'] else ''}" if o else "")
                        + f", unhealthy {unh}, pool APY {t['pool']['implied_apy']:.1%}" + book)
        print(" | ".join(line), flush=True)
        if not loop:
            break
        time.sleep(loop)


if __name__ == "__main__":
    main()
