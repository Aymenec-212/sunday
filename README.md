# CommitScope

A push-triggered analyzer that inspects a commit, extracts structural facts,
applies deterministic rules, and publishes a report.

**Core constraint:** the same commit always produces the same report. The LLM
is an optional cosmetic layer, not a decision-maker. Disable it with
`--no-llm` and you still get a complete, useful report.

Target language for v1: **Python** (uses the stdlib `ast`).

## What it catches

| ID | Name | Fires when | Severity |
|----|------|------------|----------|
| R001 | breaking_signature | a required param is added/removed and an external caller still uses the old signature | high |
| R002 | public_symbol_removed | a public symbol is deleted while other modules still reference it | high |
| R003 | layer_violation | a new import crosses a forbidden architectural boundary | high |
| R004 | undocumented_env_var | an env var is read in code but undocumented | medium |
| R005 | wide_blast_radius | a changed symbol is referenced widely across many files | medium |
| R006 | unimported_dependency | a dependency is added but never imported | medium |
| R007 | arch_doc_stale | the import graph changed but `ARCHITECTURE.md` did not | low |
| R008 | test_gap | a new public symbol was added with no test changes | low |

Rules are pure functions of the analyzed facts; thresholds and the layer map
live in `commitscope.yaml`, never as literals in rule bodies.

## Usage

```bash
pip install -e .

# Analyze one commit and print/write the report
commitscope run --sha <sha>

# Replay the analysis over recent history
commitscope replay --last 10

# Print findings for a commit to stdout
commitscope explain --sha <sha>
```

Useful flags: `--no-llm` (skip narration), `--publish` (post/refresh the
commit comment), `--strict` (exit non-zero on failure; by default the CLI is
an observer and always exits 0), `--output DIR` (artifact directory).

## Environment variables

All are optional; the tool degrades cleanly when they are unset.

| Variable | Purpose |
|----------|---------|
| `COMMITSCOPE_API_KEY` / `ANTHROPIC_API_KEY` | API key that enables the narration layer |
| `COMMITSCOPE_MODEL` | Override the narration model id |
| `GITHUB_TOKEN` | Auth for posting the commit comment (`--publish`) |
| `GITHUB_REPOSITORY` | `owner/repo`, supplied by GitHub Actions |
| `GITHUB_API_URL` | GitHub API base (for GitHub Enterprise) |
| `GITHUB_STEP_SUMMARY` | Job-summary file path, supplied by GitHub Actions |

## Determinism

- Every list on `Facts` is sorted by a documented key before the model is
  built, and `facts_hash` is a SHA-256 over the canonical JSON.
- No wall-clock value ever enters `Facts` or the rendered report.
- Narrations are cached on disk keyed by `facts_hash + finding.id`, and are
  the *only* thing that differs between a full run and `--no-llm`
  (`tests/test_no_llm_parity.py` enforces this).

## Narration guardrails

Exactly one model call per commit (plus at most one retry). The output is
validated in order: **schema → id allowlist → length → grounding**. The
grounding check extracts identifier-shaped tokens (dotted qualnames, `*.py`
paths, SCREAMING_CASE names) and rejects any that are not in the finding's
`facts_refs` — this is what catches invented filenames and functions. On
failure the finding renders from a template; the run never fails because of
the model.

## Layout

```
commitscope/
  cli.py            # argparse: run, replay, explain
  pipeline.py       # orchestration + skip conditions + time limit
  config.py         # commitscope.yaml -> Config
  models.py         # Facts, Finding — the data contract
  collect/          # git subprocess wrapper
  analyze/          # symbols, refs, contracts, layers, assemble
  rules/            # engine + the eight built-in rules
  narrate/          # single model call, grounding, cache
  render/           # markdown templates
  publish/          # commit comment + job summary
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the pipeline and its layer rules.
