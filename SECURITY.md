# Security Policy

## Supported versions

Vector Passport is a draft v1.0 specification plus a reference CLI. Report issues against the current `main` branch.

## Reporting a vulnerability

Please do **not** open a public issue for a vulnerability in the CLI, signing helpers, or schema validation.

Use GitHub's private vulnerability reporting on this repository (Security → Advisories → Report a vulnerability), or email the maintainer listed on the GitHub profile.

Include:

- the affected command or file
- a minimal reproduction
- impact (signature bypass, hash collision assumptions, secret leakage, and so on)

You should hear back within a week. Fixes that change the v1.0 wire format will be called out in `CHANGELOG.md` and `SPEC.md`.

## Signing keys

Keep `private_key.pem` files out of git and out of CI logs. The CLI writes POSIX key files as owner-read/write only. Public keys used for `verify-signature` are not secrets.
