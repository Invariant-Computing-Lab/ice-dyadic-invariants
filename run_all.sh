#!/usr/bin/env bash
set -euo pipefail
python code/ice_invariant_validation.py
python code/build_documents.py
