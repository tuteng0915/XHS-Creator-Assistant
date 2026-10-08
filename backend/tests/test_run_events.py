from app.services.run_events import RUN_EVENT_TYPES, RunEventEmitter, terminal_event_type


def test_run_event_emitter_builds_stable_ordered_envelopes() -> None:
    ids = iter(["event-1", "event-2", "event-3"])
    emitter = RunEventEmitter(
        run_id="run-1",
        run_type="account_diagnosis",
        event_id_factory=lambda: next(ids),
        clock=lambda: "2026-10-06T00:00:00+00:00",
    )
    caller_payload = {"answer": 42, "eventType": "untrusted"}

    created = emitter.run_created(status="pending")
    started = emitter.stage_started("profile", data=caller_payload)
    completed = emitter.stage_succeeded("profile", data={"profile": {"name": "A"}})

    assert [event["sequence"] for event in [created, started, completed]] == [1, 2, 3]
    assert [event["eventId"] for event in [created, started, completed]] == [
        "event-1",
        "event-2",
        "event-3",
    ]
    assert created == {
        "eventId": "event-1",
        "runId": "run-1",
        "runType": "account_diagnosis",
        "stageKey": None,
        "status": "pending",
        "sequence": 1,
        "occurredAt": "2026-10-06T00:00:00+00:00",
        "data": {"eventType": "run.created"},
    }
    assert started["data"] == {"answer": 42, "eventType": "stage.started"}
    assert caller_payload == {"answer": 42, "eventType": "untrusted"}
    assert completed["data"]["eventType"] == "stage.succeeded"
    assert all(
        event["data"]["eventType"] in RUN_EVENT_TYPES
        for event in [created, started, completed]
    )


def test_run_event_lifecycle_helpers_map_terminal_states() -> None:
    emitter = RunEventEmitter(
        run_id="run-2",
        run_type="audience_simulation",
        event_id_factory=lambda: "event",
        clock=lambda: "now",
    )

    failed = emitter.stage_failed("synthesis", data={"error": "bad output"})
    partial = emitter.run_terminal(status="partially_completed")
    completed = emitter.run_terminal(status="completed")
    failed_run = emitter.run_terminal(status="failed")

    assert failed["status"] == "failed"
    assert failed["stageKey"] == "synthesis"
    assert [event["data"]["eventType"] for event in [partial, completed, failed_run]] == [
        "run.partial",
        "run.succeeded",
        "run.failed",
    ]
    assert terminal_event_type("unknown_future_terminal_status") == "run.failed"
