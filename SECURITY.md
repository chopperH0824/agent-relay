# Security Policy

## Supported versions

Security fixes are provided for the latest published release.

| Version | Supported |
| --- | --- |
| `0.1.x` | Yes |
| `< 0.1` | No executable release |

## Reporting a vulnerability

Use the repository's private vulnerability reporting feature when available. Do not place real credentials, private project content, or exploitable secret material in a public issue.

Include:

- affected Agent Relay version;
- operating system and Python version;
- command and minimal reproduction using synthetic data;
- expected and actual boundary behavior;
- whether secrets, project-external paths, sealed artifacts, or adapter files are affected.

For the runtime trust model, persistence boundary, redaction rules, and recovery guarantees, read [the Security and Privacy Reference](./skills/agent-relay/references/SECURITY.md).
