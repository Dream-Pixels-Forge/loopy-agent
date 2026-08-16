"""CLI coverage tests — chat, agent commands, edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from loopy.cli import cmd_agent, cmd_chat


class TestCmdChat:
    def test_chat_openai(self, capsys):
        args = MagicMock()
        args.message = "What is 2+2?"
        args.provider = "openai"
        args.model = "gpt-4"
        args.system = None
        args.temperature = 0.7
        args.max_tokens = 100

        mock_response = MagicMock()
        mock_response.provider = MagicMock(value="openai")
        mock_response.model = "gpt-4"
        mock_response.tokens_used = 15
        mock_response.latency_ms = 123.4
        mock_response.content = "4"

        with patch("loopy.gateway.Gateway") as MockGW:
            instance = MagicMock()
            instance.chat = AsyncMock(return_value=mock_response)
            instance.close = AsyncMock()
            MockGW.return_value = instance

            cmd_chat(args)

        captured = capsys.readouterr()
        assert "4" in captured.out

    def test_chat_anthropic(self, capsys):
        args = MagicMock()
        args.message = "Hi"
        args.provider = "anthropic"
        args.model = "claude-3"
        args.system = None
        args.temperature = 0.7
        args.max_tokens = 100

        mock_response = MagicMock()
        mock_response.provider = MagicMock(value="anthropic")
        mock_response.model = "claude-3"
        mock_response.tokens_used = 10
        mock_response.latency_ms = 50.0
        mock_response.content = "Hello!"

        with patch("loopy.gateway.Gateway") as MockGW:
            instance = MagicMock()
            instance.chat = AsyncMock(return_value=mock_response)
            instance.close = AsyncMock()
            MockGW.return_value = instance

            cmd_chat(args)

        captured = capsys.readouterr()
        assert "Hello!" in captured.out

    def test_chat_ollama(self, capsys):
        args = MagicMock()
        args.message = "Hi"
        args.provider = "ollama"
        args.model = "llama3"
        args.system = None
        args.temperature = 0.7
        args.max_tokens = 100

        mock_response = MagicMock()
        mock_response.provider = MagicMock(value="ollama")
        mock_response.model = "llama3"
        mock_response.tokens_used = 8
        mock_response.latency_ms = 30.0
        mock_response.content = "Local!"

        with patch("loopy.gateway.Gateway") as MockGW:
            instance = MagicMock()
            instance.chat = AsyncMock(return_value=mock_response)
            instance.close = AsyncMock()
            MockGW.return_value = instance

            cmd_chat(args)

        captured = capsys.readouterr()
        assert "Local!" in captured.out

    def test_chat_error_handling(self, capsys):
        args = MagicMock()
        args.message = "Hi"
        args.provider = "openai"
        args.model = "gpt-4"
        args.system = None
        args.temperature = 0.7
        args.max_tokens = 100

        with patch("loopy.gateway.Gateway") as MockGW:
            instance = MagicMock()
            instance.chat = AsyncMock(side_effect=ConnectionError("refused"))
            instance.close = AsyncMock()
            MockGW.return_value = instance

            cmd_chat(args)

        captured = capsys.readouterr()
        assert "Error" in captured.out


class TestCmdAgent:
    def test_agent_list_empty(self, capsys):
        args = MagicMock()
        args.agent_action = "list"
        cmd_agent(args)
        captured = capsys.readouterr()
        assert "Registered Agents" in captured.out

    def test_agent_list_with_agents(self, capsys):
        args = MagicMock()
        args.agent_action = "list"

        with patch("loopy.agents.Orchestrator") as MockOrch:
            instance = MagicMock()
            agent1 = MagicMock()
            agent1.name = "researcher"
            agent1.description = "Searches"
            instance.list_agents.return_value = [agent1]
            MockOrch.return_value = instance

            cmd_agent(args)

        captured = capsys.readouterr()
        assert "researcher" in captured.out
