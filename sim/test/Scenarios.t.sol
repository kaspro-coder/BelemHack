// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./ScenarioBase.sol";

/// Controlled scenarios on PT-sUSDe-26NOV2026, replayed on the real contracts.
/// Run: forge test --fork-url http://127.0.0.1:8545 -vv
/// Each test writes out-scenarios/<name>.json for the Python decision layer.
contract Scenarios is ScenarioBase {
    bytes32 constant MARKET_ID = 0x5613b170ded221c588b6e9637b910f49e5508680ceede207f44aa72e5c46cb05;
    IMetaOracle constant ORACLE = IMetaOracle(0xF8b29e7E9c00CE531434775f7923CC9fbCa01b08);
    address constant USDE_FEED = 0xa569d910839Ae8865Da8F8e70FfFb0cBA869F961;
    uint256 constant FUND_PT = 1_000_000e18; // the fund's position, ~ $0.99M
    uint256 T0;

    function setUp() public {
        setPool(0x47ad2Cd1DD15739A7a035b9d3B7828d916FEF77E);
        addMarket(MARKET_ID, Borrowers.sUSDe_USDC());
        T0 = vm.getBlockTimestamp();
    }

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
    function challengeAndSwitch() internal returns (bool switched) {
        if (!ORACLE.isPrimary() || !ORACLE.isDeviant()) return false;
        ORACLE.challenge();
        vm.warp(vm.getBlockTimestamp() + ORACLE.challengeTimelockDuration() + 1);
        try ORACLE.acceptChallenge() {
            switched = true;
        } catch {}
    }

    /// USD value (6 decimals) of `syAmount` SY, at the current USDe/USD price.
    function syToUsd(uint256 syAmount) internal view returns (uint256) {
        return syAmount * sy.exchangeRate() / WAD * usdePrice() / 1e8 / 1e12;
    }

    /// What the fund would actually receive (USD, 6 decimals) for selling `ptAmount` now.
    function exitValue(uint256 ptAmount) internal returns (uint256 usd, uint256 unsold) {
        (uint256 syOut, uint256 u) = exitSy(ptAmount);
        return (syToUsd(syOut), u);
    }

    function _noLiq() internal view returns (Liquidations memory L) {
        L.badDebtByMarket = new uint256[](marketIds.length);
    }

    /// Calm market: oracle state and the real cost of exiting at several sizes.
    function test_baseline() public {
        _open("baseline");
        string memory r = string.concat(
            "{", _kv("oracle_price", ORACLE.price()), ",", _kv("primary_price", ORACLE.primaryPrice()), ",",
            _kv("backup_price", ORACLE.backupPrice()), ",", _kv("deviation", ORACLE.getDeviation()), ",",
            _kv("threshold", ORACLE.deviationThreshold()), ",",
            _kv("challenge_timelock", ORACLE.challengeTimelockDuration()), ",", _kv("usde_price", usdePrice()), ",",
            _kv("ln_implied_rate", lnImpliedRate()), ",", _kv("unhealthy", countUnhealthy()), ",",
            _kv("timestamp", vm.getBlockTimestamp()), ",", _kv("expiry", PENDLE.expiry()), "}"
        );
        _row(r);
        uint256[7] memory sizes = [uint256(100_000e18), 500_000e18, 1_000_000e18, 2_000_000e18, 3_000_000e18, 4_000_000e18, 6_000_000e18];
        for (uint256 i; i < sizes.length; i++) {
            (uint256 usd, uint256 unsold) = exitValue(sizes[i]);
            _row(string.concat("{", _kv("exit_pt", sizes[i]), ",", _kv("exit_usd", usd), ",", _kv("unsold_pt", unsold), "}"));
        }
    }

    /// USDe depegs by `bps` and stays there. Steps: oracle reaction, challenge + 16h,
    /// switch to backup, liquidations, liquidators dump the PT, fund's exit value.
    function test_usdeDepeg() public {
        _open("usde_depeg");
        uint256[8] memory depegs = [uint256(50), 75, 100, 200, 300, 400, 500, 1000];
        (uint256 calmExit,) = exitValue(FUND_PT);
        for (uint256 i; i < depegs.length; i++) {
            uint256 snap = vm.snapshotState();
            uint256 bps = depegs[i];
            setUsdePrice(1e8 * (10_000 - bps) / 10_000);

            uint256 priceT0 = ORACLE.price();
            uint256 unhealthyT0 = countUnhealthy();
            bool deviant = ORACLE.isDeviant();
            (uint256 exitT0,) = exitValue(FUND_PT);

            bool switched = challengeAndSwitch();
            uint256 priceT1 = ORACLE.price();
            uint256 unhealthyT1 = countUnhealthy();
            Liquidations memory L = liquidateAll();
            Sale memory s = L.seizedPt > 0 ? sellPt(LIQUIDATOR, L.seizedPt) : Sale(0, 0, 0);
            (uint256 exitT2, uint256 fundUnsold) = exitValue(FUND_PT);

            _row(string.concat(
                "{", _kv("depeg_bps", bps), ",", _kb("deviant", deviant), ",", _kb("switched", switched), ",",
                _kv("oracle_t0", priceT0), ",", _kv("oracle_t1", priceT1), ",",
                _kv("unhealthy_t0", unhealthyT0), ",", _kv("unhealthy_t1", unhealthyT1), ",",
                _kv("liquidated", L.count), ",", _kv("liq_failed", L.failed), ",", _kv("seized_pt", L.seizedPt), ",",
                _kv("repaid_usdc", L.repaid), ",", _kv("bad_debt_usdc", L.badDebt), ",",
                _kv("sold_pt", s.soldPt), ",", _kv("unsold_pt", s.unsoldPt), ",",
                _kv("ln_implied_rate_after", lnImpliedRate()), ",",
                _kv("fund_exit_calm", calmExit), ",", _kv("fund_exit_t0", exitT0), ",",
                _kv("fund_exit_after", exitT2), ",", _kv("fund_unsold_after", fundUnsold), "}"
            ));
            vm.revertToState(snap);
            vm.clearMockedCalls();
            vm.warp(T0);
        }
    }

    /// Bybit-like dip: USDe at -4%, then recovers. Does it last long enough to switch the oracle?
    function test_shortDip() public {
        _open("short_dip");
        uint256[4] memory hoursDown = [uint256(6), 12, 15, 24];
        for (uint256 i; i < hoursDown.length; i++) {
            uint256 snap = vm.snapshotState();
            setUsdePrice(0.96e8);
            ORACLE.challenge();
            vm.warp(vm.getBlockTimestamp() + hoursDown[i] * 1 hours);
            if (hoursDown[i] * 1 hours < ORACLE.challengeTimelockDuration()) {
                setUsdePrice(1e8); // recovered before the timelock ends
                vm.warp(vm.getBlockTimestamp() + ORACLE.challengeTimelockDuration());
            }
            bool switched;
            try ORACLE.acceptChallenge() {
                switched = true;
            } catch {}
            Liquidations memory L = switched ? liquidateAll() : _noLiq();
            _row(string.concat(
                "{", _kv("hours_depegged", hoursDown[i]), ",", _kb("switched", switched), ",",
                _kv("liquidated", L.count), ",", _kv("seized_pt", L.seizedPt), ",", _kv("bad_debt_usdc", L.badDebt), "}"
            ));
            vm.revertToState(snap);
            vm.clearMockedCalls();
            vm.warp(T0);
        }
    }

    /// Panic in the PT market itself: a whale dumps PT. Measures the real rate shock and
    /// checks whether Morpho's oracle notices (it reads a linear discount, not the market).
    function test_ptPanic() public {
        _open("pt_panic");
        uint256[6] memory dumps = [uint256(500_000e18), 1_000_000e18, 2_000_000e18, 3_000_000e18, 4_000_000e18, 8_000_000e18];
        uint256 oracleBefore = ORACLE.price();
        for (uint256 i; i < dumps.length; i++) {
            uint256 snap = vm.snapshotState();
            address whale = address(uint160(0xD0D0 + i));
            deal(address(PT), whale, dumps[i]);
            Sale memory s = sellPt(whale, dumps[i]);
            (uint256 exitAfter,) = exitValue(FUND_PT);
            _row(string.concat(
                "{", _kv("dump_pt", dumps[i]), ",", _kv("sold_pt", s.soldPt), ",", _kv("unsold_pt", s.unsoldPt), ",",
                _kv("sy_out", s.syOut), ",", _kv("ln_implied_rate_after", lnImpliedRate()), ",",
                _kv("oracle_before", oracleBefore), ",", _kv("oracle_after", ORACLE.price()), ",",
                _kv("unhealthy", countUnhealthy()), ",", _kv("fund_exit_after", exitAfter), "}"
            ));
            vm.revertToState(snap);
            vm.clearMockedCalls();
            vm.warp(T0);
        }
    }

    /// The backup feed misreports: Chainlink USDe/USD prints a wrong price for 16h+.
    /// Because the challenge is permissionless, anyone can force the switch.
    function test_feedFailure() public {
        _open("feed_failure");
        uint256[3] memory wrong = [uint256(0.95e8), 0.90e8, 0.80e8];
        for (uint256 i; i < wrong.length; i++) {
            uint256 snap = vm.snapshotState();
            setUsdePrice(wrong[i]);
            bool switched = challengeAndSwitch();
            Liquidations memory L = liquidateAll();
            setUsdePrice(1e8); // the real USDe never moved: value the dump at the true price
            Sale memory s = L.seizedPt > 0 ? sellPt(LIQUIDATOR, L.seizedPt) : Sale(0, 0, 0);
            (uint256 exitAfter,) = exitValue(FUND_PT);
            _row(string.concat(
                "{", _kv("wrong_price", wrong[i]), ",", _kb("switched", switched), ",", _kv("liquidated", L.count), ",",
                _kv("seized_pt", L.seizedPt), ",", _kv("repaid_usdc", L.repaid), ",",
                _kv("bad_debt_usdc", L.badDebt), ",", _kv("sold_pt", s.soldPt), ",",
                _kv("unsold_pt", s.unsoldPt), ",", _kv("fund_exit_after", exitAfter), "}"
            ));
            vm.revertToState(snap);
            vm.clearMockedCalls();
            vm.warp(T0);
        }
    }
}
