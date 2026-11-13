import json
import os
import threading
import time

from orchestrate import jobs
from orchestrate.registry import Workspace


def test_lock_serialises(tmp_path):
    ws = Workspace(tmp_path)
    order = []

    def hold():
        with ws.lock():
            order.append("a-in")
            time.sleep(0.2)
            order.append("a-out")

    first = threading.Thread(target=hold)
    first.start()
    time.sleep(0.05)
    with ws.lock():
        order.append("b-in")
    first.join()
    assert order == ["a-in", "a-out", "b-in"]


def test_mark_appends_one_event_line(tmp_path):
    ws = Workspace(tmp_path)
    unit = {"unit": "A-1", "status": "building"}
    ws.mark(unit, "started")
    ws.mark(unit, "summary written")
    lines = [json.loads(line) for line in ws.events.read_text().splitlines()]
    assert [line["what"] for line in lines] == ["started", "summary written"]
    assert lines[0]["unit"] == "A-1" and lines[0]["status"] == "building"
    assert {"time", "epoch"} <= set(lines[0])
    assert unit["timeline"][1][1] == "summary written"


def test_wait_sets_status_and_event(tmp_path):
    ws = Workspace(tmp_path)
    unit = {"unit": "A-1", "status": "building"}
    assert ws.wait(unit, "builder gone") == "builder gone"
    assert unit["status"] == "waiting" and unit["event"] == "builder gone"


def test_save_load_roundtrip(tmp_path):
    ws = Workspace(tmp_path)
    ws.save({"A-1": {"status": "building"}})
    assert ws.load() == {"A-1": {"status": "building"}}


def test_background_job_reports_last_line(tmp_path):
    unit = {"name": "a-1"}
    jobs.background(unit, "land", ["bash", "-c", "echo one; echo LANDED"], tmp_path)
    for _ in range(50):
        if jobs.job(unit, "land") is not None:
            break
        time.sleep(0.1)
    assert jobs.job(unit, "land") == "LANDED"
    assert jobs.exit_code(unit, "land") == 0


def test_job_that_died_without_rc(tmp_path):
    log = tmp_path / "a-land.out"
    log.write_text("working\n")
    unit = {"name": "a", "jobs": {"land": {"log": str(log), "started": 0, "pid": 999999}}}
    assert jobs.job(unit, "land") == "FAILED job died without an exit code"
    assert jobs.exit_code(unit, "land") == 255


def test_too_old(tmp_path):
    log = tmp_path / "a-land.out"
    log.write_text("")
    unit = {"name": "a", "jobs": {"land": {"log": str(log), "started": 0, "pid": os.getpid()}}}
    assert jobs.too_old(unit, 3600, now=7200) == "land"
    assert jobs.too_old(unit, 3600, now=100) is None
