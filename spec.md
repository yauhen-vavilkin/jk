# JK: Local Jenkins Launcher

**This file is the single specification for JK.** It is the authority for both
the product contract (what JK does and does not do) and the accepted technical
decisions (how it is built). If code and this file disagree, one of them is a
defect; do not resolve the conflict by writing a third document.

## 1. Purpose

JK is a small local web panel for jobs on `https://jenkins.ci.folio.org`,
without repeatedly working with large Jenkins parameter forms. Supporting
arbitrary Jenkins controllers is outside the current scope.

JK works from saved jobs. The user saves a job once, in the Library, from a
job the controller lists, and decides for each parameter whether its value is
fixed, typed at launch, or left to Jenkins. On the Board the user puts saved
jobs into flows by a clear name. JK resolves the full Jenkins job path and the
complete parameter map from the saved job, shows exactly what will be sent,
starts the job, and monitors its result. Normal use never asks for a Jenkins
path.

JK is for one local user. It should be simple enough to build quickly and
stable enough to replace repeated manual use of Jenkins forms or Postman
requests.

## 2. Product principles

- Prefer a small set of saved, complete, understandable actions over a
  generic Jenkins client.
- Never require the user to remember or type a full Jenkins job path during
  normal use.
- Show exactly what will be sent before a job starts; the review changes
  nothing except that a value asked at launch may be typed there.
- Never guess a parameter value. Every parameter of a saved job is fixed in
  the saved job, asked at launch, or left to its Jenkins default and not sent
  at all; the saved job records which, and the review names the defaults.
- Never start the same job again automatically when the previous request has
  an unknown result.
- Preserve enough local state to continue monitoring after the application
  restarts.
- Keep every job parameter value in the saved job, or in the run for a value
  asked at launch, including a password. JK has no other place a parameter
  value can come from. The Jenkins controller credential is not a job
  parameter: it is read from the environment and is never stored with a saved
  job or a run.

## 3. Core concepts

### Saved job

A complete, user-friendly action such as `Recreate an example environment` or
`Run Cypress tests`. It is made in the Library from one parameterised Jenkins
job and nowhere else, and it lives in `.jk/runs.db`. It defines:

- a stable `id`, a clear name, and an operation name;
- the full Jenkins job path;
- for every Jenkins parameter, one mode: `fixed` with a saved value,
  `at launch` with a value typed for each run, or `default`, left to Jenkins;
- whether the action is destructive and needs its target named in review;
- a snapshot of the Jenkins parameter definitions it was saved against.

Only the fixed values, plus the values entered for this run, are submitted. A
parameter left on its Jenkins default is absent from the body, so Jenkins
applies its own. A run cannot change a fixed value; the saved job must be
edited. When Jenkins changes the job's definitions, the saved job is marked as
changed and does not run until the user has looked at the change in the
Library.

### Flow

An ordered list of steps on the Board. A step is a saved job, referenced by
stable id, plus the values typed for this run. Steps run one at a time in their
order; flows run beside each other.

Each step carries a condition, evaluated against the last real result before
it. The default continues after `SUCCESS` or `UNSTABLE` and stops the flow
after `FAILURE` or `ABORTED`. The other three are *only after SUCCESS*, *even
after FAILURE*, and *only after FAILURE*; a step whose condition does not hold
is skipped. A first step, or one after only skipped steps, has no result
before it, and every condition except *only after FAILURE* lets it start.

A flow can be kept as a **saved flow**: its steps in order, with their
conditions and the values typed for them. A flow taken from a saved flow starts
with those values filled in.

### Run

A stored record of one flow. Every flow is a run with a `flow_meta` row. It
contains each step's parameters, step order, timestamps, current state, and
Jenkins queue and build references.

### Parameter values, including passwords

Every Jenkins parameter JK sends carries its value in the saved job, or in the
run for a value asked at launch, and a Jenkins password parameter is no
exception. There is no secret store, no environment reference, and no masking
-- one mechanism, no fallback.

This is a deliberate decision for a personal, single-user application. Values
remain unencrypted in the local run database, which is ignored by Git. JK
restricts its state directory and files to the operating-system user running
it. The owner remains responsible for access to that account, the computer,
and backups. Literal values avoid a run stopping because a variable was not set.

The one credential that is *not* a job parameter is the Jenkins API token. JK
reads it, with `JENKINS_URL` and `JENKINS_USER_ID`, from the process
environment; a value missing there is taken from `.env` at the root of the
checkout. In Docker, Compose passes that same file to the container as
environment variables. The token is never read from a saved job, never stored
in the run database, and never appears in a job parameter.

## 4. Accepted technical decisions

| Area | Decision |
|---|---|
| Runtime | Python 3.14, pinned with `uv` |
| Interface | Local web panel: FastAPI, server-sent events, and a built React frontend |
| Packaging | Docker Compose; the panel is published on loopback only |
| HTTP | Async `httpx` REST client |
| Job identity | Stable `id`; display names are not references |
| Run state | SQLite WAL, one transaction per state change |
| Submission | Persist before POST; never retry an uncertain submission |
| Monitoring | Poll Jenkins REST; automatically resume after restart |
| Flows | Sequential steps with a condition each; flows run beside each other |
| Parameter values | Literal, fixed in the saved job or typed for the run; no secret store and no environment references |
| History retention | Nothing is pruned; an ended flow leaves the Board after 12 hours unless pinned |

## 5. Architecture

The dependency direction is one-way:

```text
web/       The local panel: FastAPI routes, SSE, review, and the built frontend.
engine/    Flow decisions, at-most-once submission, monitoring, and recovery.
jenkins/   Read-only client plus the two write boundaries.
store/     SQLite runs, steps, parameters, saved jobs and flows, and Jenkins references.
```

`jk serve` is the only command. The frontend's source is the top-level `web/`
directory; its build is served by the panel.

`Dockerfile` and `compose.yaml` package `jk serve` with its dependencies and
the built frontend. The run database is a volume, and Compose passes the root
`.env` to the container as environment variables (`env_file`); neither is ever
copied into the image.

JK runs from its checkout: the run-history state directory is always the
checkout's own `.jk/` (in Docker, the volume mounted there), and the
credentials file is always its own root `.env`. Nothing moves either one and
there is no home-directory fallback; a `jk` that cannot find its checkout
refuses to start with a clear message.

## 6. Jenkins validation and the parameter map

Opening a review reads each distinct referenced Jenkins job's parameter
definitions. The supported named definition types are
`StringParameterDefinition`, `TextParameterDefinition`,
`BooleanParameterDefinition`, `ChoiceParameterDefinition`,
`CascadeChoiceParameter`, and `PasswordParameterDefinition`. Unnamed
definitions, including the observed unnamed `DynamicReferenceParameter`, are
metadata and are ignored.

Validation compares only the names JK will send against Jenkins, because a
parameter left on its Jenkins default is absent from the body on purpose:

- a name Jenkins does not define is blocking;
- a sent parameter of any other named definition type is blocking;
- a value that is not one of the parameter's static Jenkins choices is
  blocking;
- a password parameter with an empty value is blocking;
- the Active Choices placeholder `error` is refused, whether as a value JK
  would send or as the Jenkins default of a parameter JK leaves unsent;
- a value asked at launch that is still empty blocks the start;
- every value that is sent is submitted explicitly, as written.

### 6.1 Active Choices limitation

The definitions response is sufficient to validate a parameter's name, type, and
static metadata, but it is not a contextual evaluation of an Active Choices
script. A `CascadeChoiceParameter` may calculate its valid values from upstream
selections such as `CLUSTER` or `NAMESPACE`; its reported default is an
observation and may be the sentinel `error`, not proof that a saved value is
valid. JK must never carry that placeholder into a build, must not silently
replace a saved value with a default, and must report a failed contextual
validation as a blocking status on the open review itself. The read-only
contract suite therefore verifies the definition shape and observed defaults
only; it never submits a build to prove a dynamic choice.

## 7. Execution behavior

A step moves through these states:

```text
Prepared -> Queued -> Running -> Success
                              -> Failed
                              -> Unstable
                              -> Aborted
                              -> Rejected
                              -> Needs attention
```

Review is the approval, and the server holds it. There is no separate
confirmation screen. The review changes nothing except that a value asked at
launch may be typed there. It shows every step with its saved job, Jenkins
path, and condition, every value exactly as it will be sent, and the
parameters left to Jenkins with their Jenkins defaults. It names every
destructive step with the cluster and namespace it will send, or says they are
left to the Jenkins default; it never guesses. It returns a token that
fingerprints exactly what it showed.

Starting a flow, resuming one, and releasing held steps each require the token
of a review read just before. The server repeats the review and refuses when
anything changed, when Jenkins changed a saved job, or when a value asked at
launch is empty. The reviewed bodies are frozen and sent as they are, whatever
later edits the saved job gets. Every question a flow can foresee is asked
before it starts; the flow then runs to the end unattended.

A step is **held** when what it would send has not been reviewed: the flow
waits at it and sends nothing for it until it is reviewed. That is:

- a step added to a flow that has started;
- after a restart, every destructive step not yet sent: an approval belongs to
  the session that gave it;
- a step whose saved job Jenkins has changed by the time its turn comes.

JK never approves a step by itself. Genuinely unforeseeable events — a
rejected submission, an ambiguous response — still stop the flow and cannot be
asked in advance; what a failed build does is the next step's condition.

JK stores state before and after each external action. Once Jenkins returns a
queue or build reference, JK stores it and uses it for all further monitoring.

JK must never automatically submit a step that already has evidence of
submission. If a network or protocol failure makes it impossible to know
whether Jenkins accepted a request, the run becomes `Needs attention`. JK
does not retry the submission or continue the flow; the user decides, and may
link the step to an existing build read-only or end the flow.

Monitoring requests may be retried after temporary connection failures.
Monitoring retries never create or repeat Jenkins builds. When a queue item
or build can no longer be found, JK preserves the last known state, marks
the run as requiring attention, and does not continue the flow.

## 8. Storage

Saved jobs, saved flows, and execution state remain local to the user's
computer. State updates must be durable and must not leave a partially updated
flow after a normal process interruption.

The dedicated `.jk` directory has mode `0700`; the database, SQLite sidecars,
process lock, and running-address file have mode `0600`. Startup tightens the
permissions of existing state owned by the current user without replacing its
data. It refuses symbolic links and state owned by a different user with a clear
startup error. In Docker the default owner is `jk`, UID 1000; a custom container
user needs a state volume prepared for that user.

The engine's tables are `runs`, `steps`, and `step_params`. The panel adds
`presets` (saved jobs), `saved_flows`, `jenkins_jobs`, `flow_meta`, and
`flow_step_meta` beside them and never replaces an engine table, so a release
that only adds tables keeps the run history:

- every flow is a run with a `flow_meta` row; `flow_step_meta` holds each
  step's saved job, condition, values typed for this run, and whether its body
  is frozen or held;
- `steps.job_config_id`, `job_name`, `job_path`, and `destructive` snapshot the
  saved job when the step is added; `job_config_id` holds the saved job's id;
  the columns `runs.kind`, `runs.source_id`, `runs.state`, `steps.operation`,
  `steps.result`, `presets.description`, `saved_flows.description` and
  `jenkins_jobs.fetched_at` are left over from earlier releases and JK reads
  none of them; they stay because dropping a column from a database that already
  holds history would need a migration, and JK has none: opening the database
  only creates the tables and columns that are missing, and turns a step an
  earlier release stored as `AWAITING_CONFIRMATION` into `PREPARED`;
- every step is inserted before it can be sent;
- `step_params` holds one name and value per parameter the step will send,
  written when a review freezes its body;
- every planned step is stored `PREPARED` until a reviewed start claims it,
  destructive or not; the `destructive` flag is what a restart holds on: no
  approval outlives the session that gave it, so after a restart every
  destructive step not yet sent is held again.

History remains available after restart. Nothing is pruned: every flow that has
started stays in History. A flow that has ended leaves the Board 12 hours after
it finished or failed, unless it is pinned, and stays in History. A draft that
never ran is not history, and removing it deletes it. JK provides no long-term
archival, analytics, synchronization, or reporting.

Run again creates a READY copy and opens its mandatory review. The original
run stays on the Board until the copy starts successfully. A failed review
sends nothing; Cancel removes only the copy. If JK cannot be reached to cancel,
the review stays open and reports the failure. After a reload, any unsent copy
remains a draft that can be reviewed or deleted; the original stays available
and can be removed from the Board separately.

A later step result never rewrites the run's error: a step that was already in
flight when the run failed or needed attention may still record its final
result, but the run keeps its error. A build that was already running cannot
overwrite a failure it did not cause.

## 9. Submission protocol

Exactly two production modules send a Jenkins POST: `jenkins/submit.py`
starts a build, and `jenkins/abort.py` stops one the user asked to stop.
Everything else only reads. A build is started by one function, as follows.

Before claiming the step, JK reads `nextBuildNumber`. If this read fails, no
submission has occurred: the step stays `PREPARED`, and its running flow stops
with the cause stored on the step. The owner fixes the problem, then reviews and
resumes the flow explicitly. Startup never retries it automatically. The stop
and note are conditional on a still-running flow and an unsent step in one
transaction, so a later read failure cannot overwrite a user's Stop or a claim.

```text
1. tx: save nextBuildNumber and timestamp; set SUBMIT_PENDING
2. POST buildWithParameters exactly once, with the stored values
3. 201/303 + Location -> QUEUED and persist queue URL
4. clear rejection -> final rejected/error state
5. uncertain response -> NEEDS_ATTENTION
```

No caller retries step 2. Startup converts a leftover `SUBMIT_PENDING` state to
`NEEDS_ATTENTION` before anything can reach Jenkins or the panel starts.
Reconciliation remains read-only and user-driven.

All persisted transitions are conditional on their expected prior state and
return whether they changed one row. A late queue/build poll therefore cannot
overwrite a newer final or attention state. Only one JK process may use a state
directory at a time: startup takes an OS lock before opening SQLite or recovering
`SUBMIT_PENDING`. A second `jk serve` on the same state directory says where the
first one is and exits.

Every planned step is stored `PREPARED`, destructive or not, and a reviewed
start claims it the same way: the step moves `PREPARED -> SUBMIT_PENDING`
together with its `nextBuildNumber` reconciliation window in one conditional
update, then the POST runs exactly once. Nothing in the panel declines a
planned step, so the claim has no decline to race. No step is claimed whose
body a review has not frozen. A restarted session finds every destructive step
not yet sent held, and must have it reviewed before anything is submitted; it
can never approve itself.

A Stop always wins. A step's claim is valid only while its flow is running,
checked in the same statement, and a flow's steps cannot be removed, moved, or
resumed while one of them is being sent.

Stopping a flow with its build aborted sends one `POST <build>/stop`, or one
`POST /queue/cancelItem` while the step is still queued. It is sent once per
build and never again: not after a failed request and not after a resume.
Stopping a flow without the abort sends nothing.

### 9.1 Candidate matching and unverifiable parameters

`find_candidates` compares the parameters JK sent against the parameters Jenkins
reports for a build. Jenkins omits the `value` key for a password parameter, so a
sent name whose value Jenkins does not report back is
*unverifiable*: it neither confirms nor rules out a build, it is skipped, and it
does not count as a comparison. A build is a candidate only when at least one
sent parameter was positively compared and every compared parameter agreed.
Without this rule a literal password would make every build disagree and
ambiguous submissions of such a job could never be reconciled.

An explicitly reported empty value is compared normally and can confirm a match.
A missing parameter is not evidence of an empty value: it remains unverifiable,
even when JK sent an empty value, and never enters `Candidate.matched`. The reader
does not distinguish an absent name from a hidden password value; neither is
match evidence. Additional Jenkins parameters that JK did not send are ignored.
Candidate details show only reported, compared values. The target summary says
what JK sent, without claiming that Jenkins confirmed an unreported target.
Candidate discovery never links a build automatically or sends the step again.

## 10. Monitoring and restart recovery

Queue and build polling use fixed intervals and a queue-item fallback.
Every poll updates SQLite; the panel hears each change over server-sent events.

After an application restart, JK finds unfinished flows, checks their actual
state in Jenkins, and continues monitoring. It starts a flow's next step only
when that step's condition accepts the result before it. A restarted session
resumes monitoring and advancement at startup; it stops at every destructive
step not yet sent, which is held for review (section 7).

`FlowSupervisor` owns one task per active flow inside the current process:
never two, and never one that outlives its flow. `start()` holds every
destructive step not yet sent in each flow that has started, then watches each
flow that is running or still has a build in Jenkins. A flow's task:

1. polls the step that is in Jenkins, if any;
2. stops when a step needs attention, or when the flow is no longer running;
3. fails the flow after a rejected submission;
4. takes the next step still waiting its turn, and finishes the flow when
   there is none;
5. waits at a held step and sends nothing for it;
6. applies the step's condition: the step runs, is skipped, or fails the flow;
7. sends the step once, through the claim of section 9, only when a review
   froze its body and Jenkins has not changed its saved job since; otherwise
   the step is held.

A step added to, moved in or removed from a running flow, held steps released
by a review, and a linked candidate each wake the flow's task. The supervisor
deduplicates watchers, so startup and the panel cannot poll the same flow twice.

The process lock complements this in-process deduplication. It prevents a
second process from recovering a submission while the first process still owns
the POST, which SQLite row claims alone cannot establish.

Linking an ambiguous candidate stores its queue/build reference, changes the step
to the corresponding monitorable state, and wakes the flow's task.

`estimatedDuration` is stored with build timing data. The panel labels it as
an estimate and computes remaining time without claiming exact percentage
progress. JK does not duplicate the full Jenkins console log; the user opens
Jenkins when detailed logs are needed.

## 11. Errors and safety

JK distinguishes between these problems:

- Jenkins authentication or authorization failure;
- connection or temporary monitoring failure;
- rejected job submission;
- ambiguous submission result;
- missing or inaccessible Jenkins queue item or build;
- Jenkins final results `FAILURE`, `UNSTABLE`, or `ABORTED`.

Each error message explains what happened, which flow step is affected, and
what the user can do next. Raw protocol details may be available for diagnosis
but must not replace the clear message.

Each time the panel is opened, and on each status poll while Jenkins is
unreachable, it checks the token with a read-only `GET /me/api/json`. While
Jenkins refuses it, every page says so and what to do, and nothing else in the
panel works.

Jenkins validation errors identify the saved job and parameter. They render as a
blocking status on the open review. Monitoring errors preserve the last known
state and retry only read-only requests with bounded backoff. Exhaustion moves
the step to `NEEDS_ATTENTION`.

A destructive step is sent only after a review that named it (section 7), and
after a restart only after a new one. Destructive jobs are explicit flow steps;
JK has no automatic cleanup after failure.

JK cancels Jenkins work only when the user asks, with one request sent once
and never repeated (section 9). Closing the browser or stopping JK does not
cancel a Jenkins build.

Only the panel may use the panel. The server answers only requests addressed
to a loopback name (`127.0.0.1`, `localhost`, `::1`), and accepts a change only
with the `X-JK-Panel: 1` header, so no other website open in the browser can
read or start anything.

Values, passwords included, are shown in the review, stored with the run, and
submitted as written. JK does not mask, redact, or hide them: there is
nowhere else they could have come from. Error boundaries still keep raw Jenkins
response bodies out of stored state, rendered text, and logs, because a response
may echo content JK never chose to send.

## 12. Testing and gates

Every behavioral change follows red-green-refactor. Tests are split by contract:

- store tests proving conditional, one-transaction state changes and the
  atomic claim;
- engine tests for at-most-once submission and restart continuation;
- flow supervisor tests for conditions, held steps, stop and abort, resume,
  and watcher deduplication;
- panel API tests over `httpx.MockTransport`, from a saved job to a finished
  flow, and safety tests proving Jenkins receives nothing nobody reviewed;
- a structural test that only the two write boundaries can write to Jenkins;
- startup tests proving pending submissions are recovered before anything can
  reach Jenkins;
- packaging tests for the Docker files and the built wheel;
- frontend tests, including the design rules in `web/src/design.test.ts`;
- opt-in read-only Jenkins contract tests.

`ruff`, the full pytest suite, `git diff --check`, and the frontend's
typecheck, tests, and build are the required gates; `README.md` lists the
commands. Automated agents never perform a Jenkins write. A real submission is
a separate human-only acceptance check.

## 13. Scope

JK includes:

- a local web panel, run in Docker and published on loopback only;
- saved jobs made in the Library from the controller's parameterised jobs,
  grouped by operation;
- flows of sequential steps with a condition each, run beside each other, and
  saved flows;
- for each parameter, a value fixed in the saved job, a value typed at launch,
  or the Jenkins default;
- a final review before submission;
- review of every destructive step, with its target, before it is sent;
- Jenkins queue and build monitoring with labelled estimates;
- durable active-run state;
- recovery and continued monitoring after restart;
- read-only reconciliation of ambiguous submissions;
- stopping a build, once, when the user asks;
- run history.

JK does not include:

- a terminal interface;
- a shared server, accounts, or team synchronization;
- execution of arbitrary jobs without a saved job;
- environment profiles, job templates, or overriding a fixed value for one run;
- a secret store, environment-variable parameter values, or value masking;
- dynamic Jenkins Active Choices loading;
- parallel steps inside one flow;
- branching beyond a step's condition, or automatic job retries;
- automatic cleanup;
- a full Jenkins log viewer;
- notifications, statistics, analytics, or reports.

## 14. Acceptance criteria

JK is complete when all of these behaviors can be demonstrated:

1. The user starts a saved job from the Board by its operation and clear
   name, without entering a Jenkins job path.
2. Before submission, JK shows the complete parameter map of every step,
   exactly as it will be sent.
3. JK sends each step at most once, follows an accepted job from the Jenkins
   queue to a build, and shows its final result.
4. A flow starts its next step only when that step's condition accepts the
   result before it.
5. Under the default condition, `FAILURE` or `ABORTED` stops the flow and
   identifies the affected step.
6. After JK is closed and restarted, it continues monitoring an existing
   build without creating another build.
7. A connection failure or ambiguous submission response never causes an
   automatic duplicate submission; the user resolves it read-only.
8. A destructive step is never sent without a review that names it with the
   cluster and namespace it will send. After a restart every destructive step
   not yet sent is held for review, and JK never approves one by itself.
9. A raw Jenkins response body never reaches stored run state, rendered text,
   or logs.

## 15. Known validation gap

The Jenkins submission protocol still lacks a committed result from a real write
against the current controller. Repository policy prohibits agents from closing
that gap. Live queue shape and controller-specific response details therefore
remain human-verification items.
