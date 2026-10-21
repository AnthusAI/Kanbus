# Getting Started

Kanbus keeps issues, events, and wiki pages as ordinary files next to your code. Where those files live, and who can write them, is up to you. This guide helps you pick a setup, install the tools, and then follow a step-by-step guide for that setup.

## Choose how to run Kanbus

| | Local files | Files in the cloud | S3 and DynamoDB in the cloud |
| --- | --- | --- | --- |
| Where the board lives | `project/` in your working tree | `project/` in a hosted git repository (GitHub, GitLab, and so on) | Objects in a private S3 bucket, indexed by a DynamoDB table |
| Who writes to it | You and the agents on your machine | Everyone with a clone: people, agents, CI, cloud coding sandboxes | Signed-in users of a web application, through an HTTP API |
| How changes travel | Instantly, on disk | `git push` and `git pull`, plus optional live updates over MQTT | Every write goes straight to S3; there is nothing to sync |
| Tools you use | `kbs` or `kanbus`, and the `kbsc` console | The same tools, in every clone | The Kanbus API service and the shared board UI (`@kanbus/ui`) |
| What you need | Git, and one Kanbus CLI | A shared git remote; an MQTT broker for live updates | An AWS account and an application backend (Amplify Gen 2) to deploy into |
| Best for | Solo projects, trying Kanbus out, personal boards | Teams and multi-agent work on code repositories | Boards embedded in a product, used by people who never touch git |

All three use the same issue format, configuration file (`.kanbus.yml`), workflows, and validation rules. A board can move between them: a local board becomes a cloud-files board as soon as you push it, and an existing folder can be imported into S3.

Pick one and follow its guide:

1. [Local files](getting-started/local-files.md). Start here if you are new to Kanbus; the other two guides build on it.
2. [Files in the cloud](getting-started/cloud-files.md). Share a board through a hosted git repository, with optional live updates.
3. [S3 and DynamoDB in the cloud](getting-started/cloud-database.md). Run the Kanbus API on AWS and embed the board in a web application.

## Install the CLI

Kanbus has two equivalent command-line tools. Both run the same behavior specifications and read and write the same files, so a team can mix them.

- `kbs` is the Rust CLI. It is the fastest and comes with `kbsc`, the web console server.
- `kanbus` is the Python CLI. It has the same commands as `kbs`; it does not include the console server.

Every example in these guides uses `kbs`. Replace it with `kanbus` if you installed the Python CLI.

### Prebuilt binaries (recommended)

Download `kbs` and `kbsc` from [GitHub Releases](https://github.com/AnthusAI/Kanbus/releases) and put them on your `PATH`:

```bash
# Linux x86_64
curl -L -o kbs.tar.gz https://github.com/AnthusAI/Kanbus/releases/latest/download/kbs-x86_64-unknown-linux-gnu.tar.gz
curl -L -o kbsc.tar.gz https://github.com/AnthusAI/Kanbus/releases/latest/download/kbsc-x86_64-unknown-linux-gnu.tar.gz

# macOS: use kbs-aarch64-apple-darwin.tar.gz (Apple Silicon) or kbs-x86_64-apple-darwin.tar.gz (Intel),
# and the matching kbsc archive

tar -xzf kbs.tar.gz
tar -xzf kbsc.tar.gz
sudo mv kbs kbsc /usr/local/bin/
kbs --version
```

### Package managers

```bash
pip install kanbus      # Python CLI: kanbus (Python 3.11 or later); add kanbus[ai] for AI summaries
cargo install kanbus    # Rust: kbs and kbsc (Rust 1.88 or later)
```

`cargo install` compiles OpenSSL bindings. On Linux, install the build dependencies first:

```bash
# Ubuntu / Debian
sudo apt-get install -y build-essential perl pkg-config libssl-dev

# Amazon Linux / RHEL
sudo yum install -y gcc make perl-core openssl-devel pkgconfig
```

### From source

```bash
git clone https://github.com/AnthusAI/Kanbus.git
cd Kanbus
cargo build --release --manifest-path rust/Cargo.toml
# Binaries: rust/target/release/kbs and rust/target/release/kbsc
```

To work on the console itself, `./dev.sh` starts the frontend watcher and the Rust backend with automatic rebuilds.

## Optional: an LLM key for AI features

Wiki rendering, summaries, compaction, and right-now summaries call an LLM through LiteLLM. Store a key once for every project on the machine:

```bash
kbs setup ai
```

The key goes in `~/.kanbus.env` (mode `600`). Setting `OPENAI_API_KEY` in your shell or a project `.env` also works. Board commands never need a key; without one, Kanbus prints a hint during `kbs init` and carries on.

## Next steps

- [CLI reference](CLI_REFERENCE.md)
- [Configuration](CONFIGURATION.md): types, workflows, statuses, realtime, and coordination settings
- [Realtime collaboration](REALTIME.md)
- [Wiki guide](WIKI_GUIDE.md)
- [Migrating from Beads](MIGRATION.md)
- [Troubleshooting](TROUBLESHOOTING.md)
