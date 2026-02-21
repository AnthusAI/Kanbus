//! Content validation for fenced code blocks in Markdown text.

use std::io::{Read, Write};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

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
            if let Some(stripped) = trimmed.strip_prefix("```") {
                let language = stripped.trim().to_string();
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
    if let Ok(forced_missing) = std::env::var("KANBUS_TEST_EXTERNAL_TOOL_MISSING") {
        if forced_missing == tool {
            return Ok(());
        }
    }
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
            "plantuml" => (
                "plantuml",
                "brew install plantuml (macOS) or apt install plantuml (Linux)",
            ),
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

    let mut command = match tool {
        "mmdc" => {
            let mut cmd = Command::new("mmdc");
            cmd.args(["-i", temp_path.to_str().unwrap_or(""), "-o", "/dev/null"]);
            cmd
        }
        "plantuml" => {
            let mut cmd = Command::new("plantuml");
            cmd.args(["-checkonly", temp_path.to_str().unwrap_or("")]);
            cmd
        }
        "d2" => {
            let mut cmd = Command::new("d2");
            cmd.args(["fmt", temp_path.to_str().unwrap_or("")]);
            cmd
        }
        _ => return Ok(()),
    };

    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| KanbusError::Io(e.to_string()))?;

    let timeout_ms = std::env::var("KANBUS_TEST_EXTERNAL_TIMEOUT_MS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(30_000);
    let timeout = Duration::from_millis(timeout_ms);
    let start = Instant::now();

    loop {
        if let Some(status) = child
            .try_wait()
            .map_err(|e| KanbusError::Io(e.to_string()))?
        {
            let mut stderr = String::new();
            if let Some(mut err) = child.stderr.take() {
                err.read_to_string(&mut stderr)
                    .map_err(|e| KanbusError::Io(e.to_string()))?;
            }
            let _ = std::fs::remove_file(&temp_path);
            if !status.success() {
                let language = match tool {
                    "mmdc" => "mermaid",
                    "plantuml" => "plantuml",
                    "d2" => "d2",
                    _ => tool,
                };
                return Err(KanbusError::IssueOperation(format!(
                    "invalid {} in code block at line {}: {}",
                    language,
                    block.start_line,
                    stderr.trim()
                )));
            }
            return Ok(());
        }
        if start.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            let _ = std::fs::remove_file(&temp_path);
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}
