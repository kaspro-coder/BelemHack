#!/usr/bin/env bash
# Fork Ethereum at the pinned block, replay every scenario, rebuild the report and the dashboard data.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
export PATH="$HOME/.foundry/bin:$PATH"
RPC=http://127.0.0.1:8545
# --fresh: re-pin the fork to the latest block and refresh borrower lists. Positions move fast
# (one borrower can lever up within the hour), so results are only as fresh as the fork.
if [ "${1:-}" = "--fresh" ]; then
  echo $(( $(cast block-number --rpc-url "$ETH_RPC_URL") - 5 )) > sim/fork_block.txt
  cp sim/fork_block.txt data/fork_block.txt
  python sim/gen_borrowers.py
  taskkill //IM anvil.exe //F >/dev/null 2>&1 || pkill -f "anvil --fork-url" 2>/dev/null || true
  sleep 1
fi
BLOCK=${FORK_BLOCK:-$(cat sim/fork_block.txt)}

if ! cast block-number --rpc-url $RPC >/dev/null 2>&1; then
  echo "starting anvil fork at block $BLOCK"
  nohup anvil --fork-url "$ETH_RPC_URL" --fork-block-number "$BLOCK" --port 8545 --silent --auto-impersonate > data/anvil.log 2>&1 &
  for _ in $(seq 1 60); do cast block-number --rpc-url $RPC >/dev/null 2>&1 && break; sleep 1; done
fi
echo "fork at block $(cast block-number --rpc-url $RPC)"

(cd sim && forge test --fork-url $RPC)
(cd src && python -m defi_risk.sim_report && python -m defi_risk.portfolio && python -m defi_risk.dashboard)
echo "done: serve dashboard/ (python -m http.server 8765) and open http://localhost:8765"
