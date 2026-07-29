#!/bin/bash
# Build a clean, self-contained Overleaf bundle for the INFOCOM submission.
#
# Two things break an Overleaf upload of paper/ as-is:
#   1. THREE files with \documentclass live here (infocom.tex, paper.tex,
#      paper_sc26_revised.tex). Overleaf guesses the main document and often
#      guesses wrong.
#   2. Sixteen build artifacts (.aux .fdb_latexmk .fls .blg .log .out) are
#      committed. They came from MiKTeX on Windows; Overleaf's latexmk reads
#      .fdb_latexmk and stale .aux and then fails in ways that look unrelated
#      to the actual source.
#
# This bundle contains exactly one \documentclass, only the four \input'd
# fragments, the .bib, and only the 8 figures actually referenced (figures/ has
# 30). Upload the zip; Overleaf will pick infocom.tex automatically.
set -e
cd "$(dirname "$0")"
OUT=overleaf_infocom
rm -rf "$OUT" "$OUT.zip"
mkdir -p "$OUT/figures"

cp infocom.tex infocom_aoi_model.tex infocom_eval.tex \
   crossdomain_predictive.tex infocom_appendix.tex infocom.bib "$OUT/"

for f in e9_adaptive_curve.png e9_competitor_harm.png feedback_phase.pdf \
         pareto_contended_poisson.png pareto_contended_square.png \
         pareto_cpu.png pareto_gpu.png tau_sweep.png; do
  cp "figures/$f" "$OUT/figures/$f"
done

cat > "$OUT/README_OVERLEAF.md" <<'EOF'
# INFOCOM submission — Overleaf bundle

**Main document: `infocom.tex`.** It is the only file here with
`\documentclass`, so Overleaf selects it without being told.

Contents: `infocom.tex` plus its four `\input` fragments
(`infocom_aoi_model`, `infocom_eval`, `crossdomain_predictive`,
`infocom_appendix`), `infocom.bib`, and the 8 referenced figures. No build
artifacts — those are what break an upload of the raw `paper/` directory.

## Before camera-ready

1. **`\blindtrue` → `\blindfalse`** (line ~20 of `infocom.tex`). The toggle
   controls the author block, the artifact citations, and the PDF metadata; the
   submitted PDF must stay anonymous, the camera-ready must not.
2. **Update the author block** (line ~30) — it currently lists one author under
   `\blindfalse`.
3. Rerun bibtex after any `.bib` edit; Overleaf does this automatically on a
   full recompile.

## Compiler

pdfLaTeX. Uses `IEEEtran` (conference), `tikz` with `arrows.meta`/`positioning`,
`amsmath`, `amssymb`, `amsthm`, `booktabs`, `multirow`, `graphicx`,
`hyperref[hidelinks]` — all present in Overleaf's TeX Live.

The page budget is tight: **9 content pages + 1 references page**, which is the
INFOCOM limit exactly. Any prose addition needs a compensating cut.
EOF

if command -v zip >/dev/null 2>&1; then
  zip -qr "$OUT.zip" "$OUT"
  echo "built $OUT.zip ($(du -h "$OUT.zip" | cut -f1))"
else
  echo "built $OUT/ (no zip binary; archive the directory manually)"
fi
find "$OUT" -type f | sort
