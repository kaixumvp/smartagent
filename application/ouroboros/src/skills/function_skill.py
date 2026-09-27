from __future__ import annotations

import asyncio
import json
import subprocess
import sys

from src.plugins.base import InvokeContext
from src.skills.base import Skill

# Restricted builtins available to a function-skill. This is a best-effort guard, not a
# security boundary: even without `__import__` a determined payload can still reach Python's
# object graph. V0.4 therefore runs function-skills in a *subprocess* by default (see below).
_SAFE_BUILTINS = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "sum": sum,
    "min": min,
    "max": max,
    "sorted": sorted,
    "abs": abs,
    "round": round,
    "range": range,
    "print": print,
}

# Executed in a fresh interpreter per invocation. It reads `{"source", "kwargs"}` as JSON on
# stdin and prints the result of `run(**kwargs)` to stdout.
_SUBPROCESS_BOOTSTRAP = r"""
import sys, json
_SAFE_NAMES = ["len", "str", "int", "float", "bool", "list", "dict",
               "sum", "min", "max", "sorted", "abs", "round", "range", "print"]
_BUILTIN = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
_SAFE = {n: _BUILTIN[n] for n in _SAFE_NAMES}

def _main():
    payload = json.loads(sys.stdin.read())
    ns = {"__builtins__": _SAFE}
    exec(compile(payload["source"], "<function_skill>", "exec"), ns)
    fn = ns.get("run")
    if not callable(fn):
        sys.stderr.write("no run() callable")
        sys.exit(3)
    print(fn(**payload.get("kwargs", {})), file=sys.stdout)

_main()
"""


class FunctionSkill(Skill):
    """A function-skill wraps a snippet of Python source exposing ``def run(**kwargs) -> str``.

    V0.4 runs the snippet in a **subprocess** (fresh interpreter, restricted builtins, a
    timeout) by default. Set ``body.sandbox = "inline"`` to opt back into in-process ``exec``
    for trusted authors only — inline mode is faster but is **not** a security boundary.
    """

    type = "function"

    async def invoke(self, ctx: InvokeContext, **kw) -> str:
        source = str(self._body.get("source", ""))
        if not source:
            return ""
        mode = str(self._body.get("sandbox", "subprocess"))
        if mode == "inline":
            return self._run_inline(source, kw)
        timeout = float(self._body.get("timeout", 5.0))
        return await asyncio.to_thread(self._run_subprocess, source, kw, timeout)

    def _run_inline(self, source: str, kwargs: dict) -> str:
        namespace: dict = {"__builtins__": _SAFE_BUILTINS}
        exec(compile(source, "<function_skill>", "exec"), namespace)  # noqa: S102
        run_fn = namespace.get("run")
        if not callable(run_fn):
            return "function skill has no run() callable"
        return str(run_fn(**kwargs))

    def _run_subprocess(self, source: str, kwargs: dict, timeout: float) -> str:
        payload = json.dumps({"source": source, "kwargs": kwargs}, ensure_ascii=False)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _SUBPROCESS_BOOTSTRAP],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return "function skill timed out"
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            if "no run()" in err:
                return "function skill has no run() callable"
            return f"function skill error: {err or 'non-zero exit'}"
        return proc.stdout.strip()
