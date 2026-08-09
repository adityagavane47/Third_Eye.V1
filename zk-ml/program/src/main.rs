// zk-ml/program/src/main.rs — Third Eye SP1 Guest Program
//
// This program runs *inside* the SP1 zkVM (RISC-V).  It:
//   1. Reads ModelWeights (the exported Isolation Forest JSON) and TxInput
//      from the SP1 stdin stream.
//   2. Traverses all Isolation Forest decision trees in Rust, exactly
//      replicating sklearn's decision_function / score_samples math.
//   3. Asserts the anomaly score < max_risk_threshold (wallet is safe).
//   4. Commits (tx_id, is_safe: bool, anomaly_score_fp: u32) as public outputs.
//
// Math Reference — sklearn's IsolationForest anomaly score:
//
//     h(x)   = path_depth + c(n_samples_at_leaf)
//     E[h(x)] = mean(h(x)) over all trees
//     s(x,n) = 2^( -E[h(x)] / c(max_samples) )
//
//     c(n) = 2*(ln(n-1) + γ) - 2*(n-1)/n   for n > 2
//     c(2) = 1.0,  c(≤1) = 0.0
//     γ    = Euler-Mascheroni ≈ 0.5772156649015329
//
// score_samples ∈ (0,1]:
//   closer to 1 → anomaly (outlier)
//   closer to 0 → normal
//
// decision_function = score_samples - offset_  (offset is also in JSON)
//
// We use integer-promoted fixed-point for the zkVM where f64 is unavailable,
// but SP1's RISC-V toolchain DOES support the f64 soft-float ABI, so we can
// use f64 directly inside the guest.

#![allow(dead_code)]
#![allow(unused_variables)]
#![allow(unused_imports)]
#![no_main]
sp1_zkvm::entrypoint!(main);

extern crate alloc;
use alloc::{string::String, vec::Vec};

use serde::{Deserialize, Serialize};

// ── Sentinel for sklearn's TREE_LEAF (-1) ────────────────────────────────────
// sklearn stores children_left[leaf] = -1.  After JSON round-trip they are i32.
const TREE_LEAF: i32 = -1;

// Euler-Mascheroni constant (same value used inside sklearn)
const EULER_GAMMA: f64 = 0.5772156649015329_f64;

// ── Serde Structs ─────────────────────────────────────────────────────────────

/// One Isolation Tree exported from sklearn's DecisionTree.
/// Field names match exactly what export_model.py writes.
#[derive(Deserialize)]
struct ExportedTree {
    /// children_left[i]: index of left child for node i, or -1 if leaf
    children_left: Vec<i32>,
    /// children_right[i]: index of right child for node i, or -1 if leaf
    children_right: Vec<i32>,
    /// feature[i]: which feature (LOCAL index into features_used) is tested
    feature: Vec<i32>,
    /// threshold[i]: the split threshold at node i
    threshold: Vec<f64>,
    /// n_node_samples[i]: number of training samples that reached node i.
    /// At a leaf, this is used to compute the path-length correction c(n).
    n_node_samples: Vec<i32>,
    /// Mapping from LOCAL feature index → GLOBAL feature index.
    /// i.e., the actual feature vector index used by this tree.
    features_used: Vec<usize>,
    /// Total number of nodes in this tree (for bounds checking)
    n_nodes: usize,
}

/// The full exported model (the contents of model_weights.json).
#[derive(Deserialize)]
struct ModelWeights {
    n_estimators:  usize,
    max_samples:   u64,
    c_max_samples: f64,   // Pre-computed c(max_samples) for efficiency
    n_features:    usize,
    offset:        f64,   // sklearn's offset_ for decision_function
    trees:         Vec<ExportedTree>,
}

/// The transaction feature vector passed from the Python FastAPI host.
#[derive(Deserialize)]
struct TxInput {
    /// Unique identifier for this transaction / wallet analysis
    tx_id: String,
    /// Feature values in the EXACT order of FEATURE_NAMES in ml_engine.py
    ///   [0] tx_count_24h
    ///   [1] avg_gas_multiple
    ///   [2] unique_contracts
    ///   [3] flash_loan_flag
    ///   [4] reentrancy_depth
    ///   [5] value_concentration
    ///   [6] cycle_score
    ///   [7] betweenness_score
    ///   [8] cross_protocol_flag
    ///   [9] velocity_score
    features: Vec<f64>,
    /// The caller's chosen risk threshold ∈ (0, 1].
    /// Proof will PANIC (invalid) if anomaly_score ≥ max_risk_threshold.
    max_risk_threshold: f64,
}

/// What we commit to the SP1 public output tape.
#[derive(Serialize)]
struct ProofOutput {
    tx_id: String,
    /// True iff anomaly_score < max_risk_threshold (wallet is safe)
    is_safe: bool,
    /// Anomaly score as a fixed-point u32: score * 1_000_000
    /// (preserves 6 decimal places without floating-point in the output)
    anomaly_score_fp: u32,
    /// The threshold used (fixed-point u32 same scale)
    threshold_fp: u32,
}

// ── c(n) helper ──────────────────────────────────────────────────────────────

/// Compute the expected path length of an unsuccessful BST search with n nodes.
/// Exactly matches sklearn's `_average_path_length` for a scalar n.
#[inline]
fn c_factor(n: i32) -> f64 {
    match n {
        n if n <= 1 => 0.0_f64,
        2            => 1.0_f64,
        n => {
            let nf = n as f64;
            2.0_f64 * ((nf - 1.0_f64).ln() + EULER_GAMMA)
                - 2.0_f64 * (nf - 1.0_f64) / nf
        }
    }
}

// ── Tree traversal ────────────────────────────────────────────────────────────

/// Walk a single Isolation Tree for the given feature vector.
///
/// Returns (path_depth, n_samples_at_leaf) where:
///   - path_depth    = number of edges from root to leaf (0-based)
///   - n_samples_at_leaf = tree.n_node_samples[leaf_node]
///
/// The path length contribution of this tree is:
///   h_i(x) = path_depth + c(n_samples_at_leaf)
#[inline]
fn traverse_tree(tree: &ExportedTree, global_features: &[f64]) -> (u32, i32) {
    let mut node  = 0usize;
    let mut depth = 0u32;

    loop {
        let left_child = tree.children_left[node];

        // Leaf node: children_left == TREE_LEAF (-1)
        if left_child == TREE_LEAF {
            let leaf_samples = tree.n_node_samples[node];
            return (depth, leaf_samples);
        }

        // Internal node: fetch the LOCAL feature index and map to global
        let local_feat_idx  = tree.feature[node] as usize;
        let global_feat_idx = tree.features_used[local_feat_idx];

        // Bounds check — in zkVM panics abort proof generation cleanly
        assert!(
            global_feat_idx < global_features.len(),
            "Feature index {} out of bounds (n_features={})",
            global_feat_idx,
            global_features.len()
        );

        let feature_val = global_features[global_feat_idx];
        let split_thr   = tree.threshold[node];

        // sklearn's split rule: go left if feature_val <= threshold
        node = if feature_val <= split_thr {
            tree.children_left[node] as usize
        } else {
            tree.children_right[node] as usize
        };

        depth += 1;

        // Bounds check on node index
        assert!(node < tree.n_nodes, "Tree traversal exceeded node count");
    }
}

// ── Isolation Forest scoring ──────────────────────────────────────────────────

/// Compute sklearn's `score_samples` for a single sample across the full forest.
///
/// Formula:
///     h_i(x) = depth_i + c(leaf_samples_i)      for each tree i
///     E[h(x)] = (1/n_trees) * Σ h_i(x)
///     s(x, n) = 2^( -E[h(x)] / c(max_samples) )
///
/// Returns anomaly score ∈ (0, 1] where 1 = most anomalous.
fn compute_anomaly_score(model: &ModelWeights, features: &[f64]) -> f64 {
    assert!(
        features.len() == model.n_features,
        "Feature vector length {} != model.n_features {}",
        features.len(),
        model.n_features
    );

    let mut total_path_length: f64 = 0.0_f64;

    for tree in &model.trees {
        let (depth, leaf_samples) = traverse_tree(tree, features);
        // Path length for this tree = traversal depth + c(leaf sub-sample)
        let h_i = depth as f64 + c_factor(leaf_samples);
        total_path_length += h_i;
    }

    let mean_path_length = total_path_length / model.n_estimators as f64;

    // 2^(-E[h(x)] / c(max_samples))
    // We use the identity: 2^x = e^(x * ln(2))
    let exponent = -mean_path_length / model.c_max_samples;
    let score    = libm::exp2(exponent);   // 2^exponent via libm (no_std safe)

    // Clamp to valid range (floating-point rounding can push past 1.0)
    score.max(0.0_f64).min(1.0_f64)
}

// ── Main (SP1 guest entrypoint) ───────────────────────────────────────────────

pub fn main() {
    // ── Step 1: Read inputs from the SP1 stdin stream ─────────────────────
    // The host program writes these in the same order using sp1_sdk::SP1Stdin.
    let model:    ModelWeights = sp1_zkvm::io::read::<ModelWeights>();
    let tx_input: TxInput      = sp1_zkvm::io::read::<TxInput>();

    // ── Step 2: Validate input dimensions ────────────────────────────────
    assert!(
        tx_input.features.len() == model.n_features,
        "TxInput has {} features but model expects {}",
        tx_input.features.len(),
        model.n_features
    );
    assert!(
        model.trees.len() == model.n_estimators,
        "Tree count mismatch: {} trees vs n_estimators={}",
        model.trees.len(),
        model.n_estimators
    );
    assert!(
        tx_input.max_risk_threshold > 0.0_f64 && tx_input.max_risk_threshold <= 1.0_f64,
        "max_risk_threshold must be in (0, 1], got {}",
        tx_input.max_risk_threshold
    );

    // ── Step 3: Run the Isolation Forest ─────────────────────────────────
    let anomaly_score = compute_anomaly_score(&model, &tx_input.features);

    // ── Step 4: Assert safety (this is the zkML proof core) ──────────────
    // If this assertion fails, the SP1 prover CANNOT generate a valid proof.
    // The zero-knowledge property ensures: a valid proof ≡ score < threshold.
    let is_safe = anomaly_score < tx_input.max_risk_threshold;
    assert!(
        is_safe,
        "RISK GATE FAILED: anomaly_score={:.6} >= threshold={:.6}. Wallet is NOT safe.",
        anomaly_score,
        tx_input.max_risk_threshold
    );

    // ── Step 5: Commit public outputs ────────────────────────────────────
    // Committed values become part of the proof's public inputs.
    // Verifiers can check these without re-running the computation.
    let output = ProofOutput {
        tx_id:            tx_input.tx_id.clone(),
        is_safe:          true,   // Only reachable if assertion above passed
        anomaly_score_fp: (anomaly_score * 1_000_000.0_f64) as u32,
        threshold_fp:     (tx_input.max_risk_threshold * 1_000_000.0_f64) as u32,
    };

    sp1_zkvm::io::commit(&output);
}
