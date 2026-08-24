# HTTP Client Recipes

These commands assume a server is running locally:

```bash
aiserver run examples.runnable_demo:server
```

## JSON task

```bash
curl -X POST http://127.0.0.1:8000/v1/tasks/embed-text/run \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"hello\"}"
```

## Multipart file upload

```bash
curl -X POST http://127.0.0.1:8000/v1/tasks/classify-image/run \
  -F "file=@sample.png"
```

## Base64 file upload

```python
import base64
import requests

payload = {
    "filename": "sample.png",
    "content_type": "image/png",
    "data_base64": base64.b64encode(open("sample.png", "rb").read()).decode("ascii"),
}
response = requests.post(
    "http://127.0.0.1:8000/v1/tasks/classify-image/run-base64",
    json=payload,
    timeout=30,
)
print(response.json())
```

## Async job polling

```python
import time
import requests

job = requests.post(
    "http://127.0.0.1:8000/v1/tasks/embed-text/jobs",
    json={"text": "hello"},
    timeout=30,
).json()

while True:
    status = requests.get(f"http://127.0.0.1:8000{job['status_url']}", timeout=30).json()
    if status["state"] in {"succeeded", "failed", "timed_out"}:
        print(status)
        break
    time.sleep(0.2)
```

## Download a file result

Submit `summarize-file` as a job, wait until it succeeds, then:

```bash
curl -L http://127.0.0.1:8000/v1/jobs/JOB_ID/result-file -o summary.json
```

## Token authentication

```powershell
$env:AISERVER_TOKEN = "use-a-long-random-value"
aiserver run examples.runnable_demo:server --host 0.0.0.0
```

```bash
curl http://SERVER:8000/v1/tasks \
  -H "Authorization: Bearer use-a-long-random-value"
```
