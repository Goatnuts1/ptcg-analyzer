#!/bin/bash
# Render a playbook HTML file to PDF via headless Chrome.
# Usage: render_pdf.sh <input.html> <output.pdf>
#
# Flags matter — these were hard-won debugging a real print bug (see SKILL.md
# "Known print-CSS gotchas"): --no-sandbox avoids a headless-Chrome crash in
# some sandboxed shells, --no-pdf-header-footer strips Chrome's default
# date/URL header/footer strip that otherwise overlays the design.
set -euo pipefail

IN="$1"
OUT="$2"

if [ -z "$IN" ] || [ -z "$OUT" ]; then
  echo "Usage: render_pdf.sh <input.html> <output.pdf>" >&2
  exit 1
fi

ABS_IN="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --no-sandbox \
  --print-to-pdf="$OUT" \
  --no-pdf-header-footer \
  "file://$ABS_IN"

echo "Wrote $OUT"
file "$OUT"
