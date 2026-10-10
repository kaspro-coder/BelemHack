"""Book-level view: which simulated event hits which pocket, directly or through contagion.

The fund holds FUND_PT of each simulated PT. Events come from the fork runs:
  * each position's own driver (USDe depeg, reUSD write-down, USDS depeg) at the severity that
    made the fund's PT unsellable on the fork;
  * contagion: a reUSD write-down large enough to leave bad debt in PT-reUSD/USDT hits Smokehouse
    USDT. IF its depositors run (assumption), the vault pulls out of PT-sUSDS/USDT (simulated: 100%
    utilisation, borrow rate 4% -> 18%). Those borrowers must sell PT-sUSDS; the panic run shows a
    dump of that size saturates the pool, so the PT-sUSDS pocket becomes unsellable too.
Probabilities are the cohort ones (persistent move >= severity before expiry). Drivers of different
issuers are treated as independent; contagion is the one link we model between them.
"""
from . import simulation


def _first_stuck(events):
    s = [e["severity"] for e in events if e["fund_stuck"]]
    return min(s) if s else None


def build(positions=None):
    positions = positions or simulation.run()
    by = {p["name"]: p for p in positions}
    rows, probs = [], {}
    for p in positions:
        sev = _first_stuck(p["events"])
        if sev is None:
            continue
        pr = p["probabilities"].get(sev) or p["probabilities"].get(f"{sev:g}")
        probs[p["name"]] = pr
        hit = {q["name"]: ("stuck" if q["name"] == p["name"] else "-") for q in positions}
        rows.append({"event": f"{p['driver'].split(' (')[0]} >= {sev:.0%}", "source": p["name"],
                     "p": pr["p"], "lo": pr["lo"], "hi": pr["hi"], "hits": hit,
                     "window": p["window"]})

    contagion = None
    if "PT-reUSD" in by and "PT-sUSDS" in by:
        bd = simulation.reusd_bad_debt_by_market()
        sev = min((s for s, v in bd.items() if v["usdt"] > 0), default=None)
        panic = by["PT-sUSDS"]["pt_panic"]
        saturating = min((r["dump_pt"] for r in panic if r["fund_stuck"]), default=None)
        if sev is not None and saturating is not None:
            pr = by["PT-reUSD"]["probabilities"].get(sev) or by["PT-reUSD"]["probabilities"].get(f"{sev:g}")
            run = simulation.contagion()
            hit = {q["name"]: "-" for q in positions}
            hit["PT-reUSD"] = "stuck"
            hit["PT-sUSDS"] = "stuck if the vault run happens"
            contagion = {"severity": sev, "p": pr["p"], "lo": pr["lo"], "hi": pr["hi"],
                         "saturating_dump_pt": saturating, "rate_before": run[0]["borrow_apr"],
                         "rate_after": run[1]["borrow_apr"], "locked": run[1]["vault_locked"]}
            rows.append({"event": f"reUSD write-down >= {sev:.0%} -> Smokehouse USDT run", "source": "contagion",
                         "p": pr["p"], "lo": pr["lo"], "hi": pr["hi"], "hits": hit, "window": "15 min, then days"})

    def any_stuck(level):
        """P(at least one pocket unsellable before its expiry). Contagion adds no new trigger
        (the reUSD write-down is already counted); it widens the damage, see expected pockets."""
        none = 1.0
        for pr in probs.values():
            none *= 1 - pr[level]
        return 1 - none

    def expected_stuck_pockets(level, with_contagion):
        e = sum(pr[level] for pr in probs.values())
        if with_contagion and contagion:
            e += contagion[level]  # the sUSDS pocket, hit through reUSD
        return e

    book = {lvl: {"any_stuck": any_stuck(lvl),
                  "expected_stuck_pockets": expected_stuck_pockets(lvl, False),
                  "expected_stuck_pockets_with_contagion": expected_stuck_pockets(lvl, True)}
            for lvl in ("lo", "p", "hi")}
    return {"pockets": [p["name"] for p in positions], "fund_pt": simulation.FUND_PT,
            "rows": rows, "contagion": contagion, "book": book}


def main():
    b = build()
    names = b["pockets"]
    print(f"Book: {b['fund_pt']:,} PT in each of {', '.join(names)}\n")
    print(f"{'event':55} {'P before expiry':>16}  " + "  ".join(f"{n:>12}" for n in names))
    for r in b["rows"]:
        print(f"{r['event']:55} {r['p']:>7.2%} ({r['lo']:.1%}-{r['hi']:.1%})  " +
              "  ".join(f"{(r['hits'][n] if r['hits'][n] != 'stuck if the vault run happens' else 'stuck*'):>12}" for n in names))
    c = b["contagion"]
    if c:
        print(f"\n* contagion: from a {c['severity']:.0%} reUSD write-down, PT-reUSD/USDT books bad debt; a Smokehouse USDT run "
              f"locks ${c['locked']:,.0f} in PT-sUSDS/USDT and lifts its borrow rate {c['rate_before']:.1%} -> {c['rate_after']:.1%}; "
              f"a {c['saturating_dump_pt']:,.0f} PT forced sale saturates the PT-sUSDS pool.")
    for lvl, lab in (("lo", "low"), ("p", "central"), ("hi", "high")):
        x = b["book"][lvl]
        print(f"  {lab:7}: P(at least one pocket unsellable) {x['any_stuck']:.2%};  expected pockets stuck "
              f"{x['expected_stuck_pockets']:.3f} -> {x['expected_stuck_pockets_with_contagion']:.3f} with contagion")


if __name__ == "__main__":
    main()
