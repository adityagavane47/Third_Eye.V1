#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo "  Third Eye — SP1 zkML Build Script"
echo "=============================================="

export PATH="/root/.cargo/bin:/root/.sp1/bin:$PATH"

echo "Installing SP1 toolchain..."
cargo prove install-toolchain

echo "Building SP1 prover (this takes 5-15 minutes first time)..."
PROJECT_DIR="/mnt/d/NExus/Nexus-Hackathon"
cd "$PROJECT_DIR/zk-ml"

cargo build --release

PROVE_BIN="$PROJECT_DIR/zk-ml/target/release/prove"
if [ -f "$PROVE_BIN" ]; then
    echo "BUILD SUCCESSFUL!"
    echo "Prover binary: $PROVE_BIN"
else
    echo "ERROR: Build failed."
    exit 1
fi
