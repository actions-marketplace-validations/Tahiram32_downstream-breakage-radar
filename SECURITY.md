# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.5.x   | ✅ Yes (latest)    |
| 0.4.x   | ❌ No              |
| 0.3.x   | ❌ No              |
| < 0.3   | ❌ No              |

## Reporting a Vulnerability

If you discover a security vulnerability in Downstream Breakage Radar, **please do not open a public issue.**

Instead, report it privately:

1. **GitHub Security Advisories (preferred)**: Use the [Report a vulnerability](https://github.com/Tahiram32/breakguard/security/advisories/new) feature on GitHub
2. **Direct contact**: Reach out to [@Tahiram32](https://github.com/Tahiram32) via GitHub

### What to include

- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Suggested fix (if you have one)

### What to expect

- **Acknowledgment** within 48 hours of your report
- **Status update** within 7 days with an assessment and timeline
- **Credit** in the release notes (unless you prefer to remain anonymous)

We take all reports seriously. Even though this project has no external dependencies and runs only `git diff` under the hood, we want to make sure it's safe for everyone.

## Security Considerations

Downstream Breakage Radar:

- **Does not execute any code** from the scanned repository — it only reads file paths from `git diff` output
- **Has zero external dependencies** — the attack surface from third-party packages is eliminated
- **Runs subprocess calls** only to `git` — inputs are passed as list arguments (not shell strings) to prevent injection
- **Does not transmit data** — all analysis happens locally; nothing is sent to external services

## Disclosure Policy

We follow coordinated disclosure. Once a fix is available, we will:

1. Release a patched version
2. Publish a GitHub Security Advisory
3. Credit the reporter (with their permission)

Thank you for helping keep Downstream Breakage Radar and its users safe. 🔒
