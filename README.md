# On-Prem Licensing Advisor

Infrastructure and deterministic Python calculator for a cited Microsoft server
licensing advisor. Guidance only; no quotes or pricing. All seeded licensing
rules are unverified pending expert review; see [rules](docs/rules.md).

Start with [setup](docs/setup.md). Future application work is described in the
component READMEs. This phase deploys a public placeholder, not a licensing API.

## Local checks

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy
pytest
az bicep build --file infra/main.bicep
az bicep lint --file infra/main.bicep
```

CI needs no Azure sign-in. Bootstrap and deployment are deliberately human-triggered
after merge; see [setup](docs/setup.md) for cloud selection and approval requirements.
