import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASH = (
    str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe")
    if os.name == "nt"
    else shutil.which("bash") or "bash"
)

HARNESS = r"""
set -euo pipefail
az() {
  printf '%s\037' az "$@" >> "$TEST_DIR/calls"
  printf '\036' >> "$TEST_DIR/calls"
  case "$1 ${2-} ${3-}" in
    'resource list --resource-group')
      [[ "${AZ_LIST_FAIL:-0}" == 0 ]] || return 9
      if [[ " $* " == *' length(@) '* ]]; then
        echo "${APP_COUNT:-0}"
      else
        echo /subscriptions/sub/resourceGroups/rg-test-dev/providers/Microsoft.App/containerApps/api
      fi ;;
    'resource show --ids')
      [[ "${AZ_SHOW_FAIL:-0}" == 0 ]] || return 8
      if [[ " $* " == *'properties.template.containers'* ]]; then
        echo "${CURRENT_IMAGE-}"
      else
        echo "${HOST_STATE:-Succeeded}"
      fi ;;
    'deployment group show') cat "$TEST_DIR/outputs.json" ;;
    'bicep build --file')
      local arg previous=
      for arg in "$@"; do
        if [[ "$previous" == --outfile ]]; then cp "$TEST_DIR/roles.json" "$arg"; fi
        previous=$arg
      done ;;
    'account show --query')
      if [[ "$4" == id ]]; then echo sub; else echo tenant; fi ;;
    'identity create --name')
      echo '{"clientId":"client","principalId":"principal"}' ;;
    'role assignment list')
      if [[ "${EXISTING_ROLES:-0}" == 1 ]]; then
        local scope= previous= arg
        for arg in "$@"; do
          if [[ "$previous" == --scope ]]; then scope=$arg; fi
          previous=$arg
        done
        jq -n --arg scope "$scope" '[{
          id:"assignment", principalId:"principal", scope:$scope,
          roleDefinitionId:(
            "/subscriptions/sub/providers/Microsoft.Authorization/roleDefinitions/" +
            "f58310d9-a9f6-439a-9e8d-f62e7b41a168")
        }]'
      else echo '[]'; fi ;;
    'ad app list')
      [[ "${ENTRA_FAIL:-0}" == 0 ]] || { echo "Insufficient Entra privileges" >&2; return 7; }
      if [[ "${EXISTING_APP:-0}" == 1 ]]; then
        echo '[{"appId":"application"}]'
      else echo '[]'; fi ;;
    'ad app create') echo application ;;
    'ad app show')
      echo '{"api":{"oauth2PermissionScopes":[
        {"id":"other","value":"other_scope","isEnabled":true}]}}' ;;
  esac
}
gh() {
  printf '%s\037' gh "$@" >> "$TEST_DIR/calls"
  printf '\036' >> "$TEST_DIR/calls"
  if [[ "$1 ${2-}" == 'api --paginate' && "${EXISTING_ENVIRONMENTS:-0}" == 1 ]]; then
    printf 'dev\nprod\n'
  fi
  return 0
}
sleep() { SECONDS=1900; }
export -f az gh sleep
bash "$TEST_SCRIPT" "${TEST_ARGS[@]}"
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    probe = subprocess.run(
        [BASH, "-c", "command -v jq"], capture_output=True, text=True, check=False
    )
    assert probe.returncode == 0, (
        "jq is required for offline Bash tests (included on CI/Cloud Shell)"
    )
    (tmp_path / "outputs.json").write_text(
        json.dumps(
            {
                "accountCapabilityHostId": {"value": "/account/capabilityHosts/account"},
                "projectCapabilityHostId": {"value": "/account/project/capabilityHosts/project"},
            }
        ),
        encoding="utf-8",
    )
    roles = dict(
        re.findall(r"^\s+(\w+): '([0-9a-f-]{36})'", (ROOT / "infra/roles.bicep").read_text(), re.M)
    )
    (tmp_path / "roles.json").write_text(
        json.dumps({"variables": {"roles": roles}}), encoding="utf-8"
    )
    return tmp_path


def run_script(
    workspace: Path, script: str, *, options: str = "", **variables: str
) -> subprocess.CompletedProcess[str]:
    jq_adapter = (
        r"""
jq() {
  local args=() arg
  for arg in "$@"; do
    if [[ -f "$arg" ]]; then arg=$(cygpath -w "$arg"); fi
    args+=("$arg")
  done
  command jq --binary "${args[@]}"
}
export -f jq
"""
        if os.name == "nt"
        else ""
    )
    environment = {
        **os.environ,
        "TEST_DIR": workspace.as_posix(),
        "TEST_SCRIPT": (ROOT / script).as_posix(),
        "AZURE_RESOURCE_GROUP": "rg-test-dev",
        "ENVIRONMENT_NAME": "dev",
        "GITHUB_OUTPUT": (workspace / "github-output").as_posix(),
        "MSYS_NO_PATHCONV": "1",
        "MSYS2_ARG_CONV_EXCL": "*",
        **variables,
    }
    return subprocess.run(
        [BASH, "-c", f"TEST_ARGS=({options})\n{jq_adapter}\n{HARNESS}"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def calls(workspace: Path) -> list[list[str]]:
    return [
        record.split("\037")[:-1]
        for record in (workspace / "calls").read_text().split("\036")
        if record
    ]


def test_first_deploy_uses_placeholder(workspace: Path) -> None:
    result = run_script(workspace, "scripts/get-api-image.sh")
    assert result.returncode == 0, result.stderr
    assert (workspace / "github-output").read_text().strip() == (
        "image=docker.io/library/nginx:1.28-alpine"
    )


def test_redeploy_preserves_current_image(workspace: Path) -> None:
    result = run_script(
        workspace,
        "scripts/get-api-image.sh",
        APP_COUNT="1",
        CURRENT_IMAGE="registry.example/licensing-api@sha256:0123456789",
    )
    assert result.returncode == 0, result.stderr
    assert (workspace / "github-output").read_text().strip() == (
        "image=registry.example/licensing-api@sha256:0123456789"
    )


@pytest.mark.parametrize(
    "variables",
    [
        {"AZ_LIST_FAIL": "1"},
        {"APP_COUNT": "1", "AZ_SHOW_FAIL": "1"},
        {"APP_COUNT": "1", "CURRENT_IMAGE": ""},
        {"APP_COUNT": "1", "CURRENT_IMAGE": "bad\nimage"},
        {"APP_COUNT": "2"},
    ],
)
def test_image_failures_never_revert_to_placeholder(
    workspace: Path, variables: dict[str, str]
) -> None:
    result = run_script(workspace, "scripts/get-api-image.sh", **variables)
    assert result.returncode != 0
    assert not (workspace / "github-output").exists()


def test_both_hosts_must_succeed(workspace: Path) -> None:
    result = run_script(workspace, "scripts/poll-capability-hosts.sh")
    assert result.returncode == 0, result.stderr
    shows = [call for call in calls(workspace) if call[:3] == ["az", "resource", "show"]]
    assert len(shows) == 2
    assert "Both capability hosts succeeded" in result.stdout


@pytest.mark.parametrize("state", ["Failed", "Canceled", "Cancelled"])
def test_terminal_host_failure_is_explicit(workspace: Path, state: str) -> None:
    result = run_script(workspace, "scripts/poll-capability-hosts.sh", HOST_STATE=state)
    assert result.returncode != 0
    assert f"entered {state}" in result.stderr


def test_host_api_errors_fail(workspace: Path) -> None:
    result = run_script(workspace, "scripts/poll-capability-hosts.sh", AZ_SHOW_FAIL="1")
    assert result.returncode != 0


def test_missing_host_output_fails(workspace: Path) -> None:
    (workspace / "outputs.json").write_text("{}", encoding="utf-8")
    result = run_script(workspace, "scripts/poll-capability-hosts.sh")
    assert result.returncode != 0
    assert "Missing capability-host IDs" in result.stderr


BOOTSTRAP_OPTIONS = "--cloud AzureCloud --location eastus2 --prefix test --repo owner/repo"


def test_bootstrap_constrains_both_rbac_operations(workspace: Path) -> None:
    result = run_script(workspace, "scripts/bootstrap/bootstrap.sh", options=BOOTSTRAP_OPTIONS)
    assert result.returncode == 0, result.stderr
    log = calls(workspace)
    assignments = [
        call
        for call in log
        if call[:4] == ["az", "role", "assignment", "create"] and "--condition" in call
    ]
    assert len(assignments) == 2
    role_ids = json.loads((workspace / "roles.json").read_text())["variables"]["roles"].values()
    for assignment in assignments:
        condition = assignment[assignment.index("--condition") + 1]
        assert "roleAssignments/write" in condition
        assert "roleAssignments/delete" in condition
        assert "@Request[" in condition and "@Resource[" in condition
        for role_id in role_ids:
            assert condition.count(role_id) == 2
        assert "b24988ac-6180-42a0-ab88-20f7382dd24c" not in condition
        assert "f58310d9-a9f6-439a-9e8d-f62e7b41a168" not in condition
    federations = [
        call for call in log if call[:4] == ["az", "identity", "federated-credential", "create"]
    ]
    assert len(federations) == 2
    assert {call[call.index("--subject") + 1] for call in federations} == {
        "repo:owner/repo:environment:dev",
        "repo:owner/repo:environment:prod",
    }
    variables = [call for call in log if call[:3] == ["gh", "variable", "set"]]
    assert len(variables) == 18
    assert "required reviewers" in result.stdout
    updates = [call for call in log if call[:4] == ["az", "ad", "app", "update"]]
    api_update = updates[0][updates[0].index("--set") + 1]
    assert "access_as_user" in api_update
    assert "other_scope" in api_update


def test_bootstrap_rerun_updates_constraints_and_reuses_app(workspace: Path) -> None:
    result = run_script(
        workspace,
        "scripts/bootstrap/bootstrap.sh",
        options=BOOTSTRAP_OPTIONS,
        EXISTING_ROLES="1",
        EXISTING_APP="1",
        EXISTING_ENVIRONMENTS="1",
    )
    assert result.returncode == 0, result.stderr
    log = calls(workspace)
    updates = [call for call in log if call[:4] == ["az", "role", "assignment", "update"]]
    assert len(updates) == 2
    for update in updates:
        assignment = json.loads(update[update.index("--role-assignment") + 1])
        assert assignment["conditionVersion"] == "2.0"
        assert "RoleDefinitionId" in assignment["condition"]
    assert not any(call[:4] == ["az", "ad", "app", "create"] for call in log)
    assert not any(call[:4] == ["gh", "api", "--method", "PUT"] for call in log)


def test_government_bootstrap_uses_matching_oidc_audience(workspace: Path) -> None:
    result = run_script(
        workspace,
        "scripts/bootstrap/bootstrap.sh",
        options=BOOTSTRAP_OPTIONS.replace("AzureCloud", "AzureUSGovernment").replace(
            "eastus2", "usgovvirginia"
        ),
    )
    assert result.returncode == 0, result.stderr
    federations = [
        call
        for call in calls(workspace)
        if call[:4] == ["az", "identity", "federated-credential", "create"]
    ]
    assert len(federations) == 2
    assert all(
        call[call.index("--audiences") + 1] == "api://AzureADTokenExchangeUSGov"
        for call in federations
    )


def test_host_timeout_is_bounded_and_explicit(workspace: Path) -> None:
    result = run_script(workspace, "scripts/poll-capability-hosts.sh", HOST_STATE="Creating")
    assert result.returncode != 0
    assert "within 30 minutes" in result.stderr


def test_bootstrap_without_entra_rights_prints_manual_steps(workspace: Path) -> None:
    result = run_script(
        workspace,
        "scripts/bootstrap/bootstrap.sh",
        options=BOOTSTRAP_OPTIONS,
        ENTRA_FAIL="1",
        API_APP_ID_URI="",
    )
    assert result.returncode == 0, result.stderr
    assert "Insufficient Entra privileges" in result.stderr
    assert "access_as_user" in result.stderr
    assert "--env dev" in result.stderr and "--env prod" in result.stderr
    variables = [call for call in calls(workspace) if call[:3] == ["gh", "variable", "set"]]
    assert not any(call[3] == "API_APP_ID_URI" for call in variables)
    assert len(variables) == 16


@pytest.mark.parametrize(
    "options",
    [
        "--cloud Invalid --location eastus2 --prefix test --repo owner/repo",
        "--location eastus2 --prefix Invalid --repo owner/repo",
        "--location eastus2 --prefix test --repo invalid",
        "--location",
    ],
)
def test_bootstrap_rejects_bad_flags(workspace: Path, options: str) -> None:
    result = run_script(workspace, "scripts/bootstrap/bootstrap.sh", options=options)
    assert result.returncode == 2
    assert not (workspace / "calls").exists()


def test_composite_exports_all_required_outputs(workspace: Path) -> None:
    output_names = {
        "projectEndpoint": "PROJECT_ENDPOINT",
        "modelDeploymentName": "MODEL_DEPLOYMENT_NAME",
        "acrLoginServer": "ACR_LOGIN_SERVER",
        "containerAppName": "CONTAINER_APP_NAME",
        "apiUrl": "API_URL",
        "apiIdentityClientId": "API_IDENTITY_CLIENT_ID",
        "storageAccountName": "STORAGE_ACCOUNT_NAME",
        "cosmosEndpoint": "COSMOS_ENDPOINT",
        "appInsightsConnectionString": "APPLICATIONINSIGHTS_CONNECTION_STRING",
    }
    action = yaml.safe_load(
        (ROOT / ".github/actions/get-infra-outputs/action.yml").read_text(encoding="utf-8")
    )
    export_script = workspace / "export.sh"
    export_script.write_text(action["runs"]["steps"][0]["run"], encoding="utf-8")
    (workspace / "outputs.json").write_text(
        json.dumps({key: {"value": f"value-{key}"} for key in output_names}), encoding="utf-8"
    )
    result = run_script(
        workspace,
        str(export_script),
        TARGET_ENVIRONMENT="dev",
        TARGET_RESOURCE_GROUP="rg-test-dev",
        GITHUB_ENV=(workspace / "github-env").as_posix(),
    )
    assert result.returncode == 0, result.stderr
    exported = dict(
        line.split("=", 1) for line in (workspace / "github-env").read_text().splitlines()
    )
    assert exported == {value: f"value-{key}" for key, value in output_names.items()}


def test_workflows_parse_and_pin_actions() -> None:
    for path in (ROOT / ".github").rglob("*.yml"):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(workflow, dict)
        for reference in re.findall(r"uses:\s+([^\s]+)", path.read_text()):
            assert reference.startswith("./") or re.fullmatch(r"[\w./-]+@v\d+", reference)


def test_names_have_no_time_dependency_and_roles_are_centralized() -> None:
    for path in (ROOT / "infra").rglob("*.bicep"):
        text = path.read_text()
        assert "utcNow(" not in text
        assert "deploymentTimestamp" not in text
        assert ".windows.net" not in text and "login.microsoftonline.com" not in text
        if "Microsoft.Authorization/roleAssignments" in text:
            assert "import { roles }" in text


def test_calculator_package_imports_without_azure() -> None:
    import licensing_calc

    assert licensing_calc.__doc__
