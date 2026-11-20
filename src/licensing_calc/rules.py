"""Local, schema-validated rules; no executable code is loaded from documents."""

import json
from datetime import date
from functools import lru_cache
from importlib.resources import files

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import Field, model_validator

from licensing_calc.models import Citation, Model, Product


class Applicability(Model):
    versions: list[str]
    editions: list[str]
    agreements: list[str]


class Rule(Model):
    id: str
    product: Product
    applies_to: Applicability
    parameters: dict[str, int]
    logic: str
    source: Citation
    effective_date: date
    verified: bool = False
    verified_by: str | None
    verified_on: date | None
    notes: str

    @model_validator(mode="after")
    def verification(self) -> "Rule":
        if self.verified and (not self.verified_by or not self.verified_on):
            raise ValueError("Verified rules require reviewer and review date")
        return self


class RuleFamily(Model):
    schema_version: int
    rules: list[Rule] = Field(min_length=1)


@lru_cache(maxsize=1)
def load_rules() -> dict[str, Rule]:
    root = files("licensing_calc")
    schema = json.loads(root.joinpath("rules.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    rules: dict[str, Rule] = {}
    for path in sorted(root.joinpath("rules").iterdir(), key=lambda p: p.name):
        if not path.name.endswith(".yaml"):
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        validator.validate(document)
        family = RuleFamily.model_validate(document)
        for rule in family.rules:
            if rule.id in rules:
                raise ValueError(f"Duplicate rule ID: {rule.id}")
            if rule.logic != rule.id:
                raise ValueError(f"Rule logic must match its registered ID: {rule.id}")
            rules[rule.id] = rule
    if not rules:
        raise ValueError("No licensing rules found")
    return rules
