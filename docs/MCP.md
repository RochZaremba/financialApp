# AI access through MCP

In **Ustawienia domu → Połączenia z AI**, create a named connection. Choose **Tylko odczyt** or **Odczyt i zapis**, a validity of 7/30/90 days, and confirm with your own password. Copy the key once; it cannot be retrieved afterwards. Each connection belongs to you and the selected household. Disconnect it in the same screen at any time.

Server URL: `https://finance.rochzaremba.com/api/mcp` (after deployment). Transport: **Streamable HTTP**. Authentication: `Authorization: Bearer <key>`. Use the URL without a trailing slash. No query-string secrets and no application password in the AI configuration.

For Codex, store the key in an environment variable through your local secret manager, then configure:

```toml
[mcp_servers.razem]
url = "https://finance.rochzaremba.com/api/mcp"
bearer_token_env_var = "RAZEM_MCP_TOKEN"
```

This also works with MCP clients that support a custom Bearer header. Direct hosted ChatGPT/Claude connections that require OAuth login need a future OAuth adapter; this implementation does not offer that login flow. Do not select “No authentication” for this protected endpoint.

Start with `app_context`, then inspect the tool catalog. All current household modules are exposed: overview, budget/planning/settlements, categories, accounts, transactions, goals, schedules/reminders, receipts/OCR, shopping/stock, activity, meters, export and household deletion. Account administration, invitations and connection management remain in the application.

Example request: “Find the electricity meter and save 12345.678 kWh for today.” The client obtains its ID through `meter_list`, inspects `meter_read`, then calls:

```json
{
  "name": "reading_create",
  "arguments": {
    "meter_id": "<ID from meter_list>",
    "idempotency_key": "<new unique ID, reused on retries>",
    "data": {"date": "<today in Europe/Warsaw>", "value": 12345678}
  }
}
```

Amounts are integer minor currency units (PLN grosze). Meter values are **thousandths** of the meter's unit. Readings must be nondecreasing and unique per day. Edit tools use the current `expected_updated_at`; stale edits fail. A read key cannot write even if the client lists write tools. Do not reuse a key for a different mutation.

Photo tools accept `image_base64` containing a JPG/PNG/WebP image up to 10 MB decoded; neither URLs nor local paths are accepted. Images are sanitized and stored privately. Returned proposals require review and an explicit separate save/apply/finalize tool; never infer a reading from an unreadable photo. Existing AI provider limits/costs apply.

All delete tools require `confirm_delete: true` after explicit user consent. Whole-household deletion additionally requires the exact name. A read/write key can modify or delete data with the creator's permissions: use read-only for analysis-only clients. Disconnecting a key blocks new calls; an already executing operation may finish. Disconnecting does not undo existing writes. Password reset by an administrator or the trusted-host CLI invalidates all the user's keys.

Operators: migration 013 adds `mcp_connections`; existing data/storage and deployment topology are preserved. The same private volume and pre-deployment backups cover uploaded images. Connection secrets must not be included in logs, screenshots, exports, tickets or chat. Audit events contain tool name/status only. No real paid-provider requests are required for tests.
