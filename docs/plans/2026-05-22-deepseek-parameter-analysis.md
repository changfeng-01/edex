# DeepSeek Parameter Analysis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an optional `deepseek-v4-pro` analysis layer that reads existing CircuitPilot parameter and metric outputs and writes human-readable plus structured AI analysis.

**Architecture:** Keep deterministic metric, scoring, recommendation, and candidate generation in existing modules. Add a small LLM client module that builds a bounded prompt from `real_summary.json`, `score_summary.json`, `real_metrics.csv`, and `next_candidates.csv`, calls the DeepSeek OpenAI-compatible chat API through an injectable transport, and writes Markdown/JSON outputs with `simulation_only` boundaries.

**Tech Stack:** Python standard library HTTP client, pandas, pytest, current `goa_eval` CLI.

---

### Task 1: Unit-Test Prompt and Output Behavior

**Files:**
- Create: `tests/test_llm_analysis.py`
- Create: `src/goa_eval/llm_analysis.py`

**Steps:**
1. Write tests for prompt payload construction from summary, score, metrics, and candidates.
2. Verify the test fails because `goa_eval.llm_analysis` does not exist.
3. Implement minimal helpers to build input payloads and write Markdown/JSON.
4. Run `python -m pytest tests/test_llm_analysis.py -q`.

### Task 2: Add DeepSeek Client Without Network in Tests

**Files:**
- Modify: `src/goa_eval/llm_analysis.py`
- Test: `tests/test_llm_analysis.py`

**Steps:**
1. Write tests with a fake transport returning a DeepSeek-like chat completion.
2. Verify the test fails because the client call path is missing.
3. Implement environment-key lookup, JSON request body, response parsing, and clear error messages.
4. Run `python -m pytest tests/test_llm_analysis.py -q`.

### Task 3: Add CLI Command

**Files:**
- Modify: `src/goa_eval/cli.py`
- Test: `tests/test_cli_smoke.py`

**Steps:**
1. Add a CLI smoke test for `analyze-params --mock-response`.
2. Verify it fails because the command is not registered.
3. Add `analyze-params` arguments and route to `run_llm_parameter_analysis`.
4. Run the CLI smoke test.

### Task 4: Docs and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/schema_spec.md`

**Steps:**
1. Document `DEEPSEEK_API_KEY`, default model `deepseek-v4-pro`, and output files.
2. Run targeted tests.
3. Run `python -m pytest -q`.
