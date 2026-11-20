# Runbook

## Infrastructure

- Use the [setup guide](setup.md) and stable `licensing-agent-<env>` deployment.
- Inspect failed deployment operations and capability-host provisioning state.
  A provisioning delay is not a reason to change names or delete agent resources.
- Confirm quota, cloud, regional API/tool availability, and RBAC propagation on failures.
- Re-run bootstrap after changing the template's exported RBAC allow-list.
- Infrastructure runs preserve the deployed API image and queue per environment.
- Keep prod required-reviewer protection enabled.
- Customer-content logging remains off.

Later phases add application operations, recovery, ingestion, and evaluation procedures.
