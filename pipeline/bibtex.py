from typing import Callable

try:
    import bibtexparser
    from bibtexparser.bwriter import BibTexWriter
    from bibtexparser.bparser import BibTexParser

    HAS_BIBTEXPARSER = True
except ImportError:
    HAS_BIBTEXPARSER = False

# Canonical field order per entry type
_FIELD_ORDER = [
    "author",
    "title",
    "journal",
    "booktitle",
    "year",
    "volume",
    "number",
    "pages",
    "publisher",
    "address",
    "editor",
    "series",
    "edition",
    "month",
    "doi",
    "url",
    "note",
]

# Fields to strip before submission
_PRIVATE_FIELDS = {"abstract", "file", "keywords", "mendeley-tags", "annote"}


def normalize_bibtex(
    source: str,
    cited_keys: set | None = None,
    warn_fn: Callable[[str], None] | None = None,
    is_biblatex: bool = False,
) -> str:
    _warn: Callable[[str], None] = warn_fn or (lambda msg: print(f"  [warn] {msg}", file=__import__("sys").stderr))
    if not HAS_BIBTEXPARSER:
        _warn("bibtexparser not installed; skipping BibTeX normalization")
        return source

    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    db = bibtexparser.loads(source, parser)

    # Group entries by dedup key (doi or title)
    groups: dict[str, list] = {}
    no_key = []
    for entry in db.entries:
        dedup = (entry.get("doi") or entry.get("title", "")).lower().strip()
        if dedup:
            groups.setdefault(dedup, []).append(entry)
        else:
            no_key.append(entry)

    # Strip private fields. biblatex: 'keywords' is functional
    # (\printbibliography[keyword=...]) — keep it there.
    private_fields = _PRIVATE_FIELDS - {"keywords"} if is_biblatex else _PRIVATE_FIELDS

    unique_entries = []
    for dedup, entries in groups.items():
        if len(entries) == 1:
            chosen = entries[0]
        else:
            # Prefer the entry whose ID is actually cited in the tex source
            if cited_keys:
                cited = [e for e in entries if e["ID"] in cited_keys]
                chosen = cited[0] if cited else entries[0]
            else:
                chosen = entries[0]
            skipped = [e["ID"] for e in entries if e is not chosen]
            for s in skipped:
                _warn(f"duplicate entry skipped: {s}")

        for f in private_fields:
            chosen.pop(f, None)

        # Reorder fields
        ordered = {k: chosen[k] for k in ["ENTRYTYPE", "ID"]}
        for f in _FIELD_ORDER:
            if f in chosen:
                ordered[f] = chosen[f]
        for f in chosen:
            if f not in ordered:
                ordered[f] = chosen[f]
        unique_entries.append(ordered)

    for entry in no_key:
        for f in private_fields:
            entry.pop(f, None)
    unique_entries.extend(no_key)
    db.entries = unique_entries
    writer = BibTexWriter()
    writer.indent = "  "
    writer.comma_first = False
    return bibtexparser.dumps(db, writer)
