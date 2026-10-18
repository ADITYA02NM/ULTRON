"""The vault is written from paho's thread, not the one that opened it.

`Link` starts paho with loop_start(), so on_message -- and therefore every Vault
call -- runs on a network thread the Vault was not constructed on. sqlite refuses
that by default, and did: the node died on the first retained message, so it
never recorded an alert, never moved its band tracker and never sent a
notification. The whole Pi3b node was dead on arrival, and nothing caught it
because the node had never actually been run.

These tests pin the property that was missing.
"""

from __future__ import annotations

import threading

# conftest.py puts nodes/{common,pi4,pi3a,pi3b} on sys.path.
import alert_manager


def _in_thread(fn, *args, **kwargs):
    """Run fn on a worker thread and re-raise whatever it raised there.

    A raise inside a thread is invisible to the test runner otherwise, which is
    exactly how the original bug survived.
    """
    box: dict = {}

    def target() -> None:
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised below on purpose
            box["error"] = exc

    worker = threading.Thread(target=target)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive(), "the worker thread never finished"
    if "error" in box:
        raise box["error"]
    return box.get("value")


def test_the_vault_works_from_a_thread_that_did_not_open_it(tmp_path):
    vault = alert_manager.Vault(str(tmp_path / "vault.db"))
    try:
        # Each of these is what paho's thread does to us on every message.
        _in_thread(vault.record_score, 42)
        _in_thread(vault.record_alert,
                   {"id": "a1", "sev": "red", "title": "T", "src": "test"})

        stored = _in_thread(vault.find_alert, "a1")
        assert stored is not None
        assert stored["title"] == "T"
        assert stored["ack"] is False

        assert _in_thread(vault.acknowledge, "a1") is True
        assert _in_thread(vault.find_alert, "a1")["ack"] is True
    finally:
        vault.close()


def test_an_alert_recorded_off_thread_is_durable(tmp_path):
    """A reopen proves it was committed, not merely buffered in the connection."""
    path = str(tmp_path / "vault.db")
    first = alert_manager.Vault(path)
    try:
        _in_thread(first.record_alert, {"id": "a2", "sev": "purple", "title": "P"})
    finally:
        first.close()

    second = alert_manager.Vault(path)
    try:
        assert second.find_alert("a2")["sev"] == "purple"
    finally:
        second.close()


def test_concurrent_writers_do_not_lose_rows(tmp_path):
    """The lock is what makes check_same_thread=False safe rather than lucky."""
    vault = alert_manager.Vault(str(tmp_path / "vault.db"))
    try:
        def hammer(worker_id: int) -> None:
            for i in range(50):
                vault.record_score(worker_id * 100 + i)

        workers = [threading.Thread(target=hammer, args=(n,)) for n in range(4)]
        for w in workers:
            w.start()
        for w in workers:
            w.join(timeout=20)
        assert all(not w.is_alive() for w in workers), "a writer hung"

        # Every thread has joined, so reading the connection directly is safe.
        count = vault.db.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        assert count == 200
    finally:
        vault.close()


def test_a_second_acknowledge_is_a_no_op(tmp_path):
    """Two acks racing from different threads must not both claim the change."""
    vault = alert_manager.Vault(str(tmp_path / "vault.db"))
    try:
        vault.record_alert({"id": "a3", "sev": "red", "title": "T"})
        results = []

        def ack() -> None:
            results.append(vault.acknowledge("a3"))

        workers = [threading.Thread(target=ack) for _ in range(2)]
        for w in workers:
            w.start()
        for w in workers:
            w.join(timeout=10)

        # Exactly one caller gets to claim it, which is what the endpoint reports.
        assert results.count(True) == 1
    finally:
        vault.close()
