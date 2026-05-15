"""Upload guide and metadata extraction for latex2arxiv."""

import os
import re
import subprocess

GUIDE_LAST_UPDATED = "v0.10.0 (2026-05-13)"

_FALLBACK = "(could not extract — check your .tex)"


def extract_metadata(tex_content: str) -> dict:
    """Extract title, authors, abstract from cleaned tex content."""
    return {
        "title": _extract_title(tex_content),
        "authors": _extract_authors(tex_content),
        "abstract": _extract_abstract(tex_content),
    }


def _extract_title(tex: str) -> str | None:
    try:
        m = re.search(r"\\title\s*(?:\[[^\]]*\])?\s*\{", tex)
        if not m:
            return None
        title = _extract_braced(tex, m.end() - 1)
        if title:
            # Collapse whitespace/newlines
            return re.sub(r"\s+", " ", title).strip() or None
    except Exception:
        pass
    return None


def _extract_authors(tex: str) -> str | None:
    try:
        # IMS style: \fnms{First}~\snm{Last}
        ims = re.findall(r"\\fnms\{([^}]*)\}\s*~?\s*\\snm\{([^}]*)\}", tex)
        if ims:
            authors = [f"{f.strip()} {s.strip()}" for f, s in ims]
            return ", ".join(authors)

        # Standard \author{...} — try multiple \author commands first
        all_authors = []
        for m in re.finditer(r"\\author\s*(?:\[[^\]]*\])?\s*\{", tex):
            content = _extract_braced(tex, m.end() - 1)
            if content:
                all_authors.append(content)

        if all_authors:
            # If multiple \author{} commands, each is one author
            if len(all_authors) > 1:
                names = []
                for a in all_authors:
                    a = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", a)
                    a = re.sub(r"\\[a-zA-Z]+", "", a)
                    a = re.sub(r"[{}]", "", a)
                    a = re.sub(r"\s+", " ", a).strip()
                    if a:
                        names.append(a)
                return ", ".join(names) or None

            # Single \author{} — parse the content
            content = all_authors[0]
            # Strip \thanks{...} (may contain nested braces)
            while r"\thanks" in content:
                tm = re.search(r"\\thanks\s*\{", content)
                if not tm:
                    break
                inner = _extract_braced(content, tm.end() - 1)
                if inner is None:
                    break
                content = content[: tm.start()] + content[tm.end() + len(inner) :]
            # Split by \and
            content = re.sub(r"\\and\b", "\n@@SEP@@\n", content)
            # Split by \\ ... and ... \\ pattern (affiliation blocks)
            content = re.sub(r"\\\\\s*and\s*\\\\", "\n@@SEP@@\n", content)
            content = re.sub(r"(?:^|\\\\)\s*and\s*(?:\\\\|$)", "\n@@SEP@@\n", content)

            parts = content.split("@@SEP@@")
            names = []
            for part in parts:
                # Split by \\ and take the first line (name), skip affiliations
                lines = [line.strip() for line in re.split(r"\\\\", part)]
                # Filter out affiliation lines
                candidate_lines = []
                for line in lines:
                    line_clean = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", line)
                    line_clean = re.sub(r"\\[a-zA-Z]+", "", line_clean)
                    line_clean = re.sub(r"[{}]", "", line_clean).strip()
                    if not line_clean:
                        continue
                    # Skip lines that look like affiliations
                    if re.search(r"(?i)(department|university|institute|school|college|laboratory|@)", line_clean):
                        continue
                    candidate_lines.append(line_clean)
                if candidate_lines:
                    names.append(candidate_lines[0])

            if names:
                # Final cleanup
                result = ", ".join(n for n in names if n)
                result = re.sub(r"\s+", " ", result).strip()
                return result or None
    except Exception:
        pass
    return None


def _extract_abstract(tex: str) -> str | None:
    try:
        m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.DOTALL)
        if m:
            abstract = m.group(1).strip()
            return abstract or None
    except Exception:
        pass
    return None


def _extract_braced(tex: str, start: int) -> str | None:
    """Extract content inside balanced braces starting at tex[start] == '{'.

    Handles escaped braces (\\{ and \\}) correctly.
    """
    if start >= len(tex) or tex[start] != "{":
        return None
    depth, i = 0, start
    while i < len(tex):
        if tex[i] == "\\" and i + 1 < len(tex) and tex[i + 1] in "{}":
            i += 2
            continue
        if tex[i] == "{":
            depth += 1
        elif tex[i] == "}":
            depth -= 1
            if depth == 0:
                return tex[start + 1 : i]
        i += 1
    return None


def count_stats(tex_content: str, pdf_path: str | None = None) -> dict:
    """Count figures, tables, and pages."""
    # Strip commented lines
    lines = [re.sub(r"(?<!\\)%.*", "", line) for line in tex_content.splitlines()]
    text = "\n".join(lines)
    figures = len(re.findall(r"\\begin\{figure\*?\}", text))
    tables = len(re.findall(r"\\begin\{table\*?\}", text))
    pages = _count_pages(pdf_path) if pdf_path else None
    return {"figures": figures, "tables": tables, "pages": pages}


def _count_pages(pdf_path: str) -> int | None:
    if not pdf_path or not os.path.isfile(pdf_path):
        return None
    try:
        out = subprocess.run(
            ["pdfinfo", pdf_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in out.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
    except Exception:
        pass
    # Fallback: count /Type /Page in binary
    try:
        with open(pdf_path, "rb") as f:
            data = f.read()
        # Count occurrences of /Type /Page (not /Pages)
        count = len(re.findall(rb"/Type\s*/Page(?!s)", data))
        return count if count > 0 else None
    except Exception:
        return None


def format_summary(metadata: dict, stats: dict, output_path: str, output_size_mb: float) -> str:
    """Format short summary block for stdout."""
    title = metadata.get("title") or _FALLBACK
    if title != _FALLBACK and len(title) > 70:
        title = title[:67] + "..."
    authors = metadata.get("authors") or _FALLBACK
    abstract = metadata.get("abstract") or _FALLBACK
    if abstract != _FALLBACK and len(abstract) > 150:
        abstract = abstract[:147] + "..."

    comments = _format_comments(stats)
    filename = os.path.basename(output_path)

    lines = [
        "── arXiv Upload Summary ──",
        f"Title:    {title}",
        f"Authors:  {authors}",
        f"Abstract: {abstract}",
        f"Comments: {comments}",
        f"Output:   {filename} ({output_size_mb:.1f} MB)",
    ]
    return "\n".join(lines)


def format_guide(
    metadata: dict,
    stats: dict,
    output_path: str,
    output_size_mb: float,
    kept_files: list[str],
    main_tex: str,
) -> str:
    """Format full upload guide as plain text."""
    title = metadata.get("title") or _FALLBACK
    authors = metadata.get("authors") or _FALLBACK
    abstract = metadata.get("abstract") or _FALLBACK
    comments = _format_comments(stats)
    filename = os.path.basename(output_path)

    file_list = ""
    for f in sorted(kept_files):
        marker = " ← main file" if f == main_tex else ""
        file_list += f"    {f}{marker}\n"

    return f"""\
── arXiv Upload Guide ──

⚠️  Reference only — verify before submitting. arXiv's UI may differ.
    Official docs: https://info.arxiv.org/help/submit_tex.html
    Guide last updated: {GUIDE_LAST_UPDATED}

📋 Your metadata (copy-paste ready):

  Title:
    {title}

  Authors:
    {authors}

  Abstract:
    {abstract}

  Comments:
    {comments} [add conference/journal info if applicable]

────────────────────────────────────────────────────────

📌 Step 1: Start a new submission or replace an existing one
   New submission: go to https://arxiv.org/submit
   Replacement: go to https://arxiv.org/user — find your paper and click "Replace."

📌 Step 2: Choose license
   Choose a license for your submission. The most common choice among
   researchers is "arXiv.org perpetual non-exclusive license."
   See https://info.arxiv.org/help/license/index.html for options.

📌 Step 3: Select category
   Pick your primary subject area (e.g., stat.ME, cs.LG, math.ST).
   You can add cross-list categories on the next screen.

📌 Step 4: Upload files
   Upload: {filename} ({output_size_mb:.1f} MB)
   arXiv will auto-detect {main_tex} as the main file.

   ⚠️  arXiv may warn that .sty or .cls files appear unused.
       IGNORE this — deleting them will break compilation.

📌 Step 5: Check processing
   arXiv compiles your paper. Review the generated PDF carefully.
   Common issues:
   • Fonts look wrong → ensure .bbl is included (latex2arxiv does this)
   • Missing figures → check paths are relative, no absolute paths
   • Date shows today → \\today was used; consider hardcoding the date

📌 Step 6: Fill in metadata
   Paste the title, authors, abstract, and comments from above.
   • "Comments" field: use for page/figure counts, conference info
   • "Journal-ref": leave blank for preprints; fill for published versions
   • "DOI": add if you have one
   • "Report-no": leave blank unless your institution requires one

📌 Step 7: Preview and submit
   Review the abstract rendering (LaTeX math is supported in abstracts).
   Once submitted, your paper enters moderation (typically <1 business day).
   You will receive an arXiv ID once accepted.

📁 Files in your zip:
{file_list}"""


def _format_comments(stats: dict) -> str:
    parts = []
    if stats.get("pages") is not None:
        parts.append(f"{stats['pages']} pages")
    parts.append(f"{stats.get('figures', 0)} figures")
    parts.append(f"{stats.get('tables', 0)} tables")
    return ", ".join(parts)
