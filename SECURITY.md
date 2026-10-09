# Security Policy

## Reporting a Vulnerability

Please report security issues by creating a private vulnerability report in the GitHub repository or by emailing the maintainer directly if an address is provided. 

**Do not open a public issue for security vulnerabilities.**

## Privacy and Data Handling

Limitline runs entirely on your local machine. It does not send analytics, telemetry, or your local usage logs anywhere. 

- **Session Logs:** Local logs created by Claude Code are parsed locally to generate charts. Limitline never logs, stores, or transmits your actual prompt or response text, only metadata (timestamp, model, cost, tokens, and git branch).
- **Plan Limits (Status Line):** The default method connects to Claude Code's status-line hook. It receives only your usage percentages and reset times. It never accesses your login tokens.
- **Plan Limits (Advanced OAuth Mode):** If you manually opt in, Limitline reads your local Claude Code credentials (`~/.claude/credentials.json`) to fetch your limits directly from Anthropic's API. Limitline uses these credentials **only** to contact `api.anthropic.com/api/oauth/usage` and `/profile`. It never sends them to a third party.

## Safe Bug Reports

When opening an issue for bugs or feature requests:
- **Never attach `credentials.json` or `.limitline-live.json`.**
- **Never attach raw `.jsonl` session logs**, as they contain your actual conversation text and code.
- If you need to share a log structure to debug a crash, please **redact all message text** before posting.
