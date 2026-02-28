use loom::sync::atomic::{AtomicUsize, Ordering};
use loom::sync::Arc;
use loom::thread;

#[test]
fn lease_allows_single_owner_at_a_time() {
    loom::model(|| {
        let owner = Arc::new(AtomicUsize::new(0));

        let owner_a = Arc::clone(&owner);
        let t1 = thread::spawn(move || {
            owner_a
                .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
                .is_ok()
        });

        let owner_b = Arc::clone(&owner);
        let t2 = thread::spawn(move || {
            owner_b
                .compare_exchange(0, 2, Ordering::AcqRel, Ordering::Acquire)
                .is_ok()
        });

        let won_a = t1.join().expect("thread A");
        let won_b = t2.join().expect("thread B");
        assert_ne!(won_a, won_b);
        let final_owner = owner.load(Ordering::Acquire);
        assert!(final_owner == 1 || final_owner == 2);
    });
}
