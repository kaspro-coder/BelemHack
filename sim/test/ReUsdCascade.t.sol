// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./ScenarioBase.sol";

/// PT-reUSD-10DEC2026: the oracle reads a 15-minute TWAP of the Pendle pool itself
/// (Ojo -> Pendle Chainlink-compatible oracle). A dump in the pool therefore reaches the
/// oracle, triggers liquidations, whose PT is dumped in the same pool: a reflexive loop.
/// This replays the loop round by round on the real contracts.
contract ReUsdCascade is ScenarioBase {
    bytes32 constant USDC_MARKET = 0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64;
    bytes32 constant USDT_MARKET = 0x6acd18854e43f93f5a90446004c35c72a68af1ad99f08cb247782ce6457914ca;
    uint256 constant TWAP_WAIT = 16 minutes; // the feed averages the last 15 minutes
    uint256 constant MAX_ROUNDS = 10;
    uint256 T0;

    function setUp() public {
        setPool(0x13285bCbc27F92b47B4EDB99D744C07B48C977c0);
        addMarket(USDC_MARKET, Borrowers.reUSD_USDC());
        addMarket(USDT_MARKET, Borrowers.reUSD_USDT());
        T0 = vm.getBlockTimestamp();
    }

    function _fundPt() internal view returns (uint256) {
        return 1_000_000 * ptUnit;
    }

    function _assetValue(uint256 syAmount) internal view returns (uint256) {
        return syAmount * sy.exchangeRate() / WAD; // in the SY's asset (USDC, 6 decimals)
    }

    function test_reusd_baseline() public {
        _open("reusd_baseline");
        _row(string.concat(
            "{", _kv("oracle_price", oraclePrice(USDC_MARKET)), ",", _kv("unhealthy", countUnhealthy()), ",",
            _kv("ln_implied_rate", lnImpliedRate()), ",", _kv("sy_rate", sy.exchangeRate()), ",",
            _kv("borrowers_usdc", borrowersOf[USDC_MARKET].length), ",", _kv("borrowers_usdt", borrowersOf[USDT_MARKET].length), ",",
            _kv("timestamp", vm.getBlockTimestamp()), ",", _kv("expiry", PENDLE.expiry()), "}"
        ));
        uint256[6] memory sizes = [uint256(500_000), 1_000_000, 2_000_000, 5_000_000, 10_000_000, 20_000_000];
        for (uint256 i; i < sizes.length; i++) sizes[i] *= ptUnit;
        for (uint256 i; i < sizes.length; i++) {
            (uint256 syOut, uint256 unsold) = exitSy(sizes[i]);
            _row(string.concat("{", _kv("exit_pt", sizes[i]), ",", _kv("exit_asset", _assetValue(syOut)), ",", _kv("unsold_pt", unsold), "}"));
        }
    }

    /// A whale dumps `shock` PT, then the loop runs: TWAP catches up, unhealthy borrowers are
    /// liquidated, liquidators sell what they seized, until no one new is liquidated.
    function test_reusd_cascade() public {
        _open("reusd_cascade");
        uint256[5] memory shocks = [uint256(500_000), 1_000_000, 2_000_000, 4_000_000, 8_000_000];
        for (uint256 i; i < shocks.length; i++) shocks[i] *= ptUnit;
        (uint256 calmSy,) = exitSy(_fundPt());
        for (uint256 i; i < shocks.length; i++) {
            uint256 snap = vm.snapshotState();
            address whale = address(uint160(0xD0D0 + i));
            deal(address(PT), whale, shocks[i]);
            Sale memory first = sellPt(whale, shocks[i]);
            _round(shocks[i], 0, first.soldPt, first.unsoldPt, _noLiq(), calmSy);
            for (uint256 r = 1; r <= MAX_ROUNDS; r++) {
                vm.warp(vm.getBlockTimestamp() + TWAP_WAIT);
                Liquidations memory L = liquidateAll();
                uint256 held = PT.balanceOf(LIQUIDATOR);
                Sale memory s = held > 0 ? sellPt(LIQUIDATOR, held) : Sale(0, 0, 0);
                _round(shocks[i], r, s.soldPt, s.unsoldPt, L, calmSy);
                if (L.count == 0) break;
            }
            vm.revertToState(snap);
            vm.warp(T0);
        }
    }

    /// The issuer's own NAV feed (read by the SY exchange rate) is written down by `bps`.
    address constant SHARE_PRICE_FEED = 0xd1D104a7515989ac82F1AFDa15a23650411b05B8;

    function _writeDown(uint256 bps) internal {
        (bool ok, bytes memory r) = SHARE_PRICE_FEED.staticcall(abi.encodeWithSignature("getSharePrice()"));
        require(ok, "share price");
        uint256 p = abi.decode(r, (uint256));
        vm.mockCall(SHARE_PRICE_FEED, abi.encodeWithSignature("getSharePrice()"), abi.encode(p * (10_000 - bps) / 10_000));
    }

    /// re.xyz marks reUSD down (e.g. a reinsurance loss). Then the same loop: oracle,
    /// liquidations, liquidators dump PT, repeat.
    function test_reusd_writedown() public {
        _open("reusd_writedown");
        uint256[7] memory cuts = [uint256(100), 200, 300, 500, 700, 1000, 2000];
        (uint256 calmSy,) = exitSy(_fundPt());
        for (uint256 i; i < cuts.length; i++) {
            uint256 snap = vm.snapshotState();
            _writeDown(cuts[i]);
            _round(cuts[i], 0, 0, 0, _noLiq(), calmSy);
            for (uint256 r = 1; r <= MAX_ROUNDS; r++) {
                vm.warp(vm.getBlockTimestamp() + TWAP_WAIT);
                Liquidations memory L = liquidateAll();
                uint256 held = PT.balanceOf(LIQUIDATOR);
                Sale memory s = held > 0 ? sellPt(LIQUIDATOR, held) : Sale(0, 0, 0);
                _round(cuts[i], r, s.soldPt, s.unsoldPt, L, calmSy);
                if (L.count == 0) break;
            }
            vm.revertToState(snap);
            vm.clearMockedCalls();
            vm.warp(T0);
        }
    }

    /// Same write-downs, flash-loan liquidators: they stop when the pool is full. Measures the
    /// debt left unhealthy with the lenders instead of PT stuck with liquidators.
    function test_reusd_writedown_prudent() public {
        _open("reusd_writedown_prudent");
        uint256[7] memory cuts = [uint256(100), 200, 300, 500, 700, 1000, 2000];
        for (uint256 i; i < cuts.length; i++) {
            uint256 snap = vm.snapshotState();
            _writeDown(cuts[i]);
            for (uint256 r = 1; r <= MAX_ROUNDS; r++) {
                vm.warp(vm.getBlockTimestamp() + TWAP_WAIT);
                Prudent memory P = liquidatePrudent();
                (uint256 fundSy, uint256 fundUnsold) = exitSy(_fundPt());
                _row(string.concat(
                    "{", _kv("cut_bps", cuts[i]), ",", _kv("round", r), ",", _kv("oracle_price", oraclePrice(USDC_MARKET)), ",",
                    _kv("liquidated", P.count), ",", _kv("skipped", P.skipped), ",", _kv("seized_pt", P.seizedPt), ",",
                    _kv("debt_at_risk", P.debtAtRisk), ",", _kv("underwater", P.underwater), ",",
                    _kv("fund_exit", _assetValue(fundSy)), ",", _kv("fund_unsold", fundUnsold), "}"
                ));
                if (P.count == 0) break;
            }
            vm.revertToState(snap);
            vm.clearMockedCalls();
            vm.warp(T0);
        }
    }

    /// Inside the 15-minute window after a 1% write-down, others sell before the fund.
    function test_reusd_crowdedExit() public {
        _open("reusd_crowd_exit");
        _writeDown(100);
        uint256[6] memory crowd = [uint256(0), 1_000_000, 2_000_000, 3_000_000, 4_000_000, 6_000_000];
        for (uint256 j; j < crowd.length; j++) {
            (uint256 syOut, uint256 unsold) = exitAfterCrowd(crowd[j] * ptUnit, _fundPt());
            _row(string.concat("{", _kv("severity_bps", 100), ",", _kv("crowd_pt", crowd[j] * ptUnit), ",",
                _kv("fund_exit", _assetValue(syOut)), ",", _kv("fund_unsold", unsold), "}"));
        }
        vm.clearMockedCalls();
    }

    function _noLiq() internal view returns (Liquidations memory L) {
        L.badDebtByMarket = new uint256[](marketIds.length);
    }

    function _round(uint256 shock, uint256 round, uint256 sold, uint256 unsold, Liquidations memory L, uint256 calmSy) internal {
        (uint256 fundSy, uint256 fundUnsold) = exitSy(_fundPt());
        _row(string.concat(
            "{", _kv("shock_pt", shock), ",", _kv("round", round), ",",
            _kv("oracle_price", oraclePrice(USDC_MARKET)), ",", _kv("unhealthy_after", countUnhealthy()), ",",
            _kv("liquidated", L.count), ",", _kv("liq_failed", L.failed), ",", _kv("seized_pt", L.seizedPt), ",",
            _kv("repaid", L.repaid), ",", _kv("bad_debt", L.badDebt), ",",
            _kv("bad_debt_usdc_mkt", L.badDebtByMarket[0]), ",", _kv("bad_debt_usdt_mkt", L.badDebtByMarket[1]), ",",
            _kv("sold_pt", sold), ",", _kv("unsold_pt", unsold), ",", _kv("ln_implied_rate", lnImpliedRate()), ",",
            _kv("fund_exit_calm", _assetValue(calmSy)), ",", _kv("fund_exit", _assetValue(fundSy)), ",",
            _kv("fund_unsold", fundUnsold), "}"
        ));
    }
}
