# Changelog

All notable changes to this project are documented in this file.

## 0.1.0 - 2026-08-20

- Rebuilt AIserver from scratch as a local-first AI inference task server.
- Added typed task registration with generated OpenAPI schemas.
- Added direct execution and in-memory asynchronous jobs.
- Added progress reporting, timeouts, concurrency limits, and lifecycle hooks.
- Added optional bearer-token authentication and request-size limits.
- Added a safe CLI that binds to localhost by default.

This release does not preserve the unrelated API from the historical 0.0.x package.
