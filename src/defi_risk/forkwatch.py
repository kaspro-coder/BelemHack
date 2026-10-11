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
FORK = "http://127.0.0.1:8545"
FORK_START = 1791666623  # timestamp of the pinned block, to show how far the demo warped time

TOKENS = [
    {"name": "PT-sUSDe", "pool": "0x47ad2cd1dd15739a7a035b9d3b7828d916fef77e", "pt_decimals": 18,
     "markets": {"USDC": ("0x5613b170ded221c588b6e9637b910f49e5508680ceede207f44aa72e5c46cb05", "sUSDe_USDC")},
     "meta_oracle": "0xF8b29e7E9c00CE531434775f7923CC9fbCa01b08",
     "feed": ("USDe/USD", "0xa569d910839ae8865da8f8e70fffb0cba869f961", "chainlink")},
    {"name": "PT-reUSD", "pool": "0x13285bcbc27f92b47b4edb99d744c07b48c977c0", "pt_decimals": 6,
     "markets": {"USDC": ("0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64", "reUSD_USDC"),
                 "USDT": ("0x6acd18854e43f93f5a90446004c35c72a68af1ad99f08cb247782ce6457914ca", "reUSD_USDT")},
     "meta_oracle": None,
     "feed": ("reUSD share price", "0xd1D104a7515989ac82F1AFDa15a23650411b05B8", "share_price")},
    {"name": "PT-sUSDS", "pool": "0x9c560ebaf78e596cbcc27411d633a74d628dd7dc", "pt_decimals": 18,
     "markets": {"USDC": ("0x22fe4c688161863c73571a2b8db65cc11a4a6bceee4f0dea4aa83e4b784f1bd9", "sUSDS_USDC"),
                 "USDT": ("0x0367161b7cb23dfd03747dd3815d1c445b0437b648a6d50346249c6e7b92ff1b", "sUSDS_USDT"),
                 "USDS": ("0x9a8dab6de1059e6dc66c34b358764b70effb289e514e237f3161ffb09eaaf24f", "sUSDS_USDS")},
     "meta_oracle": "0x3464a61A68C486241FE07201C913F055Bdce35BF",
     "feed": ("USDS/USD", "0xff30586cd0f29ed462364c7e81375fc0c71219b1", "chainlink")},
]
MORPHO = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
SEL = {"position": "93c52062", "market": "5c60e39a", "idToMarketParams": "2c3c9157", "price": "a035b1fe",
       "decimals": "313ce567", "_storage": "c3fb90d6", "getDeviation": "89ab3532",
       "deviationThreshold": "d94ad837", "isChallenged": "9df4d0fe", "challengeExpiresAt": "ccc1b9cd",
       "isPrimary": "3682152b", "latestRoundData": "feaf968c", "getSharePrice": "5b1dac60"}


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


def check():
    blk = _rpc("eth_getBlockByNumber", ["latest", False])["result"]
    now = int(blk["timestamp"], 16)
    status = {"block": int(blk["number"], 16), "timestamp": now, "hours_since_fork": (now - FORK_START) / 3600,
              "read_at": time.strftime("%H:%M:%S"), "tokens": []}
    for t in TOKENS:
        try:
            status["tokens"].append(_token(t, now))
        except Exception as e:
            status["tokens"].append({"name": t["name"], "error": str(e)[:200]})
    OUT.write_text(json.dumps(status, indent=1), encoding="utf-8")
    return status


def main():
    loop = float(sys.argv[sys.argv.index("--loop") + 1]) if "--loop" in sys.argv else 0
    while True:
        s = check()
        line = [f"block {s['block']} +{s['hours_since_fork']:.1f}h"]
        for t in s["tokens"]:
            if "error" in t:
                line.append(f"{t['name']}: ERROR")
                continue
            unh = sum(m["unhealthy"] for m in t["markets"].values())
            o = t.get("oracle", {})
            line.append(f"{t['name']}: {t['feed']['label']} {t['feed']['value']:.4f}"
                        + (f", oracle {o['active']}{' CHALLENGED' if o['challenged'] else ''}" if o else "")
                        + f", unhealthy {unh}, pool APY {t['pool']['implied_apy']:.1%}")
        print(" | ".join(line), flush=True)
        if not loop:
            break
        time.sleep(loop)


if __name__ == "__main__":
    main()
