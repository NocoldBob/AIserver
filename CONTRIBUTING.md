# Contributing

AIserver keeps a deliberately small scope: single-process, local-first serving for typed Python
inference tasks. Discuss substantial features in an issue before implementing them.

## Development setup

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
python -m ruff check .
python -m pytest
python -m build
python -m twine check dist/*
```

Use the activation command appropriate for your shell on Linux or macOS.

Do not include model weights, credentials, private model inputs, generated datasets, or telemetry
in a contribution. New behavior should include focused tests and documentation.
