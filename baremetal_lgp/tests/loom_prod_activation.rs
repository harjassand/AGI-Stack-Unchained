use loom::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use loom::sync::Arc;
use loom::thread;

#[test]
fn commit_marker_visibility_implies_pointer_visibility() {
    loom::model(|| {
        let active_pointer = Arc::new(AtomicUsize::new(0));
        let commit_marker = Arc::new(AtomicBool::new(false));

        let pointer_w = Arc::clone(&active_pointer);
        let marker_w = Arc::clone(&commit_marker);
        let writer = thread::spawn(move || {
            pointer_w.store(42, Ordering::Release);
            marker_w.store(true, Ordering::Release);
        });

        let pointer_r = Arc::clone(&active_pointer);
        let marker_r = Arc::clone(&commit_marker);
        let reader = thread::spawn(move || {
            if marker_r.load(Ordering::Acquire) {
                assert_ne!(pointer_r.load(Ordering::Acquire), 0);
            }
        });

        writer.join().expect("writer");
        reader.join().expect("reader");
    });
}

#[test]
fn activation_lock_prevents_double_commit() {
    loom::model(|| {
        let activation_lock = Arc::new(AtomicBool::new(false));
        let active_pointer = Arc::new(AtomicUsize::new(0));
        let commit_marker = Arc::new(AtomicBool::new(false));
        let commits = Arc::new(AtomicUsize::new(0));

        let mut handles = Vec::new();
        for candidate in [1usize, 2usize] {
            let lock = Arc::clone(&activation_lock);
            let pointer = Arc::clone(&active_pointer);
            let marker = Arc::clone(&commit_marker);
            let committed = Arc::clone(&commits);
            handles.push(thread::spawn(move || {
                if lock
                    .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
                    .is_ok()
                {
                    if marker
                        .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
                        .is_ok()
                    {
                        pointer.store(candidate, Ordering::Release);
                        committed.fetch_add(1, Ordering::AcqRel);
                    }
                    lock.store(false, Ordering::Release);
                }
            }));
        }

        for handle in handles {
            handle.join().expect("activation thread");
        }

        assert_eq!(commits.load(Ordering::Acquire), 1);
        let winner = active_pointer.load(Ordering::Acquire);
        assert!(winner == 1 || winner == 2);
    });
}
