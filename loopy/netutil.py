"""Outbound URL validation — SSRF guard for agent-made network calls.

Loopy lets agents connect to MCP servers, other agents (A2A), and media
URLs. If any of those URLs can be influenced by model output or fetched
content, an attacker could point the agent at internal services (the cloud
metadata endpoint ``169.254.169.254``, loopback, or RFC-1918 internal
hosts). This module rejects such destinations by default.

This is a first layer, not a complete defense: DNS rebinding and
server-side redirects can still reach internal hosts after validation.
Pair it with outbound network allow-listing at the host / egress layer.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

__all__ = ["is_private_host", "validate_outbound_url"]

_DEFAULT_SCHEMES = ("http", "https")


def is_private_host(host: str) -> bool:
    """Return True if *host* resolves to a non-global address.

    Covers loopback (127.0.0.0/8, ::1), RFC 1918 private ranges, link-local
    (incl. the AWS metadata IP ``169.254.169.254``), and the unspecified /
    reserved ranges (``ip.is_global`` is False for all of these).

    Literal IPs are checked directly; hostnames are resolved and checked
    against **all** returned A/AAAA records (any non-global result ⇒ True).
    """
    try:
        ip = ipaddress.ip_address(host)
        return not ip.is_global
    except ValueError:
        pass  # not a literal IP — treat as a hostname

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Unresolvable: fail closed (block) rather than guess.
        return True

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if not ip.is_global:
            return True
    return False


def validate_outbound_url(
    url: str,
    *,
    allow_private: bool = False,
    allow_schemes: tuple[str, ...] = _DEFAULT_SCHEMES,
) -> str:
    """Validate an outbound URL against the SSRF default-deny posture.

    Args:
        url: The URL to validate.
        allow_private: Set True to permit private/loopback/link-local hosts
            (only when the URL is operator-controlled and internal access
            is intentional).
        allow_schemes: Allowed URL schemes (default ``http``/``https``).

    Returns:
        The unchanged *url* when it is acceptable.

    Raises:
        ValueError: If the scheme is not allowed, the URL has no host, or the
            host resolves to a non-global address (and ``allow_private`` is
            False).
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in allow_schemes:
        raise ValueError(
            f"URL scheme '{parsed.scheme or ''}' not allowed (see https://loopy.dev/docs/security#ssrf-guard)"
        )

    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host (see https://loopy.dev/docs/security#ssrf-guard)")

    if not allow_private and is_private_host(host):
        raise ValueError(
            f"URL host '{host}' resolves to a private/loopback address "
            "(SSRF guard) (see https://loopy.dev/docs/security#ssrf-guard)"
        )

    return url
