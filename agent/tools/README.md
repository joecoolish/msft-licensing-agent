# Agent tools

`calculate_licenses.schema.json` is generated from Pydantic `Inventory`, not
hand-authored. Regenerate with `python -m licensing_calc.schema`; pytest fails
if it is stale. It is the tool's argument schema, not a registration envelope.
