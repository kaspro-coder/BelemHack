# BelemHack - DeFi Risk Dependency

EPFL Hackathon 2026, Belem Capital challenge.

Goal: given an on-chain position, discover its dependencies, estimate the economic
impact when one of them fails, and output a stay / exit signal.

## Pipeline
1. **Discover**: build the dependency graph of a position (chain, yield source, oracle, AMM, lending markets).
2. **Impact**: estimate the loss if each node is hit, including propagation.
3. **Exit cost**: slippage to unwind the position in the AMM.
4. **Decide**: expected loss if we stay vs. certain cost of exit.

## First reference case
PT-sUSDe-26NOV2026 (Pendle, Ethereum).

## Data sources (public, no API key)
- Pendle API: https://api-v2.pendle.finance
- DefiLlama: https://api.llama.fi
- Morpho GraphQL: https://blue-api.morpho.org/graphql
