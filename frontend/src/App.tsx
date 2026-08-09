/**
 * frontend/src/App.tsx — Application Root
 *
 * Conditionally wraps the app with PrivyProvider when VITE_PRIVY_APP_ID
 * is configured. Falls back to dev mode (no auth) otherwise.
 *
 * Chain: Base Sepolia (84532) is both the default and the only supported chain.
 * Theme: Dark + Third Eye accent (#00D4FF)
 */

import type { Chain } from "viem";
import { PrivyProvider } from "@privy-io/react-auth";
import Dashboard from "./pages/Dashboard";
import { PrivyAuthProvider } from "./context/AuthContext";


// ── Base Sepolia chain definition ────────────────────────────
export const BASE_SEPOLIA: Chain = {
  id: 84532,
  name: "Base Sepolia",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: {
    default: { http: [import.meta.env.VITE_BASE_SEPOLIA_RPC ?? "https://sepolia.base.org"] },
    public:  { http: [import.meta.env.VITE_BASE_SEPOLIA_RPC ?? "https://sepolia.base.org"] },
  },
  blockExplorers: {
    default: { name: "BaseScan", url: "https://sepolia.basescan.org" },
  },
  testnet: true,
};

const PRIVY_APP_ID = import.meta.env.VITE_PRIVY_APP_ID as string | undefined;
const HAS_PRIVY = !!PRIVY_APP_ID && PRIVY_APP_ID !== "your_privy_app_id_here";

// ── App ───────────────────────────────────────────────────────
export default function App() {
  if (!HAS_PRIVY) {
    console.info("[Third Eye] VITE_PRIVY_APP_ID not set — running in dev mode without auth.", { PRIVY_APP_ID });
    return <Dashboard />;
  }

  console.info("[Third Eye] Privy configured with ID:", PRIVY_APP_ID);

  // Production / staging: PrivyProvider is imported at top level


  return (
    <PrivyProvider
      appId={PRIVY_APP_ID!}
      config={{
        loginMethods: ["email", "wallet"],
        appearance: {
          theme: "dark",
          accentColor: "#00D4FF",
          logo: "https://Third Eye-galaxy.vercel.app/logo.svg",
          showWalletLoginFirst: false,
        },
        defaultChain: BASE_SEPOLIA,
        supportedChains: [BASE_SEPOLIA],
        embeddedWallets: {
          createOnLogin: "users-without-wallets",
          noPromptOnSignature: false,
        },
      }}
    >
      <PrivyAuthProvider>
        <Dashboard />
      </PrivyAuthProvider>
    </PrivyProvider>
  );
}
