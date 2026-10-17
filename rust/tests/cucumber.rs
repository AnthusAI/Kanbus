use std::fs;
use std::path::{Path, PathBuf};

use cucumber::cli::Empty;
use cucumber::feature::Ext as _;
use cucumber::gherkin::{self, GherkinEnv};
use cucumber::parser::{Parser, Result as ParserResult};
use cucumber::World;
use futures::stream;

#[path = "../features/steps/mod.rs"]
mod step_definitions;

use step_definitions::initialization_steps::KanbusWorld;

fn env_flag(name: &str) -> bool {
    std::env::var(name)
        .ok()
        .map(|value| {
            let normalized = value.trim().to_ascii_lowercase();
            matches!(normalized.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(false)
}

#[derive(Clone, Debug, Default)]
struct RecursiveFeatureParser;

impl RecursiveFeatureParser {
    fn collect_features(root: &Path) -> Result<Vec<PathBuf>, gherkin::ParseFileError> {
        let mut feature_files = Vec::new();
        Self::collect_feature_files(root, &mut feature_files).map_err(|error| {
            gherkin::ParseFileError::Reading {
                path: root.to_path_buf(),
                source: error,
            }
        })?;
        feature_files.sort();
        Ok(feature_files)
    }

    fn collect_feature_files(root: &Path, feature_files: &mut Vec<PathBuf>) -> std::io::Result<()> {
        for entry in fs::read_dir(root)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_dir() {
                Self::collect_feature_files(&path, feature_files)?;
            } else if path.extension().and_then(|ext| ext.to_str()) == Some("feature") {
                feature_files.push(path);
            }
        }
        Ok(())
    }
}

impl<I: AsRef<Path>> Parser<I> for RecursiveFeatureParser {
    type Cli = Empty;
    type Output = stream::Iter<std::vec::IntoIter<ParserResult<gherkin::Feature>>>;

    fn parse(self, input: I, _: Self::Cli) -> Self::Output {
        let path = input.as_ref();
        let features: Vec<ParserResult<gherkin::Feature>> = if path.is_file() {
            vec![gherkin::Feature::parse_path(path, GherkinEnv::default()).map_err(Into::into)]
        } else {
            match Self::collect_features(path) {
                Ok(feature_paths) => feature_paths
                    .into_iter()
                    .map(|feature_path| {
                        gherkin::Feature::parse_path(feature_path, GherkinEnv::default())
                            .map_err(Into::into)
                    })
                    .collect(),
                Err(error) => vec![Err(error.into())],
            }
        };

        let expanded: Vec<ParserResult<gherkin::Feature>> = features
            .into_iter()
            .map(|feature| {
                feature.and_then(|feature| feature.expand_examples().map_err(Into::into))
            })
            .collect();
        stream::iter(expanded)
    }
}

/// Environment variable prefixes stripped from the process environment
/// before the cucumber suite runs, so scenarios never observe values left
/// over from the developer's real machine (e.g. a real `~/.kanbus.env` with
/// `KANBUS_REALTIME_BROKER` pointing at a live Mosquitto broker). Kept
/// separate from `ISOLATED_ENV_EXACT_KEYS` because these match by prefix.
const ISOLATED_ENV_PREFIXES: [&str; 3] = ["KANBUS_REALTIME_", "KANBUS_COORDINATION_", "LITELLM_"];

/// Exact environment variable names stripped alongside `ISOLATED_ENV_PREFIXES`.
const ISOLATED_ENV_EXACT_KEYS: [&str; 1] = ["OPENAI_API_KEY"];

/// Redirect `HOME` to a fresh temporary directory for the whole cucumber run
/// and strip any already-set realtime/coordination/AI credential env vars,
/// so the suite's behavior does not depend on the machine it runs on (a real
/// `~/.kanbus.env`, a real broker on the loopback interface, a real
/// `OPENAI_API_KEY` in the shell, etc). Harness-set vars such as
/// `KANBUS_NO_DAEMON` are untouched since they don't match the stripped
/// prefixes/keys. The returned `TempDir` must be kept alive for the whole
/// process run; `HOME` becomes invalid once it drops.
fn isolate_process_environment_for_cucumber_suite() -> tempfile::TempDir {
    let isolated_home = tempfile::tempdir().expect("create isolated HOME for cucumber suite");
    std::env::set_var("HOME", isolated_home.path());

    let keys_to_remove: Vec<String> = std::env::vars()
        .map(|(key, _)| key)
        .filter(|key| {
            ISOLATED_ENV_EXACT_KEYS.contains(&key.as_str())
                || ISOLATED_ENV_PREFIXES
                    .iter()
                    .any(|prefix| key.starts_with(prefix))
        })
        .collect();
    for key in &keys_to_remove {
        std::env::remove_var(key);
    }

    eprintln!(
        "cucumber: isolated HOME to {} and stripped process env vars: [{}]",
        isolated_home.path().display(),
        keys_to_remove.join(", ")
    );

    isolated_home
}

#[tokio::main]
async fn main() {
    // Keep the guard alive for the whole run: dropping it would remove the
    // temp dir HOME points at.
    let _isolated_home_guard = isolate_process_environment_for_cucumber_suite();

    let features_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("features");
    if !features_dir.exists() {
        panic!("features directory missing at {}", features_dir.display());
    }
    let include_console = env_flag("KANBUS_CUCUMBER_INCLUDE_CONSOLE");
    let only_console = env_flag("KANBUS_CUCUMBER_ONLY_CONSOLE");
    let feature_filters = std::env::var("KANBUS_CUCUMBER_FEATURE_FILTER")
        .ok()
        .map(|value| {
            value
                .split(',')
                .map(|filter| filter.trim().to_ascii_lowercase())
                .filter(|filter| !filter.is_empty())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    KanbusWorld::cucumber::<PathBuf>()
        .with_parser(RecursiveFeatureParser)
        .max_concurrent_scenarios(1)
        .filter_run_and_exit(features_dir, move |feature, _, scenario| {
            if !feature_filters.is_empty()
                && !feature_filters
                    .iter()
                    .any(|filter| feature.name.to_ascii_lowercase().contains(filter))
            {
                return false;
            }
            let scenario_has_wip = scenario.tags.iter().any(|tag| tag == "wip");
            let feature_has_wip = feature.tags.iter().any(|tag| tag == "wip");
            let scenario_has_console = scenario.tags.iter().any(|tag| tag == "console");
            let feature_has_console = feature.tags.iter().any(|tag| tag == "console");
            let scenario_has_slow = scenario.tags.iter().any(|tag| tag == "slow");
            let feature_has_slow = feature.tags.iter().any(|tag| tag == "slow");
            let scenario_has_cloud = scenario.tags.iter().any(|tag| tag == "cloud");
            let feature_has_cloud = feature.tags.iter().any(|tag| tag == "cloud");
            let scenario_has_python_parity = scenario.tags.iter().any(|tag| tag == "python-parity");
            let feature_has_python_parity = feature.tags.iter().any(|tag| tag == "python-parity");
            if scenario_has_wip || feature_has_wip {
                return false;
            }
            if scenario_has_python_parity || feature_has_python_parity {
                return false;
            }
            if scenario_has_slow || feature_has_slow {
                return false;
            }
            if scenario_has_cloud || feature_has_cloud {
                return false;
            }
            let has_console = scenario_has_console || feature_has_console;
            if only_console {
                return has_console;
            }
            if !include_console && has_console {
                return false;
            }
            true
        })
        .await;
}
