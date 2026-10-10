// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./ScenarioBase.sol";

/// Controlled scenarios on PT-sUSDe-26NOV2026, replayed on the real contracts.
/// Run: forge test --fork-url http://127.0.0.1:8545 -vv
/// Each test writes out-scenarios/<name>.json for the Python decision layer.
contract Scenarios is ScenarioBase {
    uint256 constant FUND_PT = 1_000_000e18; // the fund's position, ~ $0.99M
    string out; // current output file; rows go straight to disk so state reverts cannot erase them
    uint256 T0;

    function setUp() public override {
        super.setUp();
        T0 = vm.getBlockTimestamp();
    }

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
                _kv("repaid_usdc", L.repaidUsdc), ",", _kv("bad_debt_usdc", L.badDebtUsdc), ",",
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
            Liquidations memory L = switched ? liquidateAll() : Liquidations(0, 0, 0, 0, 0);
            _row(string.concat(
                "{", _kv("hours_depegged", hoursDown[i]), ",", _kb("switched", switched), ",",
                _kv("liquidated", L.count), ",", _kv("seized_pt", L.seizedPt), ",", _kv("bad_debt_usdc", L.badDebtUsdc), "}"
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
                _kv("seized_pt", L.seizedPt), ",", _kv("repaid_usdc", L.repaidUsdc), ",",
                _kv("bad_debt_usdc", L.badDebtUsdc), ",", _kv("sold_pt", s.soldPt), ",",
                _kv("unsold_pt", s.unsoldPt), ",", _kv("fund_exit_after", exitAfter), "}"
            ));
            vm.revertToState(snap);
            vm.clearMockedCalls();
            vm.warp(T0);
        }
    }
}
