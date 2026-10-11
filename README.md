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

Book of 1M PT in each pocket: **8.5%** chance at least one pocket becomes unsellable before expiry (range 4.4% to 14.9%),
with one contagion path where two pockets that share no issuer fall together.

Ecosystem scan (every PT with $1M+ on Morpho): 9 PTs, $248M of collateral, 13 lending oracles of which 3 ignore
the PT market entirely; Smokehouse USDT is the only vault lending to two of them; APYX issues the asset behind two PTs.

**Position calculator** (on the page): pick a PT, a size and how many PT others sell ahead of you in a crisis; it
returns the exit cost at that size, how much would be stuck, the largest size that still exits fully, and the verdict.
Rule used: the fund exits fully if PT sold ahead + its size <= the pool's capacity measured on the fork; it matches all
18 crowded-exit runs (e.g. PT-sUSDe, 1M behind 2M: 266k stuck predicted, 265,625 measured).

Other results replayed on the fork:
- **The exit is a queue, not a price**: inside the window the fund gets ~fair value as long as less than ~1.5M
  (PT-sUSDe), ~4M (PT-reUSD) or ~2M (PT-sUSDS) PT were sold ahead of it; past that, part of it is stuck.
  Position size has to be judged against that room.
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
  src/DemoTools.sol       mocks and PT seller for manual demo incidents
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
  ecosystem.py            scan of every Pendle PT used as Morpho collateral, shared dependencies ranked
  portfolio.py            book view: which event hits which pocket, with contagion
  forkwatch.py            live state of the local fork during a manual demo -> dashboard/fork_status.json
  watch.py                live signals from mainnet (oracle deviation, issuer share price, vault, whales)
dashboard/index.html      the demo page
```

## Tests

```bash
cd src && python -m unittest -v      # 19 tests: base rates, Poisson intervals, expected loss, decision, graph walks, fork outputs
```

## Reproduce

Requirements: Python 3.10+ (standard library only), Foundry 1.8.x, an Ethereum RPC URL that serves historical
state (an Alchemy key works) in `.env` as `ETH_RPC_URL=...`. Only forking uses it; live reads (watcher, discovery)
go to a public node first. A fresh fork plus a full run costs a lot of RPC credits: avoid repeated `--fresh` runs.

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

## Live demo: trigger incidents by hand on the local chain

The automated scenarios (`forge test`) run in a throw-away copy and never change Anvil. For a live demo you act on
**Anvil itself** with `cast`, watch the page react, then **reset** the chain. Every command below was run on the fork
before being written here. Commands are for **Windows PowerShell**.

### The demo, in order (about 5 minutes)

1. **The question** (top of the page, summary): three PTs that look alike react in opposite ways.
2. **The book before** (orange panel, "Your book, right now"): three pockets `normal`, about $2.96M in total.
3. **Incident 1, live**, from window 4, one step at a time, pointing at the book table after each:
   - 1a USDe at $0.99: `exit still possible`, about $981k, **16 h left**. "Noticing is easy; what matters is the 16 hours."
   - 1b challenge: the clock starts, "16.0 h before the oracle switches".
   - 1c sixteen hours later: oracle on backup, the whale is liquidatable, window **closed**.
   - 1d-1e liquidation and dump: the pocket turns **`partly stuck`, 900k PT stuck**.
4. **Reset** (two commands): the book is back to `normal`. "Same chain, same contracts, reproducible."
5. **Incident 6** (optional, 30 s): Pendle pauses the SY, PT-sUSDS is stuck instantly. A different layer, no delay at all.
6. **Why it matters for sizing** (calculator): change the size and the crowd ahead, show `REDUCE`.
7. **The other pockets and layers** from precomputed results: reUSD's 15-minute window, contagion through Smokehouse
   USDT, the book's 8.5% chance of a stuck pocket, then the limits.

Keep the precomputed page as a fallback: if the live part fails, every number is already on it.

### What acts on what

| Contract / tool | Acts on | Real addresses touched |
|---|---|---|
| `sim/test/Scenarios.t.sol` | **PT-sUSDe-26NOV2026** | Pendle pool `0x47ad…f77e`, Morpho PT-sUSDe/USDC `0x5613…cb05`, oracle `0xF8b2…1b08`, Chainlink USDe/USD `0xa569…F961` |
| `sim/test/ReUsdCascade.t.sol` | **PT-reUSD-10DEC2026** | pool `0x1328…77c0`, Morpho PT-reUSD/USDC `0x1e9d…fc64` and /USDT `0x6acd…14ca`, oracle `0x217d…51f0`, re.xyz share price `0xd1D1…05B8` |
| `sim/test/SusdsScenarios.t.sol` | **PT-sUSDS-26NOV2026** | pool `0x9C56…d7dC`, Morpho PT-sUSDS/USDC, /USDT, /USDS, oracle `0x3464…35BF`, Chainlink USDS/USD `0xff30…19b1` |
| `sim/test/SusdsContagion.t.sol` | Smokehouse USDT vault → PT-sUSDS/USDT | vault `0xA080…7484`, market `0x0367…ff1b` |
| `sim/src/DemoTools.sol` | the feeds you replace in a demo | `MockAggregator` (USDe/USD, USDS/USD), `MockSharePrice` (re.xyz), `DemoSeller` (sells PT into a pool) |

No new token is created: the scenarios act on the real deployed contracts. Only price feeds are replaced, and a
reset puts the real code back.

### 0. Set up (once)

Four PowerShell windows.

**Window 1, the local chain.** First check whether one already runs:
```powershell
cast block-number --rpc-url http://127.0.0.1:8545
```
If it answers with the block number, Anvil is running. If it fails with `os error 10061` (connection refused), no
Anvil is running: start it below. If `anvil` below fails with `os error 10048`, the port is
taken by an Anvil that is already running. For a demo, run it in your own window so it does not depend on another
session: stop the old one with `Stop-Process -Name anvil -Force`, then start it here:
```powershell
cd C:\Users\Abdel\defi-risk
$env:Path += ";C:\Users\Abdel\.foundry\bin"
$env:ETH_RPC_URL = ((Get-Content .env | Select-String "ETH_RPC_URL=").ToString().Split("=", 2)[1])
anvil --fork-url $env:ETH_RPC_URL --fork-block-number (Get-Content sim\fork_block.txt) --auto-impersonate --compute-units-per-second 250
```

**Window 2, the page:**
```powershell
cd C:\Users\Abdel\defi-risk\dashboard
python -m http.server 8765
```
Open **http://localhost:8765** (not the file). The orange panel "Local chain (Anvil fork)" is the one that moves.

**Window 3, the fork monitor** (reads Anvil every 3 s and feeds that panel):
```powershell
cd C:\Users\Abdel\defi-risk\src
python -m defi_risk.forkwatch --loop 3
```

**Window 4, your commands.** Paste this block once; it defines the addresses used below:
```powershell
cd C:\Users\Abdel\defi-risk\sim
$env:Path += ";C:\Users\Abdel\.foundry\bin"
$R = "http://127.0.0.1:8545"
$DEV = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"   # Anvil's funded dev account
$LIQ = "0x000000000000000000000000000000000011C0DA"   # our liquidator
$FUND = "0x00000000000000000000000000000000000BE1E3"  # the fund
$WHALEPANIC = "0x000000000000000000000000000000000000D0D0"
$MAX = "115792089237316195423570985008687907853269984665640564039457584007913129639935"
$MORPHO = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
$IRM = "0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC"
$USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
# PT-sUSDe
$PT_E = "0xB195B618EA52b77CB2a58846F452f59f8dFa9390"; $POOL_E = "0x47ad2CD1dD15739a7A035B9D3b7828d916fEF77E"
$ORACLE_E = "0xF8b29e7E9c00CE531434775f7923CC9fbCa01b08"; $FEED_USDE = "0xa569d910839Ae8865Da8F8e70FfFb0cBA869F961"
$ID_E = "0x5613b170ded221c588b6e9637b910f49e5508680ceede207f44aa72e5c46cb05"
$WHALE_E = "0x5C430FF6F374da12218b380d2040299Ae5B6d40E"   # largest PT-sUSDe borrower, 0.97% from liquidation
$MP_E = "($USDC,$PT_E,$ORACLE_E,$IRM,915000000000000000)"
# PT-reUSD
$PT_R = "0xeCfaFdC7741323a945A163ed068B5a3C43483957"; $POOL_R = "0x13285bCbc27F92b47B4EDB99D744C07B48C977c0"
$SHARE_PRICE = "0xd1D104a7515989ac82F1AFDa15a23650411b05B8"
# PT-sUSDS
$ORACLE_S = "0x3464a61A68C486241FE07201C913F055Bdce35BF"; $FEED_USDS = "0xff30586cd0F29eD462364C7e81375FC0C71219b1"
$PT_S = "0xdC169AbE56461A2E0c034Da431Ac2a3ebf596094"
$MP_S = "($USDC,$PT_S,$ORACLE_S,$IRM,915000000000000000)"
```

Deploy the PT seller, give gas money to the actors, give **the fund its book** (1M PT in each pocket, approved for
the seller), **then** take the baseline snapshot so every reset keeps all of it:
```powershell
$SELLER = ((forge create src/DemoTools.sol:DemoSeller --rpc-url $R --unlocked --from $DEV --broadcast) | Select-String "Deployed to").ToString().Split(" ")[-1]
foreach ($a in $LIQ, $FUND, $WHALEPANIC) { cast rpc anvil_setBalance $a 0x56BC75E2D63100000 --rpc-url $R }
cast rpc anvil_setStorageAt $PT_E (cast index address $FUND 0) (cast to-uint256 1000000000000000000000000) --rpc-url $R
cast rpc anvil_setStorageAt $PT_R (cast index address $FUND 0) (cast to-uint256 1000000000000) --rpc-url $R
cast rpc anvil_setStorageAt $PT_S (cast index address $FUND 0) (cast to-uint256 1000000000000000000000000) --rpc-url $R
foreach ($t in $PT_E, $PT_R, $PT_S) { cast send $t "approve(address,uint256)" $SELLER $MAX --from $FUND --unlocked --rpc-url $R | Select-String "status" }
$SNAP = (cast rpc evm_snapshot --rpc-url $R).Trim('"')
$SELLER; $SNAP
```
`$SELLER` should print `0x17d9d652E2FD969cDfdb4eC7a71137BDd9aada95` on a fresh Anvil. If it prints anything else,
restart window 3 with `python -m defi_risk.forkwatch --loop 3 --seller <that address>`.
The orange panel's **"Your book, right now"** table now shows the three pockets as `normal`, about $2.96M in total.

### Reset the market after any incident
```powershell
cast rpc evm_revert $SNAP --rpc-url $R
$SNAP = (cast rpc evm_snapshot --rpc-url $R).Trim('"')
```
`evm_revert` puts back every price, oracle, position, pool and the real feed code, and rewinds the clock.
A snapshot can be used only once, hence the new one right after. Within 3 s the page panel is back to normal.

**Reset before running the automated scenarios** (`forge test`, `run_all.sh`): they start from Anvil's current state.

---

### Incident 1: USDe depegs 1% for more than 16 h (PT-sUSDe)

**1a. USDe drops to $0.99.** Replace the Chainlink feed by the mock and set the price:
```powershell
cast rpc anvil_setCode $FEED_USDE (forge inspect MockAggregator deployedBytecode) --rpc-url $R
cast send $FEED_USDE "setAnswer(int256)" 99000000 --from $DEV --unlocked --rpc-url $R
```
*Page:* USDe/USD 0.9900, deviation 1.01% above the 0.75% threshold. Unhealthy borrowers: still 0, because the
primary oracle does not read USDe. **The exit window is open: the fund can still sell now.**

**1b. Anyone starts the challenge:**
```powershell
cast send $ORACLE_E "challenge()" --from $DEV --unlocked --rpc-url $R
```
*Page:* "challenged, 16.0 h left".

**1c. Sixteen hours pass:**
```powershell
cast rpc evm_increaseTime 57601 --rpc-url $R
cast rpc evm_mine --rpc-url $R
cast send $ORACLE_E "acceptChallenge()" --from $DEV --unlocked --rpc-url $R
cast send $MORPHO "accrueInterest((address,address,address,address,uint256))" $MP_E --from $DEV --unlocked --rpc-url $R
```
*Page:* oracle on **backup**, PT price about 1% lower, **1 unhealthy borrower** (the $2.94M whale). The window is
closed. `accrueInterest` books the 16 h of interest Morpho only records when someone touches the market.

**1d. A liquidator takes the whale's collateral.** Fund it with 10M USDC, approve Morpho, repay all the whale's debt:
```powershell
cast rpc anvil_setStorageAt $USDC (cast index address $LIQ 9) (cast to-uint256 10000000000000) --rpc-url $R
cast send $USDC "approve(address,uint256)" $MORPHO $MAX --from $LIQ --unlocked --rpc-url $R
$SHARES = ((cast call $MORPHO "position(bytes32,address)(uint256,uint128,uint128)" $ID_E $WHALE_E --rpc-url $R)[1] -split " ")[0]
cast send $MORPHO "liquidate((address,address,address,address,uint256),address,uint256,uint256,bytes)" $MP_E $WHALE_E 0 $SHARES 0x --from $LIQ --unlocked --rpc-url $R
cast call $PT_E "balanceOf(address)(uint256)" $LIQ --rpc-url $R
```
The liquidator now holds ~3.07M PT (the whale's debt plus a 2.6% bonus). *Page:* 0 unhealthy.

**1e. The liquidator dumps into the pool:**
```powershell
cast send $PT_E "approve(address,uint256)" $SELLER $MAX --from $LIQ --unlocked --rpc-url $R
cast send $SELLER "sell(address,uint256)" $POOL_E 2500000000000000000000000 --from $LIQ --unlocked --rpc-url $R
cast send $SELLER "sell(address,uint256)" $POOL_E 573238000000000000000000 --from $LIQ --unlocked --rpc-url $R
```
The first sale (2.5M PT) passes, *page:* pool implied APY jumps from 5% to ~11%. The second **reverts**
(`custom error 0xfc68d09e` = `MarketProportionTooHigh`): the pool is full, the rest of the PT is stuck.

**1f. The fund's pocket.** The book table already shows it: PT-sUSDe went from `normal` ($990k) to
`exit still possible` ($981k, 16 h left) at 1a, and is now **`partly stuck`: about 100k PT sellable, 900k PT stuck**.
To prove it by hand, try selling the whole pocket:
```powershell
cast send $SELLER "sell(address,uint256)" $POOL_E 1000000000000000000000000 --from $FUND --unlocked --rpc-url $R
```
**Reverts**: the position is unsellable. The same command at step 1a would have passed: that is the 16 h window.
Then **reset**.

### Incident 2: a short dip does nothing (PT-sUSDe)

USDe at $0.96 for 12 h, then back, the Bybit-hack pattern:
```powershell
cast rpc anvil_setCode $FEED_USDE (forge inspect MockAggregator deployedBytecode) --rpc-url $R
cast send $FEED_USDE "setAnswer(int256)" 96000000 --from $DEV --unlocked --rpc-url $R
cast send $ORACLE_E "challenge()" --from $DEV --unlocked --rpc-url $R
cast rpc evm_increaseTime 43200 --rpc-url $R; cast rpc evm_mine --rpc-url $R
cast send $FEED_USDE "setAnswer(int256)" 99960000 --from $DEV --unlocked --rpc-url $R
cast rpc evm_increaseTime 14401 --rpc-url $R; cast rpc evm_mine --rpc-url $R
cast send $ORACLE_E "acceptChallenge()" --from $DEV --unlocked --rpc-url $R
```
The last command **reverts with `MODT: Deviation resolved`**: the oracle never switches, nobody is liquidated.
*Page:* challenged during the dip, back to normal after. The 16 h timelock filters short dips. Then **reset**.

### Incident 3: re.xyz writes reUSD down 2% (PT-reUSD)

```powershell
$CUR = ((cast call $SHARE_PRICE "getSharePrice()(uint256)" --rpc-url $R) -split " ")[0]
$NEW = [bigint]::Divide([bigint]::Parse($CUR) * 98, 100).ToString()
cast rpc anvil_setCode $SHARE_PRICE (forge inspect MockSharePrice deployedBytecode) --rpc-url $R
cast send $SHARE_PRICE "setSharePrice(uint256)" $NEW --from $DEV --unlocked --rpc-url $R
cast rpc evm_increaseTime 960 --rpc-url $R; cast rpc evm_mine --rpc-url $R
```
*Page:* share price 1.1062 → 1.0840. After the 16 minutes (the oracle averages the last 15) the oracle falls from
0.9818 to 0.9622 and **6 borrowers ($14.2M of debt) are unhealthy** on PT-reUSD/USDC. No challenge, no delay:
the exit window is one TWAP period. Then **reset**.

### Incident 4: panic in the PT-reUSD market

A whale dumps 4M PT-reUSD (this PT has 6 decimals), then 16 minutes pass:
```powershell
cast rpc anvil_setStorageAt $PT_R (cast index address $WHALEPANIC 0) (cast to-uint256 4000000000000) --rpc-url $R
cast send $PT_R "approve(address,uint256)" $SELLER $MAX --from $WHALEPANIC --unlocked --rpc-url $R
cast send $SELLER "sell(address,uint256)" $POOL_R 4000000000000 --from $WHALEPANIC --unlocked --rpc-url $R
cast rpc evm_increaseTime 960 --rpc-url $R; cast rpc evm_mine --rpc-url $R
```
*Page:* pool APY 11.8% → 16.0% right after the dump; 16 minutes later the oracle has followed (0.9818 → 0.9759)
and **1 borrower** is unhealthy. Compare with PT-sUSDe, whose oracle would not have moved at all. Then **reset**.

### Incident 5: USDS depegs 3% for more than 16 h (PT-sUSDS)

```powershell
cast rpc anvil_setCode $FEED_USDS (forge inspect MockAggregator deployedBytecode) --rpc-url $R
cast send $FEED_USDS "setAnswer(int256)" 97000000 --from $DEV --unlocked --rpc-url $R
cast send $ORACLE_S "challenge()" --from $DEV --unlocked --rpc-url $R
cast rpc evm_increaseTime 57601 --rpc-url $R; cast rpc evm_mine --rpc-url $R
cast send $ORACLE_S "acceptChallenge()" --from $DEV --unlocked --rpc-url $R
cast send $MORPHO "accrueInterest((address,address,address,address,uint256))" $MP_S --from $DEV --unlocked --rpc-url $R
```
*Page:* oracle on backup, **3 unhealthy borrowers, $4.8M of debt** on PT-sUSDS/USDC. Then **reset**.

### Incident 6: Pendle freezes the SY behind a PT (settlement layer)

Every PT is backed by an SY contract that Pendle's governance can pause. The three SYs simulated here share the same
owner, so this is one switch behind all three pockets. Freeze the PT-sUSDS one:
```powershell
$SY_S = "0xBe3d4ec488A0a042BB86F9176C24f8CD54018BA7"; $PENDLE_OWNER = "0x2aD631F72fB16d91c4953A7f4260A97C2fE2f31e"
cast rpc anvil_setBalance $PENDLE_OWNER 0x56BC75E2D63100000 --rpc-url $R
cast send $SY_S "pause()" --from $PENDLE_OWNER --unlocked --rpc-url $R
```
*Page:* the PT-sUSDS pocket turns **`stuck`** at once, "Pendle paused the SY, no exit until it is unpaused". No
oracle, no price move, no delay: an operational dependency, not a market one. Then **reset**.

### Incident coverage by dependency layer

| Layer (brief) | Incident | How it is replayed | Result for the pocket |
|---|---|---|---|
| 1. Settlement | Pendle pauses the SY | Incident 6, by hand | stuck at once, whatever the market |
| 2. Yield source & issuer | USDe / USDS depeg, reUSD NAV write-down | Incidents 1, 3, 5 and the automated sweeps | unsellable from 1% (sUSDe, reUSD) or 2% (sUSDS) |
| 2. Issuer's hedge venues | perp exchange hack | historical base rate + its ~4% USDe dip replayed as a depeg | see layer 2 |
| 3. Oracle | wrong Chainlink print for 16 h; short dip filtered by the timelock | automated `test_feedFailure`, incident 2 | wrongful liquidations, $823k bad debt at $0.80 |
| 4. PT market | whale dump; crowded exit; limit orders gone | incident 4, automated `test_ptPanic`, crowded-exit runs | sUSDe oracle blind, reUSD oracle follows; exit is a queue |
| 5. Lending | liquidation cascade; lender vault run | incident 1d-1e, automated cascades, `SusdsContagion` | pool saturated; PT-sUSDS borrow rate 4% to 18% |

Not replayed: an Ethereum outage or a bug inside Morpho or Pendle themselves.

### If something goes wrong
- `custom error 0xfc68d09e`: the Pendle pool refused the sale, it is full (`MarketProportionTooHigh`). Expected in 1e/1f.
- A pocket shows `not set up`: the fund has no PT there or did not approve the seller; rerun the end of step 0.
- `MODT: ...` messages come from the oracle's challenge rules (deviation not met, timelock not passed, resolved).
- A command fails with "insufficient funds": the sender has no ETH for gas, rerun the `anvil_setBalance` line.
- The panel does not move: check window 3 (forkwatch) is running and that you opened http://localhost:8765.
- `os error 10061` on any command: Anvil is not running (window 1 closed or stopped). Start it again, then redo step 0:
  a new Anvil has no snapshot, no seller and no fund positions. Window 3 can keep running, it reconnects by itself.

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
- Other sellers are modelled as a queue of PT sold ahead of the fund, not as a full behavioural model.
- The fork has no Pendle limit orders; live quotes look cheaper than the pool alone.
- The probability cohort is small (2 persistent depegs of 3%+) and biased towards survivors; for PT-reUSD it is a proxy.
- Borrower lists are fetched after the fork block; positions opened in between are missing.

The earlier live-data pipeline (`python -m defi_risk.report`) is kept for reference only: its cascade model assumed the
lending oracle follows the PT market, which the fork showed is false for PT-sUSDe.
