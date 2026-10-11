# Job: runCypressTests

Full Jenkins item path:

```
/job/folioTestingTools/job/runCypressTests/
```

URL: https://jenkins.ci.folio.org/job/folioTestingTools/job/runCypressTests/

Purpose: run the configured Cypress suite against an existing FOLIO tenant and
Kong endpoint.

The parameter names and types below were checked with a read-only Jenkins
request on 2026-08-30. The saved jobs in the panel's Library are the source for
values; this document is a reference, not a second source. A secret value is
never written here.

## Parameters

| Parameter | Jenkins type |
|---|---|
| `CYPRESS_BRANCH` | `CascadeChoiceParameter` |
| `TENANT_URL` | `StringParameterDefinition` |
| `KONG_URL` | `StringParameterDefinition` |
| `TENANT_ID` | `StringParameterDefinition` |
| `ADMIN_USERNAME` | `StringParameterDefinition` |
| `ADMIN_PASSWORD` | `PasswordParameterDefinition` |
| `EXEC_PARAMETERS` | `StringParameterDefinition` |
| `KB_URL` | `StringParameterDefinition` |
| `KB_ID` | `StringParameterDefinition` |
| `KB_KEY` | `PasswordParameterDefinition` |
| `NUMBER_OF_WORKERS` | `ChoiceParameterDefinition` |
| `TIMEOUT` | `StringParameterDefinition` |
| `CUSTOM_BUILD_NAME` | `StringParameterDefinition` |
| `TESTRAIL_PROJECTID` | `StringParameterDefinition` |
| `TESTRAIL_RUN_ID` | `StringParameterDefinition` |
| `PREPARE` | `BooleanParameterDefinition` |
| `REPORT_PORTAL_USE` | `BooleanParameterDefinition` |
| `REPORT_PORTAL_RUN_TYPE` | `ChoiceParameterDefinition` |
| `RUN_SANITY_CHECK` | `BooleanParameterDefinition` |
| `REFRESH_PARAMETERS` | `BooleanParameterDefinition` |

## Active Choices limitation

`CYPRESS_BRANCH` is context-dependent. Jenkins reports its current default as
`master`, but an Active Choices default is not proof that every branch-specific
value is valid for a future run. JK therefore does not load or evaluate the
script; a changed branch contract must be caught by read-only validation before a
human accepts a run.
