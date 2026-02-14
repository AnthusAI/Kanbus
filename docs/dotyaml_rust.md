# Rust dotyaml-equivalent crate (design)

## Goals
- Mirror Python `dotyaml` semantics: dotenv preload, env interpolation, flatten to env vars with prefix, optional override of existing env.
- Zero fallback logic: one YAML path, explicit options for dotenv path and override.
- Pure Rust crate suitable for reuse by Taskulus and other projects; publish on crates.io.

## Proposed crate metadata
- Name: `dotyaml` (if available) or `taskulus-dotyaml` (fallback)
- Edition: 2021
- Dependencies: `serde_yaml`, `serde`, `serde_json` (for value handling), `dotenvy` (dotenv load), `thiserror`, `indexmap` (order preservation), `once_cell` (optional), `path-absolutize` (for resolved paths)
- License: MIT OR Apache-2.0
- Minimum supported Rust version: 1.72 (aligned with current repo)

## API sketch
```rust
/// Options controlling how YAML is loaded and exported to the environment.
pub struct DotYamlOptions {
    pub prefix: String,            // e.g., "TASKULUS_"; required, non-empty
    pub yaml_path: PathBuf,        // required; one file only
    pub dotenv_path: Option<PathBuf>, // default Some(Path::new(".env"))
    pub load_dotenv: bool,         // default true
    pub override_existing: bool,   // default false (never clobber existing env)
}

/// Load YAML and export environment variables.
pub fn load_and_export(options: &DotYamlOptions) -> Result<BTreeMap<String, String>, DotYamlError>;

/// Load YAML into a structured value without exporting env vars.
pub fn load(options: &DotYamlOptions) -> Result<serde_yaml::Value, DotYamlError>;
```

### Semantics
1. **Dotenv first (optional):** if `load_dotenv`, load dotenv file (default `.env`) but do not override already-set env vars.
2. **Parse YAML:** read `yaml_path` with UTF-8; errors are surfaced verbatim.
3. **Interpolation:** resolve `{{ VAR|default }}` using current env (after dotenv). If `VAR` missing and no default, treat as empty string.
4. **Flattening:** nested keys become uppercase with `_` separators; arrays become comma-separated values; booleans become `true`/`false`; null becomes empty string.
5. **Export:** set env vars only if not present OR if `override_existing` is true. Return the map of variables actually written.
6. **No fallbacks:** only `yaml_path` is read; no search paths.

### Error cases
- Missing YAML file → `DotYamlError::NotFound` with the path.
- YAML parse error → `DotYamlError::Parse` with message and location.
- Interpolation cycle or malformed template → `DotYamlError::Interpolation`.
- Invalid prefix (empty / non-ASCII) → `DotYamlError::InvalidPrefix`.

### Testing strategy
- Golden tests comparing exported env maps against Python dotyaml outputs for the same fixtures.
- Interpolation precedence: env > dotenv > defaults > YAML literal.
- Override flag behavior: with and without `override_existing`.
- Flattening edge cases: nested objects, arrays, booleans, nulls.
- No-fallback guarantee: ensure only the specified file is ever read.

### Integration notes for Taskulus (Rust)
- Taskulus will call `load_and_export` early in CLI startup with prefix `TASKULUS_` and `yaml_path` from `--config` (default `taskulus.yml`).
- Configuration loader will read from env (already set by dotyaml) and deserialize into `ProjectConfiguration` without additional fallbacks.
- Be explicit in errors: e.g., "taskulus.yml not found" or interpolation failures.

## Open decisions
- Final crate name depending on crates.io availability.
- Whether to expose a streaming iterator API for large YAML files (likely unnecessary for our size).
- Template syntax: we will mirror Python dotyaml minimal subset; no full Jinja.
