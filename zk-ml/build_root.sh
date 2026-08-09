#!/bin/bash
export PATH="/root/.cargo/bin:/root/.sp1/bin:$PATH"
cd /root/zk-ml
cargo build --release
