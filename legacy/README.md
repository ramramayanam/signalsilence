# Legacy: the n8n / CustomGPT era (March 2026)

SignalSilence began as (1) an n8n workflow implementing a five-stage MEP
pipeline — Supabase dataset load, feature preparation, GPT-4o-mini triage
with strict JSON and fail-toward-caution parsing, human suppression-review
gate, and a Postgres feedback log — and (2) a CustomGPT running the
instruction set now preserved in `prompts/v2_instruction_set.txt`.

The v1 MEP prompt and Supabase DDL are preserved in `prompts/` and the
project documents. This repo reimplements that design as auditable Python:
the prompt rules became `policy.py` invariants and `tests/test_policy.py`.
