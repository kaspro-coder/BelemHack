#!/usr/bin/env bash
# Fork Ethereum at the pinned block, replay every scenario, rebuild the report and the dashboard data.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
export PATH="$HOME/.foundry/bin:$PATH"
BLOCK=${FORK_BLOCK:-26164460}
RPC=http://127.0.0.1:8545

if ! cast block-number --rpc-url $RPC >/dev/null 2>&1; then
  echo "starting anvil fork at block $BLOCK"
  anvil --fork-url "$ETH_RPC_URL" --fork-block-number "$BLOCK" --port 8545 --silent --auto-impersonate > data/anvil.log 2>&1 &
  for _ in $(seq 1 60); do cast block-number --rpc-url $RPC >/dev/null 2>&1 && break; sleep 1; done
fi
echo "fork at block $(cast block-number --rpc-url $RPC)"

(cd sim && forge test --fork-url $RPC)
(cd src && python -m defi_risk.sim_report && python -m defi_risk.dashboard)
echo "done: serve dashboard/ (python -m http.server 8765) and open http://localhost:8765"
