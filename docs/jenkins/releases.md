# Choosing a FOLIO release branch

Companion: [createNamespaceFromBranch](jobs/createNamespaceFromBranch.md).
Repository: [folio-org/platform-lsp](https://github.com/folio-org/platform-lsp).

The pipeline behavior below was observed in August 2026. Branches, release
versions and application lists change; verify the current target before saving
parameters. This is a selection guide, not a list of tested deployment presets.

## Select the platform's branch

On `PLATFORM=EUREKA`, `PLATFORM_BRANCH` selects a branch of `platform-lsp`.
`FOLIO_BRANCH` and `OKAPI_VERSION` are hidden in the Jenkins form and do not select
the Eureka release. On `PLATFORM=OKAPI`, `FOLIO_BRANCH` selects a branch of
`platform-complete` instead.

The observed branch selectors list repository branches without checking whether
each branch supports this job. A selectable branch is not proof that deployment
will work. A release tag is also not necessarily a selectable branch. Use the
release's documented branch and inspect its files; do not infer ancestry or
release compatibility from a matching version string.

## Check the descriptor and applications

For Eureka, inspect `platform-descriptor.json` on the selected `platform-lsp`
branch. The pipeline builds `APPLICATIONS` from `applications.required`,
`applications.optional` and `applications.experimental`. The observed script
returns an empty application list if the descriptor cannot be read.

1. Confirm the selected branch has a readable descriptor.
2. Check its release name and version against the intended release.
3. Choose application names from that descriptor. Do not copy a saved list from
   another release or working branch.
4. Review the target cluster, namespace and backing-service settings separately.

The default `snapshot` branch represents development state. A custom branch such
as `example-feature` must meet the same descriptor checks; that name is only an
example, not a branch supplied by JK.

## Sources

The recorded behavior comes from `folio-org/pipelines-shared-library`:

- `vars/folioParameters.groovy` and `vars/folioStringScripts.groovy` build the
  selectors and application list.
- `vars/folioNamespaceCreateEureka.groovy` consumes `platformBranch`.
- `pipelines/folioRancher/folioNamespaceTools/manageNamespace/createNamespaceFromBranch/Jenkinsfile`
  controls which parameters are visible for each platform.

Check those sources and the current read-only job definition when the form
changes. JK does not execute Active Choices scripts, and these notes do not
replace a human review or live deployment acceptance.
