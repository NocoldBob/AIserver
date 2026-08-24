# LAN Drone Detector Pattern

This is a public AIserver deployment pattern for a small trusted LAN. It does not include model
weights, board passwords, private paths, ROS2 message definitions, or production deployment
instructions.

## Shape

- Bind on the LAN only when `AISERVER_TOKEN` is set.
- Use one process so the detector can keep one GPU or accelerator context in memory.
- Use `concurrency=1` for the frame detector to avoid overlapping GPU inference.
- Use short per-frame timeouts and file-size limits.
- Store completed job snapshots in SQLite when operators need to inspect recent results.
- Keep model paths in environment variables, not in source control.

## Sample

```powershell
$env:AISERVER_TOKEN = "use-a-long-random-value"
$env:DRONE_DETECTOR_MODEL = "C:\models\drone-detector.engine"
aiserver run examples.drone_lan_detector:server --host 0.0.0.0
```

Submit one frame:

```bash
curl -X POST http://SERVER:8000/v1/tasks/detect-frame/run \
  -H "Authorization: Bearer use-a-long-random-value" \
  -F "file=@frame.jpg"
```

The example response uses a generic structure:

```json
{
  "frame_id": "frame.jpg",
  "timestamp": "client-supplied-or-server-generated",
  "camera": "unknown",
  "detections": [],
  "latency_ms": 0.0,
  "device": "cuda:0"
}
```

For production systems, keep ROS2 topics, camera calibration, model manifests, and board-specific
configuration in the deployment project that owns them. AIserver should expose the local inference
boundary, not become the source of truth for flight or deployment configuration.
