//! Content validation for fenced code blocks in Markdown text.

use std::io::Write;
use std::process::Command;

use crate::error::KanbusError;

/// A fenced code block extracted from Markdown text.
#[derive(Debug, Clone)]
pub struct CodeBlock {
    /// Language identifier from the opening fence.
    pub language: String,
    /// Content between the fences.
    pub content: String,
    /// One-based line number of the opening fence.
    pub start_line: usize,
}

/// Extract all fenced code blocks from Markdown text.
///
/// Scans for lines matching `` ```language `` and collects content until
/// the closing `` ``` `` fence.
pub fn extract_code_blocks(text: &str) -> Vec<CodeBlock> {
    let mut blocks = Vec::new();
    let mut in_block = false;
    let mut current_language = String::new();
    let mut current_content = Vec::new();
    let mut start_line: usize = 0;

    for (index, line) in text.lines().enumerate() {
        let trimmed = line.trim();
        if !in_block {
            if trimmed.starts_with("```") {
                let language = trimmed[3..].trim().to_string();
                in_block = true;
                current_language = language;
                current_content.clear();
                start_line = index + 1;
            }
        } else if trimmed == "```" {
            blocks.push(CodeBlock {
                language: current_language.clone(),
                content: current_content.join("\n"),
                start_line,
            });
            in_block = false;
        } else {
            current_content.push(line.to_string());
        }
    }
    blocks
}

/// Validate all code blocks in the given text.
///
/// Returns `Ok(())` if all blocks are valid or have unrecognized languages.
/// Returns an error describing the first invalid block found.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` if a code block has invalid syntax.
pub fn validate_code_blocks(text: &str) -> Result<(), KanbusError> {
    let blocks = extract_code_blocks(text);
    for block in &blocks {
        match block.language.as_str() {
            "json" => validate_json(block)?,
            "yaml" | "yml" => validate_yaml(block)?,
            "gherkin" | "feature" => validate_gherkin(block)?,
            "mermaid" => validate_external(block, "mmdc")?,
            "plantuml" => validate_external(block, "plantuml")?,
            "d2" => validate_external(block, "d2")?,
            _ => {}
        }
    }
    Ok(())
}

fn validate_json(block: &CodeBlock) -> Result<(), KanbusError> {
    serde_json::from_str::<serde_json::Value>(&block.content).map_err(|error| {
        KanbusError::IssueOperation(format!(
            "invalid json in code block at line {}: {}",
            block.start_line, error
        ))
    })?;
    Ok(())
}

fn validate_yaml(block: &CodeBlock) -> Result<(), KanbusError> {
    serde_yaml::from_str::<serde_yaml::Value>(&block.content).map_err(|error| {
        KanbusError::IssueOperation(format!(
            "invalid yaml in code block at line {}: {}",
            block.start_line, error
        ))
    })?;
    Ok(())
}

fn validate_gherkin(block: &CodeBlock) -> Result<(), KanbusError> {
    // Lightweight validation: check that the content starts with a Feature keyword
    // and contains at least one Scenario/Scenario Outline.
    let trimmed = block.content.trim();
    if trimmed.is_empty() {
        return Err(KanbusError::IssueOperation(format!(
            "invalid gherkin in code block at line {}: empty content",
            block.start_line
        )));
    }
    let has_feature = trimmed
        .lines()
        .any(|line| line.trim().starts_with("Feature:"));
    if !has_feature {
        return Err(KanbusError::IssueOperation(format!(
            "invalid gherkin in code block at line {}: expected Feature keyword",
            block.start_line
        )));
    }
    let has_scenario = trimmed.lines().any(|line| {
        let t = line.trim();
        t.starts_with("Scenario:") || t.starts_with("Scenario Outline:")
    });
    if !has_scenario {
        return Err(KanbusError::IssueOperation(format!(
            "invalid gherkin in code block at line {}: expected at least one Scenario",
            block.start_line
        )));
    }
    Ok(())
}

fn validate_external(block: &CodeBlock, tool: &str) -> Result<(), KanbusError> {
    // Check if the external tool is available on PATH.
    let available = Command::new("which")
        .arg(tool)
        .output()
        .map(|output| output.status.success())
        .unwrap_or(false);

    if !available {
        // Provide helpful installation suggestion
        let (language, install_hint) = match tool {
            "mmdc" => ("mermaid", "npm install -g @mermaid-js/mermaid-cli"),
            "plantuml" => ("plantuml", "brew install plantuml (macOS) or apt install plantuml (Linux)"),
            "d2" => ("d2", "curl -fsSL https://d2lang.com/install.sh | sh -s --"),
            _ => ("", ""),
        };

        eprintln!(
            "Note: {} code block at line {} not validated ({} not installed). Install with: {}",
            language, block.start_line, tool, install_hint
        );
        return Ok(());
    }

    // Write content to a temp file and invoke the tool.
    let extension = match tool {
        "mmdc" => "mmd",
        "plantuml" => "puml",
        "d2" => "d2",
        _ => "txt",
    };
    let temp_path = std::env::temp_dir().join(format!("kanbus_validate.{extension}"));
    {
        let mut file =
            std::fs::File::create(&temp_path).map_err(|e| KanbusError::Io(e.to_string()))?;
        file.write_all(block.content.as_bytes())
            .map_err(|e| KanbusError::Io(e.to_string()))?;
    }

    let result = match tool {
        "mmdc" => Command::new("mmdc")
            .args(["-i", temp_path.to_str().unwrap_or(""), "-o", "/dev/null"])
            .output(),
        "plantuml" => Command::new("plantuml")
            .args(["-checkonly", temp_path.to_str().unwrap_or("")])
            .output(),
        "d2" => Command::new("d2")
            .args(["fmt", temp_path.to_str().unwrap_or("")])
            .output(),
        _ => return Ok(()),
    };

    let _ = std::fs::remove_file(&temp_path);

    match result {
        Ok(output) if !output.status.success() => {
            let stderr = String::from_utf8_lossy(&output.stderr);
            let language = match tool {
                "mmdc" => "mermaid",
                "plantuml" => "plantuml",
                "d2" => "d2",
                _ => tool,
            };
            Err(KanbusError::IssueOperation(format!(
                "invalid {} in code block at line {}: {}",
                language,
                block.start_line,
                stderr.trim()
            )))
        }
        _ => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_empty_text() {
        let blocks = extract_code_blocks("");
        assert!(blocks.is_empty());
    }

    #[test]
    fn test_extract_no_code_blocks() {
        let blocks = extract_code_blocks("Just some text\nwithout code blocks.");
        assert!(blocks.is_empty());
    }

    #[test]
    fn test_extract_single_json_block() {
        let text = "Before\n```json\n{\"key\": \"value\"}\n```\nAfter";
        let blocks = extract_code_blocks(text);
        assert_eq!(blocks.len(), 1);
        assert_eq!(blocks[0].language, "json");
        assert_eq!(blocks[0].content, "{\"key\": \"value\"}");
        assert_eq!(blocks[0].start_line, 2);
    }

    #[test]
    fn test_extract_multiple_blocks() {
        let text = "```json\n{}\n```\n\n```yaml\nkey: value\n```";
        let blocks = extract_code_blocks(text);
        assert_eq!(blocks.len(), 2);
        assert_eq!(blocks[0].language, "json");
        assert_eq!(blocks[1].language, "yaml");
    }

    #[test]
    fn test_extract_block_without_language() {
        let text = "```\nplain text\n```";
        let blocks = extract_code_blocks(text);
        assert_eq!(blocks.len(), 1);
        assert_eq!(blocks[0].language, "");
    }

    #[test]
    fn test_validate_valid_json() {
        let text = "```json\n{\"key\": \"value\"}\n```";
        assert!(validate_code_blocks(text).is_ok());
    }

    #[test]
    fn test_validate_invalid_json() {
        let text = "```json\n{bad json\n```";
        let result = validate_code_blocks(text);
        assert!(result.is_err());
        let message = result.unwrap_err().to_string();
        assert!(message.contains("invalid json"));
        assert!(message.contains("code block"));
    }

    #[test]
    fn test_validate_valid_yaml() {
        let text = "```yaml\nkey: value\nlist:\n  - one\n```";
        assert!(validate_code_blocks(text).is_ok());
    }

    #[test]
    fn test_validate_invalid_yaml() {
        let text = "```yaml\nkey: value\n  bad: indentation\n```";
        let result = validate_code_blocks(text);
        assert!(result.is_err());
        let message = result.unwrap_err().to_string();
        assert!(message.contains("invalid yaml"));
        assert!(message.contains("code block"));
    }

    #[test]
    fn test_validate_valid_gherkin() {
        let text = "```gherkin\nFeature: Test\n  Scenario: Works\n    Given something\n```";
        assert!(validate_code_blocks(text).is_ok());
    }

    #[test]
    fn test_validate_invalid_gherkin() {
        let text = "```gherkin\nThis is not valid gherkin\n```";
        let result = validate_code_blocks(text);
        assert!(result.is_err());
        let message = result.unwrap_err().to_string();
        assert!(message.contains("invalid gherkin"));
        assert!(message.contains("code block"));
    }

    #[test]
    fn test_unknown_language_passes() {
        let text = "```python\ndef broken(: pass\n```";
        assert!(validate_code_blocks(text).is_ok());
    }

    #[test]
    fn test_no_language_passes() {
        let text = "```\n{{{ not valid anything\n```";
        assert!(validate_code_blocks(text).is_ok());
    }
}
