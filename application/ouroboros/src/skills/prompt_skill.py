import re

from src.plugins.base import InvokeContext
from src.skills.base import Skill

_TOKEN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


class PromptSkill(Skill):
    """A pure prompt-template skill: renders `{{key}}` placeholders and returns the result.

    The rendered text is injected back into the conversation as reference material for the
    LLM (it does not execute any code). `body.template` holds the template string.
    """

    type = "prompt"

    async def invoke(self, ctx: InvokeContext, **kw) -> str:
        template = str(self._body.get("template", ""))
        context: dict = {**ctx.model_dump(), **kw}
        # Also support a pre-formatted memory context under the `memory_ctx` key.
        if "memory_ctx" not in context:
            context["memory_ctx"] = ""
        return _TOKEN.sub(lambda m: str(context.get(m.group(1), "")), template)
