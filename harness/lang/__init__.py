"""Pluggable language adapters (ADR-0035). The single seam for every language-specific operation;
the base system never branches on language — it resolves an adapter and calls it."""

from harness.lang import python_adapter  # noqa: F401 — registers PythonAdapter
