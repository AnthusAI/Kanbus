# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Do not file a public issue or pull request for a security problem.

Include the affected version or commit, the steps to reproduce, and the impact you expect. We will acknowledge the report, investigate, and coordinate a fix and disclosure with you.

## Supported versions

Security fixes are made on the latest release of the Python package (`kanbus` on PyPI) and the Rust crate (`kanbus` on crates.io), which are released together.

## Scope

In scope: the `kbs`, `kbsc` and `kanbus` command-line tools, the Kanbus API service, and the shared board UI. Credentials for AI features are stored by `kbs setup ai` in `~/.kanbus.env` with mode `600`; reports about how Kanbus stores or transmits them are welcome.
