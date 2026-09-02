"""T2.1.1 — A2A Agent Card discovery tests (v0.9.0).

Covers the new public surface:
  * ``async A2AClient.fetch_agent_card(url) -> AgentCard``
  * ``A2AClient.from_agent_card(card) -> A2AClient``
  * Cached ``AgentCard`` reused when TTL has not elapsed
  * SSRF guard: ``file://`` and other non-http schemes are rejected
    by ``netutil.validate_outbound_url``

The tests pin the **contract**; they are written before the
implementation exists (strict TDD). Run the test file and confirm
the test suite fails before writing the production code in
``loopy/a2a.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from loopy.a2a import (
    A2AClient,
    AgentCard,
    AgentRegistry,
)

# ── fetch_agent_card ──────────────────────────────────────────


class TestFetchAgentCard:
    @pytest.mark.asyncio
    async def test_fetches_and_parses_well_known_agent_card(self):
        payload = {
            "name": "remote-agent",
            "description": "Remote agent for testing",
            "version": "1.0.0",
            "url": "https://example.com/agent",
            "skills": [
                {
                    "id": "summarize",
                    "name": "summarize",
                    "description": "summarize text",
                }
            ],
            "authentication": {"schemes": ["none"]},
            "provider": {"name": "Test Co", "version": "1.0"},
        }

        client = A2AClient(AgentRegistry())
        with patch.object(client, "_fetch_json", AsyncMock(return_value=payload)):
            card = await client.fetch_agent_card("https://example.com/.well-known/agent-card.json")

        assert card.name == "remote-agent"
        assert card.version == "1.0.0"
        assert card.url == "https://example.com/agent"
        assert card.provider == "Test Co"
        assert card.authentication == "none"
        # Skills pass through as raw dicts (per the A2A v1.0 spec).
        assert card.skills == [
            {
                "id": "summarize",
                "name": "summarize",
                "description": "summarize text",
            }
        ]

    @pytest.mark.asyncio
    async def test_malformed_json_raises_a2a_error(self):
        from loopy.a2a import A2AError

        client = A2AClient(AgentRegistry())
        with (
            patch.object(client, "_fetch_json", AsyncMock(side_effect=ValueError("bad json"))),
            pytest.raises(A2AError, match="[Aa]gent [Cc]ard"),
        ):
            await client.fetch_agent_card("https://example.com/.well-known/agent-card.json")

    @pytest.mark.asyncio
    async def test_file_url_rejected_by_ssrf_guard(self):
        client = A2AClient(AgentRegistry())
        with pytest.raises(ValueError, match="scheme"):
            await client.fetch_agent_card("file:///etc/passwd")

    @pytest.mark.asyncio
    async def test_missing_required_field_raises_a2a_error(self):
        from loopy.a2a import A2AError

        # "name" is missing
        payload = {
            "description": "no name",
            "version": "1.0",
            "url": "https://example.com",
            "skills": [],
            "authentication": {"schemes": ["none"]},
        }
        client = A2AClient(AgentRegistry())
        with (
            patch.object(client, "_fetch_json", AsyncMock(return_value=payload)),
            pytest.raises(A2AError, match="name"),
        ):
            await client.fetch_agent_card("https://example.com/.well-known/agent-card.json")


# ── from_agent_card ───────────────────────────────────────────


class TestFromAgentCard:
    def test_from_card_returns_new_client(self):
        card = AgentCard(
            name="x",
            url="https://example.com/agent",
            version="1.0",
            skills=[],
            authentication="api_key",
        )
        client = A2AClient.from_agent_card(card)
        assert isinstance(client, A2AClient)
        # The card must be discoverable from the client.
        assert client.agent_card.name == "x"

    def test_from_card_rejects_unknown_authentication(self):
        card = AgentCard(
            name="x",
            url="https://example.com/agent",
            version="1.0",
            skills=[],
            authentication="magic-link",  # not in the allowed set
        )
        with pytest.raises(ValueError, match="[Aa]uthentication"):
            A2AClient.from_agent_card(card)

    def test_from_card_accepts_all_allowed_authentication_methods(self):
        for auth in {"none", "api_key", "oauth2", "openIdConnect"}:
            card = AgentCard(
                name="x",
                url="https://example.com/agent",
                version="1.0",
                skills=[],
                authentication=auth,
            )
            client = A2AClient.from_agent_card(card)
            assert client.agent_card.authentication == auth


# ── Caching ───────────────────────────────────────────────────


class TestAgentCardCaching:
    @pytest.mark.asyncio
    async def test_cached_card_reused_within_ttl(self):
        client = A2AClient(AgentRegistry(), card_ttl=3600)
        payload = {
            "name": "cached",
            "version": "1.0",
            "url": "https://example.com",
            "skills": [],
            "authentication": {"schemes": ["none"]},
        }
        fetch_mock = AsyncMock(return_value=payload)
        with patch.object(client, "_fetch_json", fetch_mock):
            card1 = await client.fetch_agent_card("https://example.com/.well-known/agent-card.json")
            card2 = await client.fetch_agent_card("https://example.com/.well-known/agent-card.json")

        # The card is the same object and the network was hit exactly once.
        assert card1 is card2
        assert fetch_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self):
        client = A2AClient(AgentRegistry(), card_ttl=1)  # 1-second TTL
        payload = {
            "name": "cached",
            "version": "1.0",
            "url": "https://example.com",
            "skills": [],
            "authentication": {"schemes": ["none"]},
        }
        fetch_mock = AsyncMock(return_value=payload)
        with patch.object(client, "_fetch_json", fetch_mock):
            await client.fetch_agent_card("https://example.com/.well-known/agent-card.json")

            # Simulate elapsed TTL by rewinding the cached timestamp.
            assert client._card_cache["https://example.com/.well-known/agent-card.json"] is not None
            url_key = "https://example.com/.well-known/agent-card.json"
            _card, fetched_at = client._card_cache[url_key]
            client._card_cache[url_key] = (_card, fetched_at - 2)  # 2 seconds ago

            await client.fetch_agent_card("https://example.com/.well-known/agent-card.json")

        assert fetch_mock.await_count == 2
