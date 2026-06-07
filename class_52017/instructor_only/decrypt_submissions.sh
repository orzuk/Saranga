#!/usr/bin/env bash
# Collect student submissions into a gitignored scratch dir for grading.
#
# Each submissions/<pair>/ contains EITHER:
#   annotate_chapter.py.age   (encrypted to the instructor age key)  -- private
#   annotate_chapter.py       (plaintext)                            -- open
#
# This decrypts/copies each into submissions_dec/<pair>/annotate_chapter.py, which
# you then grade:  grade_all.py --submissions submissions_dec
#
# Usage:
#   AGE_KEY=/path/to/instructor_key.txt ./decrypt_submissions.sh [SUBMISSIONS_DIR] [DEC_DIR]
#
# Requires: age (https://github.com/FiloSottile/age) for the encrypted ones.

set -euo pipefail

SUBM="${1:-submissions}"
DEC="${2:-submissions_dec}"
KEY="${AGE_KEY:-instructor_key.txt}"

# Each pair folder ships a placeholder annotate_chapter.py.age (an encryption of the
# baseline) so the repo looks "submitted" and the board can seed a baseline row. That
# placeholder must NEVER be graded as a real submission: if a pair submits plaintext,
# the leftover dummy .age would otherwise shadow it. Ignore any .age whose hash matches
# the known baseline dummy.
DUMMY_MD5="6ea4773136d1dc5e078c4e1630aaf8f0"

rm -rf "$DEC"; mkdir -p "$DEC"

shopt -s nullglob
found=0
for d in "$SUBM"/*/; do
  pair="$(basename "$d")"
  out="$DEC/$pair"; mkdir -p "$out"
  age_file=""
  for f in "$d"/*.age; do
    if [ "$(md5sum "$f" | cut -d' ' -f1)" = "$DUMMY_MD5" ]; then
      echo "SKIP  [$pair]: $(basename "$f") is the baseline placeholder (not a real submission)"
      continue
    fi
    age_file="$f"; break
  done
  plain="$d/annotate_chapter.py"
  if [ -n "$age_file" ]; then
    [ -f "$KEY" ] || { echo "ERROR: age key not found at '$KEY' (set AGE_KEY=...)"; exit 1; }
    [ -f "$plain" ] && echo "WARN  [$pair]: both .age and plaintext present; using .age (their plaintext may have leaked)"
    age -d -i "$KEY" -o "$out/annotate_chapter.py" "$age_file"
    echo "OK    [$pair]: decrypted $(basename "$age_file")"
    found=$((found+1))
  elif [ -f "$plain" ]; then
    cp "$plain" "$out/annotate_chapter.py"
    echo "OK    [$pair]: plaintext"
    found=$((found+1))
  else
    echo "WARN  [$pair]: no annotate_chapter.py(.age) found, skipping"
    rmdir "$out" 2>/dev/null || true
  fi
done

echo
echo "$found submission(s) collected into $DEC/"
echo "Next:  python3 grade_all.py --submissions $DEC --out results [--test-dir <test_set>]"
