import argparse
import posixpath
import re
import shutil
import tempfile
from pathlib import Path

from papyrus_content.markus_renderer.build import build_markus_site
from papyrus_content.markus_renderer.shell import SiteChrome

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION_DIRECTORY = REPOSITORY_ROOT / "docs"
SITE_THEME_NAME = "catppuccin"
MARKDOWN_LINK_PATTERN = re.compile(r"\]\(([^)\s#]+\.(?:md|html))(#[^)\s]*)?\)")


def render_site_banner(page_context):
    navigation_links = "".join(
        f'<a href="{page_context.prefix}{item.href}"'
        + (' aria-current="page"' if item.href == page_context.active_href else "")
        + f">{item.label}</a>"
        for item in page_context.nav_items
    )
    return (
        '<header class="site-banner">'
        f'<a class="site-wordmark" href="{page_context.prefix}index.html">Kanbus</a>'
        '<p class="site-tagline">Git-backed project management for people and AI agents.</p>'
        f'<div class="site-nav-container"><nav class="site-nav" aria-label="Documentation">{navigation_links}</nav></div>'
        "</header>"
    )


SITE_CHROME = SiteChrome(
    site_name="Kanbus",
    head_html=f"<script>document.documentElement.setAttribute('data-theme','{SITE_THEME_NAME}')</script>",
    render_masthead=render_site_banner,
    footer_html='<p>Built with <a href="https://github.com/AnthusAI/Papyrus">Papyrus</a>. Source on <a href="https://github.com/AnthusAI/Kanbus">GitHub</a>.</p>',
)


def published_page_slug(documentation_relative_path: str) -> str:
    stem = documentation_relative_path.removesuffix(".md").replace("/", "-")
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def published_page_name(documentation_relative_path: str) -> str:
    if documentation_relative_path == "index.md":
        return "index.md"
    return f"articles/{published_page_slug(documentation_relative_path)}.md"


def rewrite_links_between_pages(page_text: str, documentation_relative_path: str, known_pages: set) -> str:
    source_directory = posixpath.dirname(documentation_relative_path)
    published_directory = posixpath.dirname(published_page_name(documentation_relative_path))

    def rewrite(match):
        target_path = posixpath.normpath(posixpath.join(source_directory, match.group(1)))
        if target_path.endswith(".html"):
            target_path = target_path.removesuffix(".html") + ".md"
        if target_path not in known_pages:
            return match.group(0)
        relative_target = posixpath.relpath(
            published_page_name(target_path).removesuffix(".md") + ".html", published_directory or "."
        )
        return f"]({relative_target}{match.group(2) or ''})"

    return MARKDOWN_LINK_PATTERN.sub(rewrite, page_text)


def stage_papyrus_content_layout(staging_directory: Path) -> None:
    (staging_directory / "articles").mkdir()
    source_pages = sorted(DOCUMENTATION_DIRECTORY.rglob("*.md"))
    relative_paths = {page.relative_to(DOCUMENTATION_DIRECTORY).as_posix() for page in source_pages}
    for source_page in source_pages:
        relative_path = source_page.relative_to(DOCUMENTATION_DIRECTORY).as_posix()
        page_text = rewrite_links_between_pages(source_page.read_text(encoding="utf-8"), relative_path, relative_paths)
        page_text = page_text.replace("](images/", "](../assets/")
        (staging_directory / published_page_name(relative_path)).write_text(page_text, encoding="utf-8")
    images_directory = DOCUMENTATION_DIRECTORY / "images"
    if images_directory.is_dir():
        shutil.copytree(images_directory, staging_directory / "assets")


def write_redirects_from_former_urls(output_directory: Path) -> None:
    for source_page in sorted(DOCUMENTATION_DIRECTORY.rglob("*.md")):
        relative_path = source_page.relative_to(DOCUMENTATION_DIRECTORY).as_posix()
        if relative_path == "index.md":
            continue
        published_target = f"articles/{published_page_slug(relative_path)}.html"
        former_directory = output_directory / relative_path.removesuffix(".md")
        depth_prefix = "../" * (relative_path.removesuffix(".md").count("/") + 1)
        former_directory.mkdir(parents=True, exist_ok=True)
        (former_directory / "index.html").write_text(
            '<!DOCTYPE html><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0; url={depth_prefix}{published_target}">'
            f'<link rel="canonical" href="{depth_prefix}{published_target}">'
            f'<a href="{depth_prefix}{published_target}">Moved to {published_target}</a>',
            encoding="utf-8",
        )


def build_documentation_site(output_directory: Path):
    with tempfile.TemporaryDirectory(prefix="kanbus-site-content-") as staging_name:
        staging_directory = Path(staging_name)
        stage_papyrus_content_layout(staging_directory)
        build_result = build_markus_site(
            content_dir=staging_directory,
            out_dir=output_directory,
            theme=SITE_THEME_NAME,
            chrome=SITE_CHROME,
        )
    write_redirects_from_former_urls(output_directory)
    return build_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the Kanbus documentation site with Papyrus.")
    parser.add_argument("--out", type=Path, default=REPOSITORY_ROOT / "_site")
    arguments = parser.parse_args()
    result = build_documentation_site(arguments.out)
    print(f"Built {len(result.pages)} pages into {result.out_dir}")
