# downstream-breakage-radar

A GitHub Action and CLI that detects breaking changes before release and generates plain English migration notes.

## What it does

- compares a branch against a base ref
- flags changes that touch likely public surfaces
- generates concise migration notes for maintainers
- can run locally or in GitHub Actions

## Quick start

```bash
python -m downstream_breakage_radar.cli --repo . --base origin/main
```

JSON output:

```bash
python -m downstream_breakage_radar.cli --repo . --base origin/main --format json
```

## Roadmap

- diff-aware API surface detection
- language-specific adapters
- release-note drafting
- downstream repository impact hints

## Sponsorship

This project uses GitHub Sponsors. See `.github/FUNDING.yml`.

