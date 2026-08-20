# AIserver 中文说明

AIserver 是一个轻量、本地优先的 Python AI 任务服务器，用于把推理函数快速发布为
安全、类型明确并支持并发控制的 HTTP API。

它不是模型推理引擎或云平台。你可以继续使用 PyTorch、ONNX Runtime、TensorRT、
OpenCV、Ollama 客户端或任意 Python 代码，AIserver 只负责可靠地对外提供任务接口。

## 主要能力

- 根据 Python 类型注解自动校验输入并生成 OpenAPI 文档。
- 同一个任务既可以直接执行，也可以提交为内存异步任务。
- 为每个任务设置并发数，避免多个请求耗尽显存或内存。
- 支持进度、状态、结果查询和任务超时。
- 通过启动和关闭钩子统一加载、释放模型。
- 默认只监听 `127.0.0.1`。
- 使用 `AISERVER_TOKEN` 保护局域网接口。
- 限制请求体大小，不记录请求内容，不包含遥测。

## 安装

```powershell
pip install AIserver
```

## 快速开始

新建 `app.py`：

```python
from aiserver import AIServer, TaskContext

server = AIServer("demo")


@server.task(concurrency=1, timeout=60)
def detect(image_path: str, context: TaskContext) -> dict:
    context.report(0.2, "loading image")
    result = model.predict(image_path)
    context.report(0.9, "formatting result")
    return {"detections": result}
```

启动：

```powershell
aiserver run app:server
```

然后访问 `http://127.0.0.1:8000/docs`，可以直接在浏览器中调试接口。

### 直接执行

```text
POST /v1/tasks/detect/run
```

请求会等待任务完成并直接返回结果，适合耗时较短的推理。

### 异步任务

```text
POST /v1/tasks/detect/jobs
GET  /v1/jobs/{job_id}
```

提交接口立即返回任务 ID，随后通过状态接口查询进度和结果，适合长时间推理。

## 局域网使用

开放到局域网前先设置长随机令牌：

```powershell
$env:AISERVER_TOKEN = "请替换为长随机值"
aiserver run app:server --host 0.0.0.0
```

客户端通过以下任一种请求头提交令牌：

```text
Authorization: Bearer <token>
X-API-Key: <token>
```

令牌不要写进源码、命令行参数或公开日志。需要通过互联网访问时，应在前面部署带
TLS 的反向代理。

## 当前边界

- 单进程运行，便于多个任务共享同一个内存模型。
- 异步任务记录只保存在内存，程序重启后不会保留。
- 超时可以停止等待异步函数，但无法强制终止已经在线程中运行的同步模型代码。
- 不负责下载模型、转换模型协议、分布式调度或云端管理。

## 旧版本说明

`0.1.0` 是完全重写版本，不兼容历史 `0.0.x` 中的远程聊天和机器人演示接口。旧版本
不应继续使用。
