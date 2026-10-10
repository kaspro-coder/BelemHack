// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./ScenarioBase.sol";

/// PT-sUSDS-26NOV2026 (Sky). The USDC and USDT markets use a MetaOracle whose primary reads a
/// 15-minute TWAP of the Pendle pool (market-sensitive, like reUSD) and whose backup also reads
/// Chainlink USDS/USD behind a 16 h challenge (like sUSDe). The USDS market prices the PT with a
/// linear discount and lends USDS, so a USDS depeg does not move it.
contract SusdsScenarios is ScenarioBase {
    bytes32 constant USDC_MKT = 0x22fe4c688161863c73571a2b8db65cc11a4a6bceee4f0dea4aa83e4b784f1bd9;
    bytes32 constant USDT_MKT = 0x0367161b7cb23dfd03747dd3815d1c445b0437b648a6d50346249c6e7b92ff1b;
    bytes32 constant USDS_MKT = 0x9a8dab6de1059e6dc66c34b358764b70effb289e514e237f3161ffb09eaaf24f;
    IMetaOracle constant ORACLE = IMetaOracle(0x3464a61A68C486241FE07201C913F055Bdce35BF);
    address constant USDS_FEED = 0xfF30586cD0F29eD462364C7e81375FC0C71219b1;
    uint256 constant TWAP_WAIT = 16 minutes;
    uint256 constant MAX_ROUNDS = 8;
    uint256 T0;

    function setUp() public {
        setPool(0x9C560eBaF78e596cbcC27411d633a74D628dd7dC);
        addMarket(USDC_MKT, Borrowers.sUSDS_USDC());
        addMarket(USDT_MKT, Borrowers.sUSDS_USDT());
        addMarket(USDS_MKT, Borrowers.sUSDS_USDS());
        T0 = vm.getBlockTimestamp();
    }

    function _fundPt() internal view returns (uint256) {
        return 1_000_000 * ptUnit;
    }

    function _usdsPrice() internal view returns (uint256) {
        (, int256 a,,,) = IAggregator(USDS_FEED).latestRoundData();
        return uint256(a);
    }

    function _setUsds(uint256 price8) internal {
        vm.mockCall(USDS_FEED, abi.encodeWithSelector(IAggregator.latestRoundData.selector),
            abi.encode(uint80(1), int256(price8), vm.getBlockTimestamp(), vm.getBlockTimestamp(), uint80(1)));
    }

    /// Dollars (6 decimals) for SY: SY -> USDS (18 decimals) at the SY rate, then USDS/USD.
    function _usd(uint256 syAmount) internal view returns (uint256) {
        return syAmount * sy.exchangeRate() / WAD * _usdsPrice() / 1e8 / 1e12;
    }

    function _noLiq() internal view returns (Liquidations memory L) {
        L.badDebtByMarket = new uint256[](marketIds.length);
    }

    function test_susds_baseline() public {
        _open("susds_baseline");
        _row(string.concat(
            "{", _kv("oracle_usdc", oraclePrice(USDC_MKT)), ",", _kv("oracle_usds", oraclePrice(USDS_MKT)), ",",
            _kv("deviation", ORACLE.getDeviation()), ",", _kv("threshold", ORACLE.deviationThreshold()), ",",
            _kv("challenge_timelock", ORACLE.challengeTimelockDuration()), ",", _kv("unhealthy", countUnhealthy()), ",",
            _kv("ln_implied_rate", lnImpliedRate()), ",", _kv("timestamp", vm.getBlockTimestamp()), ",",
            _kv("expiry", PENDLE.expiry()), ",", _kv("usds_price", _usdsPrice()), "}"
        ));
        uint256[5] memory sizes = [uint256(100_000), 500_000, 1_000_000, 2_000_000, 4_000_000];
        for (uint256 i; i < sizes.length; i++) {
            (uint256 syOut, uint256 unsold) = exitSy(sizes[i] * ptUnit);
            _row(string.concat("{", _kv("exit_pt", sizes[i] * ptUnit), ",", _kv("exit_usd", _usd(syOut)), ",", _kv("unsold_pt", unsold), "}"));
        }
    }

    // cascade totals, in storage to keep the stack small (written to disk before any revert)
    uint256 cCount;
    uint256 cSeized;
    uint256 cBad;

    /// Liquidate, dump, wait one TWAP period, repeat until nobody new is liquidated.
    function _cascade(uint256 maxRounds) internal returns (uint256 rounds) {
        cCount = 0;
        cSeized = 0;
        cBad = 0;
        for (uint256 r = 1; r <= maxRounds; r++) {
            rounds = r;
            if (_oneRound()) break;
        }
    }

    function _oneRound() internal returns (bool done) {
        Liquidations memory L = liquidateAll();
        uint256 held = PT.balanceOf(LIQUIDATOR);
        if (held > 0) sellPt(LIQUIDATOR, held);
        cCount += L.count;
        cSeized += L.seizedPt;
        cBad += L.badDebt;
        if (L.count == 0) return true;
        vm.warp(vm.getBlockTimestamp() + TWAP_WAIT);
    }

    struct Outcome {
        uint256 severity;
        bool switched;
        uint256 rounds;
        uint256 oracleStart;
        uint256 oracleLow;
        uint256 exitT0;
        uint256 exitAfter;
        uint256 fundUnsold;
    }

    function _finish(Outcome memory o) internal {
        (uint256 afterSy, uint256 fundUnsold) = exitSy(_fundPt());
        o.exitAfter = _usd(afterSy);
        o.fundUnsold = fundUnsold;
        _row(string.concat(
            "{", _kv("severity", o.severity), ",", _kb("switched", o.switched), ",", _kv("rounds", o.rounds), ",",
            _kv("oracle_start", o.oracleStart), ",", _kv("oracle_low", o.oracleLow), ",",
            _kv("liquidated", cCount), ",", _kv("seized_pt", cSeized), ",",
            _kv("unsold_pt", PT.balanceOf(LIQUIDATOR)), ",", _kv("bad_debt", cBad), ",",
            _kv("ln_implied_rate", lnImpliedRate()), ",", _kv("fund_exit_t0", o.exitT0), ",",
            _kv("fund_exit_after", o.exitAfter), ",", _kv("fund_unsold_after", o.fundUnsold), "}"
        ));
    }

    function _depegCase(uint256 bps) internal {
        Outcome memory o;
        o.severity = bps;
        o.oracleStart = oraclePrice(USDC_MKT);
        _setUsds(1e8 * (10_000 - bps) / 10_000);
        (uint256 t0Sy,) = exitSy(_fundPt());
        o.exitT0 = _usd(t0Sy);
        if (ORACLE.isPrimary() && ORACLE.isDeviant()) {
            ORACLE.challenge();
            vm.warp(vm.getBlockTimestamp() + ORACLE.challengeTimelockDuration() + 1);
            try ORACLE.acceptChallenge() {
                o.switched = true;
            } catch {}
        }
        o.oracleLow = oraclePrice(USDC_MKT);
        o.rounds = _cascade(MAX_ROUNDS);
        _finish(o);
    }

    /// USDS depegs and stays: challenge + 16 h, then liquidations and dumps; the TWAP feeding
    /// the primary keeps falling as the pool fills, so later rounds can follow.
    function test_susds_usdsDepeg() public {
        _open("susds_depeg");
        uint256[7] memory depegs = [uint256(50), 100, 200, 300, 500, 1000, 2000];
        for (uint256 i; i < depegs.length; i++) {
            uint256 snap = vm.snapshotState();
            _depegCase(depegs[i]);
            vm.revertToState(snap);
            vm.clearMockedCalls();
            vm.warp(T0);
        }
    }

    function _panicCase(uint256 dumpPt, uint256 i) internal {
        Outcome memory o;
        o.severity = dumpPt;
        o.oracleStart = oraclePrice(USDC_MKT);
        address whale = address(uint160(0xD0D0 + i));
        deal(address(PT), whale, dumpPt);
        sellPt(whale, dumpPt);
        vm.warp(vm.getBlockTimestamp() + TWAP_WAIT);
        o.oracleLow = oraclePrice(USDC_MKT);
        o.rounds = _cascade(MAX_ROUNDS);
        _finish(o);
    }

    /// A whale dumps PT-sUSDS. The primary reads the pool's TWAP, so the dump reaches Morpho
    /// after 15 minutes with no challenge needed.
    function test_susds_panic() public {
        _open("susds_panic");
        uint256[5] memory dumps = [uint256(1_000_000), 2_000_000, 4_000_000, 8_000_000, 16_000_000];
        for (uint256 i; i < dumps.length; i++) {
            uint256 snap = vm.snapshotState();
            _panicCase(dumps[i] * ptUnit, i);
            vm.revertToState(snap);
            vm.warp(T0);
        }
    }
}
