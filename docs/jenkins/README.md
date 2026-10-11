# Jenkins reference for JK

Controller: https://jenkins.ci.folio.org

What lives here: observed descriptions of Jenkins jobs, their parameters and
API response shapes. These are controller reference notes, not bundled
job presets. Confirm current parameters and your own target environment before
saving a job in the Library.

Everything here is collected with read-only REST `GET` requests against the
controller, using the credentials from the local `.env`
(`JENKINS_URL`, `JENKINS_USER_ID`, `JENKINS_API_TOKEN`).

## Jobs

| Job | Path | Document |
|---|---|---|
| createNamespaceFromBranch | `/job/folioRancher/job/manageNamespace/job/createNamespaceFromBranch/` | [jobs/createNamespaceFromBranch.md](jobs/createNamespaceFromBranch.md) |
| runCypressTests | `/job/folioTestingTools/job/runCypressTests/` | [jobs/runCypressTests.md](jobs/runCypressTests.md) |
| deleteNamespace (**destructive**) | `/job/folioRancher/job/manageNamespace/job/deleteNamespace/` | [jobs/deleteNamespace.md](jobs/deleteNamespace.md) |

Choose the cluster and namespace you own. Set `CLUSTER` explicitly rather than
accepting a job's default. The notes describe observations from August 2026;
check the live job definition before relying on a parameter or pipeline detail.

The offline JSON fixtures in `tests/fixtures/` preserve observed Jenkins field
shapes, including omitted password values and unnamed form parameters. Their
hostnames and example values are sanitized; they are not runnable job presets.

## Cross-cutting notes

- Environment identity is `<CLUSTER>-<NAMESPACE>`.
- Release vs snapshot is decided by a **branch**, not by a version field. On
  `PLATFORM=EUREKA` that branch is `PLATFORM_BRANCH` (repository `platform-lsp`),
  and it is the only branch parameter in play — `FOLIO_BRANCH` and `OKAPI_VERSION`
  are hidden on EUREKA and have no effect.
- `APPLICATIONS` is derived from the selected branch's `platform-descriptor.json`
  and differs between releases. Never copy an applications list from one release to
  another.
- How to check a branch for a FOLIO release: [releases.md](releases.md).
