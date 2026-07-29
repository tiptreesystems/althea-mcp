from __future__ import annotations

import pytest

from althea_mcp import cli


@pytest.mark.parametrize(
    ("exception", "expected_status", "expected_message"),
    [
        (EOFError(), 1, "setup cancelled because input ended"),
        (KeyboardInterrupt(), 130, "setup interrupted"),
    ],
)
def test_setup_cancellation_has_no_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exception: BaseException,
    expected_status: int,
    expected_message: str,
) -> None:
    async def cancelled_setup(*_args: object, **_kwargs: object) -> None:
        raise exception

    monkeypatch.setattr(cli, "run_setup", cancelled_setup)

    with pytest.raises(SystemExit) as exit_error:
        cli.main(["setup"])

    captured = capsys.readouterr()
    assert exit_error.value.code == expected_status
    assert expected_message in captured.err
    assert "Traceback" not in captured.err


def test_server_interrupt_is_not_labeled_as_setup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from althea_mcp import server

    def interrupted_server() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(server, "main", interrupted_server)

    with pytest.raises(SystemExit) as exit_error:
        cli.main(["serve"])

    captured = capsys.readouterr()
    assert exit_error.value.code == 130
    assert "server stopped" in captured.err
    assert "setup" not in captured.err
    assert "Traceback" not in captured.err
