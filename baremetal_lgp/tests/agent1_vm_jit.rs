#[cfg(all(feature = "jit", target_os = "macos", target_arch = "aarch64"))]
#[test]
fn agent1_vm_jit_exec_stub_once() {
    use baremetal_lgp::jit::aarch64;
    use baremetal_lgp::jit::map_jit;

    let code = aarch64::emit_default_vadd_stub();
    let buf = map_jit::jit_alloc(code.len());

    let a = [1.0f32, 2.0, 3.0, 4.0];
    let b = [10.0f32, 20.0, 30.0, 40.0];
    let mut dst = [0.0f32; 4];

    // SAFETY: code is freshly emitted; pointers are valid for len elements.
    unsafe {
        map_jit::jit_write(&buf, &code);
        map_jit::jit_exec_vadd(&buf, dst.as_mut_ptr(), a.as_ptr(), b.as_ptr(), dst.len());
    }

    assert_eq!(dst, [11.0, 22.0, 33.0, 44.0]);
}
