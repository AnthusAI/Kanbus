export function extractWikiTitle(content: string): string | null {
  const { frontmatter, body } = splitWikiFrontmatter(content);
  if (frontmatter !== null) {
    const frontmatterTitle = extractFrontmatterTitle(frontmatter);
    if (frontmatterTitle) {
      return frontmatterTitle;
    }
  }
  for (const line of body.split(/\r?\n/)) {
    const heading = extractMarkdownH1Title(line);
    if (heading) {
      return heading;
    }
  }
  return null;
}

export function wikiPageDisplayTitle(content: string, pagePath: string): string {
  return extractWikiTitle(content) ?? wikiPathStem(pagePath);
}

function wikiPathStem(pagePath: string): string {
  const slash = pagePath.lastIndexOf("/");
  const name = slash >= 0 ? pagePath.slice(slash + 1) : pagePath;
  return name.replace(/\.md$/i, "");
}

function splitWikiFrontmatter(content: string): { frontmatter: string | null; body: string } {
  const text = content.replace(/^\uFEFF/, "");
  const lines = text.split(/\r?\n/);
  if (lines.length === 0 || lines[0].trim() !== "---") {
    return { frontmatter: null, body: text };
  }
  for (let index = 1; index < lines.length; index += 1) {
    if (lines[index].trim() === "---") {
      return {
        frontmatter: lines.slice(1, index).join("\n"),
        body: lines.slice(index + 1).join("\n")
      };
    }
  }
  return { frontmatter: null, body: text };
}

function extractFrontmatterTitle(frontmatter: string): string | null {
  for (const line of frontmatter.split(/\r?\n/)) {
    const match = /^title:\s*(.+?)\s*$/.exec(line);
    if (!match) {
      continue;
    }
    const title = unquoteYamlScalar(match[1]);
    if (title) {
      return title;
    }
  }
  return null;
}

function unquoteYamlScalar(value: string): string {
  const trimmed = value.trim();
  if (
    trimmed.length >= 2
    && ((trimmed.startsWith('"') && trimmed.endsWith('"'))
      || (trimmed.startsWith("'") && trimmed.endsWith("'")))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function extractMarkdownH1Title(line: string): string | null {
  const match = /^#\s+(.+?)\s*$/.exec(line);
  return match ? match[1] : null;
}
