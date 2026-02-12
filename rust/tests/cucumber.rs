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

use step_definitions::initialization_steps::TaskulusWorld;

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

#[tokio::main]
async fn main() {
    let features_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("features")
        .canonicalize()
        .expect("features directory");
    TaskulusWorld::cucumber::<PathBuf>()
        .with_parser(RecursiveFeatureParser::default())
        .max_concurrent_scenarios(1)
        .filter_run(features_dir, |feature, _, scenario| {
            let scenario_has_wip = scenario.tags.iter().any(|tag| tag == "wip");
            let feature_has_wip = feature.tags.iter().any(|tag| tag == "wip");
            !(scenario_has_wip || feature_has_wip)
        })
        .await;
}
