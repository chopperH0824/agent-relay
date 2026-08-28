# Contributing

Agent Relay changes should remain small enough to audit and portable across Python 3.9+ environments.

## Local verification

```bash
python3 -m compileall -q skills/agent-relay/scripts tests
python3 -m unittest discover -s tests -v
DO_NOT_TRACK=1 npx --yes skills add . --list
```

For a disposable end-to-end install:

```bash
project="$(mktemp -d)"
python3 skills/agent-relay/scripts/relay.py init --project-root "$project" --dry-run
python3 skills/agent-relay/scripts/relay.py init --project-root "$project" --yes
python3 "$project/.agent-relay/relay.py" doctor
```

## Change requirements

- Preserve the one-time installer and project-local runtime model.
- Keep runtime dependencies to the Python standard library unless a major version explicitly changes that contract.
- Add focused tests for state format, managed-file, concurrency, redaction, sealing, or destructive-operation changes.
- Update both `README.md` and `README.en.md` for user-facing behavior.
- Do not add undocumented harness support claims. Separate official loading mechanisms from Agent Relay's own tested behavior.
- Never add real tokens, credentials, private project records, or complete chat transcripts to fixtures.

By contributing, you agree that your contribution is licensed under the repository's MIT License.
