import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from contract import schema_errors
from scripted import ScriptedGame
from support import ENVIRONMENT

from bowlharness.backends.mock import MockTarget
from bowlharness.driving.request import Request
from bowlharness.session.driven import DrivenSession
from bowlharness.session.session import ENDED, PAUSED
from bowlharness.store.queue import ProgressStream, Queue
from bowlharness.store.store import Claim, Store, content_hash


def route(request_id: str, scene: str = "ORIG") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_id": request_id,
        "kind": "record",
        "start": {"from": "booted"},
        "steps": [{"scene": scene}],
    }


def add(store: Store, document: dict[str, Any], *, age: int = 0) -> Path:
    path = store.requests / f"{document['request_id']}.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    os.utime(path, (1_700_000_000 + age, 1_700_000_000 + age))
    return path


def loaded(scene: str = "ORIG") -> ScriptedGame:
    game = ScriptedGame()
    game.scene_init(scene, 1)
    game.players_done()
    for _ in range(14):
        game.pad_poll()
    return game


def opener(games: Callable[[], ScriptedGame] = loaded) -> Callable[..., DrivenSession]:
    def open_session(
        request: Request, digest: str, claim: Claim, folder: Path, on_event: Callable[[str, dict[str, object]], None]
    ) -> DrivenSession:
        game = games()
        target = MockTarget(game.script, {**game.kernel_image(), game.profile.globals.frame: bytes(4)})
        return DrivenSession(
            target,
            game.profile,
            folder,
            request,
            digest,
            run_stem=claim.run,
            environment=ENVIRONMENT,
            harness="0.1.0+test",
            attempt=claim.attempt,
            instance=claim.instance,
            on_event=on_event,
        )

    return open_session


def queue_of(store: Store, games: Callable[[], ScriptedGame] = loaded) -> tuple[Queue, list[int]]:
    reboots: list[int] = []
    progress = ProgressStream(store.progress, store.instance)
    queue = Queue(store, progress, ScriptedGame().profile, opener(games), lambda: reboots.append(1))
    return queue, reboots


def run_all(queue: Queue) -> None:
    while (session := queue.start_next()) is not None:
        assert session.run() == ENDED
        if not queue.finish(session):
            break


def progress(store: Store) -> list[dict[str, Any]]:
    return [json.loads(line) for line in store.progress.read_text(encoding="utf-8").splitlines()]


def dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def test_two_claims_of_one_request_and_one_wins(tmp_path: Path) -> None:
    first, second = Store(tmp_path, "inst1"), Store(tmp_path, "inst2")
    add(first, route("r1"))
    (request,) = first.pending()[0]

    claims = [first.claim(request), second.claim(request)]

    assert claims[0] is not None and claims[0].run == "r1-a1" and claims[1] is None


def test_the_queue_runs_every_pending_request_oldest_first_with_a_result_each(tmp_path: Path) -> None:
    store = Store(tmp_path, "inst3")
    add(store, route("later") | {"input": {"hold": 7}}, age=5)
    add(store, route("sooner"), age=1)
    queue, _ = queue_of(store)

    run_all(queue)

    started = [line["run"] for line in progress(store) if line["event"] == "started"]
    assert started == ["sooner-a1", "later-a1"]
    for run in started:
        result = json.loads((store.runs / run / "result.json").read_text(encoding="utf-8"))
        assert (result["run"], result["instance"], result["outcome"]) == (run, "inst3", "survived")
        assert schema_errors(result, "result") == []
    assert list(store.claims.iterdir()) == []


def test_the_queue_reboots_the_guest_before_every_run(tmp_path: Path) -> None:
    store = Store(tmp_path, "inst3")
    add(store, route("r1"))
    add(store, route("r2") | {"input": {"hold": 7}})
    queue, reboots = queue_of(store)

    run_all(queue)

    assert len(reboots) == 2


def test_the_progress_stream_has_a_line_per_run_in_order(tmp_path: Path) -> None:
    store = Store(tmp_path, "inst3")
    add(store, route("r1"))
    queue, _ = queue_of(store)

    run_all(queue)

    lines = progress(store)
    assert [line["event"] for line in lines] == ["started", "finished"]
    finished = lines[-1]
    assert (finished["run"], finished["outcome"], finished["flags"], finished["token_gain"], finished["left"]) == (
        "r1-a1",
        "survived",
        [],
        None,
        0,
    )


def test_a_duplicate_of_a_request_with_a_result_is_skipped_naming_its_match(tmp_path: Path) -> None:
    store = Store(tmp_path, "inst3")
    add(store, route("first"), age=1)
    queue, _ = queue_of(store)
    run_all(queue)
    add(store, route("again") | {"client": {"note": 1}}, age=2)
    queue, _ = queue_of(store)

    run_all(queue)

    skipped = [line for line in progress(store) if line["event"] == "skipped"]
    assert [(line["request"], line["matched"]) for line in skipped] == [("again", "first")]
    assert not (store.runs / "again-a1").exists()


def test_the_content_hash_leaves_out_the_id_and_the_client() -> None:
    assert content_hash(route("a")) == content_hash(route("b") | {"client": 1}) != content_hash(route("a", "TARG"))


def test_a_duplicate_of_an_interrupted_request_is_not_skipped(tmp_path: Path) -> None:
    store = Store(tmp_path, "inst3")
    add(store, route("first"), age=1)
    queue, _ = queue_of(store, lambda: paused_game())
    session = queue.start_next()
    assert session is not None and session.run() == PAUSED
    session.stop()
    queue.finish(session)
    add(store, route("again"), age=2)

    pending, skipped, _ = store.pending()

    assert ([request.request_id for request in pending], skipped) == (["first", "again"], [])


def paused_game() -> ScriptedGame:
    game = ScriptedGame()
    game.scene_init("ORIG", 1)
    return game


def test_a_stopped_run_is_interrupted_its_claim_gone_and_the_next_queue_runs_it_as_attempt_2(tmp_path: Path) -> None:
    store = Store(tmp_path, "inst3")
    add(store, route("r1"))
    queue, _ = queue_of(store, paused_game)
    session = queue.start_next()
    assert session is not None and session.run() == PAUSED
    session.stop()

    goes_on = queue.finish(session)

    stopped = json.loads((store.runs / "r1-a1" / "result.json").read_text(encoding="utf-8"))
    assert (goes_on, stopped["outcome"], stopped["cause"], list(store.claims.iterdir())) == (
        False,
        "interrupted",
        "stopped",
        [],
    )
    queue, _ = queue_of(store)
    run_all(queue)
    second = json.loads((store.runs / "r1-a2" / "result.json").read_text(encoding="utf-8"))
    assert (second["attempt"], second["outcome"]) == (2, "survived")


def test_a_dead_claim_of_this_instance_becomes_a_lost_attempt_and_the_request_is_pending_again(tmp_path: Path) -> None:
    store = Store(tmp_path, "inst3")
    add(store, route("r1"))
    queue, _ = queue_of(store, paused_game)
    session = queue.start_next()
    assert session is not None and session.run() == PAUSED
    (store.claims / "r1.json").write_text(
        json.dumps(
            {
                "claim": {
                    "request_id": "r1",
                    "run": "r1-a1",
                    "attempt": 1,
                    "instance": "inst3",
                    "host": store.host,
                    "pid": dead_pid(),
                }
            }
        ),
        encoding="utf-8",
    )
    later = Store(tmp_path, "inst3")
    queue, _ = queue_of(later)

    recovered = queue.recover()

    lost = json.loads((store.runs / "r1-a1" / "result.json").read_text(encoding="utf-8"))
    assert (recovered, lost["outcome"], lost["cause"]) == (["r1-a1"], "interrupted", "lost")
    assert [request.request_id for request in later.pending()[0]] == ["r1"]
    assert later.claim(later.pending()[0][0]) == Claim("r1", "r1-a2", 2, "inst3", later.host, later.pid)


def test_another_instances_claim_is_left_alone(tmp_path: Path) -> None:
    store = Store(tmp_path, "inst3")
    add(store, route("r1"))
    other = Store(tmp_path, "inst4", pid=dead_pid())
    other.claim(other.pending()[0][0])

    assert (store.dead_claims(), store.pending()[0]) == ([], [])


def test_a_request_file_that_is_not_its_request_is_refused_and_the_rest_run(tmp_path: Path) -> None:
    store = Store(tmp_path, "inst3")
    (store.requests / "broken.json").write_text("{", encoding="utf-8")
    add(store, route("r1"))
    queue, _ = queue_of(store)

    run_all(queue)

    events = [(line["event"], line.get("request")) for line in progress(store)]
    assert events == [("refused", "broken.json"), ("started", None), ("finished", None)]


def test_a_stall_line_is_written_once_when_no_progress_came_for_the_stall_time(tmp_path: Path) -> None:
    now = [0.0]
    stream = ProgressStream(tmp_path / "progress.jsonl", "inst3", stall_seconds=600, clock=lambda: now[0])

    now[0] = 599
    stream.check_stall("r1-a1")
    now[0] = 601
    stream.check_stall("r1-a1")
    stream.check_stall("r1-a1")

    lines = [json.loads(line) for line in (tmp_path / "progress.jsonl").read_text().splitlines()]
    assert [(line["event"], line["run"], line["seconds"]) for line in lines] == [("stall", "r1-a1", 601)]
