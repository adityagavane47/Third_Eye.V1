path = r"d:\NExus\Nexus-Hackathon\zk-ml\script\src\main.rs"
src = open(path, encoding="utf-8").read()

# Fix 1: include_elf returns sp1_sdk::Elf in v6, not &[u8]
src = src.replace(
    "pub const THIRDEYE_ELF: &[u8] = include_elf!(\"thirdeye-zkml-program\");",
    "pub const THIRDEYE_ELF: sp1_sdk::Elf = include_elf!(\"thirdeye-zkml-program\");"
)

# Fix 2: ProverClient::new() -> ProverClient::builder().build() in v6
src = src.replace(
    "let client = ProverClient::new();",
    "let client = ProverClient::builder().build();"
)

# Fix 3: Remove unused std::io::Write import causing warning
src = src.replace("use std::io::Write;\n", "")
src = src.replace("    use std::io::Write;\n", "")

# Fix 4: Also fix the bincode import - make sure it's used directly
# bincode is now a direct dep, already accessible

open(path, "w", encoding="utf-8").write(src)
print(f"Patched {path} ({len(src)} bytes)")
