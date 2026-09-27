"""Logging helpers for Ouroboros.

The framework emits records via the standard :mod:`logging` module under the ``ouroboros``
namespace (e.g. ``ouroboros.core.runtime``). It never configures handlers or levels itself —
that is the host's job — so embedding Ouroboros in another app won't hijack that app's
logging setup.

Enable framework logs from a host application::

    import logging
    from src.log import configure_logging

    configure_logging(level=logging.INFO)
"""


import logging
import sys

_DEFAULT_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(level: int = logging.INFO, fmt: str | None = None) -> logging.Logger:
    """Configure the ``ouroboros`` logger with a stderr handler (idempotent).

    Hosts call this to opt in to framework logging; the framework itself never does. Returns
    the configured ``ouroboros`` logger.
    """
    global _configured
    logger = logging.getLogger("src")
    if _configured:
        return logger

    logger.setLevel(level)
    logger.propagate = False  # avoid double-logging with the host's root handlers
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt or _DEFAULT_FMT, datefmt=_DEFAULT_DATEFMT))
    logger.addHandler(handler)
    _configured = True
    return logger
