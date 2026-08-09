# Architecture

CommitScope is a five-stage, strictly one-directional pipeline. Each stage's
output is a serializable artifact, and the same commit always produces the
same report.

```
git push
   │
   ▼
[1] COLLECT  (commitscope/collect)  ── pure git, zero interpretation
   │
   ▼
[2] ANALYZE  (commitscope/analyze)  ── static analysis, deterministic, hashed
   │
   ▼
[3] RULES    (commitscope/rules)    ── pure functions over facts, severities here
   │
   ▼
[4] NARRATE  (commitscope/narrate)  ── OPTIONAL prose, fact-checked, cosmetic
   │
   ▼
[5] RENDER   (commitscope/render)   ── templates → report.md
   │
   ▼
       PUBLISH (commitscope/publish) ── commit comment + job summary
```

## The rule that keeps it honest

Severity, detection, and evidence are computed by code. The model gets one
job — turn a finding into a readable sentence — and its output is verified
against the facts before it is accepted. Stages 1–3 and 5 never import the
model client; only stage 4 may make a network call to a model provider.

## Declared layer edges

The pipeline's own import graph is declared in `commitscope.yaml` so
CommitScope enforces it on itself (rule R003):

- `analyze → collect` — analyzers read git blobs.
- `publish → render` — publishing renders markdown.

Every other cross-stage edge is a violation. In particular, **no stage may
import `narrate/`** — that boundary is additionally guarded by
`tests/test_layering.py`.

The orchestrators `commitscope/cli.py` and `commitscope/pipeline.py` sit above
the layers (they wire all stages together) and are intentionally unmapped.
