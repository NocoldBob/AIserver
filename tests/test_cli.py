from __future__ import annotations

import pytest

from aiserver.cli import _is_loopback, main


def test_loopback_detection() -> None:
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("::1")
    assert _is_loopback("localhost")
    assert not _is_loopback("0.0.0.0")
    assert not _is_loopback("192.168.1.10")


def test_cli_refuses_unauthenticated_lan_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AISERVER_TOKEN", raising=False)
    with pytest.raises(SystemExit) as error:
        main(["run", "examples.basic:server", "--host", "0.0.0.0"])
    assert error.value.code == 2
