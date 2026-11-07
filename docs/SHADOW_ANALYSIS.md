# Optional bird-presence shadow analysis

This is a **separate process that reads saved, completed events**. It does not own the camera, change the capture configuration, edit event manifests, delete photos, or suppress future captures. It is not a live filtering gate or a species identifier.

Read [MODEL_DECISION.md](MODEL_DECISION.md) first. The model has demonstrated both real detections and false positives; no production score threshold or feeder accuracy has been established.

## Private model installation

Keep the model outside every Git checkout. No model is bundled and application startup never downloads one automatically. Obtain the exact pinned artifact and verify its hash before use:

```sh
set -eu
model_dir="$HOME/.local/share/birdwatcher/models"
mkdir -p "$model_dir"
chmod 700 "$model_dir"
tmp="$model_dir/nanodet.onnx.download"
curl --fail --location \
  'https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_nanodet/object_detection_nanodet_2022nov.onnx' \
  --output "$tmp"
printf '%s  %s\n' \
  '4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186' \
  "$tmp" | sha256sum --check
chmod 600 "$tmp"
mv "$tmp" "$model_dir/nanodet.onnx"
```

Retain the model's Apache-2.0 license and notices with a redistributed model; the source repository includes them in `third_party/nanodet/`. The application also verifies the pinned model before loading it. A different file is an error, not an invitation to load an arbitrary model.

## Analyze a bounded batch

Use the existing private capture configuration to select the approved feeder region:

```sh
.venv/bin/birdwatcher --config "$HOME/.config/birdwatcher/config.toml" analyze \
  --model "$HOME/.local/share/birdwatcher/models/nanodet.onnx" \
  --analysis-dir "$HOME/birdwatcher-analysis" \
  --limit 20 --frames-per-event 3 --threshold 0.25
```

The analysis directory must be private, outside Git, and separate from—not inside or an ancestor of—the capture data directory. The default is a sibling of the capture data root with `-analysis` appended to its name. Keeping results separate avoids changing the files managed by the capture writer and its retention logic.

Without an enabled region, the command refuses analysis unless `--full-frame` is explicitly supplied. This flag is useful for separately reviewed full-image experiments, not a way to silently override calibration.

## Watch for a bounded time

Add `--watch-seconds 600` to repeat analysis passes for approximately ten minutes. The duration is checked between bounded passes; it is not a hard real-time cancellation deadline for an in-progress inference/pass. A pass can finish after the watch deadline. Omit the option or use zero for a single pass. The CLI rejects unbounded or invalid watch durations.

No service or schedule is installed. Use a separately installed capture snapshot if developing or updating analysis code while a capture session is running; never replace that running environment during a test.

The analyzer uses one OpenCV CPU thread and reduced process priority when supported. It has its own worker lock, not the camera lock. Still monitor capture health: a successful inference benchmark does not prove there is no CPU/I/O contention.

## Queue and result meaning

The private SQLite store holds idempotent jobs and result metadata. At most 100 jobs may be pending/running; excess discoveries are deferred. Interrupted work can be retried within a bounded attempt budget. The queue/database also has a size limit and stops analysis rather than growing without bound. These limits affect analysis only, not the capture process.

The job fingerprint includes model/settings, region geometry, the source event/manifest and frame-sampling choice. The same unchanged event is not repeatedly inferred on every pass. New analysis settings create a distinct job, not an overwrite of capture records.

By default, up to three saved frames represent an event. A result describes those sampled frames, **not every moment of the visit**:

- **`bird_candidate`**: a model-proposed bird box was returned. Review it; hardware can be a false positive.
- **`unknown`**: usable samples produced no bird candidate. This is not an empty-feeder or no-bird assertion.
- **`analysis_failed`**: no usable inference evidence was obtained. Missing/corrupt inputs and processing errors remain distinct from valid unknown outcomes.

Results retain model hash/version, score threshold, region/frame provenance, sample outcomes and original-image bounding boxes. Partial processing errors must remain visible. CLI totals count analysis work, not verified birds or unique visits; repeated watch passes can rediscover the same manifests without reprocessing identical completed jobs.

A capture retention pass can remove an eligible event between analysis discovery and reading. That is an explicit missing-input analysis outcome; the analyzer must not recreate or modify the event to hide the race.

## Next validation gate

Collect manually reviewed deployment bird positives and sway-only/lighting examples. Assess false positives and misses on a separate evaluation set before any suppression or deletion policy. Do not infer detection recall from triggered photos alone. Species classification, manual correction workflows, a capture-internal analysis worker, and automatic filtering remain future work.
