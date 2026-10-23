# Deliverable manifest

## Submission-facing documents
- `docs/ICE_Quotient_Geometric_Invariants_Main_Manuscript.docx` and `.pdf` - journal-neutral theory/methods manuscript.
- `docs/ICE_Quotient_Geometric_Invariants_Supplementary_Appendix.docx` and `.pdf` - formal claims, proofs, full synthetic specifications, statistical controls, claim-audit ledger, and reproducibility map.
- `docs/Cover_Letter_Draft.docx` and `.pdf` - neutral journal cover-letter draft.

## Reproducibility
- `code/ice_invariant_validation.py` - all S1-S6 simulations, statistics, CSVs, and figures.
- `code/build_documents.py` - deterministic document builder from result files.
- `results/` - machine-readable replicate/trial summaries.
- `figures/` - 300-dpi manuscript figures.
- `requirements.txt`, `ENVIRONMENT.txt`, and `run_all.sh` - environment and execution entry points.
- `CITATION.cff` - software citation metadata.
- `sha256_manifest.json` - file integrity hashes.

## Scope boundary
All numerical evidence in this package is synthetic. The package validates the behavior and failure modes of candidate invariant constructions under declared generators. It does not constitute biological validation of ICE or evidence for shared consciousness, remote neural coupling, or intentionality-driven inter-brain synchronization.
