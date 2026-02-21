# Kanbus Board

View your [Kanbus](https://github.com/AnthusAI/Kanbus) kanban board directly inside VSCode.

## Usage

Open a workspace that contains a `.kanbus.yml` file, then run:

**Command Palette** (`Cmd+Shift+P` / `Ctrl+Shift+P`) → **Kanbus: Open Board**

The board opens in a panel tab and updates in real time as you create or modify issues using the `kbs` CLI.

## Requirements

No separate installation needed. The `kbsc` server binary is bundled with the extension and starts automatically when you open the board.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `kanbus.port` | `0` | Port for the kbsc server. `0` = auto-select a free port. |

## About Kanbus

Kanbus is a local-first kanban board that stores issues as plain files in your git repository. Issues live alongside your code, travel with branches, and merge like any other text.

- [kanbus.app](https://kanbus.app)
- [GitHub](https://github.com/AnthusAI/Kanbus)
