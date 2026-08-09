path = r"d:\NExus\Nexus-Hackathon\zk-ml\program\src\main.rs"
src = open(path, encoding="utf-8").read()

# Add no_std allow attributes right after the comment block (before #![no_std] or the first #!)
allow_attrs = """#![allow(dead_code)]
#![allow(unused_variables)]
#![allow(unused_imports)]
"""

# Find the first line that starts with #! or the first non-comment line
lines = src.split("\n")
insert_at = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped and not stripped.startswith("//"):
        insert_at = i
        break

lines.insert(insert_at, allow_attrs.rstrip())
result = "\n".join(lines)
open(path, "w", encoding="utf-8").write(result)
print(f"Patched: added allow(dead_code) at line {insert_at}")
