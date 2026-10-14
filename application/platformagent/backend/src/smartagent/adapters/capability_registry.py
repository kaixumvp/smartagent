from typing import Any

import httpx


class CapabilityRegistryError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class CapabilityRegistryClient:
    def __init__(self, base_url: str, integration_key: str) -> None:
        if not base_url:
            raise CapabilityRegistryError("Capability Registry URL is not configured", 503)
        if not integration_key:
            raise CapabilityRegistryError("Capability integration key is not configured", 503)
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-Capability-Integration-Key": integration_key}

    async def _get(self, path: str) -> Any:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self._base_url}/internal{path}",
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            status_code = 404 if exc.response.status_code == 404 else 502
            raise CapabilityRegistryError(
                f"Capability Registry request failed (HTTP {exc.response.status_code})",
                status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise CapabilityRegistryError(
                f"Capability Registry is unreachable ({type(exc).__name__})"
            ) from exc

    async def list_providers(self) -> list[dict[str, Any]]:
        return await self._get("/providers")

    async def list_provider_tools(self, provider_id: str) -> list[dict[str, Any]]:
        return await self._get(f"/providers/{provider_id}/tools")

    async def list_tools(self) -> list[dict[str, Any]]:
        return await self._get("/tools")

    async def call_tool(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=130) as client:
                response = await client.post(
                    f"{self._base_url}/internal/tools/{tool_id}/call",
                    headers=self._headers,
                    json={"arguments": arguments},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            detail = f"Capability Registry Tool call failed (HTTP {exc.response.status_code})"
            try:
                payload = exc.response.json()
                if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                    detail = payload["detail"]
            except ValueError:
                pass
            raise CapabilityRegistryError(detail, 502) from exc
        except httpx.RequestError as exc:
            raise CapabilityRegistryError(
                f"Capability Registry is unreachable ({type(exc).__name__})"
            ) from exc
