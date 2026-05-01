try:
    import bibtexparser
    from bibtexparser.bwriter import BibTexWriter
    from bibtexparser.bparser import BibTexParser
    HAS_BIBTEXPARSER = True
except ImportError:
    HAS_BIBTEXPARSER = False

# Canonical field order per entry type
_FIELD_ORDER = [
    'author', 'title', 'journal', 'booktitle', 'year', 'volume',
    'number', 'pages', 'publisher', 'address', 'editor',
    'series', 'edition', 'month', 'doi', 'url', 'note',
]

# Fields to strip before submission
_PRIVATE_FIELDS = {'abstract', 'file', 'keywords', 'mendeley-tags', 'annote'}


def normalize_bibtex(source: str) -> str:
    if not HAS_BIBTEXPARSER:
        print("  [warn] bibtexparser not installed; skipping BibTeX normalization")
        return source

    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    db = bibtexparser.loads(source, parser)

    seen_keys = {}
    unique_entries = []
    for entry in db.entries:
        # Deduplicate by key
        key = entry.get('doi') or entry.get('title', '')
        key = key.lower().strip()
        if key and key in seen_keys:
            print(f"  [warn] duplicate entry skipped: {entry['ID']}")
            continue
        if key:
            seen_keys[key] = True

        # Strip private fields
        for f in _PRIVATE_FIELDS:
            entry.pop(f, None)

        # Reorder fields
        ordered = {k: entry[k] for k in ['ENTRYTYPE', 'ID']}
        for f in _FIELD_ORDER:
            if f in entry:
                ordered[f] = entry[f]
        for f in entry:
            if f not in ordered:
                ordered[f] = entry[f]
        unique_entries.append(ordered)

    db.entries = unique_entries
    writer = BibTexWriter()
    writer.indent = '  '
    writer.comma_first = False
    return bibtexparser.dumps(db, writer)
