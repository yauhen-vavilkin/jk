# Job: deleteNamespace

Full Jenkins item path:

```
/job/folioRancher/job/manageNamespace/job/deleteNamespace/
```

URL: https://jenkins.ci.folio.org/job/folioRancher/job/manageNamespace/job/deleteNamespace/

Purpose: destroy a FOLIO environment — the Kubernetes namespace plus the external
AWS resources that were provisioned alongside it.

**This job is destructive.** Per this repository's rules it must never be triggered
by an agent, and a human must review the exact `CLUSTER` and `NAMESPACE`
immediately before running it. Nothing here authorises running it.

The build is named `<CLUSTER>-<NAMESPACE>.<BUILD_ID>`, the same shape as
[createNamespaceFromBranch](createNamespaceFromBranch.md).

These parameter and pipeline notes were collected in August 2026. Check the
current job definition and the environment's creation settings before a run.

## Parameter reference

Eight parameters, no unnamed form elements.

### The two that identify the target

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `CLUSTER` | `CascadeChoiceParameter` | `folio-etesting` | EKS cluster holding the environment. **The default is a real, shared cluster, not a sentinel** — unlike `NAMESPACE`. Leaving it untouched points the job at `folio-etesting`. |
| `NAMESPACE` | `CascadeChoiceParameter` | `error` | Namespace to delete. `error` is a "must choose" sentinel; the choices are computed from `CLUSTER`. |

Guard rails in the pipeline:

- `folioCommon.validateNamespace(NAMESPACE)` runs for every cluster except
  `folio-tmp`.
- `folioCommon.kitfoxApproval()` is required when `CLUSTER` is `folio-etesting` —
  which is also the default, so an unedited form stops for approval.
- The namespace's existence is checked with `kubectl` first. If it does not exist,
  the job finishes without doing anything.

### The five that describe how the environment was built

These do **not** choose what to delete. They tell the teardown which external
resources exist, so it can clean them up. They must match the values the
environment was **created** with — a mismatch leaves orphaned AWS resources behind.

| Parameter | Type | Default | Allowed | Effect on teardown |
|---|---|---|---|---|
| `POSTGRESQL` | choice | `built-in` | `built-in`, `aws` | Sets Terraform `pg_embedded = (value == 'built-in')`. `aws` means an RDS instance must be destroyed. |
| `KAFKA` | choice | `built-in` | `built-in`, `aws` | Sets `kafka_shared = (value != 'built-in')`. When `aws`, the job additionally runs a **Kafka topic cleanup** stage against shared MSK. |
| `OPENSEARCH` | choice | `aws` | `aws`, `built-in` | Sets `opensearch_shared = (value != 'built-in')`. When `aws`, the job additionally runs an **OpenSearch index cleanup** stage. |
| `S3_BUCKET` | choice | `aws` | `aws`, `built-in` | Sets `s3_embedded = (value == 'built-in')`. |
| `RW_SPLIT` | boolean | `false` | | Sets `enable_rw_split`. Must match the created environment so Terraform destroys the same resource set it created. |

### Control

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `REFRESH_PARAMETERS` | boolean | `false` | `true` sets the build result to `ABORTED` and returns immediately — it only refreshes the parameter form and performs no deletion. |

---

## What the job actually removes

Stages in `vars/folioNamespaceDelete.groovy`, in order:

1. AWS Parameter Store cleanup — this is what the build description
   `#parameters deleted: <count>` reports.
2. Helm uninstall of all releases in the namespace.
3. OpenSearch index cleanup — only when `OPENSEARCH` is not `built-in`.
4. Kafka topic cleanup — only when `KAFKA` is not `built-in`.
5. Terraform destroy.
6. AWS Route53 DNS record cleanup.

---

## Notes for saved jobs

- **The backing-service values must mirror the creation parameters.** If an
  environment was created with `POSTGRESQL=aws`, deleting it with the default
  `built-in` will not destroy the RDS instance.
- `CLUSTER`'s default is not a sentinel. A saved job that leaves `CLUSTER` on
  its default targets `folio-etesting`, a shared cluster.

## Provenance

Collected on 2026-08-28 and refreshed on 2026-08-31 with authenticated read-only
`GET` requests against `https://jenkins.ci.folio.org`, plus the public pipeline
sources:

- `.../deleteNamespace/api/json?tree=property[parameterDefinitions[...]]`
- `pipelines/folioRancher/folioNamespaceTools/manageNamespace/deleteNamespace/Jenkinsfile`
  and `vars/folioNamespaceDelete.groovy` in `folio-org/pipelines-shared-library`
  on `master`
