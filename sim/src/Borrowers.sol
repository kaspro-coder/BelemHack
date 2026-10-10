// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// Borrowers of the Morpho PT-sUSDe-26NOV2026/USDC market at the fork block (from Morpho's API).
library Borrowers {
    function list() internal pure returns (address[] memory a) {
        a = new address[](13);
        a[0] = 0xdf81987465681D0515058fe0A47A3bD174012730;
        a[1] = 0x5C430FF6F374da12218b380d2040299Ae5B6d40E;
        a[2] = 0x03BAbEB24619902253FDB0D5675A816879115d98;
        a[3] = 0xE3a5BCB68EA2be70c029687BF02D3357417D8D67;
        a[4] = 0xDE79a400Ec22Ff42D875E8C12819183a8E12E141;
        a[5] = 0xBfCDb32f9E2C6d2a7c5c8C435b3da59Ff6049212;
        a[6] = 0x405B07642E7C4e1B9eDA4Ef21F16b22207d0F2CC;
        a[7] = 0x4264Ef782fc3385c62e16969618e81E079aFd880;
        a[8] = 0x9f72e6cD13C4da05BaFb173E9Ff83EB6e324315F;
        a[9] = 0x91Ab152b06eDc600B4A123c2eA1387EBe5B83795;
        a[10] = 0xA4818Ef55AC5B27308808C633dC6E00a8361a810;
        a[11] = 0x7640AEcB5a149ee48E79465f9aEd3508b1efa164;
        a[12] = 0xB91745297802AD852b286809d25199c7467584a8;
    }
}
