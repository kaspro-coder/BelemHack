// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./ScenarioBase.sol";

/// Cross-token contagion. Smokehouse USDT lends both to PT-reUSD/USDT (38% of that market)
/// and to PT-sUSDS/USDT (83% of that market). If a reUSD loss makes its depositors run, the
/// vault pulls its money out of the sUSDS market. Replays that withdrawal on the real contracts
/// and measures what PT-sUSDS borrowers then face.
contract SusdsContagion is ScenarioBase {
    bytes32 constant SUSDS_USDT = 0x0367161b7cb23dfd03747dd3815d1c445b0437b648a6d50346249c6e7b92ff1b;
    address constant SMOKEHOUSE_USDT = 0xA0804346780b4c2e3bE118ac957D1DB82F9d7484;
    address constant SUSDS_POOL = 0x9C560eBaF78e596cbcC27411d633a74D628dd7dC;

    function setUp() public {
        setPool(SUSDS_POOL);
        addMarket(SUSDS_USDT, new address[](0));
    }

    function _state() internal view returns (uint256 util, uint256 borrowApr, uint256 liquidity) {
        (uint128 tsa, uint128 tss, uint128 tba, uint128 tbs, uint128 lu, uint128 fee) = MORPHO.market(SUSDS_USDT);
        util = tsa == 0 ? 0 : uint256(tba) * WAD / tsa;
        uint256 perSecond = IIrm(paramsOf[SUSDS_USDT].irm).borrowRateView(paramsOf[SUSDS_USDT], Market(tsa, tss, tba, tbs, lu, fee));
        borrowApr = perSecond * 365 days;
        liquidity = tsa - tba;
    }

    function _vaultAssets() internal view returns (uint256) {
        (uint256 shares,,) = MORPHO.position(SUSDS_USDT, SMOKEHOUSE_USDT);
        (uint128 tsa, uint128 tss,,,,) = MORPHO.market(SUSDS_USDT);
        return shares * (uint256(tsa) + 1) / (uint256(tss) + 1e6);
    }

    function _snap(string memory step, uint256 hoursAfter) internal {
        (uint256 util, uint256 apr, uint256 liq) = _state();
        _row(string.concat(
            '{"step":"', step, '",', _kv("hours", hoursAfter), ",", _kv("utilization", util), ",",
            _kv("borrow_apr", apr), ",", _kv("liquidity", liq), ",", _kv("vault_assets", _vaultAssets()), ",",
            _kv("pt_ln_implied_rate", lnImpliedRate()), "}"
        ));
    }

    function test_vaultRun() public {
        _open("susds_contagion");
        _snap("before", 0);
        MORPHO.accrueInterest(paramsOf[SUSDS_USDT]);
        (,, uint256 liq) = _state();
        uint256 want = _vaultAssets();
        uint256 take = want < liq ? want : liq;
        vm.prank(SMOKEHOUSE_USDT);
        IMorphoWithdraw(address(MORPHO)).withdraw(paramsOf[SUSDS_USDT], take, 0, SMOKEHOUSE_USDT, SMOKEHOUSE_USDT);
        _snap("vault_withdraws_all_it_can", 0);
        uint256[4] memory later = [uint256(24), 72, 168, 336];
        uint256 t0 = vm.getBlockTimestamp();
        for (uint256 i; i < later.length; i++) {
            vm.warp(t0 + later[i] * 1 hours);
            MORPHO.accrueInterest(paramsOf[SUSDS_USDT]);
            _snap("no_one_repays", later[i]);
        }
    }
}
