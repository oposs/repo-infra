---
description: Report how far this repository has drifted from the infrastructure standard
---

Run the checker and read the report to the user:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/repo-infra/scripts/repo_infra" check
```

Report the output as it is. Do not summarise a `conflict` into "needs updating" —
the whole point of that state is that it says what breaks. If the report lists an
`ambiguous` item, ask the user the question named in its detail; do not answer it
yourself, and do not run `/repo-infra:apply` until it is answered.

`check` exits 1 when anything needs attention and 0 when the repository is
current with the standard — that exit code is the whole result, so trust it over
guessing from the text.
