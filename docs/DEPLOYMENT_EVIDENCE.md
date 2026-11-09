# Sanitized private-deployment evidence

This is a bounded evidence summary for [requirement traceability](TRACEABILITY.md), not a public copy of the deployment or a claim that all acceptance gates passed. The private helpers, settings, photographs, logs, and receipts are not in this repository. Logical `PRIVATE-*` references identify reports about those components, not reproducible public test nodes.

**Evidence boundaries:** implementation, automated tests, physical field validation, packet preparation, and message delivery are separate. A referenced document or an existing test function does not itself prove an entire requirement. Historical smoke/model reports retain their original scope; their old pending lists are not the current project tracker. Current status is in [TODO.md](TODO.md).

<a id="focus"></a>
## Focus and composition

`PRIVATE-FOCUS`: a private feeder-region preview was reviewed and the owner approved a priority feeder with movement allowance. A reversible focus comparison at the feeding plane was exercised and autofocus restored. This supports the accepted single-priority compromise, not sharp focus at every possible distance, a published optical dataset, or an implemented calibration CLI. Perch measurements, views, settings, and the approval discussion remain private.

<a id="storage"></a>
## USB storage and recorder runtime

`PRIVATE-STORAGE`: migration to a dedicated private USB photo volume compared complete file sets, sizes, and SHA-256 hashes, while preserving the original internal archive as a backup. An actual absent-volume permission check and remount were exercised. Private expected-volume guards and a separately tested storage-pressure fix protect the deployed path; the latter is not yet reconciled into this public capture source. Bounded write replays exercised the lower saved-photo rate, but are not a sustained live-camera soak or physical power-loss validation.

The deployed raw policy is 14 days / 40 GiB with a 2-GiB reserve; the package example remains 14 days / 5 GiB. Acquisition requests 15 frames/second while the private saved-photo setting is three photos/second. Keepers and preserved backups are outside managed raw cleanup. Configured limits and a preserved copy do not prove the live volume is currently healthy.

<a id="daylight"></a>
## Daylight supervision

`PRIVATE-DAYLIGHT`: owner-approved private scheduling and supervision were installed for near-sunrise capture and a conservative absolute before-sunset stop. The supervisor has pause and storage checks and refuses an unresolved daylight window. Historical bounded daylight sessions and automatic stops were exercised; private regression tests cover storage and launch guard behavior. They do not establish every solar/timezone/clock edge case or physical darkness sensing.

Enabled jobs were inspected during the documentation refresh. This is a configuration observation, not camera liveness, correct future execution, or reboot-recovery proof. The foreground public `run` command does not implement the private solar guard.

<a id="review-tests"></a>
## Private regression execution

The following isolated tests were actually rerun while preparing the traceability work, without opening the camera or modifying the live capture archive:

- `PRIVATE-COLLECTOR`: 41 collector tests covering bounded sampled packet preparation, mandatory source locking, output/source separation, source provenance, and private atomic writes.
- `PRIVATE-SCHEDULER`: 30 scheduler/monitor tests covering readiness, bounded workers, identity/fingerprint handling, and failure states.
- `PRIVATE-FINALIZER`: 111 finalizer tests covering packet-bound decisions, source hashes, output/source alias protection, keeper copying, complete CSV validation, canonical UTC, idempotent observations, and prepared receipts.
- The separate daylight/storage guard regression module: 11 tests.

Combined actual result: **193 passed, with 3 additional unittest subtests passed**. This includes the 182 private review tests and 11 guard tests. These are local private-suite results, not public CI, proof of complete requirement coverage, or independently reproducible tests from a fresh clone. No private test files or execution artifacts are published here.

The public manifest deliberately distinguishes logical private evidence from actual public pytest node references. Its checker validates the reference structure; it cannot independently audit this private suite.

<a id="pilot"></a>
## Real sampled packet pilot

The real local collector produced a candidate/control review packet from retained event photographs. Source preservation was checked by comparing file size/mtime inventories and event-manifest SHA-256 values before/after review preparation. This was not a fresh full-byte-hash audit of every photograph, an exhaustive scan, or proof that every selected tile was visually reviewed. Recorded model/decoding errors remain limitations, not absence claims.

This supports the packet preparation path. It does not establish successful finalization or delivery for every day, detector accuracy, or an exhaustive visitor count.

<a id="visual-review"></a>
## Bounded visual review

`PRIVATE-VISUAL`: approved private instructions require inspecting listed candidate/control sheets and a bounded number of original-resolution images, selecting sharp, well-exposed photographs with useful variety. Some private saved-photo samples have been visually inspected; this is not a completed untouched evaluation set or automatic quality-ranking implementation.

Current automatic budgets are at most six sheets / 120 shortlisted frames, up to three full-resolution originals/crops, and at most three keeper attachments; the finalizer permits at most five keepers. These caps bound work, not guarantee photographic quality. Selected image context is processed by the configured external vision-capable AI provider, distinct from local NanoDet inference.

<a id="delivery"></a>
## Delivery boundary

`PRIVATE-DELIVERY`: approved private orchestration prepares a dated digest and verified keeper attachment paths for Hermes/Telegram. Fingerprints and prepared receipts suppress duplicate preparation. **Prepared is not delivered.** This documentation task did not perform or verify a new end-to-end digest delivery. No receipt alone establishes Telegram acceptance, and uncertain delivery must not trigger a blind replay.

<a id="limits"></a>
## Unpassed field and release gates

No evidence here passes the 24-cumulative-hour daylight soak, complete physical unplug/replug and power-loss matrix, coordinated reboot/rollback test, combined workload memory budget, calibrated field detection accuracy, or future species-classifier accuracy gate. Referenced subset tests and short sessions are useful evidence, not substitutes for those checks. Public deployment packaging and reconciliation of the recorder's separate storage-pressure fix remain open.

All reports intentionally omit deployment locations, personal paths, device identifiers, exact sighting times, credentials, and captured images. Preserve private originals, keeper archives, and backups; publishing this report authorizes no additional integration or destructive cleanup.
