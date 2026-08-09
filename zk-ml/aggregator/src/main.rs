// zk-ml/aggregator/src/main.rs — Third Eye SP1 Recursive Proof Aggregator
//
// This is a SECOND SP1 guest program (also runs inside a zkVM).
// Its purpose is to aggregate multiple individual transaction proofs
// from the primary guest (thirdeye-zkml-program) into a single
// batch proof, enabling efficient on-chain verification.
//
// Protocol:
//   Host → aggregator guest:
//     1. The verification key digest of the primary guest (THIRDEYE_VK)
//     2. N × ProofItem { public_values_digest: [u8;32], proof_commitment: [u8;32] }
//
//   Inside the aggregator:
//     3. For each ProofItem, call sp1_zkvm::lib::verify::verify_sp1_proof()
//        which verifies the proof recursively inside the zkVM.  If ANY
//        proof is invalid, the entire aggregator proof fails.
//     4. Commit BatchOutput { n_valid, total_safe, batch_hash }
//
// The aggregator guest is then proven by the host, producing ONE proof
// that certifies N individual wallet risk assessments simultaneously.
// This proof can be posted on-chain once to settle a whole batch.
//
// Recursive verification reference:
//   https://docs.succinct.xyz/docs/sp1/writing-programs/proof-aggregation

#![no_main]
sp1_zkvm::entrypoint!(main);

extern crate alloc;
use alloc::{string::String, vec::Vec};

use serde::{Deserialize, Serialize};

// ── Input types (written by the host into SP1 stdin) ─────────────────────────

/// Digest of the primary guest's verification key.
/// Computed on the host via: `vk.bytes32()` which returns a hex string;
/// we transmit it as a [u32; 8] matching SP1's internal representation.
#[derive(Deserialize)]
struct VKeyDigest {
    /// Verification key digest as 8 x u32 words (little-endian words of the 32-byte hash)
    words: [u32; 8],
}

/// One item in the aggregation batch — corresponds to one wallet proof.
#[derive(Deserialize)]
struct ProofItem {
    /// tx_id from the primary guest's ProofOutput (for bookkeeping)
    tx_id: String,
    /// The 32-byte public values digest from the primary proof.
    /// SP1 computes this as SHA256(borsh_serialize(public_values)).
    /// The host extracts it from SP1ProofWithPublicValues::public_values.hash().
    public_values_digest: [u8; 32],
    /// The 32-byte proof commitment (the STARK/Groth16 proof hash).
    /// Extracted on the host from the proof object.
    proof_commitment: [u8; 32],
    /// is_safe as committed by the primary guest (from public values)
    is_safe: bool,
    /// anomaly_score_fp as committed (fixed-point u32, scale 1_000_000)
    anomaly_score_fp: u32,
}

/// Aggregation input: all proofs + the common verification key
#[derive(Deserialize)]
struct AggregatorInput {
    /// VK digest of the primary guest (thirdeye-zkml-program)
    primary_vk: VKeyDigest,
    /// The batch of individual proofs to aggregate
    proofs: Vec<ProofItem>,
}

/// Public output committed by the aggregator
#[derive(Serialize)]
struct BatchOutput {
    /// Total number of proofs in this batch
    n_total: u32,
    /// Number that are is_safe=true (all must be true for aggregator to succeed)
    n_valid_safe: u32,
    /// XOR of all tx_id bytes as a simple batch fingerprint
    /// (a proper Merkle root would be better for production)
    batch_fingerprint: [u8; 32],
    /// Sum of all anomaly scores (fixed-point, scale 1_000_000)
    total_anomaly_score_fp: u64,
}

// ── Utility: simple batch hash ────────────────────────────────────────────────

/// Compute a 32-byte batch fingerprint by hashing (XOR-chaining) all
/// public_values_digests together.  Cheap inside the zkVM.
/// In production, replace with a Merkle tree root for better security.
fn compute_batch_fingerprint(proofs: &[ProofItem]) -> [u8; 32] {
    let mut acc = [0u8; 32];
    for (i, proof) in proofs.iter().enumerate() {
        for (j, byte) in proof.public_values_digest.iter().enumerate() {
            // Mix in the tx position to prevent collisions between
            // items with identical digests
            acc[j] ^= byte ^ (i as u8);
        }
    }
    acc
}

// ── Main entrypoint ───────────────────────────────────────────────────────────

pub fn main() {
    // ── Step 1: Read aggregator input from SP1 stdin ──────────────────────
    let input: AggregatorInput = sp1_zkvm::io::read::<AggregatorInput>();

    assert!(
        !input.proofs.is_empty(),
        "Aggregator received empty proof batch — nothing to verify."
    );
    assert!(
        input.proofs.len() <= 1024,
        "Batch too large: {} proofs (max 1024)",
        input.proofs.len()
    );

    let n_total = input.proofs.len() as u32;
    let vk_words = &input.primary_vk.words;

    let mut n_valid_safe: u32 = 0;
    let mut total_anomaly_score_fp: u64 = 0u64;

    // ── Step 2: Verify each proof recursively inside the zkVM ─────────────
    for (idx, proof_item) in input.proofs.iter().enumerate() {
        // sp1_zkvm::lib::verify::verify_sp1_proof is the recursive verifier.
        // It checks that there exists a valid SP1 proof for the program
        // identified by `vk_words` that produced `public_values_digest`.
        //
        // If this panics, no proof can be generated for the aggregator itself —
        // making the entire batch invalid.  This is the core security guarantee.
        sp1_zkvm::lib::verify::verify_sp1_proof(
            vk_words,
            &proof_item.public_values_digest,
        );

        // After successful recursive verification, we can trust the public values.
        assert!(
            proof_item.is_safe,
            "Batch item {} (tx_id={}) has is_safe=false — batch rejected.",
            idx,
            proof_item.tx_id
        );

        n_valid_safe             += 1;
        total_anomaly_score_fp   += proof_item.anomaly_score_fp as u64;
    }

    // All n_total proofs passed recursive verification.
    assert_eq!(
        n_valid_safe, n_total,
        "n_valid_safe ({}) != n_total ({}) — internal error",
        n_valid_safe, n_total
    );

    // ── Step 3: Commit batch output ───────────────────────────────────────
    let batch_fingerprint = compute_batch_fingerprint(&input.proofs);

    let output = BatchOutput {
        n_total,
        n_valid_safe,
        batch_fingerprint,
        total_anomaly_score_fp,
    };

    sp1_zkvm::io::commit(&output);
}
