// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Test.sol";
import "../src/Interfaces.sol";
import "../src/Borrowers.sol";

/// Sells PT into the Pendle pool atomically: transfer + swap in one call, so a refused
/// swap rolls the transfer back instead of donating PT to the pool.
contract PtSeller {
    function sell(IPendleMarket market, IERC20 pt, uint256 amount, address receiver) external returns (uint256 syOut) {
        pt.transfer(address(market), amount);
        (syOut,) = market.swapExactPtForSy(receiver, amount, "");
    }
}

/// Shared building blocks for controlled scenarios on an Anvil fork of Ethereum mainnet.
/// A scenario covers one Pendle pool and every Morpho market that takes its PT as collateral.
abstract contract ScenarioBase is Test {
    IMorpho constant MORPHO = IMorpho(0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb);
    uint256 constant WAD = 1e18;
    address constant LIQUIDATOR = address(0x11C0DA7E);
    address constant FUND = address(0xBE1E3);

    IPendleMarket PENDLE;
    IERC20 PT;
    uint256 ptUnit; // 10 ** PT decimals (18 for PT-sUSDe, 6 for PT-reUSD)
    ISY sy;
    PtSeller seller;

    bytes32[] marketIds;
    mapping(bytes32 => MarketParams) paramsOf;
    mapping(bytes32 => address[]) borrowersOf;

    /// Scenario contracts call this in setUp for every Morpho market of the pool.
    function addMarket(bytes32 id, address[] memory borrowers) internal {
        (address loan, address coll, address orc, address irm, uint256 lltv) = MORPHO.idToMarketParams(id);
        paramsOf[id] = MarketParams(loan, coll, orc, irm, lltv);
        borrowersOf[id] = borrowers;
        marketIds.push(id);
        deal(loan, LIQUIDATOR, 500_000_000 * 10 ** _decimals(loan));
        vm.prank(LIQUIDATOR);
        (bool ok,) = loan.call(abi.encodeWithSelector(IERC20.approve.selector, address(MORPHO), type(uint256).max));
        require(ok, "approve failed"); // low-level: USDT's approve returns nothing
    }

    function setPool(address pendleMarket) internal {
        PENDLE = IPendleMarket(pendleMarket);
        (address syAddr, address pt,) = PENDLE.readTokens();
        PT = IERC20(pt);
        ptUnit = 10 ** _decimals(pt);
        sy = ISY(syAddr);
        seller = new PtSeller();
    }

    function _decimals(address token) internal view returns (uint256) {
        (bool ok, bytes memory r) = token.staticcall(abi.encodeWithSignature("decimals()"));
        return ok ? abi.decode(r, (uint8)) : 18;
    }

    // ---------- Morpho ----------

    function borrowAssets(bytes32 id, address b) internal view returns (uint256) {
        (, uint128 shares,) = MORPHO.position(id, b);
        (,, uint128 tba, uint128 tbs,,) = MORPHO.market(id);
        return (uint256(shares) * (uint256(tba) + 1) + (uint256(tbs) + 1e6) - 1) / (uint256(tbs) + 1e6);
    }

    function collateralOf(bytes32 id, address b) internal view returns (uint256) {
        (,, uint128 c) = MORPHO.position(id, b);
        return c;
    }

    function oraclePrice(bytes32 id) internal view returns (uint256) {
        return IOracle(paramsOf[id].oracle).price();
    }

    /// Health factor (WAD) at the oracle price Morpho uses.
    function healthFactor(bytes32 id, address b) internal view returns (uint256) {
        uint256 debt = borrowAssets(id, b);
        if (debt == 0) return type(uint256).max;
        uint256 maxBorrow = collateralOf(id, b) * oraclePrice(id) / 1e36 * paramsOf[id].lltv / WAD;
        return maxBorrow * WAD / debt;
    }

    function countUnhealthy() internal view returns (uint256 n) {
        for (uint256 m; m < marketIds.length; m++) {
            address[] storage bs = borrowersOf[marketIds[m]];
            for (uint256 i; i < bs.length; i++) {
                if (healthFactor(marketIds[m], bs[i]) < WAD) n++;
            }
        }
    }

    function liquidationIncentive(uint256 lltv) internal pure returns (uint256) {
        uint256 lif = WAD * WAD / (WAD - 0.3e18 * (WAD - lltv) / WAD);
        return lif > 1.15e18 ? 1.15e18 : lif;
    }

    struct Liquidations {
        uint256 count;
        uint256 seizedPt;
        uint256 repaid; // loan-token units, all loan tokens here have 6 decimals
        uint256 badDebt;
        uint256 failed;
    }

    /// Liquidates every unhealthy borrower in every market: full repayment when the collateral
    /// covers it, otherwise seizes all collateral and lets Morpho realise the bad debt.
    function liquidateAll() internal returns (Liquidations memory L) {
        for (uint256 m; m < marketIds.length; m++) {
            bytes32 id = marketIds[m];
            MarketParams memory p = paramsOf[id];
            MORPHO.accrueInterest(p);
            uint256 lif = liquidationIncentive(p.lltv);
            address[] storage bs = borrowersOf[id];
            for (uint256 i; i < bs.length; i++) {
                if (healthFactor(id, bs[i]) >= WAD) continue;
                _liquidate(id, p, bs[i], lif, L);
            }
        }
    }

    function _liquidate(bytes32 id, MarketParams memory p, address b, uint256 lif, Liquidations memory L) private {
        (, uint128 shares, uint128 coll) = MORPHO.position(id, b);
        uint256 debt = borrowAssets(id, b);
        bool covers = uint256(coll) * oraclePrice(id) / 1e36 * WAD / lif >= debt;
        uint256 ptBefore = PT.balanceOf(LIQUIDATOR);
        uint256 loanBefore = IERC20(p.loanToken).balanceOf(LIQUIDATOR);
        vm.prank(LIQUIDATOR);
        try MORPHO.liquidate(p, b, covers ? 0 : coll, covers ? shares : 0, "") {
            uint256 repaid = loanBefore - IERC20(p.loanToken).balanceOf(LIQUIDATOR);
            L.count++;
            L.seizedPt += PT.balanceOf(LIQUIDATOR) - ptBefore;
            L.repaid += repaid;
            if (repaid < debt && collateralOf(id, b) == 0) L.badDebt += debt - repaid;
        } catch {
            L.failed++;
        }
    }

    // ---------- Pendle ----------

    struct Sale {
        uint256 soldPt;
        uint256 unsoldPt;
        uint256 syOut;
    }

    /// Sells `amount` PT held by `from` into the pool, in shrinking chunks when the pool
    /// refuses a trade that large. Whatever cannot be sold is handed back and reported.
    function sellPt(address from, uint256 amount) internal returns (Sale memory s) {
        vm.prank(from);
        PT.transfer(address(seller), amount);
        uint256 remaining = amount;
        uint256 chunk = amount;
        while (remaining > 0 && chunk >= 1_000 * ptUnit) {
            if (chunk > remaining) chunk = remaining;
            try seller.sell(PENDLE, PT, chunk, from) returns (uint256 got) {
                s.soldPt += chunk;
                s.syOut += got;
                remaining -= chunk;
            } catch {
                chunk /= 2;
            }
        }
        s.unsoldPt = remaining;
        if (remaining > 0) {
            vm.prank(address(seller));
            PT.transfer(from, remaining);
        }
    }

    function lnImpliedRate() internal view returns (uint256) {
        (,, uint96 r,,,) = PENDLE._storage();
        return r;
    }

    /// SY received for selling `ptAmount` now; the sale is reverted afterwards.
    function exitSy(uint256 ptAmount) internal returns (uint256 syOut, uint256 unsold) {
        uint256 snap = vm.snapshotState();
        deal(address(PT), FUND, ptAmount);
        Sale memory s = sellPt(FUND, ptAmount);
        syOut = s.syOut;
        unsold = s.unsoldPt;
        vm.revertToState(snap);
    }

    // ---------- output ----------

    string out; // rows go straight to disk so state reverts cannot erase them

    function _open(string memory name) internal {
        out = string.concat("out-scenarios/", name, ".jsonl");
        vm.writeFile(out, "");
    }

    function _row(string memory r) internal {
        vm.writeLine(out, r);
    }

    function _kv(string memory k, uint256 v) internal pure returns (string memory) {
        return string.concat('"', k, '":', vm.toString(v));
    }

    function _kb(string memory k, bool v) internal pure returns (string memory) {
        return string.concat('"', k, '":', v ? "true" : "false");
    }
}
