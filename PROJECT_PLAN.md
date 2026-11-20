# Licensing Agent — Project Plan & Status

> **Single source of truth** for build order and progress. Keep this file at the repo root.
> **GitHub Copilot:** before doing any work, follow **Section 9 — Agent protocol**.

**Last audit:** 2026-11-20 (local repository contents and executable checks; GitHub/runtime unavailable)
**Current phase:** Phase 2 — implementation checks complete; P2.6 SME ownership/review gate remains human-blocked. Phase 1 P1.3 gaps require Learn MCP access before implementation; Phase 3 cannot start without deployed dev evidence.

---

## 1. Goal

A web-based agent that helps customers work out which Microsoft licenses they need for an **on-premises** deployment. It interviews the user about their environment, retrieves cited guidance from official licensing documents, and calculates quantities with a deterministic, testable calculator. Output is an **estimate with sources, not a quote** — no pricing.

## 2. Architecture at a glance

```
Power Apps code app (React/TS/Fluent UI v9)         Standalone web (optional, MSAL)
        │ custom connector (OpenAPI 2.0, Entra OAuth)        │
        └───────────────┬────────────────────────────────────┘
                        ▼
        FastAPI on Azure Container Apps (managed identity, Entra JWT)
          POST message → 202 + jobId | GET /api/jobs/{id} | SSE (standalone only)
          job + conversation state → Cosmos DB (database: appstate)
                        │
                        ▼
        Microsoft Foundry Agent Service (azure-ai-projects >= 2.x, Responses + Conversations)
          prompt agent · model: GPT-5.4 (version 2026-03-05, GlobalStandard)
          tools: file_search (licensing docs vector store) + function tool → licensing_calc
          standard agent setup: own Storage · AI Search · Cosmos DB
```

Core rules: the model never computes quantities (the calculator does); rules live in YAML with source, effective date and a `verified` flag; no prices anywhere; everything deploys through Bicep + GitHub Actions with OIDC.

## 3. Non-negotiables (summary)

The authoritative list is in `.github/copilot-instructions.md`. If the two disagree, that file wins.

1. Check current docs through the Microsoft Learn MCP server before writing Azure, Foundry or Power Platform code. Record any deviation from this plan in the Decisions log.
2. Use the **new** Foundry Agent Service API (Responses + Conversations, `agents.create_version`). Do **not** use the classic threads/runs API (retires 2027-03-31).
3. No secrets in the repo or workflows: OIDC for GitHub → Azure, managed identity at runtime.
4. The model never computes license quantities; `licensing_calc` does.
5. No invented licensing rules: every rule has `source`, `effective_date` and `verified` (default `false`). Only a licensing SME sets `verified: true`.
6. No pricing, prices or cost estimates anywhere (code, prompts, UI, evals).
7. Cloud-agnostic: works in `AzureCloud` and `AzureUSGovernment` via the `AZURE_CLOUD` variable and `environment()` in Bicep.
8. Stable resource names: no `utcNow()` or timestamps in names; fixed deployment name `licensing-agent-<env>`.
9. Power Platform calls must return within 120 seconds → async job pattern (202 + poll).
10. Tests and CI green before merge; one phase per PR.

## 4. Target repo layout

```
.github/
  copilot-instructions.md
  CODEOWNERS
  actions/get-infra-outputs/action.yml
  workflows/
    copilot-setup-steps.yml   ci.yml   infra.yml   app.yml
    agent.yml   powerapps.yml   evals.yml
infra/
  main.bicep
  modules/
  env/dev.bicepparam
  env/prod.bicepparam
scripts/bootstrap/bootstrap.sh
src/
  licensing_calc/            # pure Python calculator + rules/*.yaml + schema
  api/                       # FastAPI service + Dockerfile
agent/                       # agent.yaml, instructions.md, deploy_agent.py
knowledge/                   # manifest.yaml, ingest_knowledge.py
connector/                   # Power Platform custom connector (OpenAPI 2.0)
web/                         # Power Apps code app (React + TS + Vite + Fluent UI v9)
evals/                       # scenarios/, run.py, thresholds.yaml
tests/
docs/                        # setup.md, powerapps-setup.md, rules-authoring.md, operations.md
PROJECT_PLAN.md
```

## 5. Status board

Legend: ✅ Done · 🟡 Partial · ⬜ Not started · 👤 Needs human confirmation · ⛔ Blocked

| Phase | Name | Status | Evidence (paths, SHAs, run IDs) | Last verified |
|---|---|---|---|---|
| 0 | Prerequisites | 🟡 👤 | Instructions present; no `.git` metadata or remote; Learn MCP tools unavailable; subscription/quota/documents/SMEs unconfirmed | 2026-11-20 |
| 1 | Scaffold, infrastructure & pipelines | 🟡 👤 | Scaffold, three workflows, bootstrap, output action and Bicep audited; local build/lint pass; P1.3 gaps below; no dev deployment/CI evidence | 2026-11-20 |
| 2 | Licensing calculator | 🟡 👤 | Models/engine with per-line disclosure, 13 rules, generated tool schema, 10 seed scenarios, `tests/test_calculator.py`, `docs/rules.md`; 137 tests pass; only P2.6 ownership/review gate pending in build checklist | 2026-11-20 |
| 3 | Agent + API | 🟡 ⛔ | Function parameters schema exists; agent/API/ingestion otherwise placeholders; depends on deployed dev infrastructure | 2026-11-20 |
| 4 | Power Apps code app + connector | ⬜ ⛔ | Component READMEs and placeholder setup doc only; no Node manifest/connector; depends on Phase 3 | 2026-11-20 |
| 5 | Evals & observability | 🟡 ⛔ | Ten unapproved offline calculator seeds run in pytest; no runner, thresholds, workflow or workbook; depends on Phase 3 | 2026-11-20 |
| 6 | Pilot & production | ⬜ ⛔ | No deployment/pilot evidence; operations doc is only an infrastructure runbook; depends on Phases 4 and 5 | 2026-11-20 |

### Audit evidence and limits

- Baseline: `ruff check .`, `ruff format --check .` (28 files), `mypy` (8 source files), and `pytest -q` (131 passed). The initial pytest run had 23 setup errors because Git Bash lacked `jq`; rerun passed using checksum-verified jq 1.8.1 in `%TEMP%/licensing-agent-jq`, with PATH changed only for that invocation.
- Final Phase 2 checks: 137 tests passed; Ruff lint/format and strict mypy passed; editor diagnostics clear. Six added regression cases exercise all-unverified, mixed and all-verified mock rules for Windows/RDS and SQL failover; seed/alternative/serialization checks preserve disclosure. Real YAML approvals remain unchanged. Web/online/runtime gates remain unavailable, not passed.
- `az bicep build` and `az bicep lint` passed; Bicep MCP compilation also returned no diagnostics. CLI lint reported an unrelated local `containerapp` extension-loading warning. Both parameter files compiled for AzureCloud and AzureUSGovernment with CI placeholder identity/audience inputs. Without those required inputs the MCP parameter compiler reports BCP427, as expected.
- Bash syntax checks passed. Searches found no timestamp naming, stored workflow credentials, classic agent API use, or forbidden calculator SDK imports/monetary fields. The broad `cost` scan matched the word `concurrency`, not pricing.
- The workspace has no `.git` directory. Git status/remote inspection failed, so SHAs, committed instruction status, open/merged PRs, issues, and Actions history cannot be read. No commit, branch, PR, or cloud deployment was made.
- Web checks and `python evals/run.py --offline` are unavailable because their implementations/manifests do not exist. Green offline checks do not prove Azure provisioning, licensing accuracy, SME approval, or end-to-end behavior.

## 6. Human action required

No human-only item has been marked complete. Replace angle-bracket placeholders below with approved values; do not run bootstrap/deployment until prerequisites are confirmed.

- **P0.1 / repository evidence:** provide the actual GitHub clone/remote (this workspace lacks `.git`); in repository Settings → Copilot → Coding agent, confirm the agent is enabled. From that clone run `gh pr list --state open`, `gh pr list --state merged --limit 20`, `gh issue list --state open`, and `gh run list --limit 20` to check in-flight work and CI.
- **P0.2:** in the actual clone, run `git ls-files .github/copilot-instructions.md` and confirm the instructions are committed; only local contents were verified here.
- **P0.3:** configure Settings → Copilot → Coding agent → MCP configuration with HTTP URL `https://learn.microsoft.com/api/mcp`; also expose Microsoft Learn MCP to this editor session and verify `microsoft_docs_search` can be called. New Azure integration work is blocked until this works or the user explicitly authorizes a documentation-access exception.
- **P0.4 / H1.3:** choose cloud/subscription/region, then confirm GPT-5.4 version `2026-03-05`, deployment SKU and capacity in Foundry quota/region availability. Confirm Government tool/API availability separately; parameter compilation is not availability evidence.
- **P0.5:** collect official dated Product Terms and product guides; preserve the November 2026 seed's applicable sources and agreement context for SME review. No collected Blob documents or manifest were available to audit.
- **P0.6 / P2.6:** supply real licensing SME GitHub user/team handles; replace every `@<licensing-reviewers>` in `.github/CODEOWNERS`. In Settings → Rules → Rulesets (or branch protection), require code-owner review for the default branch. The placeholder is not an enforced gate.
- **H1.1:** after Phase 1 gaps are resolved, use Azure Cloud Shell Bash with subscription Owner/PIM permissions: `az cloud set --name <AzureCloud-or-AzureUSGovernment>`, `az login`, `az account set --subscription '<subscription-id>'`, `gh auth login`, then `bash scripts/bootstrap/bootstrap.sh --cloud <cloud> --location <quota-verified-region> --prefix <stable-prefix> --repo <OWNER/REPO>`. See `docs/setup.md` for exact rights and Entra fallback steps.
- **H1.2:** in Settings → Environments, confirm `dev` and `prod`; add required reviewers to `prod`. Confirm `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `AZURE_CLOUD`, `NAME_PREFIX`, `DEPLOY_PRINCIPAL_ID`, and `API_APP_ID_URI` on each environment.
- **H1.3 / Phase 1 runtime exit:** after reviewing infrastructure gaps and what-if, run `gh workflow run infra.yml --repo <OWNER/REPO> -f environment=dev`; inspect the successful capability-host poll and get-infra-outputs steps. Confirm latest CI on `main` succeeds; the initial health endpoint is a public placeholder, not the licensing API.
- **Phase 2 licensing sign-off:** SMEs independently check each rule/source/function and scenario. Only a reviewed PR may set `verified: true` with `verified_by`/`verified_on`, or scenario `expert_reviewed: true`; all 13 rules and 10 scenarios remain unapproved.
- **H3.1 (after ingestion exists):** in Storage → `licensing-docs`, upload official PDFs using Entra/container-scoped Blob Data Contributor rights; populate the future `knowledge/manifest.yaml`, then dispatch `agent.yml` for dev. No ingestion workflow exists yet.
- **H3.2:** in Entra → App registrations, confirm the single-tenant API registration, v2 access tokens, `api://<application-client-id>` audience, and `access_as_user` scope; register the future standalone client and connector consent. Bootstrap does not prove those registrations exist.
- **Phase 3 runtime exit (after implementation):** inspect successful dev `app.yml` and `agent.yml` runs, verify `/healthz` returns 200, then run an authenticated conversation through 202/job polling and check cited calculator line items.
- **H4.1:** in Power Platform admin center, select the approved environment and enable code apps after confirming current tenant/cloud availability.
- **H4.2:** after the connector exists, create its connection in the target environment and complete Entra delegated consent.
- **H4.3:** after web implementation, perform the first interactive `pa app push` in the approved environment; exact current CLI setup/auth flags must be verified with Learn documentation in Phase 4.
- **H4.4:** share the published app with the CI service principal's Enterprise Application **object ID**, granting edit rights; do not substitute the app/client ID.
- **H4.5 / Phase 4 runtime exit:** confirm each pilot user's eligible Power Apps entitlement; open the published app and complete a scenario, including polling, citations and unverified warnings.
- **Phase 5 sign-off:** SMEs approve eval scenarios through functioning CODEOWNERS review. After runner/workflow implementation, record baseline scores and configure the evaluation gate in branch rules.
- **P6.1:** once Phases 4 and 5 exit, dispatch `infra.yml`, `app.yml`, and `agent.yml` with `environment=prod`, reviewing what-if and approving the protected environment.
- **P6.2 / P6.3:** pilot with 5–10 approved users; file feedback issues labelled `pilot-feedback`; confirm every exercised rule is SME-verified or clearly disclosed as unverified in pilot output.
- **P6.4:** confirm required public/Government cloud and region support, set Azure budget alerts, and approve data-retention policy (currently jobs have seven-day TTL, while conversation/feedback retention requires review).
- **Phase 6 exit:** obtain the licensing SMEs' explicit go/no-go after pilot, coverage, availability and retention review.

---

## 7. Phases

### Phase 0 — Prerequisites (human)

**Depends on:** —

- [ ] **P0.1** GitHub repo created; Copilot coding agent enabled. 👤
- [ ] **P0.2** 🟡 `.github/copilot-instructions.md` locally matches Section 3; committed status cannot be verified without Git metadata. 👤
- [ ] **P0.3** 👤 Microsoft Learn MCP server not exposed in this session; `microsoft_docs_search` unavailable. Configure the HTTP server at `https://learn.microsoft.com/api/mcp` and verify a successful call.
- [ ] **P0.4** Azure subscription and region chosen; GPT-5.4 quota available. 👤
- [ ] **P0.5** Licensing source documents collected (Product Terms, product licensing guides, etc.). 👤
- [ ] **P0.6** Licensing SME reviewers identified (GitHub handles for CODEOWNERS). 👤

**Exit:** P0.2 and P0.3 verified.

---

### Phase 1 — Scaffold, infrastructure & pipelines (Issue 1)

**Depends on:** Phase 0

**Build**

- [x] **P1.1** ✅ Repo scaffold contents audited: README, gitignore, Python >=3.12 packaging and Ruff/mypy/pytest configuration, docs.
- [x] **P1.2** ✅ Setup workflow has job `copilot-setup-steps`, Python 3.12, Node 22 LTS, Azure CLI/Bicep, and editable project dependencies.
- [ ] **P1.3** 🟡 `infra/main.bicep` and modules compile/lint, with deterministic names, model parameters, AAD connections, capability-host ordering, appstate data role, API identity/ACR and monitoring. **Missing:** explicit >=3000 RU/s total or serverless agent Cosmos setup (only appstate 400 RU/s is declared); API Blob Reader in the planned role list (only deploy identity receives it). The Bicep default remains nginx; only the infra workflow preserves a running image. Runtime and current-doc validation remain unconfirmed.
  - Foundry account + project; GPT-5.4 deployment (`2026-03-05`, `GlobalStandard`, capacity as a parameter)
  - Standard agent setup dependencies: Storage, AI Search, Cosmos DB (≥ 3000 RU/s total, or serverless), capability hosts
  - Storage container `licensing-docs`
  - App Cosmos database `appstate` + containers; **data-plane** SQL role assignment for the API identity (not ARM RBAC)
  - Azure Container Registry; Container Apps environment + app (image parameter defaults to the **currently running image**, not the placeholder)
  - User-assigned managed identity for the API; role assignments (Foundry User, AcrPull, Storage Blob Data Reader, Cosmos data role)
  - Log Analytics + Application Insights
  - `utcNow()` timestamp suffix **removed**; names derived from env + `uniqueString(resourceGroup().id)`
- [x] **P1.4** ✅ Both parameter files compile for both clouds with CI placeholder inputs; real identity/audience/quota remain human configuration.
- [x] **P1.5** ✅ Bootstrap content and mocked tests cover reusable resources/app registration, both environment federations, constrained RBAC writes/deletes, variables, Entra fallback and preservation of existing environment protection. Azure execution remains H1.1.
- [x] **P1.6** ✅ CI runs Ruff, format, mypy, pytest, Bicep build/lint/parameter compilation and Bash syntax on PR/push (including main). Local checks pass; no Actions history available.
- [x] **P1.7** ✅ Workflow uses validate/what-if/deploy, stable deployment names, bounded two-host poll, OIDC/cloud audience, per-environment concurrency and GitHub environment selection. Actual prod reviewers/dev deployment remain H1.2/H1.3.
- [x] **P1.8** ✅ Composite action exports nine validated outputs from stable `licensing-agent-$TARGET_ENVIRONMENT`; mocked tests pass. Live endpoints unconfirmed.
- [x] **P1.9** ✅ `docs/setup.md` covers bootstrap, first deployment, human permissions, variables, cloud differences, placeholder contract, outputs and troubleshooting.

**Verify (repo)**

- All files above exist; `az bicep build --file infra/main.bicep` succeeds.
- `grep -rn "utcNow" infra/` finds nothing used in resource names.
- No `client-secret`, `AZURE_CREDENTIALS`, keys or connection strings in workflows; `azure/login` uses OIDC.
- Deployment name is literally `licensing-agent-<env>` in `infra.yml` and the composite action.
- `AZURE_CLOUD` is passed to `azure/login` (`environment:`); Bicep uses `environment()` for endpoints and suffixes.

**Verify (runtime — via Actions run history if readable, otherwise 👤)**

- `ci.yml` green on `main`.
- `infra.yml` succeeded for `dev`, including the capability host poll.

**Human steps after this phase** 👤

- [ ] **H1.1** Run `scripts/bootstrap/bootstrap.sh` in Azure Cloud Shell as Owner (or Contributor + User Access Administrator).
- [ ] **H1.2** Create GitHub environments `dev` and `prod`; add required reviewers on `prod`; set/confirm the variables from bootstrap.
- [ ] **H1.3** Confirm GPT-5.4 quota in the region; run `infra.yml` for `dev`.

**Exit:** dev infrastructure deployed; `get-infra-outputs` returns endpoints.

---

### Phase 2 — Licensing calculator (Issue 2)

**Depends on:** P1.1 and P1.6 (deployed infra **not** required — can run in parallel with Phase 1 human steps)

**Build**

- [x] **P2.1** ✅ Local-only package; network-blocking test and dependency/import audit pass; no Azure/LLM SDK dependencies.
- [x] **P2.2** ✅ Strict inventory/topology/population/entitlement models and cited estimate exist. Estimate-level assumptions, warnings and `unverified_rules_used` remain; every line now has a required `unverified` flag derived from its applied rules, including waiver and alternative lines. Focused and full regression tests pass; Inventory/function input schema is unchanged.
- [x] **P2.3** ✅ Five YAML families contain 13 schema-validated sourced, dated, unverified rules. Existing `notes` carries the human-readable description; no rule values or verification states changed by this audit.
- [x] **P2.4** ✅ Fixed Python logic registry loads validated packaged rules; missing inputs block affected quantities; only applied unverified rules produce warnings. Golden, incomplete-input and parameter-driven tests pass.
- [x] **P2.5** ✅ Existing `tests/test_calculator.py` covers all rules/scenarios, schemas, provenance, topology, edge cases, determinism/monotonicity and no-network behavior. Retain the established test path rather than moving files.
- [ ] **P2.6** 🟡 👤 CODEOWNERS includes rule/schema/scenario paths but uses literal `@<licensing-reviewers>` placeholders; real SME handles and required review are missing.
- [x] **P2.7** ✅ Existing `docs/rules.md` contains the full authoring/review/schema-generation procedure; retain the authoritative repository's documentation path rather than adding a duplicate.

**Verify**

- `pytest` passes; CI runs calculator tests and rule schema validation.
- Every rule has `source`, `effective_date` and `verified`.
- No price/cost/currency fields in the package or rules.
- No imports of `openai`, `azure`, `requests` or `httpx` in `licensing_calc`.

**Human** 👤 — SMEs review rules and set `verified: true` only after checking the cited source.

**Exit:** calculator tests green in CI; rule schema enforced.

---

### Phase 3 — Agent + API (Issue 3)

**Depends on:** Phase 1 (deployed dev infra) and Phase 2

**Build**

- [ ] **P3.1** 🟡 Generated `agent/tools/calculate_licenses.schema.json` matches Inventory (tested); agent.yaml, file_search/vector-store configuration and registration envelope are absent.
- [ ] **P3.2** `agent/instructions.md`: intake interview (ask only what is needed), call the calculator for **all** quantities, cite sources, state assumptions, never give pricing, "estimate, not a quote" disclaimer, recommend a licensing specialist when uncertain.
- [ ] **P3.3** `agent/deploy_agent.py`: `project.agents.create_version(agent_name, definition=PromptAgentDefinition(...))`; idempotent; prints the version.
- [ ] **P3.4** `knowledge/manifest.yaml` (title, source URL, version/date, blob path) + `knowledge/ingest_knowledge.py` (blob container `licensing-docs` → vector store; idempotent; reports per-file status).
- [ ] **P3.5** `src/api/` FastAPI service:
  - Entra JWT validation (audience/issuer correct per cloud)
  - `POST /api/conversations`
  - `POST /api/conversations/{id}/messages` → `202 { jobId }`
  - `GET /api/jobs/{jobId}`
  - `GET /api/conversations/{id}/stream` (SSE, standalone mode only)
  - `GET /healthz`
  - Job and conversation state in Cosmos `appstate`
  - Tool loop: on `function_call` run `licensing_calc` and return `function_call_output`; respect the 10-minute response expiry
  - Prefer Foundry background responses; fall back to an in-process task with Cosmos state (record the choice in the Decisions log)
  - Managed identity to Foundry and Cosmos; no keys
  - OpenAPI export used by the connector
- [ ] **P3.6** `src/api/Dockerfile`; API tests with Foundry mocked.
- [ ] **P3.7** `.github/workflows/app.yml`: build → push to ACR → update Container App → smoke test `/healthz`.
- [ ] **P3.8** `.github/workflows/agent.yml`: ingest knowledge → deploy agent version (triggers on `agent/**`, `knowledge/**`).

**Verify**

- `azure-ai-projects>=2` pinned; no classic threads/runs usage (no `create_thread`, `threads.`, `runs.create`).
- 202 + polling endpoints exist and are tested; no request path blocks longer than 120 seconds.
- No API keys; auth via managed identity.
- Runtime (Actions or 👤): `app.yml` and `agent.yml` succeeded for `dev`; `/healthz` returns 200; one end-to-end conversation returns a cited answer with calculator line items.

**Human** 👤

- [ ] **H3.1** Upload licensing PDFs to the `licensing-docs` container; update `knowledge/manifest.yaml`; run `agent.yml`.
- [ ] **H3.2** Confirm the Entra app registration (API audience/scope) exists for the connector and the standalone client.

**Exit:** dev end-to-end works via curl/Postman.

---

### Phase 4 — Power Apps code app + custom connector (Issue 4)

**Depends on:** Phase 3

**Build**

- [ ] **P4.1** `web/`: React + TypeScript + Vite + Fluent UI v9 code app, initialized with the npm-based `pa` CLI (`pac code` is being deprecated).
- [ ] **P4.2** `ApiClient` interface with `powerapps` (via connector) and `standalone` (MSAL) implementations; mode chosen by build config.
- [ ] **P4.3** UI: chat, job polling with progress state, estimate table (line items, assumptions, unverified warnings), citations, disclaimer, export (copy/CSV).
- [ ] **P4.4** `connector/`: OpenAPI **2.0** definition + properties; Entra OAuth; operations match the API routes.
- [ ] **P4.5** `.github/workflows/powerapps.yml`: build `web/`, `pa app push --non-interactive` with a service principal; connector update.
- [ ] **P4.6** ⬜ `docs/powerapps-setup.md` is only a reservation notice, not a setup procedure.
- [ ] **P4.7** _(Optional)_ Standalone hosting (e.g., Static Web App) for external customers.

**Verify**

- `npm ci && npm run build && npm test` pass in `web/`.
- Connector definition is `swagger: "2.0"` and its paths match the FastAPI routes.
- Polling handles 202 → completed / failed / timeout.
- Runtime 👤: the app opens in Power Apps and completes one scenario.

**Human** 👤

- [ ] **H4.1** Power Platform admin enables code apps in the target environment.
- [ ] **H4.2** Create the custom connector connection.
- [ ] **H4.3** First `pa app push` interactively (later pushes run from CI).
- [ ] **H4.4** Share the app with the service principal's **Enterprise Application object ID** with edit rights.
- [ ] **H4.5** Confirm end-user licensing: Power Apps Premium, pay-as-you-go or App Pass.

**Exit:** pilot users can open and use the app.

---

### Phase 5 — Evals & observability (Issue 5)

**Depends on:** Phase 3 (Phase 4 not required)

**Build**

- [ ] **P5.1** 🟡 Ten calculator seed scenarios exist under `evals/scenarios/calc/`, cover all rules and run in pytest. All are `expert_reviewed: false`; approved conversational/citation/must-not checks are absent.
- [ ] **P5.2** `evals/run.py`: offline deterministic calculator checks; online agent checks against dev (calculator called, quantities match, citations present, no pricing, asks clarifying questions when inputs are missing).
- [ ] **P5.3** `evals/thresholds.yaml`; runner fails below threshold.
- [ ] **P5.4** `.github/workflows/evals.yml`: on PRs touching `agent/**`, `knowledge/**`, `src/licensing_calc/rules/**`, plus nightly; results as artifact + job summary.
- [ ] **P5.5** Application Insights workbook: request volume, job latency, failures, token usage, tool-call rate.

**Verify:** `python evals/run.py --offline` passes; workflow exists; thresholds enforced.

**Human** 👤 — SMEs approve scenarios (via CODEOWNERS).

**Exit:** evals gate merges; baseline scores recorded in the Progress log.

---

### Phase 6 — Pilot & production

**Depends on:** Phases 4 and 5

- [ ] **P6.1** Deploy `prod` via `infra.yml`, `app.yml`, `agent.yml` (environment approval). 👤 approve
- [ ] **P6.2** Pilot with 5–10 users; capture feedback as issues labelled `pilot-feedback`.
- [ ] **P6.3** 👤 Calculator disclosures are tested, but no pilot/scenario verification evidence exists; all seeded rules remain unverified.
- [ ] **P6.4** 👤 Confirm cloud/region availability (Azure Government if needed), budgets/cost alerts, data retention.
- [ ] **P6.5** ⬜ `docs/runbook.md` covers infrastructure only; application document/rule/version promotion and rollback operations are not implemented.

**Exit:** go/no-go with SMEs.

---

## 8. Open questions / unverified assumptions

- GPT-5.4, Foundry agent tools and Power Apps code apps availability in Azure Government / GCC.
- Whether Foundry background mode works with agent references (otherwise use the in-process job fallback).
- Exact `pac connector create/update` flags and federated (OIDC) auth support for Power Platform CLI in CI.
- Whether standard-setup file search needs a separate embedding deployment.

---

## 9. Agent protocol (GitHub Copilot)

Follow this every time you are asked to "audit and continue":

1. **Read** this file, `.github/copilot-instructions.md`, `README.md` and `docs/`. Check open and merged PRs and issues for in-flight work.
2. **Audit** every phase in order. For each step, gather evidence: the file exists **and** its contents meet the step; tests pass (run them); `bicep build` passes; the grep checks pass; and, if you can read GitHub Actions run history, the latest workflow results. Never infer "done" from a file name alone.
3. **Classify** each step: ✅ evidence in repo/CI · 🟡 partial (state what is missing) · ⬜ not started · 👤 cannot be verified from repo/CI (Azure portal, Power Platform admin, SME sign-off). Never mark a 👤 item done yourself.
4. **Update this file** as the first commit of your PR: tick ✅ steps, fill in the Status board with evidence, list every outstanding 👤 item under "Human action required" with exact commands/portal steps, set "Last audit" and "Current phase", and append to the Progress log.
5. **Pick the next work:** the first ⬜/🟡 step in the earliest phase whose dependencies are met. If the only blockers are 👤 items, continue with the next phase that does not depend on them (e.g., Phase 2 does not need deployed infra) and say so.
6. **Build** that phase's remaining steps only. Check the Learn MCP server before writing Azure, Foundry or Power Platform code. Keep CI green.
7. **Stop at the phase boundary.** Re-run the phase's Verify checks, update this file again, and end with a PR description containing: the status table, what you built, what the human must do next, and the next phase.
8. If this plan conflicts with current docs, follow the docs and record the change in the Decisions log. Do not silently change the architecture.

### Quick audit commands

```bash
# Infra
az bicep build --file infra/main.bicep
grep -rn "utcNow" infra/
grep -rnE "client-secret|AZURE_CREDENTIALS|AccountKey=" .github/ || echo "no secrets found"

# Python
pip install -e ".[dev]" && pytest -q
grep -rnE "create_thread|threads\.|runs\.create" src/ agent/ || echo "no classic API usage"
grep -rniE "price|pricing|cost|usd" src/licensing_calc/ || echo "no pricing found"

# Web
(cd web && npm ci && npm run build && npm test)

# CI history (if gh is authenticated)
gh run list --limit 20
```

---

## 10. Kickoff prompt

Paste into a GitHub issue assigned to Copilot, or into the Copilot Agents panel:

```
Read PROJECT_PLAN.md and .github/copilot-instructions.md, then follow the Agent protocol in PROJECT_PLAN.md (Section 9):

1. Audit the repo against every phase and step using evidence (files and their contents, tests you run, bicep build, the grep checks, and GitHub Actions run history if you can read it). Don't infer completion from file names.
2. As the first commit, update PROJECT_PLAN.md: tick completed steps, fill in the Status board with evidence, list all human-only (👤) items under "Human action required" with exact steps, set Last audit and Current phase, and add a Progress log entry.
3. Continue with the next incomplete step in the earliest phase whose dependencies are met. If that phase is blocked only by human steps, move to the next independent phase and say so.
4. Finish that phase only, keep CI green, re-run its Verify checks and update PROJECT_PLAN.md again.
5. In the PR description include: the status table, what you built, what I need to do next (exact commands or portal steps), and the next phase.

Do not mark human-only items done. Do not change the architecture without recording it in the Decisions log.
```

---

## 11. Progress log

| Date | Phase | Summary | PR / run |
|---|---|---|---|
| 2026-11-20 | Audit / 2 | Audited every phase's contents; baseline 131 tests, Ruff, format, mypy, Bicep build/lint, both-cloud parameter compilation and Bash syntax pass. No Git/CI/runtime evidence or Learn MCP available. Recorded P1.3 gaps; selected independent P2.2 per-line verification disclosure. Human-only items remain unchecked. | Local workspace; no Git metadata/PR/run available |
| 2026-11-20 | 2 | Added calculator-derived per-line `unverified` disclosure, six mocked verification-state cases, seed/alternative assertions and output-contract docs. Final 137 tests, Ruff lint/format, mypy and editor checks pass. Stopped at Phase 2 boundary: real SME handles/review gate and licensing approval remain human work; no Phase 3/deployment changes. | Local workspace; no commit/PR/run possible without Git metadata |

## 12. Decisions log

| Date | Decision | Reason |
|---|---|---|
| 2026-11-11 | Agent core in Azure (Foundry); UI as a Power Apps code app via custom connector; optional standalone web for external customers | Keeps Power Platform UX while avoiding Copilot/Teams dependency and connector limits |
| 2026-11-11 | Async job pattern (202 + poll) | Power Platform 120-second connector timeout |
| 2026-11-11 | New Foundry Agent Service API (Responses + Conversations) | Classic agents API retires 2027-03-31 |
| 2026-11-11 | Deterministic calculator with YAML rules and `verified` flag | Model must not compute quantities; every rule traceable to a source |
| 2026-11-11 | Bicep + GitHub Actions with OIDC and user-assigned MI | No secrets; supports AzureCloud and AzureUSGovernment |
| 2026-11-20 | Retain existing `tests/test_calculator.py`, `docs/rules.md`, and YAML `notes` description field | Existing tested conventions and authoritative repo instructions satisfy these intents; no duplicate docs, test moves or rule schema churn |
| 2026-11-20 | Audit records the existing workflow-only running-image preservation, not a Bicep running-image default | The direct template defaults to nginx; direct/manual redeployment remains unsafe without passing the running image. Revisit P1.3 with current docs rather than silently calling it complete |
| 2026-11-20 | Do not start new Azure/Foundry/Power Platform code without Learn MCP in this session | P0.3 cannot be verified; prior approved direct-page fallback noted in `docs/setup.md` does not grant a new exception for this session. Continue independent Phase 2 work only |
