# Security Policy

## Supported versions

Security fixes are provided for the latest released version.

## Reporting a vulnerability

Use GitHub private vulnerability reporting for this repository. Do not open a public issue
containing credentials, private model inputs, or internal network details.

## Security defaults

- `aiserver run` binds to `127.0.0.1` by default.
- Non-loopback binding requires `AISERVER_TOKEN` unless the operator explicitly passes
  `--allow-unauthenticated`.
- Tokens are read from the environment and are not accepted as command-line values.
- AIserver does not include telemetry or request-body logging.
- Uploaded or submitted values are never treated as executable code.

AIserver is a single-process development and LAN-serving tool. Put it behind a production
reverse proxy when exposing it beyond a trusted private network.
