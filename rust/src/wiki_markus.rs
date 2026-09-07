//! Markus conversion for Jinja-resolved wiki Markdown.

use crate::error::KanbusError;
use regex::Regex;
use std::sync::OnceLock;

const KNOWN_MARKUS_DIRECTIVES: &[&str] = &[
    "aside",
    "callout",
    "card",
    "card-grid",
    "caution",
    "column",
    "details",
    "feature-card",
    "feature-grid",
    "figure",
    "metric",
    "note",
    "pull-quote",
    "step",
    "step-list",
    "tab",
    "tabs",
    "timeline",
    "timeline-event",
    "tip",
    "two-up",
    "video",
    "warning",
];

/// Convert Jinja-resolved wiki Markdown to Markus semantic HTML.
///
/// # Arguments
/// * `markdown` - Post-Jinja Markdown source
///
/// # Returns
/// HTML that includes Markus semantic classes
///
/// # Errors
/// Returns `KanbusError::IssueOperation` when a directive is unknown or the
/// source cannot be converted
pub fn convert_wiki_markdown_to_html(markdown: &str) -> Result<String, KanbusError> {
    let nodes = parse_markus_source(markdown)?;
    let body = render_nodes(&nodes);
    Ok(format!(
        r#"<article class="markus-document">{body}</article>"#
    ))
}

#[derive(Debug, Clone)]
enum MarkusNode {
    Markdown(String),
    Directive {
        name: String,
        attributes: String,
        children: Vec<MarkusNode>,
    },
}

struct ParseFrame {
    name: String,
    attributes: String,
    nodes: Vec<MarkusNode>,
}

fn parse_markus_source(source: &str) -> Result<Vec<MarkusNode>, KanbusError> {
    let fence = fence_pattern();
    let mut stack = vec![ParseFrame {
        name: String::new(),
        attributes: String::new(),
        nodes: Vec::new(),
    }];
    let mut markdown_buffer = String::new();

    for (index, line) in source.lines().enumerate() {
        if let Some(captures) = fence.captures(line) {
            flush_markdown(
                &mut stack.last_mut().expect("parse frame").nodes,
                &mut markdown_buffer,
            );
            let name = captures.get(1).map(|value| value.as_str()).unwrap_or("");
            let attributes = captures
                .get(2)
                .map(|value| value.as_str().to_string())
                .unwrap_or_default();
            if name.is_empty() {
                if stack.len() == 1 {
                    return Err(KanbusError::IssueOperation(format!(
                        "line {}: unmatched Markus closing fence",
                        index + 1
                    )));
                }
                let finished = stack.pop().expect("directive frame");
                stack
                    .last_mut()
                    .expect("parent frame")
                    .nodes
                    .push(MarkusNode::Directive {
                        name: finished.name,
                        attributes: finished.attributes,
                        children: finished.nodes,
                    });
                continue;
            }
            if !KNOWN_MARKUS_DIRECTIVES.contains(&name) {
                return Err(KanbusError::IssueOperation(format!(
                    "Unknown directive '{name}'"
                )));
            }
            stack.push(ParseFrame {
                name: name.to_string(),
                attributes,
                nodes: Vec::new(),
            });
            continue;
        }
        markdown_buffer.push_str(line);
        markdown_buffer.push('\n');
    }
    flush_markdown(
        &mut stack.last_mut().expect("parse frame").nodes,
        &mut markdown_buffer,
    );
    if stack.len() != 1 {
        return Err(KanbusError::IssueOperation(
            "unclosed Markus directive".to_string(),
        ));
    }
    Ok(stack.pop().expect("root frame").nodes)
}

fn flush_markdown(nodes: &mut Vec<MarkusNode>, buffer: &mut String) {
    if !buffer.is_empty() {
        nodes.push(MarkusNode::Markdown(std::mem::take(buffer)));
    }
}

fn fence_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"(?x)^\s*:::([A-Za-z0-9-]+)?(\{[^}]*\})?\s*$").expect("markus fence regex")
    })
}

fn render_nodes(nodes: &[MarkusNode]) -> String {
    nodes.iter().map(render_node).collect()
}

fn render_node(node: &MarkusNode) -> String {
    match node {
        MarkusNode::Markdown(source) => render_markdown_fragment(source),
        MarkusNode::Directive {
            name,
            attributes,
            children,
        } => render_directive(name, attributes, children),
    }
}

fn render_directive(name: &str, attributes: &str, children: &[MarkusNode]) -> String {
    let inner = render_nodes(children);
    let title = attribute_value(attributes, "title");
    match name {
        "pull-quote" => format!(r#"<figure class="markus-pull-quote">{inner}</figure>"#),
        "card-grid" | "feature-grid" => format!(
            r#"<section class="markus-card-grid" aria-label="Related items">{inner}</section>"#
        ),
        "card" | "feature-card" => {
            let title_html = title
                .map(|value| {
                    format!(
                        r#"<h3 class="markus-card-title">{}</h3>"#,
                        escape_html(&value)
                    )
                })
                .unwrap_or_default();
            format!(
                r#"<article class="markus-card">{title_html}<div class="markus-card-body">{inner}</div></article>"#
            )
        }
        other => format!(r#"<section class="markus-{other}">{inner}</section>"#),
    }
}

fn render_markdown_fragment(source: &str) -> String {
    let trimmed = source.trim();
    if trimmed.is_empty() {
        return String::new();
    }
    let mut html = String::new();
    let mut paragraph: Vec<&str> = Vec::new();
    for raw_line in source.lines() {
        let line = raw_line.trim_end();
        if line.trim().is_empty() {
            flush_paragraph(&mut html, &mut paragraph);
            continue;
        }
        if let Some(heading) = heading_html(line) {
            flush_paragraph(&mut html, &mut paragraph);
            html.push_str(&heading);
            continue;
        }
        if let Some(rest) = line.strip_prefix('>') {
            flush_paragraph(&mut html, &mut paragraph);
            html.push_str("<blockquote>");
            html.push_str(&inline_markdown(rest.trim()));
            html.push_str("</blockquote>");
            continue;
        }
        paragraph.push(line);
    }
    flush_paragraph(&mut html, &mut paragraph);
    html
}

fn heading_html(line: &str) -> Option<String> {
    let trimmed = line.trim_start();
    let hashes = trimmed
        .chars()
        .take_while(|character| *character == '#')
        .count();
    if (1..=6).contains(&hashes) && trimmed.as_bytes().get(hashes) == Some(&b' ') {
        let text = inline_markdown(trimmed[hashes + 1..].trim());
        return Some(format!("<h{hashes}>{text}</h{hashes}>"));
    }
    None
}

fn flush_paragraph(html: &mut String, paragraph: &mut Vec<&str>) {
    if paragraph.is_empty() {
        return;
    }
    let text = inline_markdown(&paragraph.join("\n"));
    html.push_str("<p>");
    html.push_str(&text);
    html.push_str("</p>");
    paragraph.clear();
}

fn inline_markdown(source: &str) -> String {
    let escaped = escape_html(source);
    bold_pattern()
        .replace_all(&escaped, "<strong>$1</strong>")
        .into_owned()
}

fn bold_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r"\*\*(.+?)\*\*").expect("bold regex"))
}

fn attribute_value(attributes: &str, key: &str) -> Option<String> {
    let quoted = format!(r#"{key}=""#);
    let start = attributes.find(&quoted)?;
    let rest = &attributes[start + quoted.len()..];
    let end = rest.find('"')?;
    Some(rest[..end].to_string())
}

fn escape_html(source: &str) -> String {
    source
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

#[cfg(test)]
mod tests {
    use super::convert_wiki_markdown_to_html;

    #[test]
    fn wraps_plain_markdown_in_markus_document() {
        let html =
            convert_wiki_markdown_to_html("Plain paragraph with **bold** text.").expect("convert");
        assert!(html.contains(r#"class="markus-document""#));
        assert!(html.contains("Plain paragraph with"));
    }

    #[test]
    fn renders_pull_quote_class() {
        let html = convert_wiki_markdown_to_html(":::pull-quote\n> Measure what matters.\n:::\n")
            .expect("convert");
        assert!(html.contains("markus-pull-quote"));
        assert!(html.contains("Measure what matters."));
    }

    #[test]
    fn rejects_unknown_directive() {
        let error = convert_wiki_markdown_to_html(":::unknown-directive\nInvalid.\n:::\n")
            .expect_err("unknown");
        assert!(error.to_string().contains("Unknown directive"));
    }
}
