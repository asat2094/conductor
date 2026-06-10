"""
Backend registry + resolution (ADR-0021). resolve() always returns a usable backend:
an unknown name or an unavailable backend degrades to 'null' so the host never crashes.
Third parties register backends via register(name, factory).
"""
import os
from typing import Callable

from harness.optimizer.base import Compressor, OptimizeConfig
from harness.optimizer.backends.null import NullCompressor

_BACKENDS: dict[str, Callable[[], Compressor]] = {}


def register(name: str, factory: Callable[[], Compressor]) -> None:
    _BACKENDS[name] = factory


def resolve(name: str) -> Compressor:
    factory = _BACKENDS.get(name)
    if factory is None:
        fallback = _BACKENDS.get("null")
        return fallback() if fallback else NullCompressor()
    inst = factory()
    if not inst.available():
        fallback = _BACKENDS.get("null")
        return fallback() if fallback else NullCompressor()
    return inst


def resolve_from_config(cfg: OptimizeConfig) -> Compressor:
    name = os.environ.get("CONDUCTOR_OPTIMIZER", cfg.backend)
    return resolve(name)
