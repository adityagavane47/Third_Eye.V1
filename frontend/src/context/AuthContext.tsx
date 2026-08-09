/**
 * frontend/src/context/AuthContext.tsx
 * 
 * Thin abstraction over Privy so Dashboard and other components
 * never import from @privy-io directly.
 * 
 * When VITE_PRIVY_APP_ID is set → real Privy values flow through.
 * When not set (dev mode)      → mock values with no-op handlers.
 */

import React, { createContext, useContext } from "react";
import { usePrivy } from "@privy-io/react-auth";

// ── Auth State Contract ───────────────────────────────────────
export interface AuthState {
  /** True when the user has completed Privy login */
  authenticated: boolean;
  /** Shortened wallet or email address for display */
  walletAddress: string | null;
  /** Full wallet address (0x...) */
  fullAddress: string | null;
  /** Trigger the Privy login modal */
  login: () => void;
  /** Sign the user out */
  logout: () => void;
}

// ── Default (dev mode / no Privy) context ────────────────────
const AuthContext = createContext<AuthState>({
  authenticated: false,
  walletAddress: null,
  fullAddress: null,
  login: () => {},
  logout: () => {},
});

// ── Hook ──────────────────────────────────────────────────────
export const useAuth = () => useContext(AuthContext);

// ── PrivyAuthProvider ─────────────────────────────────────────
// This component MUST be rendered inside <PrivyProvider>.
// It reads from Privy and injects values into AuthContext.
export function PrivyAuthProvider({ children }: { children: React.ReactNode }) {
  const { authenticated, login, logout, user } = usePrivy();

  const fullAddress = user?.wallet?.address ?? null;
  const walletAddress = fullAddress
    ? `${fullAddress.slice(0, 6)}…${fullAddress.slice(-4)}`
    : user?.email?.address ?? null;

  return (
    <AuthContext.Provider value={{ authenticated, login, logout, walletAddress, fullAddress }}>
      {children}
    </AuthContext.Provider>
  );
}
