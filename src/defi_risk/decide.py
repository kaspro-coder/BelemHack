"""Stay or exit, for the quantities you hold: python -m defi_risk.decide sUSDe=2000000 reUSD=500000 sUSDS=1000000

Same rule as the dashboard's position-size calculator, on the same results (dashboard/data.json):
execution cost from the sales measured on the fork, pool capacity, expected loss from the probability
range, yield given up. Optional --crowd N: PT sold ahead of the fund in a crisis (default 1,000,000).
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "dashboard" / "data.json"


def model(p):
    curve = p["exit_curve"]
    capacity = max(pt - unsold for pt, _, unsold in curve)
    sold = [(pt, usd / pt) for pt, usd, unsold in curve if unsold == 0]

    def price_at(size):  # average price per PT for a sale of `size`, interpolated between measured sizes
        if size <= sold[0][0]:
            return sold[0][1]
        for (x0, y0), (x1, y1) in zip(sold, sold[1:]):
            if size <= x1:
                return y0 + (y1 - y0) * (size - x0) / (x1 - x0)
        return sold[-1][1]

    return capacity, price_at


def decide(p, size, crowd):
    d = p["decision"]
    capacity, price_at = model(p)
    sellable = min(size, capacity)
    calm_stuck = size - sellable
    exit_cost = 1 - price_at(sellable) / p["mark"] if size else 0.0
    room = max(0.0, capacity - crowd)
    crisis_stuck = max(0.0, size - room)
    edge = {k: d["carry"] - d["at"][k]["expected_loss"] + exit_cost for k in ("lo", "p", "hi")}
    if calm_stuck > 0:
        word, why = "REDUCE", f"the pool cannot take {size:,.0f} PT even in a calm market"
    elif crisis_stuck > 0:
        word, why = "REDUCE", f"in a crisis with {crowd:,.0f} PT ahead, {crisis_stuck:,.0f} PT would be stuck"
    elif all(e > 0 for e in edge.values()):
        word, why = "STAY", "the whole probability range favours staying, and the position fits in the exit queue"
    elif all(e <= 0 for e in edge.values()):
        word, why = "EXIT", "the whole probability range favours exiting"
    else:
        word, why = "UNCLEAR", "the probability range straddles break-even: hold less rather than all-or-nothing"
    return dict(word=word, why=why, exit_cost=exit_cost, calm_stuck=calm_stuck, crisis_stuck=crisis_stuck,
                room=room, usd=size * p["mark"], loss=d["at"], carry=d["carry"])


def main():
    args = sys.argv[1:]
    crowd = 1_000_000.0
    if "--crowd" in args:
        i = args.index("--crowd")
        crowd = float(args[i + 1])
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    data = json.loads(DATA.read_text())
    by_name = {p["name"].lower().removeprefix("pt-"): p for p in data["positions"]}
    print(f"\nFork block {data['fork_block']}, {crowd:,.0f} PT sold ahead of the fund in a crisis\n")
    total = 0.0
    for a in args:
        name, _, qty = a.partition("=")
        p = by_name.get(name.lower().removeprefix("pt-"))
        if p is None or not qty:
            sys.exit(f"'{a}': use NAME=QUANTITY with NAME in {', '.join(q['name'] for q in data['positions'])}")
        r = decide(p, float(qty), crowd)
        total += r["usd"]
        L = r["loss"]
        stuck = f" + {r['calm_stuck']:,.0f} PT unsellable" if r["calm_stuck"] else ""
        e = {k: r["carry"] - L[k]["expected_loss"] + r["exit_cost"] for k in ("lo", "p", "hi")}
        print(f"{p['name']:<9} {float(qty):>12,.0f} PT (${r['usd']:,.0f})   ->  {r['word']}   "
              f"staying vs exiting {e['p']:+.2%} = ${e['p'] * r['usd']:+,.0f} (range {e['hi']:+.2%} to {e['lo']:+.2%})")
        print(f"   exit cost now {r['exit_cost']:.2%}{stuck} | expected loss if we stay {L['p']['expected_loss']:.2%} "
              f"(range {L['lo']['expected_loss']:.2%}-{L['hi']['expected_loss']:.2%}) | yield given up {r['carry']:.2%}")
        print(f"   {r['why']}")
        print(f"   largest size that still exits fully in that crisis: {r['room']:,.0f} PT; "
              f"time to act once {p['trigger'].split(':')[0]}: {p['window']}\n")
    print(f"Book: ${total:,.0f}")


if __name__ == "__main__":
    main()
