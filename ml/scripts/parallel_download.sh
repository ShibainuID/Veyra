#!/usr/bin/env bash
# Download a large file over HTTP range requests in N parallel chunks, resuming each chunk until it is
# complete, then concatenate. Useful for slow per-connection hosts (Zenodo, Hugging Face CDN, S3).
# usage: parallel_download.sh URL TOTAL_BYTES OUT_FILE [N]
set -euo pipefail
URL=$1; TOTAL=$2; OUT=$3; N=${4:-16}
CHUNK=$(( (TOTAL + N - 1) / N ))
PARTS="$OUT.parts"
mkdir -p "$PARTS"

fetch() {
  local i=$1 start=$(( $1 * CHUNK ))
  local end=$(( start + CHUNK - 1 )); [ "$end" -ge "$TOTAL" ] && end=$(( TOTAL - 1 ))
  local want=$(( end - start + 1 )) part="$PARTS/p$(printf %03d "$i")"
  for _ in $(seq 1 40); do
    local have; have=$(stat -f%z "$part" 2>/dev/null || stat -c%s "$part" 2>/dev/null || echo 0)
    [ "$have" -ge "$want" ] && return 0
    curl -sL --max-time 600 -r "$(( start + have ))-$end" "$URL" >> "$part" || true
  done
  echo "chunk $i incomplete" >&2
  return 1
}

for i in $(seq 0 $(( N - 1 ))); do fetch "$i" & done
wait
cat "$PARTS"/p* > "$OUT"
SIZE=$(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT")
if [ "$SIZE" -eq "$TOTAL" ]; then rm -rf "$PARTS"; echo "complete $OUT ($SIZE bytes)"; else echo "size mismatch $OUT: $SIZE of $TOTAL" >&2; exit 1; fi
