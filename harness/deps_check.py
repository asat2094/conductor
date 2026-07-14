"""
Dependency-existence / slopsquatting guard (ADR-0026, REQ-A4). Before any maker-proposed install,
verify the package name resolves on PyPI. The resolver is INJECTED so the harness controls the
network call and tests need none. ~19.7% of LLM-suggested packages don't exist; an unresolvable
name is rejected. Offline -> 'unverified' (do not auto-install), never silently 'ok'.

Name validation against PEP 508 regex guards against SSRF/path-injection attacks; invalid names
are rejected as 'invalid' without calling the resolver.
"""
import re
from typing import Callable

_VALID_NAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")

OFFLINE = object()   # sentinel a resolver may return to signal "couldn't check"


def _is_valid_name(name: str) -> bool:
    """Validate package name against PEP 508 regex; rejects /, .., ?, #, %, spaces, etc."""
    return bool(_VALID_NAME.match(name))


def _default_resolver(name: str):
    """Live PyPI existence check via the JSON API. Returns True/False, or OFFLINE on network error."""
    import urllib.request
    import urllib.error
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        return OFFLINE
    except Exception:
        return OFFLINE


def check_dependencies(names: list[str], resolver: Callable[[str], object] = _default_resolver) -> dict[str, str]:
    """name -> 'ok' | 'unresolvable' | 'unverified' | 'invalid'. Offline/error -> 'unverified' (fail safe)."""
    out: dict[str, str] = {}
    for name in names:
        if not _is_valid_name(name):
            out[name] = "invalid"
            continue
        try:
            result = resolver(name)
        except Exception:
            out[name] = "unverified"
            continue
        if result is OFFLINE:
            out[name] = "unverified"
        elif result:
            out[name] = "ok"
        else:
            out[name] = "unresolvable"
    return out
