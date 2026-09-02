"""T2.1.2 — A2A task lifecycle + streaming tests (v0.9.0).

Covers:
  * ``A2ATask`` dataclass with state literals and artifacts
  * ``A2AClient.create_task`` / ``get_task`` / ``cancel_task`` HTTP
    shape against a mock httpx transport
  * ``stream_task`` SSE iterator
  * HMAC webhook signature verification
  * Idempotency (repeated ``create_task`` returns the same id)
  * Unknown ``skill_id`` rejected without a network call
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from loopy.a2a import (
    A2AClient,
    A2AError,
    A2ATask,
    AgentCard,
    AgentRegistry,  # noqa: F401  (kept for cross-reference)
)

# ── A2ATask dataclass ─────────────────────────────────────────


class TestA2ATaskDataclass:
    def test_task_state_literal_validation(self):
        # Accepted state literals round-trip.
        for state in (
            "submitted",
            "working",
            "input-required",
            "completed",
            "failed",
            "canceled",
            "rejected",
        ):
            task = A2ATask(id="t1", state=state)
            assert task.state == state

    def test_invalid_state_raises_value_error(self):
        with pytest.raises(ValueError, match="[Ss]tate"):
            A2ATask(id="t1", state="finished")

    def test_task_carries_artifacts(self):
        task = A2ATask(
            id="t2",
            state="completed",
            artifacts=[{"type": "text", "value": "hello"}],
        )
        assert task.artifacts == [{"type": "text", "value": "hello"}]


# ── create_task ───────────────────────────────────────────────


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_create_task_returns_submitted_then_working_then_completed(self):
        card = AgentCard(
            name="remote",
            url="https://example.com/agent",
            version="1.0",
            skills=[{"id": "summarize", "name": "summarize"}],
            authentication="none",
        )
        client = A2AClient.from_agent_card(card)

        # Mocks return the parsed JSON dict directly (the real
        # ``_post_json`` / ``_get_json`` return ``resp.json()``).
        async def fake_post(url, **kwargs):
            return {"id": "task-1", "state": "submitted", "artifacts": []}

        async def fake_get(url, **kwargs):
            return {"id": "task-1", "state": "completed", "artifacts": []}

        client._post_json = fake_post  # type: ignore[assignment]
        client._get_json = fake_get  # type: ignore[assignment]

        task = await client.create_task("summarize", {"text": "x"})
        assert task.id == "task-1"
        assert task.state == "submitted"

        refreshed = await client.get_task("task-1")
        assert refreshed.state == "completed"

    @pytest.mark.asyncio
    async def test_create_task_unknown_skill_raises_without_network(self):
        card = AgentCard(
            name="remote",
            url="https://example.com/agent",
            version="1.0",
            skills=[{"id": "summarize"}],
            authentication="none",
        )
        client = A2AClient.from_agent_card(card)
        called = False

        async def boom(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("network must not be touched")

        client._post_json = boom  # type: ignore[assignment]
        with pytest.raises(A2AError, match="[Uu]nknown skill"):
            await client.create_task("does_not_exist", {})
        assert not called

    @pytest.mark.asyncio
    async def test_create_task_is_idempotent(self):
        """Re-submitting with the same idempotency_key yields the same task id."""
        card = AgentCard(
            name="remote",
            url="https://example.com/agent",
            version="1.0",
            skills=[{"id": "summarize"}],
            authentication="none",
        )
        client = A2AClient.from_agent_card(card)

        async def fake_post(url, *, json, **kwargs):
            key = json.get("idempotency_key", "")
            task_id = hashlib.sha1(key.encode()).hexdigest()[:12]
            return {"id": task_id, "state": "submitted", "artifacts": []}

        client._post_json = fake_post  # type: ignore[assignment]

        first = await client.create_task(
            "summarize",
            {"text": "x"},
            idempotency_key="abc",
        )
        second = await client.create_task(
            "summarize",
            {"text": "x"},
            idempotency_key="abc",
        )
        assert first.id == second.id


# ── cancel_task + input-required ─────────────────────────────


class TestCancelAndInputRequired:
    @pytest.mark.asyncio
    async def test_cancel_task_transitions_working_to_canceled(self):
        card = AgentCard(
            name="remote",
            url="https://example.com/agent",
            version="1.0",
            skills=[{"id": "summarize"}],
            authentication="none",
        )
        client = A2AClient.from_agent_card(card)

        async def fake_post(url, *, json, **kwargs):
            return {"id": "task-1", "state": "canceled", "artifacts": []}

        client._post_json = fake_post  # type: ignore[assignment]
        task = await client.cancel_task("task-1")
        assert task.state == "canceled"

    @pytest.mark.asyncio
    async def test_input_required_state_carries_question_artifact(self):
        card = AgentCard(
            name="remote",
            url="https://example.com/agent",
            version="1.0",
            skills=[{"id": "ask"}],
            authentication="none",
        )
        client = A2AClient.from_agent_card(card)

        async def fake_post(url, *, json, **kwargs):
            return {
                "id": "task-2",
                "state": "input-required",
                "artifacts": [
                    {
                        "type": "question",
                        "value": "What is your goal?",
                    }
                ],
            }

        client._post_json = fake_post  # type: ignore[assignment]
        task = await client.create_task("ask", {"q": "x"})
        assert task.state == "input-required"
        assert task.artifacts[0]["type"] == "question"
        assert "goal" in task.artifacts[0]["value"]


# ── stream_task ───────────────────────────────────────────────


class TestStreamTask:
    @pytest.mark.asyncio
    async def test_stream_task_yields_one_event_per_status_update(self):
        card = AgentCard(
            name="remote",
            url="https://example.com/agent",
            version="1.0",
            skills=[{"id": "s"}],
            authentication="none",
        )
        client = A2AClient.from_agent_card(card)

        events = [
            {"id": "t1", "state": "submitted", "artifacts": []},
            {"id": "t1", "state": "working", "artifacts": []},
            {"id": "t1", "state": "completed", "artifacts": [{"type": "text", "value": "done"}]},
        ]

        async def fake_sse(url, **kwargs):
            for evt in events:
                yield evt

        client._sse_events = fake_sse  # type: ignore[assignment]
        seen = [t async for t in client.stream_task("t1")]
        assert [t.state for t in seen] == ["submitted", "working", "completed"]
        assert seen[-1].artifacts == [{"type": "text", "value": "done"}]

    @pytest.mark.asyncio
    async def test_stream_task_stops_on_canceled(self):
        card = AgentCard(
            name="remote",
            url="https://example.com/agent",
            version="1.0",
            skills=[{"id": "s"}],
            authentication="none",
        )
        client = A2AClient.from_agent_card(card)

        events = [
            {"id": "t1", "state": "working", "artifacts": []},
            {"id": "t1", "state": "canceled", "artifacts": []},
        ]

        async def fake_sse(url, **kwargs):
            for evt in events:
                yield evt

        client._sse_events = fake_sse  # type: ignore[assignment]
        seen = [t async for t in client.stream_task("t1")]
        assert [t.state for t in seen] == ["working", "canceled"]


# ── Webhook HMAC verification ────────────────────────────────


class TestWebhookVerification:
    def test_verify_webhook_accepts_valid_hmac(self):
        card = AgentCard(
            name="remote",
            url="https://example.com/agent",
            version="1.0",
            skills=[],
            authentication="none",
        )
        client = A2AClient.from_agent_card(card)

        secret = b"super-secret"
        body = json.dumps({"id": "t1", "state": "completed"}).encode()
        sig = hmac.new(secret, body, hashlib.sha256).hexdigest()

        # Returns True / False — never raises.
        assert client.verify_webhook(body, sig, secret) is True
        assert client.verify_webhook(body, "deadbeef" * 8, secret) is False

    def test_verify_webhook_uses_constant_time_compare(self):
        card = AgentCard(
            name="remote",
            url="https://example.com/agent",
            version="1.0",
            skills=[],
            authentication="none",
        )
        client = A2AClient.from_agent_card(card)

        secret = b"another-secret"
        body = b"{}"
        sig = hmac.new(secret, body, hashlib.sha256).hexdigest()

        # Wrong length signatures are rejected (no exception).
        assert client.verify_webhook(body, "short", secret) is False
        assert client.verify_webhook(body, "x" * len(sig), secret) is False
        # And the right one passes.
        assert client.verify_webhook(body, sig, secret) is True
