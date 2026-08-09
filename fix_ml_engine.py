import re

path = r"d:\NExus\Nexus-Hackathon\backend\core\ml_engine.py"
src = open(path, encoding="utf-8").read()

# 1. Add _IS_WINDOWS flag after the timeout line
old = "ZK_PROVER_TIMEOUT_S = int(os.getenv(\"ZK_PROVER_TIMEOUT_S\", \"300\"))\n"
new = old + "\n# Whether we're on Windows (need to invoke prove via wsl -e)\n_IS_WINDOWS = os.name == \"nt\"\n"
src = src.replace(old, new, 1)

# 2. Replace is_available to support WSL check
old_av = "    def is_available(self) -> bool:\n        return self.prover_bin.exists() and self.model_weights.exists()"
new_av = """    def is_available(self) -> bool:
        if _IS_WINDOWS:
            import subprocess as _sp
            try:
                r = _sp.run(
                    ["wsl", "-d", "Ubuntu", "-u", "root", "-e",
                     "bash", "-c", f"test -f {self.prover_bin} && echo yes || echo no"],
                    capture_output=True, text=True, timeout=10,
                )
                return r.stdout.strip() == "yes"
            except Exception:
                return False
        return self.prover_bin.exists() and self.model_weights.exists()"""
src = src.replace(old_av, new_av, 1)

# 3. Replace the cmd construction to use wsl on Windows
old_cmd = """                # \u2500\u2500 Launch prover CLI \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
                cmd = [
                    str(self.prover_bin),
                    "--model",     str(self.model_weights),
                    "--tx-input",  str(tx_input_p),
                    "--output",    str(proof_out_p),
                    "--threshold", str(self.threshold),
                    "--mode",      self.mode,
                ]"""
new_cmd = """                # \u2500\u2500 Launch prover CLI \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
                def _to_wsl(p) -> str:
                    s = str(p).replace("\\\\", "/")
                    if len(s) >= 2 and s[1] == ":":
                        s = "/mnt/" + s[0].lower() + s[2:]
                    return s

                if _IS_WINDOWS:
                    cmd = [
                        "wsl", "-d", "Ubuntu", "-u", "root", "-e",
                        str(self.prover_bin),
                        "--model",     str(self.model_weights),
                        "--tx-input",  _to_wsl(tx_input_p),
                        "--output",    _to_wsl(proof_out_p),
                        "--threshold", str(self.threshold),
                        "--mode",      self.mode,
                    ]
                else:
                    cmd = [
                        str(self.prover_bin),
                        "--model",     str(self.model_weights),
                        "--tx-input",  str(tx_input_p),
                        "--output",    str(proof_out_p),
                        "--threshold", str(self.threshold),
                        "--mode",      self.mode,
                    ]"""
src = src.replace(old_cmd, new_cmd, 1)

open(path, "w", encoding="utf-8").write(src)
print(f"Patched {path} ({len(src)} bytes)")
