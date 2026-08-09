#!/bin/bash
cat << 'EOF' >> /root/zk-ml/Cargo.toml

[patch.crates-io]
num-modular = { version = "=0.6.1" }
EOF
