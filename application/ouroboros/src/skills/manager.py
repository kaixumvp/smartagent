from typing import Any

from src.plugins.base import PluginManifest
from src.skills.base import RunFlow, RunSubagent, Skill, build_skill


class SkillManager:
    """Builds concrete Skill plugins from persisted skill records.

    The manager does not own a registry; the plugin loader (plugins/loader.py) calls
    `build` per skill record and registers the resulting Skill into a PluginRegistry.
    """

    def __init__(
        self,
        run_subagent: RunSubagent | None = None,
        run_flow: RunFlow | None = None,
    ) -> None:
        self._run_subagent = run_subagent
        self._run_flow = run_flow

    def build(self, record: dict[str, Any]) -> Skill:
        """Instantiate a Skill from a dict with keys: name, version, type, description, manifest, body."""
        manifest_data: dict = record.get("manifest") or {}
        manifest = PluginManifest(
            name=record["name"],
            version=str(record.get("version", "1")),
            kind="skill",
            description=manifest_data.get("description") or record.get("description") or "",
            parameters=manifest_data.get("parameters") or {"type": "object", "properties": {}, "required": []},
            permission=manifest_data.get("permission", "read"),
            requires_approval=manifest_data.get("requires_approval", False),
            dependencies=manifest_data.get("dependencies", []),
            tags=manifest_data.get("tags", []),
        )
        return build_skill(
            record["type"],
            manifest,
            record.get("body") or {},
            run_subagent=self._run_subagent,
            run_flow=self._run_flow,
        )
