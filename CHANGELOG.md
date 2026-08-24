# Changelog

All notable changes to this project are documented in this file.

## 0.1.2 - 2026-08-24

- Added job management endpoints for listing and deleting job snapshots.
- Added `GET /v1/jobs/{job_id}/result-file` for downloading `FileResult` job outputs.
- Added `aiserver version`, `aiserver examples`, and `aiserver run --jobs-db`.
- Added a runnable no-extra-dependency demo that covers JSON tasks, file uploads, OCR-style
  metadata, embeddings, SQLite jobs, and file results.
- Added HTTP client recipes and a public LAN drone detector pattern document.
- Expanded tests for job management, file downloads, raw bytes results, and CLI helpers.

## 0.1.1 - 2026-08-24

- Added `AIServer.file_task()` for multipart file upload inference tasks.
- Added base64 JSON endpoints for file tasks.
- Added `InputFile` and `FileResult` helpers for file inputs and generated file outputs.
- Added optional SQLite job snapshot persistence.
- Added OCR, image classification, YOLO, speech-to-text, embedding, custom pipeline, and
  LAN drone detector examples.
- Added tests for multipart uploads, base64 uploads, file results, file size limits, and SQLite
  job persistence.
- Fixed the development dependency name from `httpx2` to `httpx`.
- Documented that historical `0.0.x` releases should be yanked and avoided.

## 0.1.0 - 2026-08-20

- Rebuilt AIserver from scratch as a local-first AI inference task server.
- Added typed task registration with generated OpenAPI schemas.
- Added direct execution and in-memory asynchronous jobs.
- Added progress reporting, timeouts, concurrency limits, and lifecycle hooks.
- Added optional bearer-token authentication and request-size limits.
- Added a safe CLI that binds to localhost by default.

This release does not preserve the unrelated API from the historical 0.0.x package.
