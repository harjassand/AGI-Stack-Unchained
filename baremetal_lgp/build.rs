fn main() {
    println!("cargo:rerun-if-changed=native_jit/jit_trampoline.c");
    println!("cargo:rerun-if-changed=native_jit/jit_trampoline.h");
    println!("cargo:rerun-if-changed=native_jit/sniper.c");
    println!("cargo:rerun-if-changed=native_jit/sniper.h");

    cc::Build::new()
        .file("native_jit/jit_trampoline.c")
        .file("native_jit/sniper.c")
        .opt_level(3)
        .define("_XOPEN_SOURCE", Some("700"))
        .flag_if_supported("-fno-omit-frame-pointer")
        .compile("blgp_native_jit");
}
