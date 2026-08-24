# AIserver Examples

All examples run local code only. They are intentionally small so you can replace the placeholder
body with your own PyTorch, ONNX Runtime, TensorRT, OpenCV, OCR, ASR, or embedding model.

## JSON task

```bash
aiserver run examples.basic:server
```

## File upload

```bash
aiserver run examples.file_upload:server
curl -X POST http://127.0.0.1:8000/v1/tasks/inspect-image/run -F "file=@sample.png"
```

The same file task also exposes JSON base64 endpoints:

```text
POST /v1/tasks/inspect-image/run-base64
POST /v1/tasks/inspect-image/jobs-base64
```

## AI task skeletons

- `examples.image_classification:server`
- `examples.ocr:server`
- `examples.yolo_detection:server`
- `examples.speech_to_text:server`
- `examples.embeddings:server`
- `examples.custom_pipeline:server`

## LAN drone detector sample

```powershell
$env:AISERVER_TOKEN = "use-a-long-random-value"
$env:DRONE_DETECTOR_MODEL = "C:\models\detector.engine"
aiserver run examples.drone_lan_detector:server --host 0.0.0.0
```

This sample uses `concurrency=1`, short task timeouts, per-file size limits, and a SQLite job
store. It is a local/LAN deployment pattern, not an internet-facing service.
