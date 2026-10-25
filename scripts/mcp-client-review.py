"""Real official MCP client roundtrip; keys are supplied only through the environment."""

import asyncio
import json
import os
import uuid

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + os.environ["MCP_REVIEW_TOKEN"]},
        trust_env=False,
    ) as http:  # noqa: SIM117 - transport depends on the live client
        async with streamable_http_client("http://localhost:3000/api/mcp", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                result = await session.initialize()
                assert result.serverInfo.name == "Razem"
                tools = await session.list_tools()
                assert len(tools.tools) >= 60
                context = await session.call_tool("app_context", {})
                assert not context.isError
                meter = await session.call_tool(
                    "meter_create",
                    {
                        "data": {"name": "Prąd MCP", "unit": "kWh"},
                        "idempotency_key": str(uuid.uuid4()),
                    },
                )
                assert not meter.isError
                meter_id = json.loads(meter.content[0].text)["id"]
                arguments = {
                    "meter_id": meter_id,
                    "idempotency_key": str(uuid.uuid4()),
                    "data": {"date": "2026-01-01", "value": 12345678},
                }
                first = await session.call_tool("reading_create", arguments)
                repeated = await session.call_tool("reading_create", arguments)
                assert not first.isError and not repeated.isError
                assert json.loads(first.content[0].text)["id"] == json.loads(repeated.content[0].text)["id"]
                detail = await session.call_tool("meter_read", {"meter_id": meter_id})
                assert not detail.isError
                readings = json.loads(detail.content[0].text)["readings"]
                assert len(readings) == 1 and readings[0]["value"] == 12345678
                print("Official SDK: initialize, 60 tools, context, create meter, save/retry/read: OK")


if __name__ == "__main__":
    asyncio.run(main())
