"""
Backend registry + resolution (ADR-0021). resolve() always returns a usable backend:
an unknown name or an unavailable backend degrades to 'null' so the host never crashes.
Third parties register backends via register(name, factory).
"""
import os
from typing import Callable

from harness.optimizer.base import Compressor, OptimizeConfig

_BACKENDS: dict[str, Callable[[], Compressor]] = {}


def register(name: str, factory: Callable[[], Compressor]) -> None:
    _BACKENDS[name] = factory


def resolve(name: str) -> Compressor:
    factory = _BACKENDS.get(name)
    if factory is None:
        return _BACKENDS["null"]()
    inst = factory()
    if not inst.available():
        return _BACKENDS["null"]()
    return inst


def resolve_from_config(cfg: OptimizeConfig) -> Compressor:
    name = os.environ.get("CONDUCTOR_OPTIMIZER", cfg.backend)
    return resolve(name)
