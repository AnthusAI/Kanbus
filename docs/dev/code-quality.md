# Local CodeQL ("Code Quality") Scan

Run the same CodeQL code-quality queries that GitHub executes on PRs, but locally, to fix findings before pushing.

## Prerequisites
- macOS or Linux (auto-download uses GitHub CodeQL bundle).
- `curl` and `tar` available.
- Network access to download CodeQL (if not already installed).

## Usage
From repo root:

```bash
tools/run_codeql_local.sh
```

Key options:
- `--lang "python,javascript-typescript"` to choose languages (defaults to both).
- `--keep-db` reuse existing databases.
- `--keep-reports` keep previous SARIF outputs.
- `--no-fail` always exit 0 even if findings exist.

Outputs land in `.codeql/reports/<lang>-code-quality.sarif` (gitignored).

Open SARIF in VS Code with the SARIF Viewer extension (recommended) or upload to any SARIF-capable viewer.

## What it runs
- CodeQL CLI **2.24.2** (downloaded to `.codeql-tools/` if not on PATH).
- Creates per-language databases under `.codeql/db-<lang>/`.
- Analyzes using `codeql/<lang>-queries` with `--analysis-kind=code-quality` to mirror the GitHub "Code Quality" workflow.

## Expected runtime
- Typically a few minutes per language on a laptop; first run downloads the CLI (~hundreds of MB).

## Notes
- Does not change CI. GitHub Actions will continue to run the official "Code Quality" check.
- Rust/Go are not included because the repo's CodeQL workflow only runs Python and JavaScript/TypeScript.
