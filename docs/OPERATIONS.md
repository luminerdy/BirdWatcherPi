# Operations — early capture milestone

## What is available

- `doctor`: brief live camera check and negotiated capture summary.
- `snapshot --output FILE.jpg`: private test photo; refuses overwrite and destinations inside the checkout.
- `run [--duration SECONDS]`: foreground motion-triggered capture using privately configured feeder regions.
- `status`: last saved local health report. This is a snapshot, not a live IPC endpoint; a crashed process may leave a stale report.
- `events --limit N`: inspect local event manifests without starting the camera.
- `analyze --model FILE`: optional separate-process shadow analysis of completed events; records provisional bird candidates without changing or filtering photographs. See [SHADOW_ANALYSIS.md](SHADOW_ANALYSIS.md).

Put global `--config FILE` before the subcommand. Read-only inspection does not create an absent data directory. There is no species classifier, correction/reanalysis command, web server, messaging integration, or startup service yet.

## Stored data

A dedicated private data directory contains date/event directories, `originals/*.jpg`, event manifests, a run lock, and `health.json`. Captured JPEG bytes are preserved rather than replaced with annotated images. UTC timestamps are receipt times, not guaranteed sensor-exposure timestamps.

Event manifests distinguish complete/incomplete captures and mark identification as not configured. Camera-reconnect and writer-overload interruptions must remain visible. Keep private manifests, logs, configurations, and views out of public issues and commits.

Storage cleanup applies only to recognized, eligible managed events. Active/pinned events are protected. Pinning is a metadata protection mechanism in this early release; a dedicated pin/unpin CLI is not implemented. The configured age/quota/free-space limits can remove unpinned events. Back up important photos outside the managed data root.

A bounded writer separates camera acquisition from disk writes. Missed saves and I/O failures are counted. This is not lossless capture: stalls, connection failures, overload, poor light, or missed motion can lose photos. Inspect health rather than assuming zero losses.

## Stop and recovery

Use Ctrl-C or SIGTERM for graceful shutdown. This closes the active event, drains the bounded writer, closes storage, and releases camera ownership. Do not run two capture processes against one camera. A per-user camera lock coordinates application commands; it cannot stop unrelated applications from opening the device.

On camera failure, the run loop closes the interrupted event, resets detection, and retries with capped backoff. A new stream gets a new warm-up period. A process that is forcibly killed can leave an incomplete event; next startup must recover it as incomplete rather than claim an intact capture.

If disk writes fail, inspect the health counters and free space. The initial implementation retries subsequent event writes and must not delete unrelated files to make space. If protected events fill the quota, move or unpin selected data deliberately. Never delete a credential file or private configuration as part of cleanup.

Recovery claims temporary files only when their journal-recorded identity, canonical path, size, and hash can be verified. Corrupt/partial files, unjournaled metadata temporaries, and legacy temporaries without a recorded nonce are deliberately preserved and may need operator inspection. Do not bulk-delete unknown files to clear a quota error. Process-termination tests are not a guarantee against every physical power-loss scenario.

## Validation and limitations

Repeatable tests use synthetic/replayed scenes and isolated temporary files. They do not establish real-world bird arrival capture yield or species accuracy. Actual feeder calibration, reviewed bird-arrival samples, disconnect testing, model feasibility, and a 24-hour soak remain separate release gates in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

No automated install or reboot is part of this milestone. Later deployment must include an approved least-privilege service and tested rollback. To revert an experimental session now, stop it and use the prior known-good virtual environment/configuration; retain data outside the checkout.
