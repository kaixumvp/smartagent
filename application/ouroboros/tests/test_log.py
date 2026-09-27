"""Tests for the logging helper."""

import logging

import src.log as logmod


def _mock_getLogger(mock):
    real = logging.getLogger

    def fake(name=None):
        return mock if name == "src" else real(name)

    return fake


def _fresh_mock_logger():
    mock = logging.getLogger("src._test_mock")
    mock.handlers = []
    mock.propagate = True
    mock.setLevel(logging.NOTSET)
    return mock


def test_configure_logging_sets_up_logger(monkeypatch):
    mock = _fresh_mock_logger()
    monkeypatch.setattr(logmod.logging, "getLogger", _mock_getLogger(mock))
    monkeypatch.setattr(logmod, "_configured", False)

    lg = logmod.configure_logging(logging.INFO)

    assert lg is mock
    assert lg.level == logging.INFO
    assert lg.propagate is False
    assert any(isinstance(h, logging.StreamHandler) for h in lg.handlers)


def test_configure_logging_idempotent(monkeypatch):
    mock = _fresh_mock_logger()
    monkeypatch.setattr(logmod.logging, "getLogger", _mock_getLogger(mock))
    monkeypatch.setattr(logmod, "_configured", False)

    logmod.configure_logging(logging.INFO)
    before = len([h for h in mock.handlers if isinstance(h, logging.StreamHandler)])
    logmod.configure_logging(logging.DEBUG)  # second call → no-op
    after = len([h for h in mock.handlers if isinstance(h, logging.StreamHandler)])

    assert after == before
