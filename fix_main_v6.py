# Write a fully correct SP1 v6 async main.rs
content = r'''// zk-ml/script/src/main.rs — Third Eye SP1 v6 Host/Prover CLI (async)
//
// SP1 v6 key changes from v3:
//   - include_elf! returns sp1_sdk::Elf, not &[u8]
//   - ProverClient::builder().build().await  (async constructor)
//   - main() must be #[tokio::main] async
//   - SP1_PROVER=network routes to Succinct proving network

use std::path::PathBuf;
use std::time::Instant;

use clap::{Parser, ValueEnum};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sp1_sdk::{include_elf, ProverClient, SP1ProofWithPublicValues, SP1Stdin};
use tracing::{error, info, warn};

pub const THIRDEYE_ELF: sp1_sdk::Elf = include_elf!("thirdeye-zkml-program");

#[derive(Debug, Clone, ValueEnum)]
enum ProofMode {
    Simulate,
    Core,
    Groth16,
    Plonk,
}

#[derive(Parser, Debug)]
#[command(name = "thirdeye-prover", version = "0.1.0",
    about = "Third Eye SP1 v6 zkML Prover")]
struct Cli {
    #[arg(long, default_value = "zk-ml/model_weights.json")]
    model: PathBuf,
    #[arg(long)]
    tx_input: PathBuf,
    #[arg(long, default_value = "/tmp/thirdeye_proof.json")]
    output: PathBuf,
    #[arg(long, default_value_t = 0.65_f64)]
    threshold: f64,
    #[arg(long, value_enum, default_value_t = ProofMode::Core)]
    mode: ProofMode,
}

#[derive(Serialize, Deserialize, Debug)]
struct TxInputJson {
    tx_id: String,
    features: Vec<f64>,
    max_risk_threshold: f64,
}

#[derive(Serialize, Deserialize, Debug)]
struct ProofResult {
    tx_id: String,
    is_safe: bool,
    anomaly_score: f64,
    threshold: f64,
    proof_bytes_b64: String,
    public_values: Value,
    proving_time_ms: u64,
    proof_mode: String,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let cli = Cli::parse();

    info!("Third Eye SP1 v6 Prover starting");
    info!("  model     : {:?}", cli.model);
    info!("  tx_input  : {:?}", cli.tx_input);
    info!("  threshold : {}", cli.threshold);
    info!("  mode      : {:?}", cli.mode);

    let model_raw = std::fs::read_to_string(&cli.model).unwrap_or_else(|e| {
        error!("Cannot read model: {:?}: {}", cli.model, e);
        std::process::exit(1);
    });
    let _: Value = serde_json::from_str(&model_raw).unwrap_or_else(|e| {
        error!("model_weights.json invalid JSON: {}", e);
        std::process::exit(1);
    });
    info!("Model loaded ({} bytes)", model_raw.len());

    let tx_raw = std::fs::read_to_string(&cli.tx_input).unwrap_or_else(|e| {
        error!("Cannot read tx_input: {:?}: {}", cli.tx_input, e);
        std::process::exit(1);
    });
    let mut tx_input: TxInputJson = serde_json::from_str(&tx_raw).unwrap_or_else(|e| {
        error!("tx_input.json parse error: {}", e);
        std::process::exit(1);
    });
    tx_input.max_risk_threshold = cli.threshold;
    info!("TxInput: id={}, features={}", tx_input.tx_id, tx_input.features.len());

    let mut stdin = SP1Stdin::new();
    stdin.write_slice(model_raw.as_bytes());
    let tx_bytes = serde_json::to_vec(&tx_input).expect("tx serialization failed");
    stdin.write_slice(&tx_bytes);

    // SP1 v6: async builder — reads SP1_PROVER env var (network|local|mock)
    let client = ProverClient::builder().build().await;
    let (pk, vk) = client.setup(THIRDEYE_ELF).await;
    info!("SP1 proving key set up.");

    let t0 = Instant::now();

    let proof: SP1ProofWithPublicValues = match cli.mode {
        ProofMode::Simulate => {
            warn!("SIMULATE mode — no proof generated.");
            let (_pv, _report) = client
                .execute(THIRDEYE_ELF, &stdin)
                .run()
                .await
                .unwrap_or_else(|e| { error!("Execute failed: {}", e); std::process::exit(1); });
            info!("Simulation OK.");
            panic!("Simulate does not produce a proof. Use --mode core.");
        }
        ProofMode::Core => {
            info!("Generating SP1 Core STARK proof...");
            client.prove(&pk, &stdin).run().await
                .unwrap_or_else(|e| { error!("Core proof failed: {}", e); std::process::exit(1); })
        }
        ProofMode::Groth16 => {
            info!("Generating Groth16 proof...");
            client.prove(&pk, &stdin).groth16().run().await
                .unwrap_or_else(|e| { error!("Groth16 failed: {}", e); std::process::exit(1); })
        }
        ProofMode::Plonk => {
            info!("Generating PLONK proof...");
            client.prove(&pk, &stdin).plonk().run().await
                .unwrap_or_else(|e| { error!("PLONK failed: {}", e); std::process::exit(1); })
        }
    };

    let elapsed_ms = t0.elapsed().as_millis() as u64;
    info!("Proof generated in {}ms", elapsed_ms);

    client.verify(&proof, &vk).await
        .unwrap_or_else(|e| { error!("Verification failed: {}", e); std::process::exit(1); });
    info!("Proof verified OK.");

    let mut pv = proof.public_values.clone();
    let _tx_id_out: String = pv.read::<String>();
    let is_safe: bool = pv.read::<bool>();
    let anomaly_score_fp: u32 = pv.read::<u32>();
    let threshold_fp: u32 = pv.read::<u32>();

    let anomaly_score = anomaly_score_fp as f64 / 1_000_000.0;
    let threshold_out = threshold_fp as f64 / 1_000_000.0;

    info!("is_safe={}, score={:.6}, threshold={:.6}", is_safe, anomaly_score, threshold_out);

    let proof_bytes = bincode::serialize(&proof).unwrap_or_else(|e| {
        error!("Proof serialize failed: {}", e); std::process::exit(1);
    });
    let proof_b64 = base64_encode(&proof_bytes);

    let result = ProofResult {
        tx_id: tx_input.tx_id.clone(),
        is_safe,
        anomaly_score,
        threshold: threshold_out,
        proof_bytes_b64: proof_b64,
        public_values: serde_json::json!({
            "is_safe": is_safe,
            "anomaly_score_fp": anomaly_score_fp,
            "threshold_fp": threshold_fp,
        }),
        proving_time_ms: elapsed_ms,
        proof_mode: format!("{:?}", cli.mode),
    };

    let json = serde_json::to_string_pretty(&result).expect("result serialize failed");
    std::fs::write(&cli.output, &json).unwrap_or_else(|e| {
        error!("Write proof failed: {:?}: {}", cli.output, e); std::process::exit(1);
    });
    info!("Proof written to {:?} ({} bytes)", cli.output, json.len());
    println!(
        r#"{{"success":true,"anomaly_score":{},"is_safe":{},"proof_path":"{}"}}"#,
        anomaly_score, is_safe, cli.output.display()
    );
}

fn base64_encode(data: &[u8]) -> String {
    const C: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = Vec::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0] as usize;
        let b1 = if chunk.len() > 1 { chunk[1] as usize } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] as usize } else { 0 };
        out.push(C[(b0 >> 2) & 0x3F]);
        out.push(C[((b0 << 4) | (b1 >> 4)) & 0x3F]);
        out.push(if chunk.len() > 1 { C[((b1 << 2) | (b2 >> 6)) & 0x3F] } else { b'=' });
        out.push(if chunk.len() > 2 { C[b2 & 0x3F] } else { b'=' });
    }
    String::from_utf8(out).unwrap()
}
'''

path = r"d:\NExus\Nexus-Hackathon\zk-ml\script\src\main.rs"
open(path, "w", encoding="utf-8").write(content)
print(f"Written {len(content)} bytes to {path}")
