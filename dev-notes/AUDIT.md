# AUDIT — `loopy-agent` Production Readiness Matrix (2026-09-02)

> **Source:** `docs/research/competitive-analysis-2026.md` + `dev-notes/DISCOVERY.md`.
> **Mode:** Existing Application Realignment. Each finding references the file/line and proposes a remediation in the Tier 1 (v0.8.0) / Tier 2 (v0.9.0) / Tier 3 (v1.0.0) buckets.
> **Severity scale:** `CRITICAL` (blocks production) / `HIGH` (gating for category leadership) / `MEDIUM` (polish) / `LOW` (cosmetic).

---

## 1. Security & Authentication

| # | Finding | Severity | Remediation |
|---|---|---|---|
| AUD-S01 | No graph control flow → infinite-loop DoS via `AgentLoop(max_steps=N)` without cycle detection | HIGH | Tier 1 F1 — graph control flow + max-iterations safety |
| AUD-S02 | `LLMCache` reads from disk but no SSRF on cache-key derivation | LOW | Audit `cache.py::_make_key` (already uses sha256, no SSRF risk) |
| AUD-S03 | `MarketplacePlugin` validates PEP-508 names but not package signatures | MEDIUM | Tier 2 D3 — signed plugin marketplace with TOFU |
| AUD-S04 | `prompting.py` has `CANARY_PREFIX` injection defense — **already implemented (v0.7.1)** | ✓ | — |
| AUD-S05 | `netutil.py::is_private_host` + `validate_outbound_url` — **already implemented** | ✓ | — |

## 2. Authorization & Multi-Tenancy

| # | Finding | Severity | Remediation |
|---|---|---|---|
| AUD-A01 | Single-tenant design (no `tenant_id` in spans) | LOW | Optional — most users are single-tenant; document as "BYO tenancy" |
| AUD-A02 | No RBAC matrix for `MCPClient.call_tool` — caller decides | LOW | Document existing capability gates in `mcp.py` |
| AUD-A03 | `A2AClient.broadcast` rate-limited (v0.7.0) but no per-agent ACL | MEDIUM | Tier 2 — `A2AAuth` with bearer/HMAC |

## 3. Database & Durability

| # | Finding | Severity | Remediation |
|---|---|---|---|
| AUD-D01 | `StateManager` uses JSON file — single-process only | HIGH | Tier 3 C1 — durable SQLite-backed runtime |
| AUD-D02 | `DecisionTracker` FIFO-bounded at 100 records (since v0.7.6) | ✓ | — |
| AUD-D03 | `MemoryStore` async I/O (since v0.7.7) + dirty flag (since v0.7.6) | ✓ | — |
| AUD-D04 | No migrations system for `LoopState` shape changes | MEDIUM | Add `LoopState.schema_version: int = 1` + migration in `state.py::load()` |
| AUD-D05 | `RunRecord` JSON shape not formally versioned | LOW | Add `LoopState.schema_version` propagated to records |

## 4. API Surface & Idempotency

| # | Finding | Severity | Remediation |
|---|---|---|---|
| AUD-API01 | `Gateway.chat()` has no `Idempotency-Key` header support | LOW | Optional — chat is async fire-and-forget; document caller responsibility |
| AUD-API02 | `MCPClient.call_tool()` is implicitly idempotent (caller chooses) | LOW | Document |
| AUD-API03 | `A2AClient.broadcast()` cycle-detection (since v0.7.0) | ✓ | — |
| AUD-API04 | `StructuredOutput` validation (since v0.7.9) sets `structured=None` on failure — **backward compatible** | ✓ | — |
| AUD-API05 | No RFC 7807 error format | MEDIUM | Tier 2 — add `ErrorResponse` dataclass + JSON encoder |

## 5. Resilience & Background Workers

| # | Finding | Severity | Remediation |
|---|---|---|---|
| AUD-R01 | `Gateway._call_*` has no retry on transient HTTP errors | MEDIUM | Tier 2 D5 — use `tenacity` (already in `[gateway]` extra) |
| AUD-R02 | `LoopConfig.resume_from` requires StateManager — no fallback | ✓ | Documented behavior |
| AUD-R03 | `LoopConfig.max_retries` exists but unused in `_run_step` | LOW | Either implement or document |
| AUD-R04 | No durable outbox pattern for multi-step workflows | HIGH | Tier 3 C1 |

## 6. Observability

| # | Finding | Severity | Remediation |
|---|---|---|---|
| AUD-O01 | `Tracer` exposes `start_span`/`add_event` but no `@observe()` decorator | HIGH | Tier 1 F6 — decorator + auto-instrumentation |
| AUD-O02 | `TraceExporter.export_http` has retry + backoff (since v0.7.6) | ✓ | — |
| AUD-O03 | `Redactor` PII scrubbing (since v0.7.9) | ✓ | — |
| AUD-O04 | No `/metrics` Prometheus endpoint | LOW | Tier 2 — add `MetricsCollector.export_prometheus()` |
| AUD-O05 | Structured logs are stdlib `logging` only; no JSON formatter | MEDIUM | Tier 2 — add `loopy.observe.JsonFormatter` |

## 7. Deployment & Containerization

| # | Finding | Severity | Remediation |
|---|---|---|---|
| AUD-DP01 | No Dockerfile (library, not service) | LOW | Optional — `loopy serve` (Tier 3 C4) will need one |
| AUD-DP02 | GitHub Trusted Publishing via OIDC (since v0.7.0) | ✓ | — |
| AUD-DP03 | SBOM not generated | LOW | Add Syft SPDX generation to `release.yml` |
| AUD-DP04 | Cosign image signing not generated | LOW | Add to `release.yml` after Tier 3 C4 ships |

## 8. Testing & Quality Gates

| # | Finding | Severity | Remediation |
|---|---|---|---|
| AUD-T01 | Coverage 92% (target 90%) | ✓ | — |
| AUD-T02 | Strict warnings (filterwarnings=error) | ✓ | — |
| AUD-T03 | No mutation testing (mutmut / cosmic-ray) | LOW | Optional — add to `dev` extras |
| AUD-T04 | No property-based testing (Hypothesis) | MEDIUM | Tier 3 C2 — `VerifiedAgent` |
| AUD-T05 | No contract tests (Pact) | LOW | Tier 2 — add when API server ships (Tier 3 C4) |
| AUD-T06 | Test count 581 (good) — but no test coverage for `llms-full.txt` content freshness | LOW | Add to `test_v0710_features.py` |

## 9. Documentation & Discoverability

| # | Finding | Severity | Remediation |
|---|---|---|---|
| AUD-DOC01 | mkdocs-material site (v0.7.10) | ✓ | — |
| AUD-DOC02 | `llms-full.txt` + 22 per-module (v0.7.10) | ✓ | — |
| AUD-DOC03 | `AGENTS.md` (v0.7.10) | ✓ | — |
| AUD-DOC04 | `skills/loopy-router.md` (v0.7.10) | ✓ | — |
| AUD-DOC05 | `docs/research/competitive-analysis-2026.md` (v0.7.10) | ✓ | — |
| AUD-DOC06 | No doc deployment (mkdocs-material needs `mkdocs build` + Pages workflow) | MEDIUM | Add `.github/workflows/docs.yml` |

---

## Summary

- **17 ✓** — Already production-grade (lint, coverage, PII redactor, MCP capability gates, async cache, FIFO bounds, OIDC publish, docs site, llms, etc.)
- **4 CRITICAL/HIGH** — Tier 1 work (graph control flow, HITL interrupts, OTel auto-instrumentation, durable execution)
- **8 MEDIUM** — Tier 2 work (A2A handoff, compliance policies, signed plugins, structured errors, JSON logs, Prometheus, docs deployment, property-based testing)
- **6 LOW** — Backlog (RFC 7807 idempotency, mutations, SBOM, Cosign, mutation testing, contract tests)

**Verdict:** Loopy-agent is **production-ready as a library** (every function has tests, zero-deps core, OIDC publish, lint+format+strict-warnings green). It's **not yet production-ready as a runtime** (no durable execution, no graph control flow, no HITL interrupts) — which is exactly what Tier 1 → 1.0.0 roadmap delivers.

The **next machine-verifiable artifact** in this dev-notes series is **`GOAL.md`** — turn this audit + the Tier 1/2/3 roadmap into a phase-gated execution contract.