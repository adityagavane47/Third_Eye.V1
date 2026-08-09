// zk-ml/script/build.rs
// Compiles the guest program ELF and makes it available to the host
// via the sp1_sdk::include_elf! macro.

fn main() {
    sp1_build::build_program("../program");
}
