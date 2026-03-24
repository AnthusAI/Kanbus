//! File edit operations mirroring the Anthropic text editor tool.
//!
//! Provides view, str_replace, create, and insert commands with strict single-match
//! replacement semantics for agent compatibility.

use std::path::Path;

use crate::error::KanbusError;

/// View file contents or directory listing.
///
/// # Arguments
///
/// * `root` - Repository root (current working directory for relative paths)
/// * `path` - File or directory path (relative to root)
/// * `view_range` - Optional (start, end) line numbers (1-indexed; -1 for end)
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` if path does not exist or escapes root.
pub fn edit_view(
    root: &Path,
    path: &Path,
    view_range: Option<(i32, i32)>,
) -> Result<String, KanbusError> {
    let resolved = root
        .join(path)
        .canonicalize()
        .map_err(|e| KanbusError::IssueOperation(format!("file or directory not found: {}", e)))?;
    let root_canonical = root
        .canonicalize()
        .map_err(|e| KanbusError::Io(e.to_string()))?;
    if !resolved.starts_with(&root_canonical) {
        return Err(KanbusError::IssueOperation(
            "path escapes repository root".to_string(),
        ));
    }
    if resolved.is_dir() {
        let mut entries: Vec<_> = std::fs::read_dir(&resolved)
            .map_err(|e| KanbusError::Io(e.to_string()))?
            .filter_map(|e| e.ok())
            .collect();
        entries.sort_by(|a, b| {
            let a_dir = a.path().is_dir();
            let b_dir = b.path().is_dir();
            (a_dir, a.file_name()).cmp(&(b_dir, b.file_name()))
        });
        let names: Vec<String> = entries
            .iter()
            .map(|e| {
                let name = e.file_name().to_string_lossy().into_owned();
                if e.path().is_dir() {
                    format!("{}/", name)
                } else {
                    name
                }
            })
            .collect();
        return Ok(names.join("\n"));
    }
    let content = std::fs::read_to_string(&resolved).map_err(|e| KanbusError::Io(e.to_string()))?;
    let lines: Vec<&str> = content.lines().collect();
    let (sliced, line_start) = if let Some((start_one, end_one)) = view_range {
        let start_idx = if start_one >= 1 {
            ((start_one - 1) as usize).min(lines.len())
        } else {
            0
        };
        let end_idx = if end_one == -1 {
            lines.len()
        } else {
            (end_one as usize).min(lines.len())
        };
        let sliced: Vec<&str> = lines[start_idx..end_idx].to_vec();
        let line_start = start_idx + 1;
        (sliced, line_start)
    } else {
        (lines, 1)
    };
    let output: Vec<String> = sliced
        .iter()
        .enumerate()
        .map(|(i, line)| format!("{}: {}", line_start + i, line))
        .collect();
    Ok(output.join("\n"))
}

/// Replace exactly one occurrence of old_str with new_str.
///
/// # Arguments
///
/// * `root` - Repository root
/// * `path` - File path (relative to root)
/// * `old_str` - Exact text to replace
/// * `new_str` - Replacement text
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` if file not found, 0 matches, or multiple matches.
pub fn edit_str_replace(
    root: &Path,
    path: &Path,
    old_str: &str,
    new_str: &str,
) -> Result<String, KanbusError> {
    let resolved = root.join(path);
    if !resolved.exists() || !resolved.is_file() {
        return Err(KanbusError::IssueOperation("file not found".to_string()));
    }
    let root_canonical = root.canonicalize().ok();
    let resolved_canonical = resolved.canonicalize().ok();
    if let (Some(ref rc), Some(ref rp)) = (root_canonical, resolved_canonical) {
        if !rp.starts_with(rc) {
            return Err(KanbusError::IssueOperation(
                "path escapes repository root".to_string(),
            ));
        }
    }
    let content = std::fs::read_to_string(&resolved).map_err(|e| KanbusError::Io(e.to_string()))?;
    let count = content.matches(old_str).count();
    if count == 0 {
        return Err(KanbusError::IssueOperation(
            "no match found for replacement".to_string(),
        ));
    }
    if count > 1 {
        return Err(KanbusError::IssueOperation(format!(
            "found {} matches for replacement text; provide more context for a unique match",
            count
        )));
    }
    let new_content = content.replacen(old_str, new_str, 1);
    std::fs::write(&resolved, new_content).map_err(|e| KanbusError::Io(e.to_string()))?;
    Ok("Successfully replaced text at exactly one location.".to_string())
}

/// Create a new file with the given content.
///
/// # Arguments
///
/// * `root` - Repository root
/// * `path` - File path (relative to root)
/// * `file_text` - Content to write
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` if file already exists or path escapes root.
pub fn edit_create(root: &Path, path: &Path, file_text: &str) -> Result<String, KanbusError> {
    let resolved = root.join(path);
    if resolved.exists() {
        return Err(KanbusError::IssueOperation(
            "file already exists".to_string(),
        ));
    }
    let parent = resolved
        .parent()
        .ok_or_else(|| KanbusError::IssueOperation("invalid path".to_string()))?;
    std::fs::create_dir_all(parent).map_err(|e| KanbusError::Io(e.to_string()))?;
    if let (Ok(rc), Ok(rp)) = (root.canonicalize(), resolved.canonicalize()) {
        if !rp.starts_with(&rc) {
            return Err(KanbusError::IssueOperation(
                "path escapes repository root".to_string(),
            ));
        }
    }
    std::fs::write(&resolved, file_text).map_err(|e| KanbusError::Io(e.to_string()))?;
    Ok("Successfully created file.".to_string())
}

/// Insert text after the given line number.
///
/// insert_line 0 means insert at the beginning. Line numbers are 1-indexed for display.
///
/// # Arguments
///
/// * `root` - Repository root
/// * `path` - File path (relative to root)
/// * `insert_line` - Line number after which to insert (0 = beginning)
/// * `insert_text` - Text to insert
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` if file not found or insert_line is invalid.
pub fn edit_insert(
    root: &Path,
    path: &Path,
    insert_line: i32,
    insert_text: &str,
) -> Result<String, KanbusError> {
    if insert_line < 0 {
        return Err(KanbusError::IssueOperation(
            "insert_line must be non-negative".to_string(),
        ));
    }
    let resolved = root.join(path);
    if !resolved.exists() || !resolved.is_file() {
        return Err(KanbusError::IssueOperation("file not found".to_string()));
    }
    let root_canonical = root.canonicalize().ok();
    let resolved_canonical = resolved.canonicalize().ok();
    if let (Some(ref rc), Some(ref rp)) = (root_canonical, resolved_canonical) {
        if !rp.starts_with(rc) {
            return Err(KanbusError::IssueOperation(
                "path escapes repository root".to_string(),
            ));
        }
    }
    let content = std::fs::read_to_string(&resolved).map_err(|e| KanbusError::Io(e.to_string()))?;
    let lines: Vec<&str> = content.lines().collect();
    let idx = insert_line as usize;
    if idx > lines.len() {
        return Err(KanbusError::IssueOperation(
            "insert_line exceeds file length".to_string(),
        ));
    }
    let insert_lines: Vec<&str> = insert_text.lines().collect();
    let mut new_lines: Vec<String> = lines[..idx].iter().map(|s| (*s).to_string()).collect();
    new_lines.extend(insert_lines.iter().map(|s| (*s).to_string()));
    new_lines.extend(lines[idx..].iter().map(|s| (*s).to_string()));
    let output = new_lines.join("\n");
    let trailing = if content.ends_with('\n') || new_lines.is_empty() {
        "\n"
    } else {
        ""
    };
    std::fs::write(&resolved, format!("{}{}", output, trailing))
        .map_err(|e| KanbusError::Io(e.to_string()))?;
    Ok("Successfully inserted text.".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn edit_view_lists_directory_and_supports_line_ranges() {
        let tmp = tempfile::tempdir().expect("tempdir");
        fs::write(tmp.path().join("a.txt"), "alpha").expect("write file");
        fs::create_dir_all(tmp.path().join("sub")).expect("create dir");
        fs::write(tmp.path().join("sample.txt"), "one\ntwo\nthree\n").expect("write sample");

        let listing = edit_view(tmp.path(), Path::new("."), None).expect("view dir");
        assert!(listing.contains("a.txt"));
        assert!(listing.contains("sub/"));

        let ranged = edit_view(tmp.path(), Path::new("sample.txt"), Some((2, -1))).expect("range");
        assert_eq!(ranged, "2: two\n3: three");
    }

    #[test]
    fn edit_view_errors_for_missing_path() {
        let tmp = tempfile::tempdir().expect("tempdir");
        let result = edit_view(tmp.path(), Path::new("missing.txt"), None);
        match result {
            Err(KanbusError::IssueOperation(message)) => {
                assert!(message.contains("file or directory not found"))
            }
            other => panic!("expected missing-path error, got {other:?}"),
        }
    }

    #[test]
    fn edit_str_replace_covers_success_no_match_and_multiple_matches() {
        let tmp = tempfile::tempdir().expect("tempdir");
        let path = tmp.path().join("replace.txt");
        fs::write(&path, "hello world").expect("write replace");

        let ok = edit_str_replace(tmp.path(), Path::new("replace.txt"), "hello", "hi")
            .expect("replace success");
        assert_eq!(ok, "Successfully replaced text at exactly one location.");
        assert_eq!(
            fs::read_to_string(&path).expect("read replaced"),
            "hi world"
        );

        let no_match = edit_str_replace(tmp.path(), Path::new("replace.txt"), "absent", "x");
        match no_match {
            Err(KanbusError::IssueOperation(message)) => {
                assert_eq!(message, "no match found for replacement")
            }
            other => panic!("expected no-match error, got {other:?}"),
        }

        fs::write(&path, "foo foo").expect("rewrite replace");
        let many = edit_str_replace(tmp.path(), Path::new("replace.txt"), "foo", "bar");
        match many {
            Err(KanbusError::IssueOperation(message)) => {
                assert!(message.contains("found 2 matches"));
            }
            other => panic!("expected multi-match error, got {other:?}"),
        }
    }

    #[test]
    fn edit_create_and_insert_cover_success_and_error_paths() {
        let tmp = tempfile::tempdir().expect("tempdir");

        let created = edit_create(tmp.path(), Path::new("nested/new.txt"), "line1\nline2\n")
            .expect("create file");
        assert_eq!(created, "Successfully created file.");
        assert!(tmp.path().join("nested/new.txt").exists());

        let exists = edit_create(tmp.path(), Path::new("nested/new.txt"), "again");
        match exists {
            Err(KanbusError::IssueOperation(message)) => assert_eq!(message, "file already exists"),
            other => panic!("expected exists error, got {other:?}"),
        }

        let negative = edit_insert(tmp.path(), Path::new("nested/new.txt"), -1, "x");
        match negative {
            Err(KanbusError::IssueOperation(message)) => {
                assert_eq!(message, "insert_line must be non-negative")
            }
            other => panic!("expected negative-line error, got {other:?}"),
        }

        let too_large = edit_insert(tmp.path(), Path::new("nested/new.txt"), 10, "x");
        match too_large {
            Err(KanbusError::IssueOperation(message)) => {
                assert_eq!(message, "insert_line exceeds file length")
            }
            other => panic!("expected range error, got {other:?}"),
        }

        let inserted =
            edit_insert(tmp.path(), Path::new("nested/new.txt"), 1, "middle").expect("insert line");
        assert_eq!(inserted, "Successfully inserted text.");
        assert_eq!(
            fs::read_to_string(tmp.path().join("nested/new.txt")).expect("read inserted"),
            "line1\nmiddle\nline2\n"
        );
    }
}
