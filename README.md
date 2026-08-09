# Third Eye: Autonomous On-Chain Immunity System

Built by Team **Vmax** (Aditya Gavane, Gaurav Jain, Nishad Kulkarni)

\---

## Overview

**Third Eye** is an autonomous on-chain immunity system designed to act as both a forensic analysis tool and an active defense mechanism for Web3 protocols.

Instead of relying on reactive post-mortem reports, Third Eye ingests real transaction data, analyzes structural behavior, and automatically shields protocols from identified threats via an on-chain blacklist.

## How It Works

1. **Ingest:** Pulls real transaction data, including flash loans and ERC-20 transfers, directly from Ethereum Mainnet via Etherscan V2.
2. **Analyze:** Constructs a comprehensive graph representation of transaction topologies using Neo4j. We then utilize an **Isolation Forest** machine learning model to evaluate wallet transaction behavior (volume, graph metrics, etc.) and generate a precise risk score.
3. **Report:** Generates human-readable forensic threat intelligence reports using the Groq API.
4. **Defend (Shield):** Automatically blacklists malicious wallets (scoring >= 0.75) on the Guardian smart contract deployed on Base Sepolia. Protocols can integrate with this contract to shield themselves pre-emptively.

## Tech Stack

* **Backend:** Python, FastAPI, Celery, Redis
* **Database:** Neo4j (Local instance `bolt://localhost:7687`)
* **Frontend:** React, TypeScript, Vite (Featuring a "Galaxy" graph visualization)
* **Machine Learning:** `scikit-learn` (**Isolation Forest** for anomaly/risk detection)
* **Smart Contracts:** Solidity (Guardian contract on Base Sepolia - `0xd9145CCE52D386f254917e481eB44e9943F39138`)
* **External APIs:** Etherscan API V2, Groq API

## Core Architecture

### Data Ingestion

Utilizes Etherscan API V2 to fetch transactions. Includes a real data seeder (`scripts/seed\_real.py`) that performs a BFS-crawl from known attackers (e.g., Ronin Hacker) and whales to populate the database.

### Graph Database

* **Nodes:** `:Wallet` (address, label, risk\_score, flagged, balance\_eth, tx\_count)
* **Edges:** `:SENT\_TO` (tx\_hash, value\_eth, timestamp, gas\_used)

Provides topology for advanced feature extraction like centrality and cycle detection.

### ML Engine

Relies strictly on **Isolation Forest** (contamination=0.05). Wallet transaction history and graph metrics are processed to output a risk score from 0.0 to 1.0.

### The Shield (Guardian Contract)

When a wallet is flagged as high risk, the backend signs a transaction using `OPERATOR\_PRIVATE\_KEY` and calls `blacklistWallet(address, uint256 riskScore, string reason)` on the Base Sepolia network.

## API Endpoints

|Endpoint|Method|Purpose|
|-|-|-|
|`/api/ingest/wallet`|`POST`|Live ingestion via Etherscan, ML scoring, and Neo4j upsert.|
|`/api/shield/blacklist`|`POST`|Signs a tx and calls the Base Sepolia contract to blacklist an address.|
|`/api/simulate-exploit`|`POST`|Injects a demo attacker wallet into the graph.|
|`/api/graph/nodes`|`GET`|Retrieves graph data for the frontend Galaxy visualization.|
|`/api/graph/flag`|`POST`|Updates the flagged status in Neo4j.|
|`/api/forensic/report/{addr}`|`GET`|Fetches an LLM threat report via Groq.|


