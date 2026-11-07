# Shadow-analysis integration validation

Scope: optional local, saved-event analysis. This report intentionally omits deployment locations, personal paths, exact capture timestamps, event identifiers, images, and private configuration.

## Actual execution

The new application pipeline was run on saved captures while an independently installed, previously approved camera application continued its time-bounded capture session.

- First pass: 20 events analyzed, 60 sampled frames, all results `unknown`; no failed analyses or partial processing errors. CLI elapsed time was 9.34 seconds, including discovery and analysis work rather than inference alone.
- A subsequent process resumed the durable queue, analyzed 24 more jobs, and produced two `bird_candidate` results and 22 `unknown` results, with no failures. CLI elapsed time was 10.772 seconds.
- The SQLite store was read back: **44 completed results**, consisting of two candidate events and 42 unknown events. These are model/sampling outcomes, not verified visit counts or an absence claim.
- A selected set of **511 original image/manifest files** was fingerprinted before analysis and verified unchanged afterward. This is a measured subset check, not a claim that every original was individually fingerprinted.
- Capture health continued reporting active capture with no recorded reconnects or storage-write errors during those checks. Sensor-frame loss and scheduling latency were not independently instrumented.

## Visual review of candidates

Both candidate frames were inspected privately:

- One contains a real bird at the selected feeder. The model score was about **0.2595**; species was not identified.
- One is a false candidate on feeder material, scoring about **0.2804**.

The false candidate scored higher than the real bird in these examples. Simply raising the threshold would not reliably separate the two. These two reviewed results are far too few, and too selectively collected, to establish accuracy, precision, recall, or a safe filtering threshold. Reference copies remain private, outside both managed capture storage and Git.

Every original was retained; no candidate or unknown result suppresses a photograph. `unknown` means the sampled images produced no returned bird proposal, not that no bird visited.

## Packaging and license checks

A 0.2.0 wheel was built and installed into a new isolated environment without replacing the environment of the running camera process. Its version and analysis-command help were exercised. Wheel inspection verified the application MIT license, NanoDet Apache-2.0 texts/notices, and the decoder were bundled, while ONNX binaries, photos, and databases were not.

The repaired package was rebuilt and reinstalled in that separate environment. Actual inference through its immutable-buffer loader returned a bird candidate on the public positive control, with the same highest model score as the source implementation. The final source passed **139 automated tests**, Ruff lint/format checks, and staged whitespace checks. Future changes must rerun:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
git diff --cached --check
```

Independent review found a model-integrity time-of-check/time-of-use issue in the initial loader: verified bytes were followed by a separate filename read. The repaired loader performs one bounded read, verifies its exact size/hash, and loads that same immutable buffer without reopening the pathname. The replacement-race and bounded-read regressions pass. Follow-up independent review passed with no blocking correctness or security findings in the experimental shadow-mode scope.

## Not yet validated or implemented

- Calibrated field detection accuracy, false-alarm rate, or missed-arrival recall.
- Automatic photo filtering/deletion or live pre-capture gating.
- Species classification and a manual correction UI.
- Capture-internal model worker integration or automatic boot/service installation.
- 24-hour reliability and physical power-loss durability.

See [MODEL_DECISION.md](MODEL_DECISION.md) for the model experiment and [SHADOW_ANALYSIS.md](SHADOW_ANALYSIS.md) for optional operation and uncertainty semantics.
