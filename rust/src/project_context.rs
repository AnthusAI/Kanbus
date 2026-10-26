//! One resolved project context per command.
//!
//! A [`ProjectContext`] is built once at command entry. It carries the root
//! the command runs from, the configuration file that governs it, the loaded
//! configuration, the primary project directory and the overlay settings, so
//! no code path below the entry point rediscovers the root or reloads the
//! configuration.

use std::borrow::Cow;
use std::path::{Path, PathBuf};

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{
    canonicalize_path, get_configuration_path, is_path_ignored, resolve_project_directories,
    ResolvedProject,
};
use crate::models::{OverlayConfig, ProjectConfiguration};

/// Message raised when no `.kanbus.yml` governs the working root.
pub const PROJECT_NOT_INITIALIZED_MESSAGE: &str = "project not initialized";

/// Everything a command needs to know about the project it runs against.
///
/// # Fields
/// * `root` - Working root the command was started from.
/// * `config_path` - The `.kanbus.yml` that governs `root`.
/// * `repository_root` - Directory containing `config_path`.
/// * `configuration` - The configuration loaded once from `config_path`.
/// * `project_dir` - Primary project directory declared by the configuration.
/// * `overlay` - Overlay settings from the configuration.
#[derive(Debug, Clone)]
pub struct ProjectContext {
    pub root: PathBuf,
    pub config_path: PathBuf,
    pub repository_root: PathBuf,
    pub configuration: ProjectConfiguration,
    pub project_dir: PathBuf,
    pub overlay: OverlayConfig,
}

/// Locate the configuration file that governs a root.
///
/// # Arguments
/// * `root` - Working root used for the upward search.
///
/// # Returns
/// `Ok(None)` only when no `.kanbus.yml` exists above `root`.
///
/// # Errors
/// Returns any lookup error other than a missing configuration file.
pub fn locate_configuration_path(root: &Path) -> Result<Option<PathBuf>, KanbusError> {
    match get_configuration_path(root) {
        Ok(path) => Ok(Some(path)),
        Err(KanbusError::IssueOperation(message)) if message == PROJECT_NOT_INITIALIZED_MESSAGE => {
            Ok(None)
        }
        Err(error) => Err(error),
    }
}

impl ProjectContext {
    /// Build a context for a root, returning `None` when no configuration exists.
    ///
    /// # Arguments
    /// * `root` - Working root used for the upward search.
    ///
    /// # Errors
    /// Returns the configuration error when the file exists but is invalid.
    pub fn discover(root: &Path) -> Result<Option<ProjectContext>, KanbusError> {
        match locate_configuration_path(root)? {
            Some(config_path) => Self::from_configuration_path(root, config_path).map(Some),
            None => Ok(None),
        }
    }

    /// Build a context for a root, failing when no configuration exists.
    ///
    /// # Arguments
    /// * `root` - Working root used for the upward search.
    ///
    /// # Errors
    /// Returns `project not initialized` when no configuration exists.
    pub fn require(root: &Path) -> Result<ProjectContext, KanbusError> {
        Self::discover(root)?
            .ok_or_else(|| KanbusError::IssueOperation(PROJECT_NOT_INITIALIZED_MESSAGE.to_string()))
    }

    /// Build a context from an already located configuration path.
    ///
    /// # Arguments
    /// * `root` - Working root the command runs from.
    /// * `config_path` - Path returned by [`locate_configuration_path`].
    ///
    /// # Errors
    /// Returns the configuration error when the file is invalid.
    pub fn from_configuration_path(
        root: &Path,
        config_path: PathBuf,
    ) -> Result<ProjectContext, KanbusError> {
        let configuration = load_project_configuration(&config_path)?;
        let repository_root = config_path
            .parent()
            .unwrap_or_else(|| Path::new(""))
            .to_path_buf();
        let declared_project_dir = repository_root.join(&configuration.project_directory);
        let project_dir = canonicalize_path(&declared_project_dir).unwrap_or(declared_project_dir);
        let overlay = configuration.overlay.clone();
        Ok(ProjectContext {
            root: root.to_path_buf(),
            config_path,
            repository_root,
            configuration,
            project_dir,
            overlay,
        })
    }

    /// Return the configuration when it lives directly in the working root.
    ///
    /// Commands scan for nested workspaces only when the root itself does not
    /// hold the configuration; this tells them which case applies.
    pub fn configuration_at_root(&self) -> Option<&ProjectConfiguration> {
        let same_directory = match (
            canonicalize_path(&self.repository_root),
            canonicalize_path(&self.root),
        ) {
            (Ok(repository), Ok(root)) => repository == root,
            _ => self.repository_root == self.root,
        };
        same_directory.then_some(&self.configuration)
    }

    /// Return the primary project directory for write operations.
    ///
    /// # Errors
    /// Returns `project not initialized` when the primary directory is ignored.
    pub fn primary_project_directory(&self) -> Result<PathBuf, KanbusError> {
        if is_path_ignored(
            &self
                .repository_root
                .join(&self.configuration.project_directory),
            &self.repository_root,
            &self.configuration.ignore_paths,
        ) {
            return Err(KanbusError::IssueOperation(
                PROJECT_NOT_INITIALIZED_MESSAGE.to_string(),
            ));
        }
        Ok(self.project_dir.clone())
    }

    /// Resolve every labeled project directory declared by the configuration.
    ///
    /// # Errors
    /// Returns `KanbusError::IssueOperation` when a virtual project path is missing.
    pub fn labeled_projects(&self) -> Result<Vec<ResolvedProject>, KanbusError> {
        resolve_project_directories(&self.repository_root, &self.configuration)
    }

    /// Return the configuration that governs a project directory.
    ///
    /// The context configuration is reused when the directory belongs to the
    /// same configuration file. A project owned by a different configuration
    /// file, such as a virtual project, is loaded from that file.
    ///
    /// # Arguments
    /// * `project_dir` - Project directory whose configuration is needed.
    ///
    /// # Errors
    /// Returns lookup or configuration errors for the owning file.
    pub fn configuration_for_project_directory(
        &self,
        project_dir: &Path,
    ) -> Result<Cow<'_, ProjectConfiguration>, KanbusError> {
        let owning_path = get_configuration_path(project_dir)?;
        let same_file = match (
            canonicalize_path(&owning_path),
            canonicalize_path(&self.config_path),
        ) {
            (Ok(owning), Ok(own)) => owning == own,
            _ => owning_path == self.config_path,
        };
        if same_file {
            return Ok(Cow::Borrowed(&self.configuration));
        }
        load_project_configuration(&owning_path).map(Cow::Owned)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write_configuration(root: &Path, contents: &str) {
        std::fs::write(root.join(".kanbus.yml"), contents).expect("write configuration");
    }

    #[test]
    fn discover_returns_none_without_configuration() {
        let temp = tempfile::tempdir().expect("tempdir");
        assert!(ProjectContext::discover(temp.path())
            .expect("discover")
            .is_none());
        let error = ProjectContext::require(temp.path()).expect_err("require fails");
        assert!(matches!(
            error,
            KanbusError::IssueOperation(message) if message == PROJECT_NOT_INITIALIZED_MESSAGE
        ));
    }

    #[test]
    fn discover_propagates_malformed_configuration() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_configuration(temp.path(), "project_key: [unclosed\n");
        let error = ProjectContext::discover(temp.path()).expect_err("malformed fails");
        assert!(matches!(
            error,
            KanbusError::Configuration(message) if message == "configuration is not valid YAML"
        ));
    }

    #[test]
    fn context_resolves_primary_directory_and_overlay_once() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_configuration(temp.path(), "project_key: kanbus\n");
        std::fs::create_dir_all(temp.path().join("project/issues")).expect("create project");

        crate::config_loader::reset_configuration_load_count();
        let context = ProjectContext::require(temp.path()).expect("context");
        let primary = context.primary_project_directory().expect("primary");
        let labeled = context.labeled_projects().expect("labeled");

        assert_eq!(crate::config_loader::configuration_load_count(), 1);
        assert_eq!(
            primary,
            temp.path()
                .join("project")
                .canonicalize()
                .expect("canonical")
        );
        assert_eq!(labeled.len(), 1);
        assert_eq!(labeled[0].label, "kanbus");
        assert_eq!(
            context.overlay.enabled,
            context.configuration.overlay.enabled
        );
        assert!(context.configuration_at_root().is_some());
    }

    #[test]
    fn nested_root_reports_no_configuration_at_root() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_configuration(temp.path(), "project_key: kanbus\n");
        let nested = temp.path().join("nested");
        std::fs::create_dir_all(&nested).expect("create nested");

        let context = ProjectContext::require(&nested).expect("context");

        assert!(context.configuration_at_root().is_none());
        assert_eq!(
            context.repository_root.canonicalize().expect("canonical"),
            temp.path().canonicalize().expect("canonical")
        );
    }

    #[test]
    fn configuration_for_owning_directory_reuses_loaded_configuration() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_configuration(temp.path(), "project_key: kanbus\n");
        std::fs::create_dir_all(temp.path().join("project")).expect("create project");
        let context = ProjectContext::require(temp.path()).expect("context");

        crate::config_loader::reset_configuration_load_count();
        let configuration = context
            .configuration_for_project_directory(&temp.path().join("project"))
            .expect("configuration");

        assert!(matches!(configuration, Cow::Borrowed(_)));
        assert_eq!(crate::config_loader::configuration_load_count(), 0);
    }

    #[test]
    fn configuration_for_foreign_directory_loads_its_own_file() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_configuration(temp.path(), "project_key: kanbus\n");
        let foreign = temp.path().join("foreign");
        std::fs::create_dir_all(foreign.join("project")).expect("create foreign");
        write_configuration(&foreign, "project_key: other\n");
        let context = ProjectContext::require(temp.path()).expect("context");

        let configuration = context
            .configuration_for_project_directory(&foreign.join("project"))
            .expect("configuration");

        assert!(matches!(configuration, Cow::Owned(_)));
        assert_eq!(configuration.project_key, "other");
    }

    #[test]
    fn ignored_primary_directory_is_not_initialized() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_configuration(
            temp.path(),
            "project_key: kanbus\nignore_paths:\n  - project\n",
        );
        std::fs::create_dir_all(temp.path().join("project")).expect("create project");
        let context = ProjectContext::require(temp.path()).expect("context");

        let error = context
            .primary_project_directory()
            .expect_err("ignored primary fails");

        assert!(matches!(
            error,
            KanbusError::IssueOperation(message) if message == PROJECT_NOT_INITIALIZED_MESSAGE
        ));
    }
}
