# JK -- repository instructions

## Purpose

This directory builds **JK**, a local web panel (`jk serve`, run in Docker through `compose.yaml`) for jobs on the FOLIO Jenkins controller:

`https://jenkins.ci.folio.org`

JK talks to that controller over its REST API. JK uses its own HTTP client; it does not shell out to a Jenkins CLI.

## The Jenkins credential

- The API token goes in `JENKINS_API_TOKEN` in `.env` at the repository root, which Git ignores; keep it readable only by its owner (`chmod 600 .env`); never put the token in documentation, shell history, or a job parameter. `.env.example` is the tracked template and holds placeholders only; README "Configure" says how JK reads `.env`.
- Never disable TLS certificate validation.
- `JENKINS_URL`, `JENKINS_USER_ID` and `JENKINS_API_TOKEN` are the only values JK reads from the environment. Job parameters, passwords included, live in the saved jobs in `.jk/runs.db`; JK has no secret store, no `env:` reference, and no masking. Do not reintroduce one.

## Project documents and their authority

Each kind of decision has exactly one authoritative document. Read the relevant
one before changing anything; do not create a parallel document.

| Document | Authority for |
|---|---|
| `spec.md` | the specification: what JK does and does not do, and the accepted technical decisions -- stack, storage, submission protocol, monitoring |
| `design/UI_DESIGN.md` | how the panel looks: palette, glyphs and wording; prose for `design/tokens.json`, enforced by `web/src/design.test.ts` |
| `README.md` | how to install, configure and use JK |
| `docs/KNOWN_BUGS.md` | the current state of known defects, never intended behaviour |

`docs/jenkins/` records what the real controller returns. It is observed
reference material about an external system, not a JK contract.

There is no separate technical design document and no plan directory. Finished
plans and development notes are not part of the public source snapshot. Never
add a parallel authority: correct `spec.md` instead.

## UI design rules

Every panel screen must match `design/UI_DESIGN.md`. The rules are not advisory:
only colours from the palette in `design/tokens.json`, a closed set of glyphs,
and **no emoji anywhere in the interface**.

`web/src/design.test.ts`, run by `npm test`, fails on an off-palette colour, an
unapproved glyph, an emoji, or a control that would send a step again.
`design/tokens.json` is the source of truth for colours and glyphs — change it
there, never in a local copy.

## The gate

Before any commit, run `make check`, the chain in the `Development` section of
`README.md`. Stage explicit paths, never `git add -A`.

## Development checks

- Run focused tests while making a change; run the full `make check` gate before committing.
- Format changed Python files with `uv run ruff format <files>` before the gate.
- Follow existing code and test patterns. Keep fixtures offline and use clearly fictional values.

## Read-only CI policy

- Agents may run read-only REST `GET` requests themselves to inspect identity, connectivity, job configuration, parameters, builds, and logs.
- Agents must never change Jenkins state from this project: do not trigger, replay, cancel, or approve builds; never call `buildWithParameters`; and never submit a Jenkins `POST`, `PUT`, or `DELETE`.
- If a requested operation would write to Jenkins, stop and report the exact blocking action instead of executing it.

## Primary documentation

Use the official [Jenkins Remote Access API documentation](https://www.jenkins.io/doc/book/using/remote-access-api/) as the source of truth for every request JK makes.

If this file, `spec.md`, or the README conflicts with the current Jenkins
documentation, verify the behaviour against the official source and against the
controller itself, then correct the one document that owns the statement.
