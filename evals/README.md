# Evaluations

The [calculator seeds](scenarios/calc/) contain 10 deterministic expected-output
scenarios, all `expert_reviewed: false`. Pytest exercises them directly.

Later phases add agent evaluation `thresholds.yaml` and `run.py` for citations,
calculator-only quantities, and unverified-rule disclosures.
