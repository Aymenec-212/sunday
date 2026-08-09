# Rules for this repo

- `models.py` is the contract. Do not change a field without being asked.
- Stages collect/analyze/rules/render must never import from `narrate/`.
  There is a test enforcing this. Do not modify that test.
- No new runtime dependencies beyond: pydantic, pyyaml, httpx.
  Everything else is stdlib. Ask before adding.
- Every list stored on Facts must be explicitly sorted before construction.
- No `datetime.now()` anywhere in collect/, analyze/, or rules/.
- Rules are pure functions. No I/O, no network, no reading files.
- Write the test before the implementation for anything in analyze/ or rules/.
- Never raise out of `cli.py`. Catch, log, degrade, exit 0.
