import json
from pathlib import Path
import joblib
import numpy as np
import ezkl

from sklearn.neural_network import MLPRegressor
from skl2onnx import to_onnx

WEIGHTS_PATH = Path(__file__).parent.parent / "core" / "weights" / "isolation_forest.pkl"
EZKL_DIR = Path(__file__).parent.parent / "core" / "ezkl_artifacts"
EZKL_DIR.mkdir(exist_ok=True, parents=True)

ONNX_PATH = str(EZKL_DIR / "network.onnx")
INPUT_JSON = str(EZKL_DIR / "input.json")
MODEL_PKL = str(EZKL_DIR / "zk_model.pkl")

print("Loading Isolation Forest to generate training data...")
if_model = joblib.load(WEIGHTS_PATH)

print("Generating synthetic data and labels...")
# Use smaller values to avoid ZK circuit overflow (halo2 synthesis error)
X_train = np.random.uniform(-1, 1, size=(2000, 10)).astype(np.float32)

raw = if_model.decision_function(X_train)
y_train = np.clip(0.5 - raw, 0.0, 1.0).astype(np.float32)

print("Training scikit-learn MLPRegressor for ZK-ML...")
# Use extremely tiny MLP to avoid ZK halo2 synthesis overflow!
mlp = MLPRegressor(hidden_layer_sizes=(4,), max_iter=100, alpha=1.0, random_state=42)
mlp.fit(X_train, y_train)
print(f"Final training score (R^2): {mlp.score(X_train, y_train):.4f}")

joblib.dump(mlp, MODEL_PKL)

print("Exporting MLPRegressor to ONNX using skl2onnx...")
dummy_input = X_train[:1].astype(np.float32)

# Convert to standard ONNX (target opset 14 usually works well for EZKL)
onx = to_onnx(mlp, dummy_input, target_opset=14)

with open(ONNX_PATH, "wb") as f:
    f.write(onx.SerializeToString())

print("Creating input.json for EZKL...")
# EZKL expects a list of lists, where each inner list is a flattened tensor
data = {"input_data": [dummy_input.flatten().tolist()]}
with open(INPUT_JSON, "w") as f:
    json.dump(data, f)

print("Running EZKL compilation...")
SETTINGS_PATH = str(EZKL_DIR / "settings.json")
COMPILED_MODEL_PATH = str(EZKL_DIR / "network.compiled")
VK_PATH = str(EZKL_DIR / "vk.key")
PK_PATH = str(EZKL_DIR / "pk.key")
SRS_PATH = str(EZKL_DIR / "kzg.srs")

import sys
sys.stdout.reconfigure(encoding='utf-8')

ezkl.gen_settings(ONNX_PATH, SETTINGS_PATH)

import json
with open(SETTINGS_PATH, 'r') as f:
    settings = json.load(f)

# Force small scales to absolutely prevent halo2 integer overflow
settings['run_args']['input_scale'] = 5
settings['run_args']['param_scale'] = 5
# Adjust logrows explicitly
settings['run_args']['logrows'] = 14

with open(SETTINGS_PATH, 'w') as f:
    json.dump(settings, f)

# Skip calibrate_settings to avoid it overriding our scales
# ezkl.calibrate_settings(INPUT_JSON, ONNX_PATH, SETTINGS_PATH, "resources")

ezkl.compile_circuit(ONNX_PATH, COMPILED_MODEL_PATH, SETTINGS_PATH)
with open(SETTINGS_PATH, 'r') as f:
    settings = json.load(f)
logrows = settings['run_args']['logrows']
print(f"Generating SRS for logrows={logrows}...")
ezkl.gen_srs(SRS_PATH, logrows)

WITNESS_PATH = str(EZKL_DIR / "witness.json")
print("Generating witness...")
ezkl.gen_witness(INPUT_JSON, COMPILED_MODEL_PATH, WITNESS_PATH)

print("Running mock to test circuit validity...")
try:
    res = ezkl.mock(COMPILED_MODEL_PATH, WITNESS_PATH)
    print(f"Mock execution result: {res}")
except Exception as e:
    print(f"Mock execution failed: {e}")

# Comment out setup since it panics on Windows with NotPresent
# ezkl.setup(COMPILED_MODEL_PATH, VK_PATH, PK_PATH, SRS_PATH, witness_path=WITNESS_PATH)
