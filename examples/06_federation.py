"""06 — FederatedServer HTTP endpoint.

Run with::

    python examples/06_federation.py

No API key required. Starts a local ``FederatedServer`` on a
random port, queries its Agent Card endpoint, then shuts it
down.
"""

import socket
import time
import urllib.request
from contextlib import closing

from loopy.a2a import AgentCard, AgentCapability
from loopy.federate import FederatedServer


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.settimeout(0.2)
                s.connect(("127.0.0.1", port))
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"port {port} never opened")


def main() -> None:
    port = _free_port()
    card = AgentCard(
        name="federation-example",
        description="minimal federated agent",
        version="1.0.0",
        capabilities=[AgentCapability.TEXT_GENERATION],
        endpoint="local",
    )
    server = FederatedServer(agent_card=card, host="127.0.0.1", port=port)
    server.start()
    try:
        _wait_for_port(server.port)
        url = f"http://127.0.0.1:{server.port}/.well-known/agent-card.json"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            data = resp.read().decode("utf-8")
        assert "federation-example" in data
        print(f"federation: GET agent-card returned {len(data)} bytes")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
