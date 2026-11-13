# Operations — early capture milestone

## Current recovery status

**Production capture is manually paused and not restored. Keep it stopped.** The kernel NTFS3 driver failed actual production health-file replacement. Limited `ntfsfix` work and the NTFS-3G replacement driver allowed isolated temporary-file and replayed-writer tests, but subsequent actual recorder startup still failed with `EIO` replacing the real `health.json`. A stale `capturing` value is not live evidence. Do not repeat filesystem repair blindly or treat synthetic URL-whitespace/ENOSPC regression results as a filesystem repair.

Recovery acceptance requires an approved supervised daylight test: real recorder startup, fresh saved JPEGs read back successfully, and a successful restart, with current process/frame evidence and all storage/solar guards intact. Preserve originals, keepers, backups, and unknown files. This checkpoint does not pass those gates or authorize a restart.

A sunrise attempt also failed on a fixed solar-cache temporary filename. Concurrent writers are a hypothesis, not an established cause. Validate the launch path separately after repair.

Gallery/report source is implemented locally but unactivated. Private helper review found import-resolution binding, unrelated-artifact adoption/deletion, and historical-receipt symlink gaps. Automatic report generation and delivery must remain disabled until fixes and adversarial verification pass. Exporter performance work is partially edited and unverified.

The implementation and historical evidence below do not override this failed production status.

## What is available

- `doctor`: brief live camera check and negotiated capture summary.
- `snapshot --output FILE.jpg`: private test photo; refuses overwrite and destinations inside the checkout.
- `run [--duration SECONDS]`: foreground motion-triggered capture using privately configured feeder regions.
- `status`: last saved local health report. This is a snapshot, not a live IPC endpoint; a crashed process may leave a stale report.
- `events --limit N`: inspect local event manifests without starting the camera.
- `report --packet FILE --output-dir DIR`: read-only offline gallery/activity report from a completed packet, optionally with a matching prepared receipt. See [DAILY_REPORT.md](DAILY_REPORT.md).
- `analyze --model FILE`: optional separate-process shadow analysis of completed events; records provisional bird candidates without changing or filtering photographs. See [SHADOW_ANALYSIS.md](SHADOW_ANALYSIS.md).

Put global `--config FILE` before the subcommand. Read-only inspection does not create an absent data directory. The core CLI does not provide a species classifier, correction/reanalysis command, web server, messaging integration, or startup-service installer. The approved deployment uses separate private daylight/review/Hermes helpers for scheduling and Telegram digests; these are not installed by cloning this repository. See [ARCHITECTURE.md](ARCHITECTURE.md) for the Mermaid diagrams and implementation boundary.

## Stored data

A dedicated private data directory contains date/event directories, `originals/*.jpg`, event manifests, a run lock, and `health.json`. Captured JPEG bytes are preserved rather than replaced with annotated images. UTC timestamps are receipt times, not guaranteed sensor-exposure timestamps.

Event manifests distinguish complete/incomplete captures and mark identification as not configured. Camera-reconnect and writer-overload interruptions must remain visible. Keep private manifests, logs, configurations, and views out of public issues and commits.

Storage cleanup applies only to recognized, eligible managed events. Active/pinned events are protected. Pinning is a metadata protection mechanism in this early release; a dedicated pin/unpin CLI is not implemented. The configured age/quota/free-space limits can remove unpinned events. The approved private review copies verified selected originals into a separate keeper archive outside this raw-retention root. The deployed raw policy is 14 days / 40 GiB with a 2-GiB reserve; package examples use a 5-GiB quota. Ordinary history may expire; do not wipe keepers, preserved backups, or unknown files. Review is not a recognition-based deletion policy.

A bounded writer separates camera acquisition from disk writes. Missed saves and I/O failures are counted. This is not lossless capture: stalls, connection failures, overload, poor light, or missed motion can lose photos. Inspect health rather than assuming zero losses.

## Private daylight and review automation

Approved private schedules implement near-sunrise arming and periodic evening-readiness checks; they do not override the current manual pause. The supervisor validates date/timezone/ephemeris, pause/storage identity, and an absolute conservative sunset cutoff. A missing/wrong volume must not fall back to internal storage. The separately reviewed recorder storage-pressure fix is now reconciled into source. The source also reports writer queue depth, pending JPEG bytes and cached storage-full/last-error fields; these are last-observed state, not a fresh disk probe or liveness guarantee. Existing immutable runtime adoption must be verified separately.

The core foreground run command does not implement those solar/volume guards. Do not bypass them for unattended operation or install a second competing recorder. A job marked enabled/scheduled and an old health file do not establish liveness; inspect the real process plus fresh increasing frame receipts at the configured live root.

After capture is idle, bounded local NanoDet sampling produces candidate/control sheets. The approved visual-review agent inspects at most six sheets / 120 tiles and up to three originals/crops, selecting at most three keeper photographs for the digest. Source hashes and explicit packet-bound decisions are checked before finalization. The finalizer supports at most five keepers, but the automatic review uses the smaller budget. Sampling is intentional; no box/unknown does not mean an empty feeder.

Capture and local NanoDet do not use cloud inference. Solar lookup, selected-image external AI review, and private Telegram delivery are separate service boundaries. The prepared receipt proves local finalization, not delivery. Unchanged packet fingerprints/receipts suppress duplicates; uncertain delivery must not be blindly replayed.

## Stop and recovery

Use Ctrl-C or SIGTERM for graceful shutdown. This closes the active event, drains the bounded writer, closes storage, and releases camera ownership. Do not run two capture processes against one camera. A per-user camera lock coordinates application commands; it cannot stop unrelated applications from opening the device.

On camera failure, the run loop closes the interrupted event, resets detection, and retries with capped backoff. A new stream gets a new warm-up period. A process that is forcibly killed can leave an incomplete event; next startup must recover it as incomplete rather than claim an intact capture.

If disk writes fail, inspect the health counters and free space. The initial implementation retries subsequent event writes and must not delete unrelated files to make space. If protected events fill the quota, move or unpin selected data deliberately. Never delete a credential file or private configuration as part of cleanup.

Recovery claims temporary files only when their journal-recorded identity, canonical path, size, and hash can be verified. Corrupt/partial files, unjournaled metadata temporaries, and legacy temporaries without a recorded nonce are deliberately preserved and may need operator inspection. Do not bulk-delete unknown files to clear a quota error. Process-termination tests are not a guarantee against every physical power-loss scenario.

## Validation and limitations

Repeatable tests use synthetic/replayed scenes and isolated temporary files. They do not establish real-world bird arrival capture yield or species accuracy. Private framing/focus review, real photos, and local detector runtime feasibility have been exercised. Calibrated field accuracy, physical disconnect/power-loss testing, and a 24-hour cumulative daylight-only soak remain distinct evidence gaps in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

The public package installs no automated service and this documentation performs no reboot. Private approved scheduling exists separately; portable packaging and coordinated reboot/rollback validation remain incomplete. To revert a session, coordinate the existing supervisor/schedule, stop capture, and use the prior known-good environment/configuration without starting a competing owner. Preserve raw data, keeper archives, and backups outside the checkout.
