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

/// Shared building blocks for the controlled scenarios. Every scenario runs on an Anvil
/// fork of Ethereum mainnet, against the real deployed contracts.
abstract contract ScenarioBase is Test {
    IMorpho constant MORPHO = IMorpho(0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb);
    bytes32 constant MARKET_ID = 0x5613b170ded221c588b6e9637b910f49e5508680ceede207f44aa72e5c46cb05;
    IPendleMarket constant PENDLE = IPendleMarket(0x47ad2Cd1DD15739A7a035b9d3B7828d916FEF77E);
    IERC20 constant PT = IERC20(0xB195B618EA52b77CB2a58846F452f59f8dFa9390);
    IERC20 constant USDC = IERC20(0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48);
    IMetaOracle constant ORACLE = IMetaOracle(0xF8b29e7E9c00CE531434775f7923CC9fbCa01b08);
    address constant USDE_FEED = 0xa569d910839Ae8865Da8F8e70FfFb0cBA869F961;

    uint256 constant WAD = 1e18;
    address constant LIQUIDATOR = address(0x11C0DA7E);
    address constant FUND = address(0xBE1E3);

    MarketParams params;
    ISY sy;
    PtSeller seller;
    address[] borrowers;

    function setUp() public virtual {
        (address loan, address coll, address orc, address irm, uint256 lltv) = MORPHO.idToMarketParams(MARKET_ID);
        params = MarketParams(loan, coll, orc, irm, lltv);
        (address syAddr,,) = PENDLE.readTokens();
        sy = ISY(syAddr);
        seller = new PtSeller();
        borrowers = Borrowers.list();
        deal(address(USDC), LIQUIDATOR, 100_000_000e6);
        vm.prank(LIQUIDATOR);
        USDC.approve(address(MORPHO), type(uint256).max);
    }

    // ---------- price controls ----------

    /// Current USDe/USD answer of the real Chainlink feed (8 decimals), unless mocked.
    function usdePrice() internal view returns (uint256) {
        (, int256 answer,,,) = IAggregator(USDE_FEED).latestRoundData();
        return uint256(answer);
    }

    /// Makes the Chainlink USDe/USD feed report `price8` (8 decimals).
    function setUsdePrice(uint256 price8) internal {
        vm.mockCall(
            USDE_FEED,
            abi.encodeWithSelector(IAggregator.latestRoundData.selector),
            abi.encode(uint80(1), int256(price8), vm.getBlockTimestamp(), vm.getBlockTimestamp(), uint80(1))
        );
    }

    /// Runs the permissionless challenge and, after the timelock, accepts it.
    /// Returns true if the market ended up on the backup oracle.
    function challengeAndSwitch() internal returns (bool switched) {
        if (!ORACLE.isPrimary() || !ORACLE.isDeviant()) return false;
        ORACLE.challenge();
        vm.warp(vm.getBlockTimestamp() + ORACLE.challengeTimelockDuration() + 1);
        try ORACLE.acceptChallenge() {
            switched = true;
        } catch {}
    }

    // ---------- Morpho ----------

    function borrowAssets(address b) internal view returns (uint256) {
        (, uint128 shares,) = MORPHO.position(MARKET_ID, b);
        (,, uint128 tba, uint128 tbs,,) = MORPHO.market(MARKET_ID);
        return (uint256(shares) * (uint256(tba) + 1) + (uint256(tbs) + 1e6) - 1) / (uint256(tbs) + 1e6);
    }

    function collateralOf(address b) internal view returns (uint256) {
        (,, uint128 c) = MORPHO.position(MARKET_ID, b);
        return c;
    }

    /// Health factor (WAD) at the oracle price Morpho currently uses.
    function healthFactor(address b) internal view returns (uint256) {
        uint256 debt = borrowAssets(b);
        if (debt == 0) return type(uint256).max;
        uint256 maxBorrow = collateralOf(b) * ORACLE.price() / 1e36 * params.lltv / WAD;
        return maxBorrow * WAD / debt;
    }

    function countUnhealthy() internal view returns (uint256 n) {
        for (uint256 i; i < borrowers.length; i++) {
            if (healthFactor(borrowers[i]) < WAD) n++;
        }
    }

    function liquidationIncentive() internal view returns (uint256) {
        uint256 lif = WAD * WAD / (WAD - 0.3e18 * (WAD - params.lltv) / WAD);
        return lif > 1.15e18 ? 1.15e18 : lif;
    }

    struct Liquidations {
        uint256 count;
        uint256 seizedPt;
        uint256 repaidUsdc;
        uint256 badDebtUsdc;
        uint256 failed;
    }

    /// Liquidates every unhealthy borrower: full repayment when the collateral covers it,
    /// otherwise seizes all collateral and lets Morpho realise the bad debt.
    function liquidateAll() internal returns (Liquidations memory L) {
        MORPHO.accrueInterest(params);
        uint256 lif = liquidationIncentive();
        for (uint256 i; i < borrowers.length; i++) {
            address b = borrowers[i];
            if (healthFactor(b) >= WAD) continue;
            (, uint128 shares, uint128 coll) = MORPHO.position(MARKET_ID, b);
            uint256 debt = borrowAssets(b);
            uint256 collValue = uint256(coll) * ORACLE.price() / 1e36;
            uint256 ptBefore = PT.balanceOf(LIQUIDATOR);
            uint256 usdcBefore = USDC.balanceOf(LIQUIDATOR);
            vm.prank(LIQUIDATOR);
            try MORPHO.liquidate(
                params, b, collValue * WAD / lif >= debt ? 0 : coll, collValue * WAD / lif >= debt ? shares : 0, ""
            ) {
                uint256 repaid = usdcBefore - USDC.balanceOf(LIQUIDATOR);
                L.count++;
                L.seizedPt += PT.balanceOf(LIQUIDATOR) - ptBefore;
                L.repaidUsdc += repaid;
                if (repaid < debt && collateralOf(b) == 0) L.badDebtUsdc += debt - repaid;
            } catch {
                L.failed++;
            }
        }
    }

    // ---------- Pendle ----------

    struct Sale {
        uint256 soldPt;
        uint256 unsoldPt;
        uint256 syOut;
    }

    /// Sells `amount` PT held by `from` into the pool, in shrinking chunks when the pool
    /// refuses a trade that large. Whatever cannot be sold is reported as unsold.
    function sellPt(address from, uint256 amount) internal returns (Sale memory s) {
        vm.prank(from);
        PT.transfer(address(seller), amount);
        uint256 remaining = amount;
        uint256 chunk = amount;
        while (remaining > 0 && chunk >= 1_000e18) {
            if (chunk > remaining) chunk = remaining;
            try seller.sell(PENDLE, PT, chunk, from) returns (uint256 out) {
                s.soldPt += chunk;
                s.syOut += out;
                remaining -= chunk;
            } catch {
                chunk /= 2;
            }
        }
        s.unsoldPt = remaining;
    }

    /// USD value (6 decimals) of `syAmount` SY, at the current USDe/USD price.
    function syToUsd(uint256 syAmount) internal view returns (uint256) {
        return syAmount * sy.exchangeRate() / WAD * usdePrice() / 1e8 / 1e12;
    }

    function lnImpliedRate() internal view returns (uint256) {
        (,, uint96 r,,,) = PENDLE._storage();
        return r;
    }

    /// What the fund would actually receive (USD, 6 decimals) for selling `ptAmount` now.
    /// The sale is reverted afterwards: it measures, it does not change the scenario.
    function exitValue(uint256 ptAmount) internal returns (uint256 usd, uint256 unsold) {
        uint256 snap = vm.snapshotState();
        deal(address(PT), FUND, ptAmount);
        Sale memory s = sellPt(FUND, ptAmount);
        usd = syToUsd(s.syOut);
        unsold = s.unsoldPt;
        vm.revertToState(snap);
    }
}
