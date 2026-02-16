from tasks.make_curriculum import generate_tasks


def test_curriculum_deterministic():
    tasks_a = generate_tasks(25, seed=0)
    tasks_b = generate_tasks(25, seed=0)
    assert tasks_a == tasks_b
    assert len(tasks_a) == 25
