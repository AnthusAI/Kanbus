//! Rich text quality signals for CLI output.
//!
//! Detects and repairs common malformations in issue descriptions and comments
//! submitted through the CLI, and emits actionable warnings and suggestions.

use std::cell::RefCell;

thread_local! {
    static CAPTURED_STDERR: RefCell<Option<String>> = const { RefCell::new(None) };
}

/// Enable stderr capture for the current thread.
///
/// When enabled, all calls to `emit_signals` write to an internal buffer
/// instead of the real stderr. Call `take_captured_stderr` to retrieve and
/// clear the buffer.
pub fn start_stderr_capture() {
    CAPTURED_STDERR.with(|cell| {
        *cell.borrow_mut() = Some(String::new());
    });
}

/// Disable stderr capture and return the captured content.
///
/// Returns `None` if capture was not active.
pub fn take_captured_stderr() -> Option<String> {
    CAPTURED_STDERR.with(|cell| cell.borrow_mut().take())
}

fn write_stderr(message: &str) {
    let mut captured = false;
    CAPTURED_STDERR.with(|cell| {
        if let Some(ref mut buffer) = *cell.borrow_mut() {
            buffer.push_str(message);
            buffer.push('\n');
            captured = true;
        }
    });
    if !captured {
        eprintln!("{}", message);
    }
}

/// Result of applying quality signals to a text value.
///
/// # Fields
/// * `text` - The (possibly repaired) text after processing
/// * `warnings` - Warning messages describing automatic transformations
/// * `suggestions` - Non-blocking suggestion messages
/// * `escape_sequences_repaired` - True if literal `\n` sequences were replaced
#[derive(Debug, Clone, Default)]
pub struct TextQualityResult {
    /// The (possibly repaired) text after processing.
    pub text: String,
    /// Warning messages describing automatic transformations.
    pub warnings: Vec<String>,
    /// Non-blocking suggestion messages.
    pub suggestions: Vec<String>,
    /// True if literal `\n` sequences were replaced with real newlines.
    pub escape_sequences_repaired: bool,
}

/// Replace literal backslash-n sequences with real newline characters.
///
/// # Arguments
/// * `text` - Input text that may contain literal `\n` sequences
///
/// # Returns
/// Tuple of (repaired text, whether any replacements were made)
pub fn repair_escape_sequences(text: &str) -> (String, bool) {
    if text.contains("\\n") {
        (text.replace("\\n", "\n"), true)
    } else {
        (text.to_string(), false)
    }
}

/// Return true if the text contains at least one Markdown element.
///
/// # Arguments
/// * `text` - Text to inspect
pub fn has_markdown_formatting(text: &str) -> bool {
    let markdown_patterns: &[fn(&str) -> bool] = &[
        |t| {
            t.lines().any(|line| {
                let trimmed = line.trim_start();
                trimmed.starts_with("# ")
                    || trimmed.starts_with("## ")
                    || trimmed.starts_with("### ")
                    || trimmed.starts_with("#### ")
                    || trimmed.starts_with("##### ")
                    || trimmed.starts_with("###### ")
            })
        },
        |t| contains_pattern(t, "**"),
        |t| contains_inline_emphasis(t, '*'),
        |t| contains_pattern(t, "__"),
        |t| contains_inline_emphasis(t, '_'),
        |t| t.contains("```"),
        |t| t.contains('`'),
        |t| t.lines().any(|line| line.trim_start().starts_with('>')),
        |t| {
            t.lines().any(|line| {
                let trimmed = line.trim_start();
                trimmed.starts_with("- ") || trimmed.starts_with("* ") || trimmed.starts_with("+ ")
            })
        },
        |t| {
            t.lines().any(|line| {
                let trimmed = line.trim_start();
                trimmed.len() > 2
                    && trimmed
                        .as_bytes()
                        .first()
                        .is_some_and(|b| b.is_ascii_digit())
                    && trimmed.contains(". ")
            })
        },
        |t| t.lines().any(|line| line.trim() == "---"),
        |t| t.contains("]("),
    ];

    markdown_patterns.iter().any(|check| check(text))
}

fn contains_pattern(text: &str, pattern: &str) -> bool {
    let count = text.matches(pattern).count();
    count >= 2
}

fn contains_inline_emphasis(text: &str, marker: char) -> bool {
    let mut chars = text.chars().peekable();
    let mut in_emphasis = false;
    let mut prev = ' ';
    while let Some(ch) = chars.next() {
        if ch == marker && prev != marker {
            if let Some(&next) = chars.peek() {
                if in_emphasis && !next.is_whitespace() {
                    return true;
                }
                if !in_emphasis && !next.is_whitespace() && next != marker {
                    in_emphasis = true;
                } else if in_emphasis {
                    in_emphasis = false;
                }
            }
        }
        prev = ch;
    }
    false
}

/// Return true if the text contains at least one diagram fenced code block.
///
/// Checks for mermaid, plantuml, or d2 language identifiers.
///
/// # Arguments
/// * `text` - Text to inspect
pub fn has_diagram_block(text: &str) -> bool {
    text.lines().any(|line| {
        let trimmed = line.trim();
        trimmed.eq_ignore_ascii_case("```mermaid")
            || trimmed.eq_ignore_ascii_case("```plantuml")
            || trimmed.eq_ignore_ascii_case("```d2")
    })
}

/// Apply all quality signals to the given text.
///
/// Repairs literal escape sequences, then checks for missing Markdown
/// formatting and missing diagram blocks, collecting warnings and suggestions.
///
/// # Arguments
/// * `text` - Raw text from the CLI argument
pub fn apply_text_quality_signals(text: &str) -> TextQualityResult {
    let (repaired_text, sequences_were_repaired) = repair_escape_sequences(text);

    let mut warnings = Vec::new();
    let mut suggestions = Vec::new();

    if sequences_were_repaired {
        warnings.push(
            "WARNING: Literal \\n escape sequences were detected and replaced with real newlines.\n\
             \x20 To pass multi-line text correctly, use a heredoc or $'...\\n...' syntax:\n\
             \x20   kbs create \"Title\" --description $'First line\\nSecond line'\n\
             \x20   kbs create \"Title\" --description \"$(cat <<'EOF'\\nFirst line\\nSecond line\\nEOF\\n)\""
                .to_string(),
        );
    }

    if !has_markdown_formatting(&repaired_text) {
        suggestions.push(
            "SUGGESTION: Markdown formatting is supported in descriptions and comments.\n\
             \x20 Use headings, bold, code blocks, and lists when they improve readability."
                .to_string(),
        );
    }

    if !has_diagram_block(&repaired_text) {
        suggestions.push(
            "SUGGESTION: Diagrams can be embedded using fenced code blocks.\n\
             \x20 Supported: mermaid, plantuml, d2. Use these to visualize flows or structures."
                .to_string(),
        );
    }

    TextQualityResult {
        text: repaired_text,
        warnings,
        suggestions,
        escape_sequences_repaired: sequences_were_repaired,
    }
}

/// Print quality signal messages to stderr.
///
/// Emits warnings first, then suggestions, and finally a follow-up command
/// hint if any suggestions were generated.
///
/// # Arguments
/// * `result` - The quality result to emit signals from
/// * `context` - Human-readable label for what was processed (e.g. "description")
/// * `issue_id` - Issue identifier for follow-up command hints
/// * `comment_id` - Comment identifier for comment-update hints
/// * `is_update` - Whether this is an update operation (affects hint wording)
pub fn emit_signals(
    result: &TextQualityResult,
    context: &str,
    issue_id: Option<&str>,
    comment_id: Option<&str>,
    _is_update: bool,
) {
    for warning in &result.warnings {
        write_stderr(warning);
    }

    if !result.suggestions.is_empty() {
        for suggestion in &result.suggestions {
            write_stderr(suggestion);
        }

        if let Some(issue_id) = issue_id {
            emit_follow_up_hint(context, issue_id, comment_id);
        }
    }
}

fn emit_follow_up_hint(context: &str, issue_id: &str, comment_id: Option<&str>) {
    if let Some(comment_id) = comment_id {
        write_stderr(&format!(
            "  -> To update this comment: kbs comment update {} {} \"<your improved comment here>\"",
            issue_id, comment_id
        ));
    } else {
        write_stderr(&format!(
            "  -> To update the {}: kbs update {} --description \"<your improved description here>\"",
            context, issue_id
        ));
    }
}
