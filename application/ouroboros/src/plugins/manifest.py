"""Reference parsing and manifest helpers for the plugin system.

A plugin reference has the form `{kind}:{name}@{version}` where `@version` is optional
and defaults to the latest version. Examples: `tool:calculator`, `skill:refund@1.2.0`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PluginRef:
    kind: str
    name: str
    version: str | None = None


def parse_ref(ref: str) -> PluginRef | None:
    """Parse a `kind:name@version` reference; return None when malformed."""
    if not ref or ":" not in ref:
        return None
    kind, _, rest = ref.partition(":")
    name, _, version = rest.partition("@")
    name = name.strip()
    kind = kind.strip()
    if not kind or not name:
        return None
    return PluginRef(kind=kind, name=name, version=version.strip() or None)


def format_ref(kind: str, name: str, version: str | None = None) -> str:
    """Serialize a plugin identity back into a reference string."""
    return f"{kind}:{name}" if version is None else f"{kind}:{name}@{version}"
