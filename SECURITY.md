# Security

## Reporting a problem

Please do not open a public issue for a security problem. Report it privately through
[GitHub's private vulnerability reporting](https://github.com/magnetoid/spark/security/advisories/new)
for this repository.

Include what an attacker can do, the steps to reproduce it, and the version from `/healthz`.
You will get an answer within a week. Once a fix is released we credit you in the changelog
unless you prefer not to be named.

## Supported versions

Fixes go into the latest release on the `main` branch. Upgrade to it to receive them.

## Running Spark safely

- Set `SPARK_SETUP_TOKEN` before a new install is reachable from the internet.
- Use a long random `SPARK_SECRET_KEY` and keep it private. It encrypts saved keys and channel
  tokens.
- Serve Spark over HTTPS with `SPARK_ENV=production`.
- Turn on two-factor for owners, and require it for the whole team under
  **Settings → Brand & team**.
- Personal API and MCP tokens act with their owner's role. Give them to tools you trust and
  delete the ones you no longer use.
