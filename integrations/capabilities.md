# Integration capabilities

| Channel | Input | Access check | Missing access |
| --- | --- | --- | --- |
| Local CLI | Authorized workspace and owner-only Vault | `workspace check`, then live record commands | Use a supplied export or scoped package |
| Codex workspace | Named manifest and user-selected files | Grant the directory explicitly and check the source | Prepare an evidence-backed JSON checkpoint |
| ChatGPT export | Approved ZIP or known conversation JSON | Grant the exact export, with separate L3 consent | Use normalized records or evidence summaries |
| Other AI and connectors | Actual per-environment Git or file permissions | Verify the connection and exact revision | Ask for the minimal approved handoff |

Schedules and connector scopes are deployment choices. A manual run verifies only its observed runtime and coverage.
