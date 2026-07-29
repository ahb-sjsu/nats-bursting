#!/bin/bash
# Build a clean, self-contained Overleaf bundle for the INFOCOM submission.
#
# Two things break an Overleaf upload of paper/ as-is.
#   1. THREE files with \documentclass live here (infocom.tex, paper.tex,
#      paper_sc26_revised.tex). Overleaf guesses the main document and often
#      guesses wrong.
#   2. Sixteen build artifacts (.aux .fdb_latexmk .fls .blg .log .out) are
#      committed. They came from MiKTeX on Windows. Overleaf's latexmk reads
#      .fdb_latexmk and stale .aux and then fails in ways that look unrelated
#      to the actual source.
#
# This bundle contains exactly one \documentclass, only the three \input'd
# fragments, the .bib, and only the 3 figures actually referenced (figures/ has
# 30). Upload the zip and Overleaf will pick infocom.tex automatically.
set -e
cd "$(dirname "$0")"
OUT=overleaf_infocom
rm -rf "$OUT" "$OUT.zip"
mkdir -p "$OUT/figures"

cp infocom.tex infocom_aoi_model.tex infocom_eval.tex infocom_appendix.tex \
   infocom.bib "$OUT/"

for f in feedback_phase.pdf tau_sweep.png e9_adaptive_curve.png; do
  cp "figures/$f" "$OUT/figures/$f"
done

cat > "$OUT/README_OVERLEAF.md" <<'EOF'
# INFOCOM submission, Overleaf bundle

**Main document is `infocom.tex`.** It is the only file here with
`\documentclass`, so Overleaf selects it without being told.

Contents are `infocom.tex` plus its three `\input` fragments
(`infocom_aoi_model`, `infocom_eval`, `infocom_appendix`), `infocom.bib`, and the
3 referenced figures. No build artifacts, since those are what break an upload of
the raw `paper/` directory.

## House style enforced in this draft

Applied end to end and worth preserving in edits.

1. No em-dashes, no colons, no semicolons anywhere in prose. Semicolons and
   colons still appear inside TikZ, math and `algorithmic` blocks, where they are
   syntax rather than punctuation.
2. The words gap, regime and paradigm are avoided. The one exception is
   "spectral gap", which is the defined quantity for a Markov chain and has no
   accurate substitute.
3. No equations or mathematical symbols in the abstract or the introduction.
   Both are plain prose. Math begins in Section III.
4. `\paragraph{}` is not used. IEEEtran renders it as "a) Title:" with a colon,
   which violates rule 1. Bold run-in headings are used instead.
5. Sentences state one thing that matters. Self-justifying phrasing such as "to
   our knowledge" or "what is new here" has been removed.

## Before camera-ready

1. **`\blindtrue` to `\blindfalse`** near line 20 of `infocom.tex`. That toggle
   controls the author block, the artifact citations and the PDF metadata. The
   submitted PDF must stay anonymous and the camera-ready must not.
2. **Update the author block** near line 30, which currently lists one author
   under `\blindfalse`.
3. Rerun bibtex after any `.bib` edit. Overleaf does this on a full recompile.

## Compiler and budget

pdfLaTeX. Uses `IEEEtran` (conference), `algorithm` with `algpseudocode`, `tikz`
with `arrows.meta` and `positioning`, `amsmath`, `amssymb`, `amsthm`, `booktabs`,
`multirow`, `graphicx` and `hyperref` with `hidelinks`. All are in Overleaf's TeX
Live.

The current draft is **9 pages including references**, inside the limit of 9
content pages plus 1 reference page. There is roughly one column of headroom.
EOF

if command -v zip >/dev/null 2>&1; then
  zip -qr "$OUT.zip" "$OUT"
  echo "built $OUT.zip ($(du -h "$OUT.zip" | cut -f1))"
else
  echo "built $OUT/ (no zip binary, archive the directory manually)"
fi
find "$OUT" -type f | sort
