//! Issue identifier generation and short-ID display formatting.

use std::collections::{HashMap, HashSet};
use std::sync::{Mutex, OnceLock};
use uuid::Uuid;

use crate::error::KanbusError;

/// Default number of hash characters shown in short IDs.
pub const DEFAULT_SHORT_ID_LENGTH: usize = 4;

/// Upper bound on short ID length; full UUID hashes are 32 hex characters.
pub const MAX_SHORT_ID_LENGTH: usize = 32;

/// Request to generate a unique issue identifier.
#[derive(Debug, Clone)]
pub struct IssueIdentifierRequest {
    /// Issue title.
    pub title: String,
    /// Existing identifiers to avoid collisions.
    pub existing_ids: HashSet<String>,
    /// ID project key (prefix).
    pub prefix: String,
    /// Explicitly requested issue ID.
    pub requested_id: Option<String>,
}

/// Generated issue identifier.
#[derive(Debug, Clone)]
pub struct IssueIdentifierResult {
    /// Unique issue identifier.
    pub identifier: String,
}

static TEST_UUID_SEQUENCE: OnceLock<Mutex<Vec<Uuid>>> = OnceLock::new();

/// Set a deterministic UUID sequence for tests.
///
/// # Arguments
/// * `sequence` - Optional list of UUIDs to consume before falling back to random.
pub fn set_test_uuid_sequence(sequence: Option<Vec<Uuid>>) {
    let cell = TEST_UUID_SEQUENCE.get_or_init(|| Mutex::new(Vec::new()));
    let mut guard = cell.lock().expect("lock test uuid sequence");
    *guard = sequence.unwrap_or_default();
}

fn next_uuid() -> Uuid {
    let cell = TEST_UUID_SEQUENCE.get_or_init(|| Mutex::new(Vec::new()));
    let mut guard = cell.lock().expect("lock test uuid sequence");
    if let Some(next) = guard.first().cloned() {
        guard.remove(0);
        return next;
    }
    Uuid::new_v4()
}

/// Split an identifier into (project key, normalized hash base, dotted tail).
///
/// The project key is the segment before the first hyphen. The hash base has
/// hyphens removed (UUIDs contain hyphens) and the dotted tail removed.
fn split_identifier(identifier: &str) -> (Option<&str>, &str, Option<&str>) {
    if identifier.chars().all(|ch| ch.is_ascii_digit()) {
        return (None, identifier, None);
    }
    let (key, remainder) = match identifier.split_once('-') {
        Some((key, rest)) if !key.is_empty() && !rest.is_empty() => (Some(key), rest),
        _ => (None, identifier),
    };
    match remainder.split_once('.') {
        Some((base, tail)) if !base.is_empty() => (key, base, Some(tail)),
        _ => {
            let base = remainder.strip_suffix('.').unwrap_or(remainder);
            (key, base, None)
        }
    }
}

fn normalized_base(identifier: &str) -> String {
    let (key, base, _) = split_identifier(identifier);
    let _ = key;
    base.chars().filter(|ch| *ch != '-').collect()
}

fn longest_common_prefix_length(left: &str, right: &str) -> usize {
    left.chars()
        .zip(right.chars())
        .take_while(|(left_ch, right_ch)| left_ch == right_ch)
        .count()
}

fn clamp_short_id_length(length: usize) -> usize {
    length.clamp(1, MAX_SHORT_ID_LENGTH)
}

/// Display widths for short IDs, derived from a universe of full identifiers.
///
/// Widths make every identifier in the universe uniquely prefix-matchable at
/// the shortest length that is at least the configured default, so the same
/// identifier renders identically in every list built from the same universe.
#[derive(Debug, Clone, Default)]
pub struct ShortIdWidths {
    default_len: usize,
    widths: HashMap<String, usize>,
}

impl ShortIdWidths {
    /// Build widths from a universe of full identifiers.
    ///
    /// Uniqueness is checked per project key: an identifier is widened only
    /// while its prefix collides with another identifier sharing its key.
    ///
    /// # Arguments
    /// * `universe` - Full identifiers of all live issues in scope.
    /// * `default_len` - Default prefix length (from configuration).
    pub fn new<'a, I>(universe: I, default_len: usize) -> Self
    where
        I: IntoIterator<Item = &'a str>,
    {
        let default_len = clamp_short_id_length(default_len);
        let mut groups: HashMap<&str, Vec<(&str, String)>> = HashMap::new();
        for identifier in universe {
            let (key, _, _) = split_identifier(identifier);
            if identifier.chars().all(|ch| ch.is_ascii_digit()) {
                continue;
            }
            let group_key = key.unwrap_or("");
            let normalized = normalized_base(identifier);
            if normalized.is_empty() {
                continue;
            }
            groups
                .entry(group_key)
                .or_default()
                .push((identifier, normalized));
        }
        let mut widths = HashMap::new();
        for entries in groups.values_mut() {
            entries.sort_by(|left, right| left.1.cmp(&right.1));
            for (index, (identifier, normalized)) in entries.iter().enumerate() {
                let mut width = default_len;
                if let Some((_, previous)) = index
                    .checked_sub(1)
                    .and_then(|previous| entries.get(previous))
                {
                    width = width.max(longest_common_prefix_length(normalized, previous) + 1);
                }
                if let Some((_, next)) = entries.get(index + 1) {
                    width = width.max(longest_common_prefix_length(normalized, next) + 1);
                }
                let width = clamp_short_id_length(width).min(normalized.chars().count());
                widths.insert((*identifier).to_string(), width);
            }
        }
        Self {
            default_len,
            widths,
        }
    }

    /// Display width for one identifier; unknown identifiers use the default.
    pub fn width_for(&self, identifier: &str) -> usize {
        self.widths
            .get(identifier)
            .copied()
            .unwrap_or(self.default_len)
    }
}

/// Build widths for one identifier alone (no widening, default length).
pub fn single_id_widths(identifier: &str) -> ShortIdWidths {
    ShortIdWidths::new([identifier], DEFAULT_SHORT_ID_LENGTH)
}

/// Produce a display-friendly issue key.
///
/// # Arguments
/// * `identifier` - Full issue identifier (may include project key and UUID).
/// * `project_context` - When true, omit the project key.
///
/// # Returns
/// Formatted key with optional project key and abbreviated hash.
pub fn format_issue_key(identifier: &str, project_context: bool) -> String {
    let widths = single_id_widths(identifier);
    format_issue_key_with(identifier, project_context, &widths)
}

/// Produce a display-friendly issue key using universe-derived widths.
///
/// # Arguments
/// * `identifier` - Full issue identifier (may include project key and UUID).
/// * `project_context` - When true, omit the project key.
/// * `widths` - Widths derived from the project-wide identifier universe.
///
/// # Returns
/// Formatted key with optional project key and abbreviated hash.
pub fn format_issue_key_with(
    identifier: &str,
    project_context: bool,
    widths: &ShortIdWidths,
) -> String {
    if identifier.chars().all(|ch| ch.is_ascii_digit()) {
        return identifier.to_string();
    }

    let (key_part, remainder) = if let Some((key, rest)) = identifier.split_once('-') {
        if key.is_empty() || rest.is_empty() {
            (None, identifier)
        } else {
            (Some(key), rest)
        }
    } else {
        (None, identifier)
    };

    let (base, suffix) = if let Some((head, tail)) = remainder.split_once('.') {
        (head, Some(tail))
    } else {
        (remainder, None)
    };
    let _ = base;

    let normalized = normalized_base(identifier);
    let width = widths.width_for(identifier);
    let truncated: String = normalized.chars().take(width).collect();

    if project_context {
        return match suffix {
            Some(tail) => format!("{}.{}", truncated, tail.to_ascii_lowercase()),
            None => truncated,
        };
    }

    if let Some(key) = key_part {
        return match suffix {
            Some(tail) => format!(
                "{}-{}.{}",
                key.to_ascii_lowercase(),
                truncated,
                tail.to_ascii_lowercase()
            ),
            None => format!("{}-{}", key.to_ascii_lowercase(), truncated),
        };
    }

    match suffix {
        Some(tail) => format!("{}.{}", truncated, tail.to_ascii_lowercase()),
        None => truncated,
    }
}

/// Check if a candidate identifier matches a full issue identifier.
///
/// Accepts full identifiers, project-context short ids, and abbreviated
/// prefixes. Comparison is hyphen-insensitive (display strips UUID hyphens)
/// and dotted sub-ID suffixes must match exactly.
///
/// # Arguments
/// * `candidate` - User-provided identifier value.
/// * `full_id` - Full issue identifier from storage.
///
/// # Returns
/// True if the candidate matches the full identifier.
pub fn issue_identifier_matches(candidate: &str, full_id: &str) -> bool {
    if candidate == full_id {
        return true;
    }
    if candidate.is_empty() || full_id.is_empty() {
        return false;
    }

    // Numeric identifiers are not abbreviated; they only match exactly.
    if candidate.chars().all(|ch| ch.is_ascii_digit()) {
        return false;
    }

    let (candidate_key, candidate_base, candidate_tail) = split_identifier(candidate);
    let (full_key, full_base, full_tail) = split_identifier(full_id);

    if candidate_tail != full_tail && !(candidate_tail.is_none() && full_tail.is_none()) {
        return false;
    }

    if let Some(key) = candidate_key {
        if Some(key) != full_key {
            return false;
        }
    }

    let candidate_normalized: String = candidate_base.chars().filter(|ch| *ch != '-').collect();
    let full_normalized: String = full_base.chars().filter(|ch| *ch != '-').collect();

    // Hyphen-insensitive: a dash-less candidate may glue the project key to
    // the hash ("kanbusaaaabbbb" for "kanbus-aaaabbbb"); strip the glued key.
    let candidate_normalized = match candidate_key {
        None => match full_key {
            Some(full_key_value) => {
                let glued = full_key_value
                    .chars()
                    .filter(|ch| *ch != '-')
                    .collect::<String>();
                if !glued.is_empty() && candidate_normalized.starts_with(&glued) {
                    candidate_normalized[glued.len()..].to_string()
                } else {
                    candidate_normalized
                }
            }
            None => candidate_normalized,
        },
        Some(_) => candidate_normalized,
    };

    if candidate_normalized.is_empty() {
        return false;
    }

    full_normalized.starts_with(&candidate_normalized)
}

/// Generate a unique issue ID using a UUID.
///
/// # Arguments
///
/// * `request` - Validated request containing title and existing IDs.
///
/// # Returns
///
/// A unique ID string with format '{prefix}-{uuid}'.
///
/// # Errors
///
/// Returns `KanbusError::IdGenerationFailed` if unable to generate unique ID after 10 attempts.
pub fn generate_issue_identifier(
    request: &IssueIdentifierRequest,
) -> Result<IssueIdentifierResult, KanbusError> {
    if let Some(req_id) = &request.requested_id {
        if request.existing_ids.contains(req_id) {
            return Err(KanbusError::IssueOperation(format!(
                "requested id '{}' already exists",
                req_id
            )));
        }
        return Ok(IssueIdentifierResult {
            identifier: req_id.clone(),
        });
    }

    for _ in 0..10 {
        let identifier = format!("{}-{}", request.prefix, next_uuid());
        if !request.existing_ids.contains(&identifier) {
            return Ok(IssueIdentifierResult { identifier });
        }
    }

    Err(KanbusError::IdGenerationFailed(
        "unable to generate unique id after 10 attempts".to_string(),
    ))
}

/// Generate multiple identifiers for uniqueness checks.
///
/// # Arguments
///
/// * `title` - Base title for hashing.
/// * `prefix` - ID prefix.
/// * `count` - Number of IDs to generate.
///
/// # Returns
///
/// Set of generated identifiers.
///
/// # Errors
///
/// Returns `KanbusError` if ID generation fails.
pub fn generate_many_identifiers(
    title: &str,
    prefix: &str,
    count: usize,
) -> Result<HashSet<String>, KanbusError> {
    let mut existing = HashSet::new();
    for _ in 0..count {
        let request = IssueIdentifierRequest {
            title: title.to_string(),
            existing_ids: existing.clone(),
            prefix: prefix.to_string(),

            requested_id: None,
        };
        let result = generate_issue_identifier(&request)?;
        existing.insert(result.identifier);
    }
    Ok(existing)
}

/// Render a human-readable ambiguity error listing formatted candidates.
pub fn render_ambiguous_error(
    candidate: &str,
    matches: &[crate::error::AmbiguousCandidate],
) -> String {
    let ordered = sorted_matches(matches);
    let widths = ShortIdWidths::new(
        ordered.iter().map(|issue| issue.identifier.as_str()),
        DEFAULT_SHORT_ID_LENGTH,
    );
    let mut text = format!(
        "ambiguous identifier \"{candidate}\"; {} issues match:",
        ordered.len()
    );
    for issue in &ordered {
        let key = format_issue_key_with(&issue.identifier, false, &widths);
        text.push_str(&format!(
            "\n  {key}  [{}, {}]  {}",
            issue.issue_type, issue.status, issue.title
        ));
    }
    text.push_str("\nRe-run with one of the full IDs above.");
    text
}

fn sorted_matches(
    matches: &[crate::error::AmbiguousCandidate],
) -> Vec<crate::error::AmbiguousCandidate> {
    let mut ordered = matches.to_vec();
    ordered.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    ordered
}

/// Render the structured JSON ambiguity payload (full IDs included).
pub fn ambiguous_matches_json(
    candidate: &str,
    matches: &[crate::error::AmbiguousCandidate],
) -> String {
    let ordered = sorted_matches(matches);
    let widths = ShortIdWidths::new(
        ordered.iter().map(|issue| issue.identifier.as_str()),
        DEFAULT_SHORT_ID_LENGTH,
    );
    let payload = serde_json::json!({
        "error": "ambiguous_identifier",
        "candidate": candidate,
        "matches": ordered
            .iter()
            .map(|issue| {
                serde_json::json!({
                    "id": issue.identifier,
                    "key": format_issue_key_with(&issue.identifier, false, &widths),
                    "type": issue.issue_type,
                    "status": issue.status,
                    "title": issue.title,
                })
            })
            .collect::<Vec<_>>(),
    });
    serde_json::to_string_pretty(&payload).unwrap_or_default()
}

/// Print the interactive disambiguation menu and read a selection.
///
/// Returns the chosen full identifier, or None when the user cancels.
pub fn prompt_ambiguous_choice(
    candidate: &str,
    matches: &[crate::error::AmbiguousCandidate],
) -> Option<String> {
    use std::io::BufRead;
    let ordered = sorted_matches(matches);
    let widths = ShortIdWidths::new(
        ordered.iter().map(|issue| issue.identifier.as_str()),
        DEFAULT_SHORT_ID_LENGTH,
    );
    println!(
        "\"{candidate}\" is ambiguous; {} issues match:\n",
        ordered.len()
    );
    for (index, issue) in ordered.iter().enumerate() {
        let key = format_issue_key_with(&issue.identifier, false, &widths);
        println!(
            "  {}) {key}  [{}, {}]  {}",
            index + 1,
            issue.issue_type,
            issue.status,
            issue.title
        );
    }
    println!("\nSelect 1-{}, or press Enter to cancel:", matches.len());
    let stdin = std::io::stdin();
    let mut line = String::new();
    if stdin.lock().read_line(&mut line).is_err() {
        return None;
    }
    let choice: usize = line.trim().parse().ok()?;
    ordered
        .get(choice.checked_sub(1)?)
        .map(|issue| issue.identifier.clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_issue_key_defaults_to_four_characters() {
        assert_eq!(
            format_issue_key("kanbus-0123456789ab", false),
            "kanbus-0123"
        );
        assert_eq!(format_issue_key("kanbus-0123456789ab", true), "0123");
    }

    #[test]
    fn widths_widen_only_colliding_groups() {
        let universe = ["kanbus-aaaa1111", "kanbus-aaaa2222", "kanbus-bbbb3333"];
        let widths = ShortIdWidths::new(universe, DEFAULT_SHORT_ID_LENGTH);
        assert_eq!(widths.width_for("kanbus-aaaa1111"), 5);
        assert_eq!(widths.width_for("kanbus-aaaa2222"), 5);
        assert_eq!(widths.width_for("kanbus-bbbb3333"), 4);
    }

    #[test]
    fn widths_group_by_project_key() {
        let universe = ["alpha-aaaa1111", "beta-aaaa2222"];
        let widths = ShortIdWidths::new(universe, DEFAULT_SHORT_ID_LENGTH);
        assert_eq!(widths.width_for("alpha-aaaa1111"), 4);
        assert_eq!(widths.width_for("beta-aaaa2222"), 4);
    }

    #[test]
    fn widths_cover_local_and_shared_together() {
        let universe = ["kanbus-aaaa1111", "kanbus-aaaa2222"];
        let widths = ShortIdWidths::new(universe, DEFAULT_SHORT_ID_LENGTH);
        assert_eq!(
            format_issue_key_with("kanbus-aaaa1111", false, &widths),
            "kanbus-aaaa1"
        );
    }

    #[test]
    fn matcher_is_hyphen_insensitive() {
        let full = "kanbus-123e4567-e89b-12d3-a456-426614174000";
        assert!(issue_identifier_matches("kanbus-123e4567e89b", full));
        assert!(issue_identifier_matches("kanbus-123e4567-e89b", full));
        assert!(issue_identifier_matches("kanbus-123e", full));
        assert!(issue_identifier_matches(
            "kanbus-123e4567e89b12d3a456426614174000",
            full
        ));
        assert!(!issue_identifier_matches(
            "kanbus-123e4567e89b12d3a456426614174001",
            full
        ));
    }

    #[test]
    fn matcher_handles_dotted_sub_ids() {
        let full = "kanbus-abc1234567.2";
        assert!(issue_identifier_matches("kanbus-abc1234567.2", full));
        assert!(issue_identifier_matches("kanbus-abc.2", full));
        assert!(!issue_identifier_matches("kanbus-abc.3", full));
        assert!(!issue_identifier_matches("kanbus-abc", full));
    }

    #[test]
    fn matcher_keeps_legacy_six_char_references_resolving() {
        let full = "kanbus-0123456789ab";
        assert!(issue_identifier_matches("kanbus-012345", full));
        assert!(issue_identifier_matches("kanbus-0123", full));
    }

    #[test]
    fn matcher_rejects_empty_and_mismatched_keys() {
        assert!(!issue_identifier_matches("kanbus-", "kanbus-abcdef"));
        assert!(!issue_identifier_matches("alpha-abc", "kanbus-abcdef"));
        assert!(!issue_identifier_matches("", "kanbus-abcdef"));
    }

    #[test]
    fn matcher_supports_beads_style_ids() {
        assert!(issue_identifier_matches("tskl-abcdef", "tskl-abcdef2"));
        assert!(issue_identifier_matches(
            "custom-uuid00",
            "custom-uuid-0000001"
        ));
    }

    #[test]
    fn sub_id_display_preserves_suffix_with_widths() {
        let universe = ["kanbus-abc1234567.2", "kanbus-abc1299999.3"];
        let widths = ShortIdWidths::new(universe, DEFAULT_SHORT_ID_LENGTH);
        assert_eq!(
            format_issue_key_with("kanbus-abc1234567.2", false, &widths),
            "kanbus-abc123.2"
        );
        assert_eq!(
            format_issue_key_with("kanbus-abc1299999.3", false, &widths),
            "kanbus-abc129.3"
        );
    }

    /// Deterministic pseudo-random property check: formatted keys stay unique
    /// project-wide and never exceed the default unless a collision forces it.
    #[test]
    fn property_formatted_keys_are_unique_and_minimal() {
        let mut state: u64 = 0x9E3779B97F4A7C15;
        let mut next = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            state
        };
        for _case in 0..32 {
            let count = (next() % 200) as usize + 1;
            let universe: Vec<String> = (0..count)
                .map(|_| format!("kanbus-{:032x}", next()))
                .collect();
            let widths = ShortIdWidths::new(universe.iter().map(|s| s.as_str()), 4);
            let mut seen: HashSet<String> = HashSet::new();
            for identifier in &universe {
                let key = format_issue_key_with(identifier, false, &widths);
                assert!(seen.insert(key.clone()), "duplicate key {key}");
            }
        }
    }

    #[test]
    fn property_widths_are_minimal_against_brute_force() {
        let mut state: u64 = 0xDEADBEEF;
        let mut next = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            state
        };
        for _case in 0..16 {
            let count = (next() % 60) as usize + 2;
            let universe: Vec<String> = (0..count)
                .map(|_| format!("kanbus-{:032x}", next()))
                .collect();
            let widths = ShortIdWidths::new(universe.iter().map(|s| s.as_str()), 4);
            for identifier in &universe {
                let base = normalized_base(identifier);
                let width = widths.width_for(identifier);
                // Unique at its width within the same project key.
                let prefix: String = base.chars().take(width).collect();
                let conflicts = universe
                    .iter()
                    .filter(|other| {
                        other != &identifier
                            && normalized_base(other)
                                .chars()
                                .take(width)
                                .collect::<String>()
                                == prefix
                    })
                    .count();
                assert_eq!(conflicts, 0, "width {width} for {identifier} collides");
                // Not unique one character shorter (unless at the default).
                if width > 4 {
                    let shorter: String = base.chars().take(width - 1).collect();
                    let conflicts = universe
                        .iter()
                        .filter(|other| {
                            other != &identifier
                                && normalized_base(other)
                                    .chars()
                                    .take(width - 1)
                                    .collect::<String>()
                                    == shorter
                        })
                        .count();
                    assert!(conflicts > 0, "width {width} for {identifier} not minimal");
                }
            }
        }
    }
}
