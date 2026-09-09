"""Tests for loopy.netutil — SSRF guard and outbound URL validation."""

from __future__ import annotations

import pytest

from loopy.netutil import is_private_host, validate_outbound_url


class TestIsPrivateHost:
    def test_loopback_ipv4(self):
        assert is_private_host("127.0.0.1") is True
        assert is_private_host("127.255.255.255") is True

    def test_loopback_ipv6(self):
        assert is_private_host("::1") is True

    def test_aws_metadata(self):
        assert is_private_host("169.254.169.254") is True

    def test_rfc1918_private(self):
        assert is_private_host("10.0.0.1") is True
        assert is_private_host("172.16.0.1") is True
        assert is_private_host("192.168.1.1") is True

    def test_global_public_ip(self):
        assert is_private_host("8.8.8.8") is False
        assert is_private_host("1.1.1.1") is False

    def test_unresolvable_hostname_fails_closed(self):
        """Unresolvable hostnames should fail closed (return True / blocked)."""
        assert is_private_host("this-host-name-does-not-exist-xyz.invalid") is True

    def test_public_hostname(self):
        assert is_private_host("example.com") is False
        assert is_private_host("github.com") is False

    def test_link_local(self):
        assert is_private_host("169.254.0.1") is True


class TestValidateOutboundUrl:
    def test_allowed_scheme_http(self):
        url = validate_outbound_url("http://example.com/path")
        assert url == "http://example.com/path"

    def test_allowed_scheme_https(self):
        url = validate_outbound_url("https://example.com/path?q=1")
        assert url == "https://example.com/path?q=1"

    def test_disallowed_scheme_raises(self):
        with pytest.raises(ValueError, match="not allowed"):
            validate_outbound_url("ftp://example.com/file")

    def test_disallowed_scheme_custom_tuple(self):
        with pytest.raises(ValueError, match="not allowed"):
            validate_outbound_url("ws://example.com/socket", allow_schemes=("http", "https"))

    def test_no_host_with_scheme_raises(self):
        with pytest.raises(ValueError, match="no host"):
            validate_outbound_url("http:///path")

    def test_no_host_no_scheme_raises(self):
        # "/path-only" has no scheme → scheme "" not in default allow list
        with pytest.raises(ValueError):
            validate_outbound_url("/path-only")

    def test_private_host_raises_by_default(self):
        with pytest.raises(ValueError, match="private"):
            validate_outbound_url("http://127.0.0.1:8080/internal")

    def test_private_host_allowed_when_flagged(self):
        url = validate_outbound_url("http://127.0.0.1:8080/internal", allow_private=True)
        assert url == "http://127.0.0.1:8080/internal"

    def test_public_host_allows(self):
        url = validate_outbound_url("https://api.github.com/repos")
        assert url == "https://api.github.com/repos"

    def test_empty_scheme_rejected(self):
        """A bare '//example.com' has empty scheme — rejected before host check."""
        with pytest.raises(ValueError, match="not allowed"):
            validate_outbound_url("//example.com/path")
