/**
 * frontend/src/hooks/useShield.ts — ThirdEyeGuardian Contract Hook
 * Role: Web3 Enforcer (Member 2)
 *
 * Custom React hook that:
 * 1. Uses Privy for wallet connection (2026 Web3 onboarding standard)
 * 2. Provides typed methods to interact with ThirdEyeGuardian.sol
 * 3. Handles Base Sepolia network switching automatically
 * 4. Exposes transaction state for the Sidebar UI component
 */

import { useCallback, useState } from "react";
import { usePrivy, useWallets } from "@privy-io/react-auth";
import { ethers, Contract, BrowserProvider, JsonRpcSigner } from "ethers";

// ── Contract ABI (subset — only used functions) ────────────────
const GUARDIAN_ABI = [
  // Read
  "function isBlacklisted(address wallet) external view returns (bool)",
  "function getEntry(address wallet) external view returns (tuple(bool active, uint256 riskScore, string reason, uint256 flaggedAt, address flaggedBy))",
  "function blacklistCount() external view returns (uint256)",
  "function riskThreshold() external view returns (uint256)",

  // Write (operator only)
  "function blacklistWallet(address wallet, uint256 riskScore, string reason) external",
  "function whitelistWallet(address wallet) external",
  "function batchBlacklist(address[] wallets, uint256[] riskScores, string reason) external",

  // Events
  "event WalletBlacklisted(address indexed wallet, uint256 riskScore, string reason, uint256 timestamp)",
  "event WalletWhitelisted(address indexed wallet, uint256 timestamp)",
  "event ShieldActivated(address indexed protectedContract, address indexed blockedCaller, uint256 timestamp)",
] as const;

// ── Base Sepolia Chain Config ──────────────────────────────────
const BASE_SEPOLIA_CHAIN_ID = 84532;
const BASE_SEPOLIA_PARAMS = {
  chainId: `0x${BASE_SEPOLIA_CHAIN_ID.toString(16)}`,
  chainName: "Base Sepolia",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: [import.meta.env.VITE_BASE_SEPOLIA_RPC ?? "https://sepolia.base.org"],
  blockExplorerUrls: ["https://sepolia.basescan.org"],
};

const GUARDIAN_ADDRESS =
  import.meta.env.VITE_GUARDIAN_CONTRACT_ADDRESS ?? "0x0000000000000000000000000000000000000000";

// ── Types ──────────────────────────────────────────────────────
export interface BlacklistEntry {
  active: boolean;
  riskScore: bigint;          // 0–1000n
  reason: string;
  flaggedAt: bigint;          // Unix timestamp
  flaggedBy: string;
}

export type ShieldTxStatus = "idle" | "pending" | "confirming" | "success" | "error";

export interface UseShieldReturn {
  // State
  isConnected: boolean;
  isOperator: boolean;
  txStatus: ShieldTxStatus;
  txHash: string | null;
  error: string | null;
  blacklistCount: bigint | null;

  // Actions
  connectWallet: () => Promise<void>;
  blacklistWallet: (wallet: string, riskScore: number, reason: string) => Promise<string | null>;
  whitelistWallet: (wallet: string) => Promise<string | null>;
  checkIsBlacklisted: (wallet: string) => Promise<boolean>;
  getBlacklistEntry: (wallet: string) => Promise<BlacklistEntry | null>;
  fetchBlacklistCount: () => Promise<bigint | null>;
  resetStatus: () => void;
}

// ── Hook Implementation ────────────────────────────────────────
export function useShield(): UseShieldReturn {
  const { login, authenticated } = usePrivy();
  const { wallets } = useWallets();

  const [txStatus, setTxStatus] = useState<ShieldTxStatus>("idle");
  const [txHash, setTxHash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // isOperator: backend determines operator role via OPERATOR_PRIVATE_KEY — always false in frontend context
  const isOperator = false;
  const [blacklistCount, setBlacklistCount] = useState<bigint | null>(null);

  /**
   * Get an ethers.js signer from the Privy-connected embedded wallet.
   * Automatically switches to Base Sepolia if on the wrong network.
   */
  const getSigner = useCallback(async (): Promise<JsonRpcSigner> => {
    const embeddedWallet = wallets.find((w) => w.walletClientType === "privy");
    if (!embeddedWallet) throw new Error("No Privy embedded wallet found — please connect first");

    const provider = await embeddedWallet.getEthereumProvider();
    const ethersProvider = new BrowserProvider(provider);

    // Auto-switch to Base Sepolia
    const network = await ethersProvider.getNetwork();
    if (Number(network.chainId) !== BASE_SEPOLIA_CHAIN_ID) {
      try {
        await provider.request({
          method: "wallet_switchEthereumChain",
          params: [{ chainId: BASE_SEPOLIA_PARAMS.chainId }],
        });
      } catch (switchError: any) {
        // Chain not added — add it first
        if (switchError?.code === 4902) {
          await provider.request({
            method: "wallet_addEthereumChain",
            params: [BASE_SEPOLIA_PARAMS],
          });
        } else {
          throw switchError;
        }
      }
    }

    return ethersProvider.getSigner();
  }, [wallets]);

  /**
   * Get a read-only contract instance (no signer required for view functions).
   */
  const getReadContract = useCallback((): Contract => {
    const provider = new ethers.JsonRpcProvider(
      import.meta.env.VITE_BASE_SEPOLIA_RPC ?? "https://sepolia.base.org"
    );
    return new Contract(GUARDIAN_ADDRESS, GUARDIAN_ABI, provider);
  }, []);

  /**
   * Get a write-enabled contract instance (requires Privy signer).
   */
  const getWriteContract = useCallback(async (): Promise<Contract> => {
    const signer = await getSigner();
    return new Contract(GUARDIAN_ADDRESS, GUARDIAN_ABI, signer);
  }, [getSigner]);

  // ── Public Actions ─────────────────────────────────────────

  const connectWallet = useCallback(async () => {
    if (!authenticated) await login();
  }, [authenticated, login]);

  /**
   * Blacklist a wallet on-chain via ThirdEyeGuardian.blacklistWallet().
   * @param wallet     Ethereum address to blacklist
   * @param riskScore  Float 0.0–1.0 (converted to 0–1000 uint256)
   * @param reason     Human-readable reason from ForensicAgent
   * @returns          Transaction hash if successful, null on error
   */
  const blacklistWallet = useCallback(
    async (wallet: string, riskScore: number, reason: string): Promise<string | null> => {
      setError(null);
      setTxStatus("pending");
      setTxHash(null);

      try {
        const contract = await getWriteContract();
        const riskScoreUint = BigInt(Math.round(riskScore * 1000));

        const tx = await contract.blacklistWallet(wallet, riskScoreUint, reason);
        setTxHash(tx.hash);
        setTxStatus("confirming");

        await tx.wait(1); // Wait for 1 confirmation
        setTxStatus("success");
        return tx.hash as string;
      } catch (err: any) {
        const message = err?.reason ?? err?.message ?? "Transaction failed";
        setError(message);
        setTxStatus("error");
        return null;
      }
    },
    [getWriteContract]
  );

  /**
   * Remove a wallet from the blacklist (owner only).
   */
  const whitelistWallet = useCallback(
    async (wallet: string): Promise<string | null> => {
      setError(null);
      setTxStatus("pending");

      try {
        const contract = await getWriteContract();
        const tx = await contract.whitelistWallet(wallet);
        setTxHash(tx.hash);
        setTxStatus("confirming");
        await tx.wait(1);
        setTxStatus("success");
        return tx.hash as string;
      } catch (err: any) {
        setError(err?.reason ?? err?.message ?? "Whitelist failed");
        setTxStatus("error");
        return null;
      }
    },
    [getWriteContract]
  );

  /**
   * Read-only: check if a wallet is currently blacklisted.
   */
  const checkIsBlacklisted = useCallback(
    async (wallet: string): Promise<boolean> => {
      try {
        const contract = getReadContract();
        return (await contract.isBlacklisted(wallet)) as boolean;
      } catch {
        return false;
      }
    },
    [getReadContract]
  );

  /**
   * Read-only: get the full BlacklistEntry for a wallet.
   */
  const getBlacklistEntry = useCallback(
    async (wallet: string): Promise<BlacklistEntry | null> => {
      try {
        const contract = getReadContract();
        const entry = await contract.getEntry(wallet);
        return {
          active: entry[0] as boolean,
          riskScore: entry[1] as bigint,
          reason: entry[2] as string,
          flaggedAt: entry[3] as bigint,
          flaggedBy: entry[4] as string,
        };
      } catch {
        return null;
      }
    },
    [getReadContract]
  );

  /**
   * Read-only: get total count of blacklisted addresses.
   */
  const fetchBlacklistCount = useCallback(async (): Promise<bigint | null> => {
    try {
      const contract = getReadContract();
      const count = (await contract.blacklistCount()) as bigint;
      setBlacklistCount(count);
      return count;
    } catch {
      return null;
    }
  }, [getReadContract]);

  const resetStatus = useCallback(() => {
    setTxStatus("idle");
    setTxHash(null);
    setError(null);
  }, []);

  return {
    isConnected: authenticated,
    isOperator,
    txStatus,
    txHash,
    error,
    blacklistCount,
    connectWallet,
    blacklistWallet,
    whitelistWallet,
    checkIsBlacklisted,
    getBlacklistEntry,
    fetchBlacklistCount,
    resetStatus,
  };
}
