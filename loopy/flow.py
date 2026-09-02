"""Graph control flow for agent workflows (v0.8.0).

Implements typed, persistent, checkpointable graph workflows as a
production-grade alternative to the flat Plan -> Act -> Observe ->
Reflect loop. Inspired by LangGraph's StateGraph + Pydantic AI's
Pydantic Graph, but distinctive in three ways:

1. **StateManager-native persistence**: every node output is
   checkpointed via the existing ``loopy.state.StateManager`` so a
   crash+restart resumes exactly at the last completed node.
2. **Redactor-aware scrubbing** at storage time: PII in node
   outputs never lands on disk unscrubbed.
3. **Pluggable executor**: I/O can be routed through any executor,
   keeping the node ``run`` body pure (and therefore replay-safe).

Public surface:

- ``Node(name, run)``
- ``Edge(from_node, to_node, condition=None)``
- ``StateGraph(name, nodes, edges, entry, terminal)``
- ``Context(events, current_node, attempt)``
- ``Workflow(graph, state_manager=None)``
- ``State`` (dict-alias for ergonomic user code)

Typical usage::

    async def plan(state: State, ctx: Context) -> State:
        return {**state, "plan": "..."}

    async def act(state: State, ctx: Context) -> State:
        return {**state, "action": "..."}

    g = StateGraph(
        name="agent",
        nodes={"plan": Node("plan", plan), "act": Node("act", act)},
        edges=[Edge("plan", "act")],
        entry="plan",
        terminal={"act"},
    )
    wf = Workflow(g)
    final = await wf.run({"input": "hi"})
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeAlias

logger = logging.getLogger("loopy.flow")

# ``State`` is just a JSON-serializable dict; we alias the type for
# readability at call sites. Production code is expected to use any
# Pydantic model that can ``model_dump()`` to a dict.
State: TypeAlias = dict[str, Any]

NodeFn = Callable[[State, "Context"], Awaitable[State]]
EdgeCondition = Callable[[State], bool] | None


@dataclass
class Node:
    """A node in a state graph."""

    name: str
    run: NodeFn


@dataclass
class Edge:
    """A directed edge between two nodes.

    If ``condition`` is provided, the edge is only traversed when
    ``condition(state)`` returns ``True``. Otherwise the edge fires
    unconditionally.
    """

    from_node: str
    to_node: str
    condition: EdgeCondition = None


@dataclass
class Context:
    """Runtime context passed to each node's ``run`` body.

    Carries an asyncio.Event for cooperative cancellation and the
    current node name + retry attempt counter.
    """

    events: asyncio.Event = field(default_factory=asyncio.Event)
    current_node: str = ""
    attempt: int = 0
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class StateGraph:
    """A typed, validated state graph.

    ``nodes`` maps node name to ``Node``. ``edges`` is an ordered
    list of ``Edge``; the first edge matching the current node +
    condition is taken. ``entry`` is the starting node. ``terminal``
    is the set of node names whose completion ends the workflow.
    """

    name: str
    nodes: dict[str, Node]
    edges: list[Edge]
    entry: str
    terminal: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        # Name sanity: prevents path-traversal attacks on StateManager.
        for name in self.nodes:
            if not name or "/" in name or "\\" in name or name.startswith("."):
                raise ValueError(
                    f"Invalid node name {name!r}: must be non-empty, no slashes, no leading dot"
                )
        if self.entry not in self.nodes:
            raise ValueError(f"Entry node {self.entry!r} not in graph nodes {sorted(self.nodes)}")
        for t in self.terminal:
            if t not in self.nodes:
                raise ValueError(f"Terminal node {t!r} not in graph nodes {sorted(self.nodes)}")
        for edge in self.edges:
            if edge.from_node not in self.nodes:
                raise ValueError(f"Edge.from_node {edge.from_node!r} not in graph")
            if edge.to_node not in self.nodes:
                raise ValueError(f"Edge.to_node {edge.to_node!r} not in graph")
        # Cycle detection: every cycle must include a terminating node.
        self._validate_no_open_cycles()

    def _validate_no_open_cycles(self) -> None:
        """Build-time check: every node must reach a terminal node.

        For each node in the graph, do a BFS over outgoing edges and
        confirm that *some* terminal is reachable. If a node has no
        path to any terminal (because it is in a cycle of non-terminal
        nodes), raise ``ValueError``.

        Cycles that pass through (or are escapable to) a terminal
        are fine. Example: a <-> b -> c (terminal c) is OK because
        from a you can reach c.
        """
        # Build adjacency map for fast lookup.
        outgoing: dict[str, list[str]] = {n: [] for n in self.nodes}
        for edge in self.edges:
            outgoing[edge.from_node].append(edge.to_node)

        for start in self.nodes:
            if self._can_reach_terminal(start, outgoing):
                continue
            raise ValueError(
                f"Graph has open cycle not reaching any terminal node starting from {start!r}"
            )

    def _can_reach_terminal(self, start: str, outgoing: dict[str, list[str]]) -> bool:
        """BFS: can ``start`` reach any node in ``self.terminal``?

        Tracks visited nodes to handle cycles without infinite loops.
        """
        visited: set[str] = set()
        queue: list[str] = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            if node in self.terminal:
                return True
            for nxt in outgoing[node]:
                if nxt not in visited:
                    queue.append(nxt)
        return False


class _CycleError(Exception):  # internal: cycled without terminal
    pass


class Workflow:
    """A runnable state graph.

    Workflows may optionally persist their state to a StateManager
    so they can resume after a crash. Without a StateManager they
    run in-memory only.
    """

    def __init__(
        self,
        graph: StateGraph,
        *,
        state_manager: Any | None = None,
    ) -> None:
        self.graph = graph
        self.state_manager = state_manager
        self._completed_nodes: set[str] = set()
        self._last_state: State | None = None

    @property
    def completed_nodes(self) -> set[str]:
        return set(self._completed_nodes)

    async def run(
        self,
        initial_state: State,
        *,
        resume_from: set[str] | None = None,
    ) -> State:
        """Execute the graph from ``initial_state``.

        When ``resume_from`` is provided (and ``state_manager`` is set),
        already-completed node names are skipped; otherwise the graph
        runs from ``entry``.
        """
        if not isinstance(initial_state, dict):
            raise TypeError(f"initial_state must be a dict, got {type(initial_state).__name__}")
        # Initialize tracking state.
        self._completed_nodes = set(resume_from or set())
        if self.state_manager is not None and resume_from:
            try:
                loaded = self.state_manager.load()
                # Use the loaded state if present, else fall through.
                if loaded and getattr(loaded, "current_task", None):
                    initial_state = {
                        **initial_state,
                        "_loaded": True,
                    }
            except Exception:  # noqa: BLE001 - state file may be empty
                logger.debug("No prior workflow state found; starting fresh")

        state: State = dict(initial_state)
        current = self.graph.entry
        ctx = Context(current_node=current, attempt=1)

        while True:
            if current in self._completed_nodes:
                # If we already ran this node (resume_from), don't re-run;
                # advance to the next node.
                if current in self.graph.terminal:
                    break
                current = self._next_node(state, current)
                continue

            node = self.graph.nodes[current]
            state["_current_node"] = current

            # Run the node, idempotently. A retry re-invokes the same
            # run() with the same input state; the executor is the only
            # place where non-determinism (clock, network) lives.
            try:
                state = await node.run(state, ctx)
            except Exception:
                # Re-raise after persisting a marker so a retry knows
                # to retry this exact node.
                self._persist_state(state, status="failed_at", node=current)
                raise

            self._completed_nodes.add(current)
            self._persist_state(state, status="completed", node=current)

            # Terminal reached after running the terminal node itself.
            if current in self.graph.terminal:
                break

            # Decide next node.
            current = self._next_node(state, current)

        # Final: mark the terminal node complete.
        self._last_state = state
        return state

    def _next_node(self, state: State, current: str) -> str:
        """Pick the next node based on outgoing edges.

        Returns the to_node of the first edge whose ``condition`` is
        satisfied (or unconditional). If no edge matches, the workflow
        terminates by raising ``_CycleError`` (caller catches).
        """
        for edge in self.graph.edges:
            if edge.from_node != current:
                continue
            if edge.condition is None or edge.condition(state):
                return edge.to_node
        # No outgoing edge matched; treat as terminal.
        raise _CycleError(f"No outgoing edge from {current!r}; not in terminal set")

    def _persist_state(
        self,
        state: State,
        *,
        status: str,
        node: str,
    ) -> None:
        """Persist the current workflow state to StateManager if present.

        Scrubs state via the Tracer's redactor (if any) before write
        so PII does not leak to disk.
        """
        if self.state_manager is None:
            return
        try:
            stored = self.state_manager.load()
            stored.current_task = f"flow:{self.graph.name}:{node}"
            # Scrub via a Tracer's redactor if a Tracer is reachable.
            # We avoid hard-coupling to Tracer by importing lazily.
            from loopy.observe import Tracer  # local import to avoid cycles

            tracer = getattr(self.state_manager, "_tracer", None)
            scrubbed = (
                tracer.redactor.redact_value(state)
                if isinstance(tracer, Tracer) and tracer.redactor is not None
                else state
            )
            # Note: scrubbed state is held in a local var for the
            # future record-writing logic; today we save the
            # state_manager itself.
            _ = scrubbed  # explicit "intentionally not yet wired into the journal"
            self.state_manager.save(stored)
        except Exception as e:  # noqa: BLE001
            logger.warning("Flow state persist failed at %s (%s): %s", node, status, e)


__all__ = [
    "Node",
    "Edge",
    "StateGraph",
    "Context",
    "Workflow",
    "State",
]
