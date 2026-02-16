# Kanbus (Rust crate)

Kanbus is a high-performance command-line interface and console server for the Kanbus issue tracker.

## Install

```bash
cargo install kanbus
```

This installs two binaries:
- `kanbus` - The CLI for creating, listing, and managing issues
- `kanbus-console` - The web UI server with embedded frontend assets

## Shortcuts (Optional)

For convenience, you can create short command shortcuts:

```bash
# Run the installer script
curl -sSL https://raw.githubusercontent.com/AnthusAI/Kanbus/main/rust/install-aliases.sh | bash

# Or manually create symlinks in ~/.cargo/bin/:
cd ~/.cargo/bin
ln -s kanbus kbs
ln -s kanbus-console kbsc
```

These shortcuts work in all shells and scripts.

## Usage

**CLI:**
```bash
kanbus --help          # or: kbs --help
kanbus init
kanbus create "Fix the login flow"
kanbus list
```

**Console Server:**
```bash
kanbus-console         # or: kbsc
# Opens web UI at http://127.0.0.1:5174/
```

For full guidance, see the Kanbus documentation:

- Homepage: https://kanb.us
- Documentation: https://kanb.us/docs

## License

Licensed under the MIT License. See `LICENSE` in this directory.
