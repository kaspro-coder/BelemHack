// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "./Interfaces.sol";

/// Stand-ins installed on the local Anvil fork with `anvil_setCode` during a live demo.
/// They replace a real feed's code at its own address, so every contract that reads the feed
/// (Morpho oracles, Pendle SY) sees the price set by hand. `evm_revert` restores the real code.

/// Replaces a Chainlink aggregator (USDe/USD, USDS/USD): 8 decimals, answer set by hand.
contract MockAggregator {
    int256 public answer;

    function setAnswer(int256 a) external {
        answer = a;
    }

    function decimals() external pure returns (uint8) {
        return 8;
    }

    function description() external pure returns (string memory) {
        return "demo mock";
    }

    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80) {
        return (1, answer, block.timestamp, block.timestamp, 1);
    }
}

/// Replaces re.xyz's share price feed read by the PT-reUSD SY.
contract MockSharePrice {
    uint256 public sharePrice;

    function setSharePrice(uint256 p) external {
        sharePrice = p;
    }

    function getSharePrice() external view returns (uint256) {
        return sharePrice;
    }
}

/// Sells PT into a Pendle pool in one transaction: pull, transfer to the pool, swap. If the pool
/// refuses the trade, the whole call reverts and the seller keeps its PT.
contract DemoSeller {
    function sell(address market, uint256 amount) external returns (uint256 syOut) {
        (, address pt,) = IPendleMarket(market).readTokens();
        IERC20Pull(pt).transferFrom(msg.sender, market, amount);
        (syOut,) = IPendleMarket(market).swapExactPtForSy(msg.sender, amount, "");
    }
}

interface IERC20Pull {
    function transferFrom(address, address, uint256) external returns (bool);
}
