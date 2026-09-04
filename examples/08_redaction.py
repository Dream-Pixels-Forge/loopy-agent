"""08 — PII redaction.

Run with::

    python examples/08_redaction.py

No API key required. Demonstrates ``Redactor`` scrubbing
PII (a US SSN) out of an attribute dict before it lands in
a trace span.
"""

from loopy.observe import Redactor, Tracer


def main() -> None:
    redactor = Redactor()
    tracer = Tracer(redactor=redactor)

    # Simulate an agent producing a span with sensitive data.
    span = tracer.start_span("demo", attributes={"prompt": "hi ssn 123-45-6789"})
    span.end()

    spans = tracer.get_spans()
    raw = str(span.attributes)
    pii_visible = "123-45-6789" in raw
    print(f"redact: pii_visible_after_redact={pii_visible}")


if __name__ == "__main__":
    main()
