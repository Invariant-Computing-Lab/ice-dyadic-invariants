# ICE Quotient-Geometric Invariants - Reproducibility Package

This package accompanies the manuscript **Relational Identity Under Transformation in Dyadic Neural Systems**.

## Scope
All numerical results are **synthetic**. They test mathematical/statistical behavior of candidate invariants. They do **not** demonstrate intentionality-driven inter-brain synchrony, shared consciousness, empathy causation, clinical validity, or biological identity invariants.

## Reproduce
From the package root:

```bash
python -m pip install -r requirements.txt
bash run_all.sh
```

The master random seed is `20260812`.

## Contents
- `code/ice_invariant_validation.py` - S1-S6 synthetic experiments and figures
- `code/build_documents.py` - DOCX manuscript/supplement builder
- `results/` - trial/replicate-level CSVs and JSON summary
- `figures/` - 300 dpi manuscript and supplementary figures
- `docs/` - main manuscript, supplement, PDFs, and cover-letter draft
- `sha256_manifest.json` - file-integrity manifest

## Experimental modules
S1: exact O(p) x O(q) invariance and out-of-group scaling.
S2: restricted invertible-linear extension using canonical-correlation spectra.
S3: minimal-generator ablation and OOD relational-class reconstruction.
S4: EEG-like dual-signal simulation with partner-shuffled surrogate controls.
S5: cross-level reconstructibility with linked, independent-null, and common-cause worlds.
S6: controlled approach to a rank-deficient algebraic locus.

## Claim boundary
A mathematically invariant statistic need not be partner-specific, causal, biologically valid, or empirically useful. The manuscript deliberately separates these properties.
