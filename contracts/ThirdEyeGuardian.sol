// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title  ThirdEyeGuardian
 * @author Third Eye — Web3 Enforcer (Member 2)
 * @notice On-Chain Immunity Contract for the Third Eye system.
 *         Maintains a blacklist of malicious wallet addresses and provides
 *         a guardian shield that can block flagged addresses from interacting
 *         with protected DeFi protocols.
 *
 * @dev    Deployed on Base Sepolia Testnet.
 *         Guardian pattern: owner sets blacklist, protocols query isBlacklisted().
 *
 * Architecture:
 *   ForensicAgent (AI) → Celery task → Backend API
 *         │
 *         ▼
 *   useShield.ts (Frontend) → ThirdEyeGuardian.blacklistWallet()
 *         │
 *         ▼
 *   Protected contracts query: ThirdEyeGuardian.isBlacklisted(address)
 */

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

contract ThirdEyeGuardian is Ownable, Pausable {
    // ── Events ────────────────────────────────────────────────

    /// @notice Emitted when a wallet is added to the blacklist
    event WalletBlacklisted(
        address indexed wallet,
        uint256 riskScore,      // Risk score * 1000 (3 decimal precision, no floats)
        string  reason,
        uint256 timestamp
    );

    /// @notice Emitted when a wallet is removed from the blacklist
    event WalletWhitelisted(
        address indexed wallet,
        uint256 timestamp
    );

    /// @notice Emitted when the guardian shield is activated on a protected target
    event ShieldActivated(
        address indexed protectedContract,
        address indexed blockedCaller,
        uint256 timestamp
    );

    // ── State ─────────────────────────────────────────────────

    /// @dev Core blacklist mapping: address → BlacklistEntry
    struct BlacklistEntry {
        bool    active;
        uint256 riskScore;      // 0–1000 (maps to 0.000–1.000 in backend)
        string  reason;
        uint256 flaggedAt;
        address flaggedBy;      // The Third Eye operator who flagged
    }

    mapping(address => BlacklistEntry) private _blacklist;

    /// @dev Addresses authorized to submit blacklist entries (Third Eye operators)
    mapping(address => bool) public thirdEyeOperators;

    /// @dev Count of currently blacklisted addresses
    uint256 public blacklistCount;

    /// @dev Minimum risk score (0–1000) required to blacklist. Default: 850 (0.85)
    uint256 public riskThreshold = 850;

    // ── Modifiers ─────────────────────────────────────────────

    modifier onlyOperator() {
        require(
            thirdEyeOperators[msg.sender] || msg.sender == owner(),
            "ThirdEyeGuardian: caller is not a Third Eye operator"
        );
        _;
    }

    modifier notBlacklisted(address wallet) {
        require(
            !_blacklist[wallet].active,
            "ThirdEyeGuardian: wallet is blacklisted"
        );
        _;
    }

    // ── Constructor ───────────────────────────────────────────

    /**
     * @param initialOwner Address of the deploying Third Eye operator (multi-sig recommended)
     */
    constructor(address initialOwner) Ownable(initialOwner) {
        thirdEyeOperators[initialOwner] = true;
    }

    // ── Blacklist Management ──────────────────────────────────

    /**
     * @notice Add a wallet to the on-chain blacklist.
     * @dev    Only callable by Third Eye operators.
     *         riskScore must exceed riskThreshold.
     *
     * @param wallet     Address to blacklist
     * @param riskScore  AI-assigned risk score (0–1000, where 1000 = 100% risk)
     * @param reason     Human-readable reason from ForensicAgent report
     */
    function blacklistWallet(
        address wallet,
        uint256 riskScore,
        string calldata reason
    ) external onlyOperator whenNotPaused {
        require(wallet != address(0), "ThirdEyeGuardian: zero address");
        require(wallet != owner(), "ThirdEyeGuardian: cannot blacklist owner");
        require(riskScore >= riskThreshold, "ThirdEyeGuardian: risk score below threshold");
        require(!_blacklist[wallet].active, "ThirdEyeGuardian: already blacklisted");

        _blacklist[wallet] = BlacklistEntry({
            active:    true,
            riskScore: riskScore,
            reason:    reason,
            flaggedAt: block.timestamp,
            flaggedBy: msg.sender
        });

        blacklistCount++;

        emit WalletBlacklisted(wallet, riskScore, reason, block.timestamp);
    }

    /**
     * @notice Remove a wallet from the blacklist (pardon / false positive).
     * @dev    Only callable by the contract owner (higher authority than operators).
     *
     * @param wallet Address to whitelist
     */
    function whitelistWallet(address wallet) external onlyOwner {
        require(_blacklist[wallet].active, "ThirdEyeGuardian: not blacklisted");

        delete _blacklist[wallet];
        blacklistCount--;

        emit WalletWhitelisted(wallet, block.timestamp);
    }

    /**
     * @notice Batch blacklist multiple wallets in a single transaction.
     *         Used by the backend when sweeping high-risk wallets.
     *
     * @param wallets    Array of addresses to blacklist
     * @param riskScores Corresponding risk scores (0–1000)
     * @param reason     Shared reason string (e.g., "Batch sweep — Celery task #1234")
     */
    function batchBlacklist(
        address[] calldata wallets,
        uint256[] calldata riskScores,
        string calldata reason
    ) external onlyOperator whenNotPaused {
        require(wallets.length == riskScores.length, "ThirdEyeGuardian: length mismatch");
        require(wallets.length <= 100, "ThirdEyeGuardian: max 100 per batch");

        for (uint256 i = 0; i < wallets.length; i++) {
            if (
                wallets[i] != address(0) &&
                !_blacklist[wallets[i]].active &&
                riskScores[i] >= riskThreshold
            ) {
                _blacklist[wallets[i]] = BlacklistEntry({
                    active:    true,
                    riskScore: riskScores[i],
                    reason:    reason,
                    flaggedAt: block.timestamp,
                    flaggedBy: msg.sender
                });
                blacklistCount++;
                emit WalletBlacklisted(wallets[i], riskScores[i], reason, block.timestamp);
            }
        }
    }

    // ── Shield Function ───────────────────────────────────────

    /**
     * @notice The Guardian Shield — blocks blacklisted callers.
     *         Protected DeFi protocols call this as a modifier gate.
     *
     *         Usage in a protected protocol:
     *         ```
     *         IThirdEyeGuardian guardian = IThirdEyeGuardian(GUARDIAN_ADDRESS);
     *         guardian.shield(msg.sender); // Reverts if blacklisted
     *         ```
     *
     * @param caller The address attempting to interact with the protected protocol
     */
    function shield(address caller) external whenNotPaused {
        if (_blacklist[caller].active) {
            emit ShieldActivated(msg.sender, caller, block.timestamp);
            revert(
                string(abi.encodePacked(
                    "ThirdEyeGuardian: address blocked | risk=",
                    _uintToString(_blacklist[caller].riskScore),
                    " | ",
                    _blacklist[caller].reason
                ))
            );
        }
    }

    // ── View Functions ────────────────────────────────────────

    /**
     * @notice Check if a wallet is currently blacklisted.
     * @param wallet Address to check
     * @return True if blacklisted
     */
    function isBlacklisted(address wallet) external view returns (bool) {
        return _blacklist[wallet].active;
    }

    /**
     * @notice Retrieve the full blacklist entry for a wallet.
     * @param wallet Address to query
     * @return entry The BlacklistEntry struct
     */
    function getEntry(address wallet) external view returns (BlacklistEntry memory entry) {
        return _blacklist[wallet];
    }

    // ── Admin ─────────────────────────────────────────────────

    /**
     * @notice Grant Third Eye operator role to an address.
     * @param operator Address to authorize (e.g., backend signing key)
     */
    function addOperator(address operator) external onlyOwner {
        thirdEyeOperators[operator] = true;
    }

    /**
     * @notice Revoke Third Eye operator role.
     * @param operator Address to deauthorize
     */
    function removeOperator(address operator) external onlyOwner {
        thirdEyeOperators[operator] = false;
    }

    /**
     * @notice Update the minimum risk score threshold for blacklisting.
     * @param newThreshold Value between 0–1000 (recommended: ≥ 700)
     */
    function setRiskThreshold(uint256 newThreshold) external onlyOwner {
        require(newThreshold <= 1000, "ThirdEyeGuardian: threshold out of range");
        riskThreshold = newThreshold;
    }

    /// @notice Emergency pause — halts blacklisting and shield functions
    function pause() external onlyOwner { _pause(); }

    /// @notice Resume operations after pause
    function unpause() external onlyOwner { _unpause(); }

    // ── Internal Utils ────────────────────────────────────────

    function _uintToString(uint256 value) internal pure returns (string memory) {
        if (value == 0) return "0";
        uint256 temp = value;
        uint256 digits;
        while (temp != 0) { digits++; temp /= 10; }
        bytes memory buffer = new bytes(digits);
        while (value != 0) {
            digits--;
            buffer[digits] = bytes1(uint8(48 + uint256(value % 10)));
            value /= 10;
        }
        return string(buffer);
    }
}
