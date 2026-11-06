import stat

import pytest


def test_lock_schema_symlinks_and_three_attempts(tmp_path):
    import sqlite3

    from birdwatcher.analysis_queue import AnalysisError, AnalysisQueue

    root = tmp_path / "queue"
    q = AnalysisQueue(root)
    with pytest.raises(AnalysisError):
        AnalysisQueue(root)
    q.enqueue("a", {})
    for _ in range(3):
        assert q.claim()["key"] == "a"
        q.close()
        q = AnalysisQueue(root)
    assert q.claim() is None
    q.close()
    db = sqlite3.connect(root / "analysis.sqlite3")
    db.execute("PRAGMA user_version=99")
    db.close()
    with pytest.raises(AnalysisError, match="schema"):
        AnalysisQueue(root)
    root2 = tmp_path / "linked"
    root2.mkdir()
    (root2 / "analysis.sqlite3-wal").symlink_to(tmp_path / "outside")
    with pytest.raises(AnalysisError, match="Symlink"):
        AnalysisQueue(root2)


def test_size_budget_stops_before_growth(tmp_path):
    from birdwatcher.analysis_queue import AnalysisError, AnalysisQueue

    q = AnalysisQueue(tmp_path / "q")
    q.max_bytes = 65536
    with pytest.raises(AnalysisError, match="budget"):
        q.enqueue("large", {"value": "x" * 65536})
    with pytest.raises(AnalysisError, match="budget"):
        q.claim()
    assert q.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    q.close()


def test_database_errors_are_health_errors_and_recovery_has_result(tmp_path):
    from birdwatcher.analysis_queue import AnalysisError, AnalysisQueue

    root = tmp_path / "q"
    q = AnalysisQueue(root)
    q.db.execute("PRAGMA query_only=ON")
    with pytest.raises(AnalysisError, match="database"):
        q.enqueue("a", {})
    q.db.execute("PRAGMA query_only=OFF")
    q.enqueue("a", {})
    for _ in range(3):
        q.claim()
        q.close()
        q = AnalysisQueue(root)
    assert q.result("a")["status"] == "analysis_failed"
    assert q.result("a")["errors"][0]["code"] == "retry_exhausted"
    q.close()


def test_unversioned_existing_database_is_rejected(tmp_path):
    import sqlite3

    from birdwatcher.analysis_queue import AnalysisError, AnalysisQueue

    root = tmp_path / "q"
    root.mkdir()
    db = sqlite3.connect(root / "analysis.sqlite3")
    db.execute("CREATE TABLE foreign_data(value)")
    db.close()
    with pytest.raises(AnalysisError, match="schema"):
        AnalysisQueue(root)


def test_parent_traversal_cannot_hide_a_symlink(tmp_path):
    from birdwatcher.analysis_queue import AnalysisError, AnalysisQueue

    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / "link").symlink_to(target, target_is_directory=True)
    with pytest.raises(AnalysisError, match="Symlink|traversal"):
        AnalysisQueue(tmp_path / "link" / ".." / "queue")


def test_page_size_and_existing_lock_permissions_are_bounded(tmp_path):
    import os
    import sqlite3

    from birdwatcher.analysis_queue import AnalysisQueue

    root = tmp_path / "q"
    root.mkdir()
    path = root / "analysis.sqlite3"
    db = sqlite3.connect(path)
    db.execute("PRAGMA page_size=8192")
    db.execute("VACUUM")
    db.close()
    lock = root / "worker.lock"
    lock.write_text("")
    os.chmod(lock, 0o644)
    q = AnalysisQueue(root)
    assert q.db.execute("PRAGMA max_page_count").fetchone()[0] <= 3072
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    q.close()


def test_queue_durable_bounded_idempotent(tmp_path):
    from birdwatcher.analysis_queue import AnalysisQueue

    path = tmp_path / "analysis"
    q = AnalysisQueue(path, queue_limit=1)
    assert q.enqueue("a", {"event_id": "a"}) == "enqueued"
    assert q.enqueue("a", {}) == "duplicate"
    assert q.enqueue("b", {}) == "deferred"
    job = q.claim()
    assert job["key"] == "a"
    q.close()
    q = AnalysisQueue(path, queue_limit=1)
    assert q.claim()["key"] == "a"
    q.finish("a", {"status": "unknown"})
    q.close()
    q = AnalysisQueue(path)
    assert q.result("a") == {"status": "unknown"}
    assert q.claim() is None
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert stat.S_IMODE((path / "analysis.sqlite3").stat().st_mode) == 0o600
    q.close()
