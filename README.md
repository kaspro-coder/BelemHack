# BelemHack - DeFi Risk Dependency

EPFL Hackathon 2026, Belem Capital challenge.

Given on-chain positions, the tool **discovers their dependencies**, **replays controlled failure
scenarios on a local fork of Ethereum mainnet** (the real Pendle, Morpho and oracle contracts),
and turns the measured impact into a **stay / exit / unclear** verdict with an action plan.

## What it found (fork block 26164635, 10 Oct 2026)

| | PT-sUSDe (26 Nov) | PT-reUSD (10 Dec) | PT-sUSDS (26 Nov) |
|---|---|---|---|
| Oracle the lending market uses | primary: linear discount, blind to the market; backup adds Chainlink USDe/USD; switch after a **16 h** permissionless challenge above 0.75% deviation | 15-minute TWAP of the Pendle pool itself | primary: min(pool TWAP, conservative floor); backup adds Chainlink USDS/USD behind the same 16 h challenge |
| Position becomes unsellable from | a **1%** USDe depeg lasting > 16 h (5% with flash-loan liquidators) | a **1%** NAV write-down by re.xyz | a **2%** USDS depeg lasting > 16 h |
| Exit window once the signal fires | **16 h** | **15 min** (must be automated) | **16 h** |
| Verdict for 1M PT | UNCLEAR (probability range straddles the threshold) | STAY (carry dominates across the range) | UNCLEAR |

Other results replayed on the fork:
- A USDe dip shorter than 16 h liquidates nobody; at 24 h it liquidates 3 borrowers.
- A crash of the PT-sUSDe market liquidates nobody (the oracle ignores the market): lenders carry it silently.
- A Chainlink USDe/USD feed stuck at $0.80 for 16 h liquidates 10 borrowers whose collateral never lost value ($823k bad debt).
- PT-reUSD market panic is bounded by the pool's 96% PT cap: the TWAP can fall ~1.5% at most. That is now
  enough to liquidate an $11M borrower sitting 0.67% from liquidation.
- **Risk moves within the hour**: between two forks ~35 minutes apart, that borrower levered up 4.7%. The
  write-down that makes PT-reUSD unsellable dropped from 2% to 1%. Hence the live watcher and `--fresh` re-forks.
- PT-sUSDS market panic barely moves its oracle (0.05% for a pool-saturating dump): the floor in Ojo's min() absorbs it.
- **Contagion**: Smokehouse USDT supplies 38% of PT-reUSD/USDT and 83% of PT-sUSDS/USDT. A run on it after a
  reUSD loss locks $3.4M in the sUSDS market and lifts its borrow rate from 4.3% to 18% at once, 47% a week later.
- Pendle's live quotes fill off-chain limit orders; the on-chain pool alone saturates near 2.7M PT-sUSDe.

## Layout

```
sim/                    Foundry project: the controlled scenarios
  test/ScenarioBase.sol   building blocks: liquidate, sell into the pool, measure exit value, revert
  test/Scenarios.t.sol    PT-sUSDe: USDe depeg, short dip, PT panic, feed failure, baseline
  test/ReUsdCascade.t.sol PT-reUSD: reflexive market cascade, issuer write-down, baseline
  test/SusdsScenarios.t.sol  PT-sUSDS: USDS depeg, market panic, baseline
  test/SusdsContagion.t.sol  vault run on PT-sUSDS/USDT
  out-scenarios/*.jsonl   results (committed)
  gen_borrowers.py        borrower lists from Morpho's API -> src/Borrowers.sol
src/defi_risk/
  discover.py             multi-token dependency graph, shared dependencies, contagion paths
  oracle.py               on-chain classification of Morpho oracles and feeds
  cohort.py, venues.py    measured base rates (stablecoin depegs, exchange hacks)
  simulation.py           decision layer fed by the fork results
  sim_report.py           text report;  dashboard.py: exports dashboard/data.json
  watch.py                live signals from mainnet (oracle deviation, issuer share price, vault, whales)
dashboard/index.html      the demo page
```

## Reproduce

Requirements: Python 3.10+ (standard library only), Foundry 1.8.x, an Ethereum RPC URL that serves historical
state (an Alchemy key works) in `.env` as `ETH_RPC_URL=...`.

```bash
bash scripts/run_all.sh          # fork at sim/fork_block.txt, scenarios, report, dashboard data
bash scripts/run_all.sh --fresh  # same on the latest block
cd src && python -m defi_risk.watch --loop 60   # live signals -> dashboard/status.json
cd dashboard && python -m http.server 8765   # then open http://localhost:8765
```

Step by step:
```bash
anvil --fork-url $ETH_RPC_URL --fork-block-number $(cat sim/fork_block.txt) --auto-impersonate
cd sim && forge test --fork-url http://127.0.0.1:8545
cd ../src && python -m defi_risk.sim_report && python -m defi_risk.dashboard
```

## Method

1. **Discover**: Pendle metadata gives the issuer; Morpho's API gives every market taking the PT as collateral,
   its borrowers and the vaults with money in it; each oracle is read on-chain and classified.
2. **Simulate**: each scenario starts from the real state, forces one event (mocked Chainlink feed, issuer NAV
   write-down, whale dump, time warp past the oracle timelock or TWAP), lets the contracts react, liquidates
   every unhealthy borrower, sells the seized PT into the real pool, measures, and reverts.
3. **Decide**: carry given up vs expected permanent loss vs measured exit cost. Probabilities come from a cohort
   of 17 non-fiat stablecoins above $100M with a 90% Poisson range; the verdict is STAY or EXIT only if the whole
   range agrees, UNCLEAR otherwise. The liquidity risk and the exit window come from the simulation.

## Honest limits
- Liquidator behaviour is bracketed by two runs: dump everything vs flash-loan liquidators who stop when the pool is full.
- Only liquidators sell; other panicking holders are not simulated, so in-window exit values are optimistic.
- The fork has no Pendle limit orders; live quotes look cheaper than the pool alone.
- The probability cohort is small (2 persistent depegs of 3%+) and biased towards survivors; for PT-reUSD it is a proxy.
- Borrower lists are fetched after the fork block; positions opened in between are missing.

The earlier live-data pipeline (`python -m defi_risk.report`) is kept for reference.
