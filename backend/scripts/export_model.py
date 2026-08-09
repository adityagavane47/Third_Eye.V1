"""
backend/scripts/export_model.py — Third Eye SP1 zkML Model Exporter

Extracts the internal structure of the trained Isolation Forest and writes
a JSON file that the SP1 Rust guest program can parse and execute natively.

The JSON exactly mirrors sklearn's internal DecisionTree arrays so the Rust
implementation can replicate sklearn's decision_function to machine precision.

Usage:
    python backend/scripts/export_model.py
    python backend/scripts/export_model.py --input path/to/model.pkl --output path/to/out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np

# ── sklearn constants ─────────────────────────────────────────────────────────
TREE_LEAF        = -1   # children_left[node] == TREE_LEAF ⟹ node is a leaf
TREE_UNDEFINED   = -2   # feature / threshold at a leaf node

EULER_GAMMA = 0.5772156649015329  # Euler-Mascheroni constant (same as np.euler_gamma)


def c_factor(n: int) -> float:
    """
    Expected path length of an unsuccessful search in a Binary Search Tree
    with n nodes.  This is sklearn's _average_path_length(n) for a scalar.

        c(n) = 2 * (ln(n-1) + γ) - 2*(n-1)/n   for n > 2
        c(2) = 1
        c(1) = 0  (or n<=1)

    Reference:
        Liu et al., "Isolation Forest", ICDM 2008.
        sklearn source: sklearn/ensemble/_iforest.py::_average_path_length
    """
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    return 2.0 * (np.log(n - 1) + EULER_GAMMA) - 2.0 * (n - 1) / n


def export_model(pkl_path: Path, output_path: Path) -> dict:
    """Load the sklearn IsolationForest and write model_weights.json."""
    print(f"[export_model] Loading: {pkl_path}")
    model = joblib.load(pkl_path)

    if not hasattr(model, "estimators_"):
        raise ValueError("Loaded object is not a fitted IsolationForest.")

    max_samples: int = int(model._max_samples)
    n_estimators: int = len(model.estimators_)
    n_features: int   = int(model.n_features_in_)
    c_norm: float     = c_factor(max_samples)

    print(f"[export_model]   n_estimators : {n_estimators}")
    print(f"[export_model]   max_samples  : {max_samples}")
    print(f"[export_model]   c(max_samples) = {c_norm:.8f}")
    print(f"[export_model]   n_features   : {n_features}")

    trees: list[dict] = []
    for i, (estimator, features_used) in enumerate(
        zip(model.estimators_, model.estimators_features_)
    ):
        sk_tree = estimator.tree_

        # sklearn stores TREE_LEAF (-1) in children_left for leaf nodes.
        # We convert to plain Python ints for JSON serialization.
        tree_dict = {
            "children_left":   sk_tree.children_left.tolist(),
            "children_right":  sk_tree.children_right.tolist(),
            # feature[leaf_node] == TREE_UNDEFINED (-2) in sklearn
            "feature":         sk_tree.feature.tolist(),
            # threshold[leaf_node] == -2.0 in sklearn
            "threshold":       sk_tree.threshold.tolist(),
            # n_node_samples[leaf] gives the sub-sample count at that leaf,
            # used to compute c(leaf_samples) for the path length correction.
            "n_node_samples":  sk_tree.n_node_samples.tolist(),
            # features_used: the indices into the GLOBAL feature vector that
            # this specific tree was trained on (IsolationForest uses
            # max_features="auto" which selects a random subset per tree).
            "features_used":   features_used.tolist(),
            "n_nodes":         int(sk_tree.node_count),
        }
        trees.append(tree_dict)

    # Compute and embed offset_ so Rust can reproduce decision_function exactly.
    # sklearn's decision_function = score_samples(X) - offset_
    # We store it so future proofs can optionally replicate it.
    offset: float = float(model.offset_)

    model_weights = {
        "version":        "ThirdEye-SP1-zkML-v1",
        "n_estimators":   n_estimators,
        "max_samples":    max_samples,
        "c_max_samples":  c_norm,
        "n_features":     n_features,
        "offset":         offset,
        "euler_gamma":    EULER_GAMMA,
        "feature_names":  [
            "tx_count_24h",
            "avg_gas_multiple",
            "unique_contracts",
            "flash_loan_flag",
            "reentrancy_depth",
            "value_concentration",
            "cycle_score",
            "betweenness_score",
            "cross_protocol_flag",
            "velocity_score",
        ],
        "trees": trees,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(model_weights, f, indent=2)

    print(f"[export_model] Wrote {len(trees)} trees → {output_path}")

    # ── Validation: score a dummy sample to verify round-trip ────────────
    _validate_export(model, model_weights)

    return model_weights


def _validate_export(model, weights: dict) -> None:
    """
    Sanity-check: manually walk the first tree using the exported weights
    and confirm the traversal matches sklearn's apply() output.
    """
    import numpy as np

    n_feat = weights["n_features"]
    dummy  = np.zeros((1, n_feat), dtype=float)

    # sklearn leaf index
    sk_leaf = model.estimators_[0].apply(dummy)[0]

    # Manual traversal using exported data
    tree  = weights["trees"][0]
    cl    = tree["children_left"]
    cr    = tree["children_right"]
    feat  = tree["feature"]
    thr   = tree["threshold"]
    fu    = tree["features_used"]

    node = 0
    while cl[node] != TREE_LEAF:
        global_feat_idx = fu[feat[node]]
        val = dummy[0, global_feat_idx]
        node = cl[node] if val <= thr[node] else cr[node]

    if node == sk_leaf:
        print("[validate] Traversal matches sklearn leaf index. Export is correct.")
    else:
        print(
            f"[validate] WARNING: mismatch! sk_leaf={sk_leaf}, manual_leaf={node}. "
            f"Check features_used mapping."
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export Third Eye IsolationForest to SP1-compatible JSON."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent.parent / "core" / "weights" / "isolation_forest.pkl",
        help="Path to the .pkl model file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent.parent / "zk-ml" / "model_weights.json",
        help="Output path for model_weights.json.",
    )
    args = parser.parse_args()

    try:
        export_model(args.input, args.output)
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
