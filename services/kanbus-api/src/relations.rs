//! Relations control records and the attach, detach and delete protocols that keep
//! parent and dependency references consistent under concurrent writers.
//!
//! Each issue that is, or was, the target of a parent or dependency reference has one
//! control object, `relations/<issue id>.json`, listing the issues that reference it.
//! Every read-modify-write of that object is conditional on its revision. The record is
//! control state: the canonical issue JSON is unchanged.

use super::*;

const RELATION_ATTEMPTS: usize = 16;
const LISTED_BLOCKING_IDENTIFIERS: usize = 10;
const RELATIONS_PREFIX: &str = "relations/";

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(crate) enum RelationKind {
    Child,
    Dependent,
}

/// Relation changes implied by moving an issue from its previous state to a new state.
#[derive(Debug, Default, PartialEq, Eq)]
pub(crate) struct RelationPlan {
    parent_added: Option<String>,
    parent_removed: Option<String>,
    dependency_targets_added: Vec<String>,
    dependency_targets_removed: Vec<String>,
}

impl RelationPlan {
    pub(crate) fn between(before: Option<&IssueData>, after: &IssueData) -> Self {
        let previous_parent = before.and_then(|issue| issue.parent.clone());
        let previous_targets: Vec<String> = before
            .map(|issue| unique_targets(issue))
            .unwrap_or_default();
        let next_targets = unique_targets(after);
        let parent_changed = previous_parent != after.parent;
        Self {
            parent_added: if parent_changed {
                after.parent.clone()
            } else {
                None
            },
            parent_removed: if parent_changed {
                previous_parent
            } else {
                None
            },
            dependency_targets_added: next_targets
                .iter()
                .filter(|target| !previous_targets.contains(target))
                .cloned()
                .collect(),
            dependency_targets_removed: previous_targets
                .iter()
                .filter(|target| !next_targets.contains(target))
                .cloned()
                .collect(),
        }
    }
}

fn unique_targets(issue: &IssueData) -> Vec<String> {
    let mut targets: Vec<String> = Vec::new();
    for link in &issue.dependencies {
        if !targets.contains(&link.target) {
            targets.push(link.target.clone());
        }
    }
    targets
}

#[derive(Serialize, Deserialize, Default, Clone, PartialEq, Eq, Debug)]
#[serde(deny_unknown_fields)]
pub(crate) struct RelationsRecord {
    #[serde(default)]
    children: Vec<String>,
    #[serde(default)]
    dependents: Vec<String>,
    #[serde(default)]
    deleted: bool,
}

impl RelationsRecord {
    fn members_mut(&mut self, kind: RelationKind) -> &mut Vec<String> {
        match kind {
            RelationKind::Child => &mut self.children,
            RelationKind::Dependent => &mut self.dependents,
        }
    }

    fn insert(&mut self, kind: RelationKind, source: &str) -> bool {
        let members = self.members_mut(kind);
        if members.iter().any(|member| member == source) {
            return false;
        }
        members.push(source.to_string());
        true
    }

    fn remove(&mut self, kind: RelationKind, source: &str) -> bool {
        let members = self.members_mut(kind);
        let before = members.len();
        members.retain(|member| member != source);
        members.len() != before
    }
}

fn relations_path(identifier: &str) -> String {
    format!("{RELATIONS_PREFIX}{identifier}.json")
}

fn relation_target_missing() -> ApiError {
    ApiError::new(
        409,
        "relation_target_missing",
        "The parent or dependency target does not exist or is being deleted.",
    )
}

fn hierarchy_violation(message: String) -> ApiError {
    ApiError::new(409, "hierarchy_violation", message)
}

fn blocking_identifiers_error(code: &'static str, noun: &str, identifiers: &[String]) -> ApiError {
    let listed: Vec<&str> = identifiers
        .iter()
        .take(LISTED_BLOCKING_IDENTIFIERS)
        .map(String::as_str)
        .collect();
    let more = identifiers
        .len()
        .saturating_sub(LISTED_BLOCKING_IDENTIFIERS);
    let suffix = if more > 0 {
        format!(" and {more} more")
    } else {
        String::new()
    };
    ApiError::new(
        409,
        code,
        format!(
            "This issue still has live {noun}: {}{suffix}. Remove or move them first.",
            listed.join(", ")
        ),
    )
}

impl ScopedApi {
    async fn load_relations(
        &self,
        identifier: &str,
    ) -> Result<Option<(RelationsRecord, String)>, ApiError> {
        let Some(object) = self
            .object_store
            .get_control(&self.scope, &relations_path(identifier))
            .await
            .map_err(storage_error)?
        else {
            return Ok(None);
        };
        let record = serde_json::from_slice(&object.bytes).map_err(|_| {
            ApiError::new(
                503,
                "invalid_relations",
                "Relations record is not valid JSON.",
            )
        })?;
        Ok(Some((record, object.revision)))
    }

    async fn store_relations(
        &self,
        identifier: &str,
        record: &RelationsRecord,
        condition: WriteCondition,
    ) -> Result<(), StoreError> {
        self.object_store
            .put_control(
                &self.scope,
                &relations_path(identifier),
                &json_bytes(record),
                condition,
            )
            .await
            .map(|_| ())
    }

    async fn seed_relations_from_canonical_issues(
        &self,
        configuration: &ProjectConfiguration,
        identifier: &str,
    ) -> Result<RelationsRecord, ApiError> {
        let mut record = RelationsRecord::default();
        for (_, object) in self
            .objects(
                &format!("{}/issues/", configuration.project_directory),
                &mut ReadBudget::default(),
            )
            .await?
        {
            let other: IssueData = serde_json::from_slice(&object.bytes)
                .map_err(|error| invalid(error.to_string()))?;
            if other.parent.as_deref() == Some(identifier) {
                record.insert(RelationKind::Child, &other.identifier);
            }
            if other
                .dependencies
                .iter()
                .any(|link| link.target == identifier)
            {
                record.insert(RelationKind::Dependent, &other.identifier);
            }
        }
        Ok(record)
    }

    async fn relations_for_update(
        &self,
        configuration: &ProjectConfiguration,
        identifier: &str,
    ) -> Result<(RelationsRecord, WriteCondition), ApiError> {
        match self.load_relations(identifier).await? {
            Some((record, revision)) => Ok((record, WriteCondition::Revision(revision))),
            None => Ok((
                self.seed_relations_from_canonical_issues(configuration, identifier)
                    .await?,
                WriteCondition::Absent,
            )),
        }
    }

    async fn relation_target(
        &self,
        configuration: &ProjectConfiguration,
        target: &str,
    ) -> Result<IssueData, ApiError> {
        let stored = match self.issue(configuration, target).await {
            Ok(stored) => stored,
            Err(error) if error.status == 404 => return Err(relation_target_missing()),
            Err(error) => return Err(error),
        };
        serde_json::from_slice(&stored.bytes).map_err(|error| invalid(error.to_string()))
    }

    pub(crate) async fn attach_planned_relations(
        &self,
        configuration: &ProjectConfiguration,
        issue: &IssueData,
        plan: &RelationPlan,
    ) -> Result<(), ApiError> {
        if let Some(parent) = &plan.parent_added {
            self.attach_relation(
                configuration,
                parent,
                &issue.identifier,
                RelationKind::Child,
                &issue.issue_type,
            )
            .await?;
        }
        for target in &plan.dependency_targets_added {
            self.attach_relation(
                configuration,
                target,
                &issue.identifier,
                RelationKind::Dependent,
                &issue.issue_type,
            )
            .await?;
        }
        Ok(())
    }

    async fn attach_relation(
        &self,
        configuration: &ProjectConfiguration,
        target: &str,
        source: &str,
        kind: RelationKind,
        source_type: &str,
    ) -> Result<(), ApiError> {
        for _ in 0..RELATION_ATTEMPTS {
            let target_issue = self.relation_target(configuration, target).await?;
            if kind == RelationKind::Child {
                validate_parent_child_relationship(
                    configuration,
                    &target_issue.issue_type,
                    source_type,
                )
                .map_err(|error| hierarchy_violation(error.to_string()))?;
            }
            let (mut record, condition) = self.relations_for_update(configuration, target).await?;
            if record.deleted {
                return Err(relation_target_missing());
            }
            if !record.insert(kind, source) {
                return Ok(());
            }
            match self.store_relations(target, &record, condition).await {
                Ok(()) => {
                    return self
                        .confirm_target_survives(configuration, target, source, kind)
                        .await
                }
                Err(StoreError::Conflict) => continue,
                Err(error) => return Err(storage_error(error)),
            }
        }
        Err(storage_error(StoreError::Conflict))
    }

    async fn confirm_target_survives(
        &self,
        configuration: &ProjectConfiguration,
        target: &str,
        source: &str,
        kind: RelationKind,
    ) -> Result<(), ApiError> {
        match self.relation_target(configuration, target).await {
            Ok(_) => Ok(()),
            Err(error) => {
                self.detach_relation(target, source, kind).await;
                Err(error)
            }
        }
    }

    pub(crate) async fn detach_planned_relations(&self, source: &str, plan: &RelationPlan) {
        if let Some(parent) = &plan.parent_removed {
            self.detach_relation(parent, source, RelationKind::Child)
                .await;
        }
        for target in &plan.dependency_targets_removed {
            self.detach_relation(target, source, RelationKind::Dependent)
                .await;
        }
    }

    async fn detach_relation(&self, target: &str, source: &str, kind: RelationKind) {
        for _ in 0..RELATION_ATTEMPTS {
            let Ok(Some((mut record, revision))) = self.load_relations(target).await else {
                return;
            };
            if !record.remove(kind, source) {
                return;
            }
            match self
                .store_relations(target, &record, WriteCondition::Revision(revision))
                .await
            {
                Err(StoreError::Conflict) => continue,
                _ => return,
            }
        }
    }

    pub(crate) async fn mark_relations_deleted(
        &self,
        configuration: &ProjectConfiguration,
        identifier: &str,
    ) -> Result<(), ApiError> {
        for _ in 0..RELATION_ATTEMPTS {
            let (mut record, condition) =
                self.relations_for_update(configuration, identifier).await?;
            if record.deleted {
                return Ok(());
            }
            record.deleted = true;
            match self.store_relations(identifier, &record, condition).await {
                Ok(()) => return Ok(()),
                Err(StoreError::Conflict) => continue,
                Err(error) => return Err(storage_error(error)),
            }
        }
        Err(storage_error(StoreError::Conflict))
    }

    pub(crate) async fn clear_relations_deleted(&self, identifier: &str) {
        for _ in 0..RELATION_ATTEMPTS {
            let Ok(Some((mut record, revision))) = self.load_relations(identifier).await else {
                return;
            };
            if !record.deleted {
                return;
            }
            record.deleted = false;
            match self
                .store_relations(identifier, &record, WriteCondition::Revision(revision))
                .await
            {
                Err(StoreError::Conflict) => continue,
                _ => return,
            }
        }
    }

    pub(crate) async fn ensure_no_live_references(
        &self,
        configuration: &ProjectConfiguration,
        identifier: &str,
    ) -> Result<(), ApiError> {
        let Some((mut record, revision)) = self.load_relations(identifier).await? else {
            return Ok(());
        };
        let mut live_children = Vec::new();
        for child in &record.children {
            if let Some(issue) = self.live_issue(configuration, child).await? {
                if issue.parent.as_deref() == Some(identifier) {
                    live_children.push(child.clone());
                }
            }
        }
        let mut live_dependents = Vec::new();
        for dependent in &record.dependents {
            if let Some(issue) = self.live_issue(configuration, dependent).await? {
                if issue
                    .dependencies
                    .iter()
                    .any(|link| link.target == identifier)
                {
                    live_dependents.push(dependent.clone());
                }
            }
        }
        if !live_children.is_empty() {
            return Err(blocking_identifiers_error(
                "issue_has_children",
                "children",
                &live_children,
            ));
        }
        if !live_dependents.is_empty() {
            return Err(blocking_identifiers_error(
                "issue_has_dependents",
                "dependents",
                &live_dependents,
            ));
        }
        if !record.children.is_empty() || !record.dependents.is_empty() {
            record.children.clear();
            record.dependents.clear();
            let _ = self
                .store_relations(identifier, &record, WriteCondition::Revision(revision))
                .await;
        }
        Ok(())
    }

    async fn live_issue(
        &self,
        configuration: &ProjectConfiguration,
        identifier: &str,
    ) -> Result<Option<IssueData>, ApiError> {
        match self.issue(configuration, identifier).await {
            Ok(stored) => serde_json::from_slice(&stored.bytes)
                .map(Some)
                .map_err(|error| invalid(error.to_string())),
            Err(error) if error.status == 404 => Ok(None),
            Err(error) => Err(error),
        }
    }

    pub(crate) async fn remove_relations_record(&self, identifier: &str) {
        if let Ok(Some((_, revision))) = self.load_relations(identifier).await {
            let _ = self
                .object_store
                .delete_control(&self.scope, &relations_path(identifier), &revision)
                .await;
        }
    }
}
