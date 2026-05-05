#!/usr/bin/env bash
# Zip and run latex2arxiv against every fixture in this directory.
# Pass --compile to also exercise the pdflatex/biber path (requires TeX Live).
#
# Usage:
#   tests/fixtures/run_all.sh           # dry-run on each
#   tests/fixtures/run_all.sh --compile # full pipeline
#
# Output: per-fixture filtered log (errors/warnings/summary), colored on TTY,
# followed by a one-line-per-fixture status table.

set -o pipefail

FIXTURES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$FIXTURES_DIR/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Always run from source so the runner exercises the working tree, not a
# stale installed version on $PATH.
L2A=(python3 "$REPO_ROOT/converter.py")

EXTRA_ARGS=("$@")
if [[ "${1-}" != "--compile" ]]; then
    EXTRA_ARGS=(--dry-run)
fi

# Colors only when stdout is a TTY (avoids leaking ANSI into log files).
if [[ -t 1 ]]; then
    RED=$'\033[31m'
    YELLOW=$'\033[33m'
    GREEN=$'\033[32m'
    BOLD=$'\033[1m'
    DIM=$'\033[2m'
    RESET=$'\033[0m'
else
    RED='' YELLOW='' GREEN='' BOLD='' DIM='' RESET=''
fi

# Stash per-fixture results for the summary table at the end.
declare -a STATUSES

TOTAL=0
NONZERO=0
for fixture in "$FIXTURES_DIR"/*/; do
    name="$(basename "$fixture")"
    TOTAL=$((TOTAL + 1))
    echo "${BOLD}=== $name ===${RESET}"

    zip_path="$WORK/$name.zip"
    out_path="$WORK/$name-out.zip"
    (cd "$fixture" && zip -qr "$zip_path" . -x ".DS_Store" "*.DS_Store")

    cfg_args=()
    if [[ -f "$fixture/arxiv_config.yaml" ]]; then
        cfg_args=(--config "$fixture/arxiv_config.yaml")
    fi

    # Capture full output once so we can both display (filtered+colored) and
    # parse the Summary line for the status table.
    output=$("${L2A[@]}" "$zip_path" "$out_path" "${cfg_args[@]}" "${EXTRA_ARGS[@]}" 2>&1)
    rc=$?

    # Live filtered, colored output. head bound is generous; pre-flight-warnings
    # alone has ~10 issue lines.
    echo "$output" \
        | grep -E '(remove:|Summary:|\[warn\]|\[error\]|main tex:|PDF →|Done →)' \
        | head -40 \
        | sed -E \
            -e "s/\[error\]/${RED}[error]${RESET}/g" \
            -e "s/\[warn\]/${YELLOW}[warn]${RESET}/g" \
            -e "s/^(Summary:.*)/${BOLD}\1${RESET}/" \
            -e "s/^(Done →.*)/${DIM}\1${RESET}/" \
            -e "s/^(  PDF →.*)/${DIM}\1${RESET}/"

    # Parse the Summary line — format: "Summary: ... | N errors, N warnings"
    summary_line=$(echo "$output" | grep -E '^Summary:' | head -1)
    errors=$(echo "$summary_line" | sed -nE 's/.*\| ([0-9]+) errors?,.*/\1/p')
    warnings=$(echo "$summary_line" | sed -nE 's/.*, ([0-9]+) warnings?.*/\1/p')
    errors=${errors:-?}
    warnings=${warnings:-?}

    STATUSES+=("$name|$errors|$warnings|$rc")
    if [[ $rc -ne 0 ]]; then
        NONZERO=$((NONZERO + 1))
    fi
    echo
done

# ─── Summary table ──────────────────────────────────────────────────────────
echo "${BOLD}── Summary ──${RESET}"
for entry in "${STATUSES[@]}"; do
    IFS='|' read -r name errors warnings rc <<< "$entry"
    if [[ "$errors" == "0" && "$warnings" == "0" ]]; then
        status="${GREEN}✓ clean${RESET}"
    elif [[ "$errors" == "0" ]]; then
        status="${YELLOW}$warnings warning(s)${RESET}"
    else
        status="${RED}$errors error(s), $warnings warning(s)${RESET}"
    fi
    printf "  %-28s  %s\n" "$name" "$status"
done
echo
echo "$TOTAL fixtures ran, $NONZERO with non-zero exit (05-pre-flight-warnings is expected)."
