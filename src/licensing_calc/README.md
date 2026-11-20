# Licensing calculator

Pure deterministic Python calculations with Pydantic v2 input/output models,
schema-validated local YAML rules, and explicit missing-input reporting.

```python
from licensing_calc import Inventory, calculate, compare_editions
```

See [rule semantics and expert review](../../docs/rules.md) and
[seed scenarios](../../evals/scenarios/calc/). All seeds are unverified and
limited to the documented current EA snapshot; they are not entitlement advice.
