// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

interface IERC20 {
    function balanceOf(address) external view returns (uint256);
    function transfer(address, uint256) external returns (bool);
    function approve(address, uint256) external returns (bool);
}

struct MarketParams {
    address loanToken;
    address collateralToken;
    address oracle;
    address irm;
    uint256 lltv;
}

interface IMorpho {
    function idToMarketParams(bytes32 id)
        external view returns (address loanToken, address collateralToken, address oracle, address irm, uint256 lltv);
    function position(bytes32 id, address user)
        external view returns (uint256 supplyShares, uint128 borrowShares, uint128 collateral);
    function market(bytes32 id)
        external view
        returns (
            uint128 totalSupplyAssets,
            uint128 totalSupplyShares,
            uint128 totalBorrowAssets,
            uint128 totalBorrowShares,
            uint128 lastUpdate,
            uint128 fee
        );
    function accrueInterest(MarketParams memory params) external;
    function liquidate(
        MarketParams memory params,
        address borrower,
        uint256 seizedAssets,
        uint256 repaidShares,
        bytes memory data
    ) external returns (uint256, uint256);
}

interface IOracle {
    function price() external view returns (uint256);
}

/// Steakhouse MetaOracleDeviationTimelock (primary/backup with challenge).
interface IMetaOracle is IOracle {
    function primaryPrice() external view returns (uint256);
    function backupPrice() external view returns (uint256);
    function isPrimary() external view returns (bool);
    function isDeviant() external view returns (bool);
    function getDeviation() external view returns (uint256);
    function deviationThreshold() external view returns (uint256);
    function challengeTimelockDuration() external view returns (uint256);
    function challenge() external;
    function acceptChallenge() external;
    function revokeChallenge() external;
}

interface IAggregator {
    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80);
}

interface IPendleMarket {
    function readTokens() external view returns (address sy, address pt, address yt);
    function expiry() external view returns (uint256);
    function _storage()
        external view
        returns (int128 totalPt, int128 totalSy, uint96 lastLnImpliedRate, uint16, uint16, uint16);
    function swapExactPtForSy(address receiver, uint256 exactPtIn, bytes calldata data)
        external returns (uint256 netSyOut, uint256 netSyFee);
}

interface ISY {
    function exchangeRate() external view returns (uint256);
}

struct Market {
    uint128 totalSupplyAssets;
    uint128 totalSupplyShares;
    uint128 totalBorrowAssets;
    uint128 totalBorrowShares;
    uint128 lastUpdate;
    uint128 fee;
}

interface IIrm {
    function borrowRateView(MarketParams memory params, Market memory market) external view returns (uint256);
}

interface IMorphoWithdraw {
    function withdraw(MarketParams memory params, uint256 assets, uint256 shares, address onBehalf, address receiver)
        external returns (uint256, uint256);
}
