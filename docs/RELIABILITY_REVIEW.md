# Critical reliability review

**Scope:** public source at `d08bbd3d92099dd5e7272720fed2758a0e82bbd4`, not the state of any deployment. Findings are prioritized risks and proposed work, not claims that fixes are implemented. See the [phased reliability plan](RELIABILITY_IMPLEMENTATION_PLAN.md). Synthetic results do not establish real-world bird recall or hardware reliability.

## Strengths

The architecture separates photo capture from optional analysis, bounds the writer and analysis backlog, uses pre-trigger buffering and camera locking, and includes storage recovery and privacy safeguards. The repository has a substantial automated test suite and explicit specification and traceability documentation. These are useful foundations, not proof of current field performance.

## Findings

| Priority | Evidence and finding | Impact and next action |
|---|---|---|
| P0 | **Code inspection (with a previously reported synthetic reproduction not included here):** transient detector activity that starts and clears between event sampling ticks can be missed. In `src/birdwatcher/runner.py`, detector updates replace `active` before the sampled event machine sees it. | A genuine short motion pulse can produce no event or photo. Latch observed regions between sample ticks and add deterministic end-to-end regression coverage; this does not quantify missed birds in the field. |
| P0 | **Code inspection:** health writes in `runner.py` can raise on storage failure, including during reconnect and shutdown. `cli.py` reports a local I/O error, but a failed write can leave the on-disk health record stale. | Operators may lack a fresh durable status precisely during a storage fault. Define bounded fallback reporting, explicit freshness and exit behavior, and fault-injection tests. |
| P0 | **Code inspection:** `cli.py` checks storage errors and frames received for the run exit status, but not `dropped_saves`. | A run can appear successful despite dropped save actions. Report drops as a degraded or failed outcome and test queue saturation. |
| P0 | **Code inspection / recovery risk:** an event directory may be created before its first manifest is successfully written. | A failed initial write can leave an incomplete artifact. Make creation transactional or recovery safe and idempotent; never delete ambiguous or unmanaged data. |
| P1 | **Code inspection:** `AnalysisQueue` defaults to 100 pending/running jobs and allows a smaller limit; completed and failed jobs do not count against that limit. A separate database storage budget applies, but no completed-result cleanup lifecycle is provided. | Long-term accumulation can exhaust the storage budget even as work finishes. Specify backlog visibility and an owner-approved derived-data retention policy, keeping analysis independent of capture. |
| P1 | **Repository inspection:** no public CI workflow was present at the reviewed commit. `doctor` reports enabled region count but does not make zero enabled regions an explicit readiness warning. | Repeatable offline automation and a clearer onboarding/readiness check would reduce integration and setup failures. |
| P1 | **Evidence gap:** synthetic tests and source inspection do not validate the current physical camera, storage, private orchestration, recovery or sustained operation. | Require owner-approved isolated hardware validation and explicit rollout/rollback gates before claiming field readiness. |

A previously reported synthetic reproduction is limited to the motion timing scenario; its standalone evidence is not included here. The finding is independently supported by source inspection. Other rows are source-inspection findings or validation gaps. No test-suite pass count is asserted here. Prior results do not establish the current state of a deployment, and no current field validation is implied.

## Order of work

First protect capture and failure visibility, then address analysis lifecycle and onboarding, then reproducible CI and separately approved hardware validation. Follow the [plan](RELIABILITY_IMPLEMENTATION_PLAN.md) for tests, safety boundaries, issue relationships and acceptance gates. Existing age/quota retention is distinct from recognition-based deletion; do not enable a new deletion policy without approval.
