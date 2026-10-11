# Job: createNamespaceFromBranch

Full Jenkins item path:

```
/job/folioRancher/job/manageNamespace/job/createNamespaceFromBranch/
```

URL: https://jenkins.ci.folio.org/job/folioRancher/job/manageNamespace/job/createNamespaceFromBranch/

Purpose: create (or fully rebuild) a FOLIO environment — a Kubernetes namespace on
an EKS cluster — from selected `platform-complete` / `platform-lsp` branches.

The observed build display-name convention is
`#<CLUSTER>-<NAMESPACE>.<BUILD_ID>`. It is not a documented Jenkins guarantee.

These parameter and pipeline notes were collected in August 2026. Defaults and
pipeline behavior can change; check the current job before preparing a run.

## Parameter reference

Types below are the Jenkins parameter classes reported by the job definition.
`CascadeChoiceParameter` means the allowed values are computed at form render
time and depend on earlier parameters — they are **not** a fixed list, so a
saved job must use a value that actually exists for the chosen upstream
selection.

### Target platform and location

| Parameter | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `PLATFORM` | choice | `EUREKA` | `EUREKA`, `OKAPI` | Which FOLIO platform to deploy. `EUREKA` is the Keycloak-based stack (Kong + sidecars + managers). `OKAPI` is the legacy Okapi stack. Drives what the cascading parameters below offer. |
| `CLUSTER` | cascade choice | `error` (**required**) | depends on `PLATFORM` | EKS cluster that hosts the environment. A literal `error` value means nothing was selected — the job will fail. |
| `NAMESPACE` | cascade choice | `error` (**required**) | depends on `CLUSTER` | Kubernetes namespace inside the cluster. Together with `CLUSTER` this is the environment identity: `<CLUSTER>-<NAMESPACE>`. |

### Source branches and versions — this is where the release-vs-snapshot choice is made

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `FOLIO_BRANCH` | cascade choice | `snapshot` (**required**) | Branch of the **`platform-complete`** repository used for the build. Used on `PLATFORM=OKAPI`; hidden on EUREKA. |
| `PLATFORM_BRANCH` | cascade choice | `snapshot` (**required**) | Branch of the **`platform-lsp`** repository used for the build. Selects the release or development branch on EUREKA. |
| `OKAPI_VERSION` | cascade choice | `error` | Okapi version for the build. Hidden on EUREKA. Options depend on the selected branches. |
| `APPLICATIONS` | cascade choice, rendered as a checkbox list | `""` | Comma-separated list of FOLIO applications to install. The available set is derived from the chosen branches, so an application name valid on one branch may not exist on another. |

Note: `FOLIO_BRANCH` and `PLATFORM_BRANCH` are two **different repositories**.
Use the parameter for the selected platform; a recorded hidden value is not
evidence that the pipeline used it.

### Deployment configuration

| Parameter | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `CONFIG_TYPE` | choice | `development` | `development`, `performance`, `testing`, `release` | EKS deployment profile — resource sizing and related settings. |
| `TYPE` | choice | `full` (**required**) | `full`, `terraform`, `update` | What the run does. `full` = complete create; `terraform` = infrastructure only; `update` = update an existing namespace. |
| `ENTITLEMENT_APPROACH` | choice | `STATE` | `STATE`, `CREATE` | How applications are entitled to tenants. `STATE` = `PUT /entitlements/state` (declarative). `CREATE` = `POST /entitlements` (procedural). |
| `SET_BASE_URL` | boolean | `true` | | Set `false` to skip `PUT /base-url` during tenant configuration (needed for Sunflower). |
| `SC_NATIVE` | boolean | `true` | | `true` = native sidecar image; `false` = Java-based sidecar image. |
| `REFRESH_PARAMETERS` | boolean | `false` | | `true` only refreshes this job's parameter form and **does not run the pipeline**. Never set this on a real deployment run. |

### Data loading

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `LOAD_REFERENCE` | boolean | `true` | Load module reference data (instances, holdings, …) for automated tests. |
| `LOAD_SAMPLE` | boolean | `true` | Load module sample data. |
| `DATASET` | boolean | `false` | Build a BugFest-like environment from a dataset. |
| `DB_BACKUP_NAME` | string | job-specific; check the current definition | Name of the DB backup to restore. Relevant when restoring/`DATASET` flows are used. |
| `SKIP_REINDEX` | boolean | `false` | `true` skips triggering the search index rebuild. |

### UI and consortia

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `BUILD_UI` | boolean | `true` | Include the UI bundle in the environment. |
| `CONSORTIA` | boolean | `true` | Create a consortium (ECS setup). |
| `CONSORTIA_SINGLE_UI` | boolean | `true` | Build a single UX bundle instead of the tenant drop-down for ECS. |
| `CONSORTIA_EXTRA` | boolean | `false` | Create a second consortium. |
| `HAS_SECURE_TENANT` | boolean | `true` | Enable a secure tenant on one of the consortium institutional tenants. |
| `SECURE_TENANT` | choice | `university` | Allowed: `university`, `college`. Which institutional tenant becomes the secure tenant. Only meaningful when `HAS_SECURE_TENANT=true`. |

### Optional feature modules

All of these are `BooleanParameterDefinition`.

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `LINKED_DATA` | boolean | `true` | Deploy LinkedData. |
| `MARC_MIGRATIONS` | boolean | `false` | Deploy Marc-Migrations. |
| `RTAC_CACHE` | boolean | `false` | Deploy Rtac-Cache. |
| `EDGE_LOCATE` | boolean | `false` | Deploy Edge-Locate. |
| `SPLIT_FILES` | boolean | `true` | Enable split-files functionality. |
| `RW_SPLIT` | boolean | `false` | Enable database read/write split. |
| `ECS_CCL` | boolean | `false` | Enable ECS Circulation + Congressional loans. |
| `GREENMAIL` | boolean | `false` | Deploy a GreenMail SMTP server. |
| `MOCK_SERVER` | boolean | `false` | Deploy a mock server. |
| `RTR` | boolean | `false` | Enable RTR (refresh token rotation). |

### Backing services

| Parameter | Type | Default | Allowed | Meaning |
|---|---|---|---|---|
| `POSTGRESQL` | choice | `built-in` | `built-in`, `aws` | In-cluster PostgreSQL vs AWS RDS. |
| `DB_VERSION` | cascade choice | `16.8` | depends on `POSTGRESQL` | PostgreSQL version. |
| `KAFKA` | choice | `built-in` | `built-in`, `aws` | In-cluster Kafka vs AWS MSK. |
| `OPENSEARCH` | choice | `aws` | `aws`, `built-in` | AWS OpenSearch vs in-cluster OpenSearch. |
| `S3_BUCKET` | choice | `aws` | `aws`, `built-in` | AWS S3 vs built-in MinIO. |

### Validation

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `RUN_SANITY_CHECK` | boolean | `true` | Run the Cypress sanity check after deployment. Set `false` to skip it. |

---

## Notes for saved jobs

- The job defines **five unnamed `DynamicReferenceParameter` entries** (empty
  `name`). Their defaults are not all empty: two are `""` and three are `"error"`.
  Observed build responses include unnamed empty values carried through the form. They are rendered form elements, not inputs a caller chooses —
  treat them as "not settable" rather than "must be omitted"; the JSON does not
  say what happens if a caller sends a value for one.
- `CLUSTER`, `NAMESPACE`, `OKAPI_VERSION` have the literal default `error`. That
  default is a sentinel meaning "you must choose": submitting it fails the job.
- Cascading parameters (`CLUSTER`, `NAMESPACE`, `FOLIO_BRANCH`,
  `PLATFORM_BRANCH`, `OKAPI_VERSION`, `APPLICATIONS`, `DB_VERSION`) have no fixed
  value list in the job definition. Validate a chosen value against a real recent
  build of the same shape rather than assuming.

## Parameters hidden by `PLATFORM`

The job's Jenkinsfile hides part of the form depending on `PLATFORM`:

| `PLATFORM` | hidden parameters |
|---|---|
| `EUREKA` | `OKAPI_VERSION`, `EDGE_LOCATE`, `RTAC_CACHE`, `FOLIO_BRANCH`, `LINKED_DATA`, `MARC_MIGRATIONS` |
| `OKAPI` | `PLATFORM_BRANCH`, `APPLICATIONS`, `SC_NATIVE`, `ENTITLEMENT_APPROACH`, `SET_BASE_URL` |

Also hidden: `HAS_SECURE_TENANT` and `SECURE_TENANT` when `CONSORTIA` is false, and
`SECURE_TENANT` when `HAS_SECURE_TENANT` is false.

Hidden parameter values may still appear in build JSON as carried-over form state.
The observed `vars/folioNamespaceCreateEureka.groovy` implementation uses
`platformBranch` and does not read `folioBranch` or `platform-complete`.

## Approval gate

The Jenkinsfile calls `folioCommon.kitfoxApproval()` when **any** of these holds:

- `CLUSTER` is `folio-etesting`, or
- `DATASET` is `true`, or
- `CONFIG_TYPE` is `release`.

A run matching any of those waits for a Kitfox approver, so a saved job
hitting one of them will not proceed unattended.

`REFRESH_PARAMETERS=true` sets the build result to `ABORTED` and returns before any
work — it only refreshes the form.

## How the cascading parameters are computed

Source: `folio-org/pipelines-shared-library` on `master` —
`vars/folioParameters.groovy` and `vars/folioStringScripts.groovy`. This is where
the behaviour below is defined; the Jenkins API alone does not show it.

| Parameter | Computed from |
|---|---|
| `FOLIO_BRANCH` | every branch of **`platform-complete`**, unfiltered, with `snapshot`/`master`/`main` floated to the top |
| `PLATFORM_BRANCH` | every branch of **`platform-lsp`**, same rule |
| `APPLICATIONS` | `platform-lsp/<PLATFORM_BRANCH>/platform-descriptor.json` -> `applications.required` + `.optional` + `.experimental` |
| `OKAPI_VERSION` | `platform-complete/<FOLIO_BRANCH>/install.json`, the `okapi-*` entry; if absent, Docker Hub tags of `folioci/okapi` when `FOLIO_BRANCH` contains `snapshot`, otherwise `folioorg/okapi`. Hidden on `EUREKA`. |

Two consequences that matter when setting up a saved job:

1. **A branch appearing in the drop-down proves nothing.** Both branch lists are
   the raw repository branch list with no filtering.
2. **`PLATFORM_BRANCH` must point at a branch that has `platform-descriptor.json`.**
   If the file is missing, the script catches the error and returns an **empty
   applications list** — with no clear error message. See
   [../releases.md](../releases.md) for how to check the selected branch.

## Provenance

Observed in August 2026 using read-only Jenkins REST GET requests:

- Job definitions: `.../createNamespaceFromBranch/api/json?tree=property[parameterDefinitions[...]]`
- Build parameters: `.../createNamespaceFromBranch/<BUILD_ID>/api/json?tree=actions[parameters[name,value]]`

Pipeline interpretation comes from `folio-org/pipelines-shared-library`:
`vars/folioParameters.groovy`, `vars/folioStringScripts.groovy`,
`vars/folioNamespaceCreateEureka.groovy`, and
`pipelines/folioRancher/folioNamespaceTools/manageNamespace/createNamespaceFromBranch/Jenkinsfile`.
These observations do not establish successful live submission through JK.
