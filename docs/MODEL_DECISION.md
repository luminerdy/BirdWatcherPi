# Bird presence — model decision and evidence

Status: experimental **shadow-mode** selection, not an accuracy claim or authorization to filter captures. Species identification remains separate future work.

## Selected candidate

OpenCV Zoo **NanoDet-m-plus-1.5x_416**, FP32 ONNX, using the existing OpenCV DNN CPU backend. The model was selected for a small, locally exercised runtime footprint without adding Torch or an inference service.

- Pinned Zoo revision: `48b10fa505aeb51fbd127fc60a5c660040e823b7`.
- Artifact: `object_detection_nanodet_2022nov.onnx`.
- Size: **3,800,954 bytes**.
- SHA-256: `4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186`.
- Exact contiguous class index **14** is `bird`, verified from the pinned official label tuple. This is not necessarily a dataset category ID.
- Code/model directory explicitly licenses all files under Apache-2.0. See the preserved license and attribution files in `third_party/nanodet/`. The application's own code retains its MIT license; package metadata describes the combined distribution.

Model binaries, test photographs, labels tied to deployment, and detailed benchmark outputs remain private and are not included in Git or a package wheel. Public control photos are not bundled either.

## Real on-device feasibility findings

A bounded experiment used Linux ARM64, Python 3.13.5, OpenCV 4.14.0 and NumPy 2.5.4, one OpenCV CPU thread, and reduced scheduling priority. No camera settings or original photos were changed.

- Two public CC0 bird-positive images were exercised, alongside eight private negative/uncertain feeder controls in both full-frame and approved-region mode.
- A clearly visible branch bird produced a model score about **0.4475** and was returned at thresholds 0.25 and 0.4, but not 0.6.
- A partly occluded feeder bird scored about **0.2804**, while feeder hardware produced a false `bird` box around **0.3979**. Both disappeared at 0.4.
- The private controls returned no bird boxes at the tested thresholds, but they are not certified empty-feeder ground truth. Other non-bird false object labels occurred.
- Measured median inference pipeline latency was about **128 ms**, p95 about **147 ms**, excluding file I/O/JPEG decoding. Peak process RSS was about **142 MiB**, including interpreter and image buffers, not model-only memory.
- Capture remained alive during that experiment, but capture latency and sensor-frame losses were not instrumented. Do not infer zero contention or long-term stability from these measurements.

These results establish runnable local inference, **not reliable feeder bird confirmation**. Threshold 0.25 is a provisional review setting, not calibrated probability. Raising the threshold can remove genuine birds as well as false positives.

## Preprocessing/postprocessing contract

Preserve the pinned official convention: decoded BGR image to RGB; aspect-preserving 416×416 letterbox with zero padding; normalization using mean `[103.53, 116.28, 123.675]` and standard deviation `[57.375, 57.12, 58.395]`; no additional channel swap during blob creation.

The pinned decoder uses strides 8/16/32/64, eight-bin distance distributions, argmax class scores, and class-agnostic NMS at IoU 0.6. Reverse letterbox scaling/padding and any crop offsets to original-image coordinates; clip and reject degenerate/nonfinite boxes. A generic object label is not a bird result.

## Safety decision

Proceed with saved-frame shadow analysis only:

- `bird_candidate`: the model proposed a bird, requiring review; not a verified bird visit.
- `unknown`: no returned bird candidate; **not** proof of an empty feeder.
- `analysis_failed`: no usable analyzed evidence because processing failed.

Preserve all originals and capture manifests. Sampled images cannot establish what happened in unexamined frames or reveal missed arrivals. Collect reviewed deployment positives, sway-only events, and difficult lighting/occlusion before considering any filtering or stronger confirmation rule.

## Primary provenance

Pinned model-directory README, license, decoder, and demo:

```text
https://raw.githubusercontent.com/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_nanodet/README.md
https://raw.githubusercontent.com/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_nanodet/LICENSE
https://raw.githubusercontent.com/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_nanodet/nanodet.py
https://raw.githubusercontent.com/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_nanodet/demo.py
```

Positive-control provenance retained privately: owner-published CC0 `Sparrows1.JPG` on Wikimedia Commons and a second Commons CC0 bird photograph with retained license-review metadata. The second photograph's original host was blocked; do not claim independent original-host verification. Neither control proves deployment accuracy.
