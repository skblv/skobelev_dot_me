#!/usr/bin/env python3
"""Build index.html from assets: bio, social links, and publications."""

from __future__ import annotations

import csv
import re
from pathlib import Path
import html
from typing import Iterable

from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
PUBLICATIONS_DIR = ASSETS_DIR / "publications"
INDEX_PATH = BASE_DIR / "index.html"
BIO_PATH = ASSETS_DIR / "bio.txt"
LINKS_CSV = ASSETS_DIR / "links.csv"
COAUTHOR_CSV = ASSETS_DIR / "coauthor_links.csv"
PUBLICATIONS_CSV = PUBLICATIONS_DIR / "publications.csv"

PROFILE_IMG = ASSETS_DIR / "Kirill_Skobelev.jpg"
PAGE_TITLE = "Kirill Skobelev"
NAME = "Kirill Skobelev"
EMAIL = "skobelev@uchicago.edu"


# The regex links plain URLs to anchors; avoids capturing closing parentheses.
URL_PATTERN = re.compile(r"(https?://[^\s)]+)")
LABEL_URL_PATTERN = re.compile(r"(?<![A-Za-z])([A-Z][^()]+?)\s*\((https?://[^)\s]+)\)")


def load_author_links() -> dict[str, str]:
    """Load mapping of author names to URLs from coauthor_links.csv."""

    links: dict[str, str] = {}
    if not COAUTHOR_CSV.exists():
        return links
    with COAUTHOR_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            url = (row.get("url") or "").strip()
            if name and url:
                links[name] = url
    return links


def load_social_links() -> dict[str, str]:
    """Load social links from links.csv. Always include Email.

    Empty links are ignored.
    """

    links: dict[str, str] = {"Email": f"mailto:{EMAIL}"}
    if not LINKS_CSV.exists():
        return links
    with LINKS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = (row.get("type") or "").strip()
            href = (row.get("link") or "").strip()
            if label and href:
                links[label] = href
    return links


def paragraphs_from_file(path: Path) -> list[str]:
    """Split a UTF-8 text file into paragraphs on blank lines."""

    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    blocks = [para.strip() for para in text.replace("\r\n", "\n").split("\n\n")]
    return [para for para in blocks if para]


def render_bio_paragraph_html(text: str) -> str:
    """Convert 'Label (URL)' pairs to anchors without exposing raw URLs.

    The label is taken as the phrase immediately before the opening parenthesis,
    starting after the nearest connector such as ' at ', ' in ', ' and ', etc.
    """

    paren_url = re.compile(r"\((https?://[^)\s]+)\)")
    connectors = [
        " at the ",
        " from the ",
        " in the ",
        " at ",
        " from ",
        " in ",
        " and ",
        " or ",
        " (",
        "; ",
        ": ",
        ", ",
        "\n",
        ". ",
    ]

    result_parts: list[str] = []
    cursor = 0

    for m in paren_url.finditer(text):
        lparen = m.start()
        url = m.group(1)
        left = text[cursor:lparen]
        abs_left = text[:lparen]

        split_at = -1
        split_conn = ""
        for conn in connectors:
            idx = abs_left.rfind(conn)
            if idx > split_at:
                split_at = idx
                split_conn = conn

        label_start = split_at + len(split_conn) if split_at >= 0 else cursor
        label = text[label_start:lparen].strip()

        if not label:
            result_parts.append(text[cursor:m.end()])
            cursor = m.end()
            continue

        result_parts.append(text[cursor:label_start])
        anchor = (
            f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
        )
        cursor = m.end()
        result_parts.append(anchor)

    result_parts.append(text[cursor:])
    return "".join(result_parts)


def find_publication_folder(pub_id: str) -> Path | None:
    """Find folder for a publication like '1_delm' given id '1'."""

    matches = sorted(PUBLICATIONS_DIR.glob(f"{pub_id}_*"))
    return matches[0] if matches else None


def first_file(folder: Path, pattern: str) -> Path | None:
    """Return the first file in folder that matches the glob pattern."""

    matches = sorted(folder.glob(pattern))
    return matches[0] if matches else None


def load_publication_rows() -> Iterable[dict[str, str]]:
    """Iterate over publications.csv rows as trimmed dicts."""

    with PUBLICATIONS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k: (v or "").strip() for k, v in row.items()}


def build_social_nav(soup: BeautifulSoup, links: dict[str, str]) -> BeautifulSoup:
    """Construct the social links <nav> with preferred ordering."""

    order = ["Email", "LinkedIn", "CV", "Google Scholar"]
    nav = soup.new_tag("nav", attrs={"class": "social-links"})
    for label in order:
        href = links.get(label)
        if not href:
            continue
        a = soup.new_tag("a", href=href)
        if label == "CV":
            a["download"] = ""
        a.string = label
        nav.append(a)
    return nav


def build_bio_section(soup: BeautifulSoup) -> BeautifulSoup:
    """Create the Bio section with paragraphs from bio.txt, linkifying URLs."""

    section = soup.new_tag("section", attrs={"class": "section", "id": "bio"})
    h2 = soup.new_tag("h2")
    h2.string = "Bio"
    section.append(h2)

    container = soup.new_tag("div", id="bio-content")
    for para in paragraphs_from_file(BIO_PATH):
        p = soup.new_tag("p")
        html_para = render_bio_paragraph_html(para)
        p.append(BeautifulSoup(html_para, "html.parser"))
        container.append(p)
    section.append(container)
    return section


def build_publication_article(
    soup: BeautifulSoup, row: dict[str, str], author_links: dict[str, str]
) -> BeautifulSoup:
    """Render a single publication article from a CSV row."""

    article = soup.new_tag("article", attrs={"class": "publication"})

    folder = find_publication_folder(row.get("publication", ""))
    illustration = first_file(folder, "*_illustration.*") if folder else None

    media_div = soup.new_tag("div", attrs={"class": "pub-media"})
    if illustration:
        img = soup.new_tag("img")
        try:
            rel_src = illustration.relative_to(BASE_DIR)
        except ValueError:
            rel_src = illustration
        img["src"] = rel_src.as_posix()
        img["alt"] = f"Visualization for {row.get('title', '')}"
        media_div.append(img)
    article.append(media_div)

    content_div = soup.new_tag("div", attrs={"class": "pub-content"})

    title = soup.new_tag("h3")
    title.string = row.get("title", "")
    content_div.append(title)

    meta = soup.new_tag("p", attrs={"class": "pub-meta"})
    authors = row.get("authors", "")
    year = row.get("year", "")
    if authors:
        names = [name.strip() for name in authors.replace(";", ",").split(",") if name.strip()]
        for idx, name in enumerate(names):
            if idx:
                meta.append(soup.new_string(", "))
            link = author_links.get(name)
            if link:
                tag = soup.new_tag("a", href=link)
                tag.string = name
                meta.append(tag)
            else:
                meta.append(soup.new_string(name))
    if authors and year:
        meta.append(f" · {year}")
    elif year:
        meta.append(year)
    content_div.append(meta)

    details = soup.new_tag("details", attrs={"class": "pub-abstract"})
    summary = soup.new_tag("summary")
    summary.string = "Abstract"
    details.append(summary)

    body = soup.new_tag("div", attrs={"class": "pub-abstract-body"})
    if folder:
        abstract_path = first_file(folder, "*_abstract.txt")
        for para in paragraphs_from_file(abstract_path) if abstract_path else []:
            p = soup.new_tag("p")
            p.string = para
            body.append(p)
    details.append(body)
    content_div.append(details)

    if row.get("comments"):
        comments = soup.new_tag("p", attrs={"class": "pub-comments"})
        comments.string = row["comments"]
        content_div.append(comments)

    links_div = soup.new_tag("div", attrs={"class": "pub-links"})
    if row.get("code_link"):
        code_link = soup.new_tag("a", attrs={"class": "pub-link", "href": row["code_link"]})
        code_link.string = "[code]"
        links_div.append(code_link)
    if row.get("paper_link"):
        paper_link = soup.new_tag("a", attrs={"class": "pub-link", "href": row["paper_link"]})
        paper_link.string = "[paper]"
        links_div.append(paper_link)
    if links_div.contents:
        content_div.append(links_div)

    article.append(content_div)
    return article


def build_publications_section(soup: BeautifulSoup) -> BeautifulSoup:
    """Construct the Research section from CSV and asset folders."""

    section = soup.new_tag("section", attrs={"class": "section", "id": "publications"})
    heading = soup.new_tag("h2")
    heading.string = "Research"
    section.append(heading)

    author_links = load_author_links()
    for row in load_publication_rows():
        section.append(build_publication_article(soup, row, author_links))
    return section


def build_document() -> str:
    """Assemble the full HTML document and return as a string."""

    soup = BeautifulSoup("", "html.parser")

    html_tag = soup.new_tag("html", lang="en")
    head = soup.new_tag("head")

    meta_charset = soup.new_tag("meta", charset="utf-8")
    meta_viewport = soup.new_tag(
        "meta", attrs={"content": "width=device-width, initial-scale=1", "name": "viewport"}
    )
    title = soup.new_tag("title")
    title.string = PAGE_TITLE
    link_preconnect_1 = soup.new_tag("link", rel="preconnect", href="https://fonts.googleapis.com")
    link_preconnect_2 = soup.new_tag(
        "link", rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""
    )
    link_fonts = soup.new_tag(
        "link",
        rel="stylesheet",
        href=(
            "https://fonts.googleapis.com/css2?family=Roboto+Slab:wght@100..900&family=Roboto:ital,wght@0,100..900;"
            "1,100..900&display=swap"
        ),
    )
    link_css = soup.new_tag("link", rel="stylesheet", href="styles.css")

    head.extend([meta_charset, meta_viewport, title, link_preconnect_1, link_preconnect_2, link_fonts, link_css])

    body = soup.new_tag("body")
    layout = soup.new_tag("div", attrs={"class": "layout"})

    aside = soup.new_tag("aside", attrs={"class": "sidebar"})
    profile_header = soup.new_tag("div", attrs={"class": "profile-header"})
    img = soup.new_tag("img", attrs={"class": "profile-photo"})
    try:
        img_src = PROFILE_IMG.relative_to(BASE_DIR)
    except ValueError:
        img_src = PROFILE_IMG
    img["src"] = img_src.as_posix()
    img["alt"] = f"Portrait of {NAME}"
    h1 = soup.new_tag("h1")
    h1.string = NAME
    profile_header.extend([img, h1])

    social_nav = build_social_nav(soup, load_social_links())
    aside.extend([profile_header, social_nav])

    main = soup.new_tag("main", attrs={"class": "content"})
    main.append(build_bio_section(soup))
    main.append(build_publications_section(soup))

    footer = soup.new_tag("footer", attrs={"class": "site-footer"})
    p = soup.new_tag("p")
    p.append("© ")
    span = soup.new_tag("span", id="copy-year")
    p.append(span)
    p.append(f" {NAME}")
    footer.append(p)

    layout.extend([aside, main])
    body.append(layout)

    script = soup.new_tag("script")
    script.string = (
        "(function () {\n"
        "  const yearEl = document.getElementById(\"copy-year\");\n"
        "  if (yearEl) { yearEl.textContent = new Date().getFullYear(); }\n"
        "})();"
    )
    body.append(script)

    html_tag.extend([head, body])
    soup.append(html_tag)
    return soup.decode()


def main() -> None:
    """Generate index.html from assets and write it to the project root."""

    html = build_document()
    INDEX_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {INDEX_PATH}")


if __name__ == "__main__":
    main()
