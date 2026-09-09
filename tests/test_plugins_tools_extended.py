"""Extended tests for loopy.plugins.tools — registry gates, deny log, ToolsPlugin handlers."""

from __future__ import annotations

import asyncio
import json

import pytest

from loopy.plugins.tools import Tool, ToolParameter, ToolRegistry, ToolsPlugin
from loopy.plugins.tools import _eval_math as eval_math  # noqa: PLC2701 (private helper)

# ── Tool Registry: capability gates ─────────────────────────


class TestToolRegistryGates:
    @pytest.mark.asyncio
    async def test_not_found_returns_error(self):
        reg = ToolRegistry()
        result = await reg.execute("missing", {})
        assert result.success is False
        assert "not found" in result.error.lower()
        denials = reg.denials()
        assert len(denials) == 1
        assert denials[0]["reason"] == "not_found"

    @pytest.mark.asyncio
    async def test_disabled_tool_blocked(self):
        reg = ToolRegistry()
        reg.register(Tool(name="x", description="d", handler=lambda c: "ok", enabled=False))
        result = await reg.execute("x", {})
        assert result.success is False
        assert "disabled" in result.error.lower()
        assert reg.denials()[0]["reason"] == "disabled"

    @pytest.mark.asyncio
    async def test_allowed_values_enforced(self):
        reg = ToolRegistry()

        async def handler(**kwargs):
            return kwargs.get("v", "")

        reg.register(
            Tool(
                name="env",
                description="set env",
                handler=handler,
                parameters=[ToolParameter(name="v", type="string")],
                allowed_values={"v": {"prod", "staging"}},
            )
        )
        ok = await reg.execute("env", {"v": "prod"})
        assert ok.success is True
        bad = await reg.execute("env", {"v": "evil"})
        assert bad.success is False
        assert "allowed values" in bad.error.lower()

    @pytest.mark.asyncio
    async def test_requires_approval_no_approver_denied(self):
        reg = ToolRegistry()
        reg.register(
            Tool(
                name="delete",
                description="delete thing",
                handler=lambda c: "done",
                requires_approval=True,
            )
        )
        result = await reg.execute("delete", {})
        assert result.success is False
        assert "approval" in result.error.lower()

    @pytest.mark.asyncio
    async def test_requires_approval_granted(self):
        approved = False

        async def approver(tool, args):
            nonlocal approved
            approved = True
            return True

        async def handler(**kwargs):
            return "wrote"

        reg = ToolRegistry(approver=approver)
        reg.register(
            Tool(
                name="write",
                description="write file",
                handler=handler,
                requires_approval=True,
            )
        )
        result = await reg.execute("write", {})
        assert result.success is True
        assert approved is True

    @pytest.mark.asyncio
    async def test_requires_approval_denied_by_approver(self):
        async def approver(tool, args):
            return False

        reg = ToolRegistry(approver=approver)
        reg.register(
            Tool(
                name="rm",
                description="remove",
                handler=lambda **kwargs: "removed",
                requires_approval=True,
            )
        )
        result = await reg.execute("rm", {})
        assert result.success is False
        assert "not approved" in result.error.lower()
        denials = reg.denials()
        assert denials[-1]["reason"] == "approval_denied"

    def test_list_schemas(self):
        reg = ToolRegistry()
        reg.register(Tool(name="greet", description="say hi", handler=lambda **k: "hi"))
        schemas = reg.list_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "greet"

    def test_get_summary(self):
        reg = ToolRegistry()
        reg.register(Tool(name="a", description="a", handler=lambda **k: 1))
        reg.register(Tool(name="b", description="b", handler=lambda **k: 2, parameters=[]))
        summary = reg.get_summary()
        assert summary["total_tools"] == 2
        names = {t["name"] for t in summary["tools"]}
        assert names == {"a", "b"}

    @pytest.mark.asyncio
    async def test_handler_exception_returns_failure(self):
        reg = ToolRegistry()
        reg.register(Tool(name="crash", description="c", handler=lambda **k: 1 / 0))
        result = await reg.execute("crash", {})
        assert result.success is False
        assert "division by zero" in result.error.lower()

    @pytest.mark.asyncio
    async def test_denial_log_bounded(self):
        """Denial log is bounded; old entries are dropped."""
        reg = ToolRegistry()
        for i in range(1100):
            await reg.execute(f"tool{i}", {})
        denials = reg.denials()
        assert len(denials) <= 1000  # DENIAL_LOG_MAX


# ── ToolsPlugin handlers ────────────────────────────────────


class TestToolsPlugin:
    def test_info_property(self):
        plugin = ToolsPlugin()
        info = plugin.info
        assert info.name == "loopy-tools"
        assert info.version == "0.3.0"

    def test_setup_registers_builtins(self):
        plugin = ToolsPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        asyncio.run(plugin.setup(reg))
        names = reg.list_tools()  # returns list[str]
        assert "list_tools" in names
        assert "get_tool_schema" in names

    @pytest.mark.asyncio
    async def test_calculator_ok(self):
        plugin = ToolsPlugin()
        result = await plugin._calculator(expression="2 + 3 * 4")
        assert result == {"result": 14.0, "expression": "2 + 3 * 4"}

    @pytest.mark.asyncio
    async def test_calculator_unsupported_syntax_raises(self):
        plugin = ToolsPlugin()
        with pytest.raises(ValueError, match="Unsupported"):
            await plugin._calculator(expression="__import__('os')")

    @pytest.mark.asyncio
    async def test_calculator_division_by_zero_propagates(self):
        plugin = ToolsPlugin()
        with pytest.raises(ZeroDivisionError):
            await plugin._calculator(expression="1 / 0")

    @pytest.mark.asyncio
    async def test_parse_json_valid(self):
        plugin = ToolsPlugin()
        result = await plugin._parse_json(text='{"a": 1}')
        assert result == {"a": 1}

    @pytest.mark.asyncio
    async def test_parse_json_invalid_raises(self):
        plugin = ToolsPlugin()
        with pytest.raises(json.JSONDecodeError):
            await plugin._parse_json(text="not json")

    @pytest.mark.asyncio
    async def test_list_tools_returns_builtin_names(self):
        plugin = ToolsPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        await plugin.setup(reg)
        names = reg.list_tools()
        assert "list_tools" in names
        assert "get_tool_schema" in names

    @pytest.mark.asyncio
    async def test_get_tool_schema_returns_schema(self):
        plugin = ToolsPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        await plugin.setup(reg)
        schema_handler = reg._tools["get_tool_schema"]
        result = await schema_handler(name="calculator")
        assert result is not None
        assert result["function"]["name"] == "calculator"

    @pytest.mark.asyncio
    async def test_get_tool_schema_missing_returns_none(self):
        plugin = ToolsPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        await plugin.setup(reg)
        schema_handler = reg._tools["get_tool_schema"]
        result = await schema_handler(name="nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_tool_registry_has_calculator(self):
        """Built-in tools live on tool_registry after setup."""
        plugin = ToolsPlugin()
        from loopy.plugins import PluginRegistry

        reg = PluginRegistry()
        await plugin.setup(reg)
        # After setup, plugin.tool_registry exists with built-in tools
        assert "calculator" in plugin.tool_registry.tools
        assert "parse_json" in plugin.tool_registry.tools


# ── _eval_math direct ───────────────────────────────────────


class TestEvalMath:
    def test_simple_addition(self):
        assert eval_math("2 + 3") == 5.0

    def test_multiplication_before_addition(self):
        assert eval_math("2 + 3 * 4") == 14.0

    def test_unary_minus(self):
        assert eval_math("-5") == -5.0

    def test_nested_parens(self):
        assert eval_math("(2 + 3) * 4") == 20.0

    def test_float_arithmetic(self):
        assert eval_math("1.5 * 2") == 3.0

    def test_modulo(self):
        assert eval_math("10 % 3") == 1.0

    def test_floor_division(self):
        assert eval_math("10 // 3") == 3.0

    def test_power(self):
        assert eval_math("2 ** 3") == 8.0

    def test_name_access_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            eval_math("x + 1")

    def test_function_call_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            eval_math("len([1,2])")

    def test_attribute_access_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            eval_math("(1).__class__")
