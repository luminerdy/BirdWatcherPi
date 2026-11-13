# Recovery checkpoint — not a release

This checkpoint preserves unfinished source and documentation before a possible clean-system rebuild. It is **not a verified deployment**, does not enable automatic gallery generation, and must not be interpreted as a claim that recording is working. The stable branch is deliberately unchanged.

## Preserved work

- Private offline gallery/activity data, HTML rendering, bounded export, and CLI source with tests.
- Reconciled storage-pruning performance changes and cached writer/storage health reporting.
- Portable-URL whitespace validation and write-time ENOSPC/EDQUOT classification regressions.
- Updated [specification](SPECIFICATION.md), [implementation plan](IMPLEMENTATION_PLAN.md), [traceability](TRACEABILITY.md), diagrams, and operating guidance.

The exporter optimization was interrupted. Its partial edits are preserved for review, not declared complete. Read the draft pull request for the exact checks performed on this checkpoint; historical test results do not validate subsequent edits.

## Unresolved operational failures

1. The actual recorder failed while atomically replacing its production health file. Isolated create/fsync/rename tests and a separate writer replay passed, but **did not prove that the production recorder could start or save photographs**. Treat storage recovery as incomplete.
2. A scheduled sunrise start also failed when replacing a solar-cache temporary file. Shared temporary-name contention is a hypothesis to reproduce, not an established root cause.
3. A saved health document can still say `capturing` after a stopped process. Require a live camera owner and fresh, advancing frame receipts; inspect actual new image files before reporting success.
4. Limited NTFS metadata repair and alternate-driver access are not exhaustive filesystem validation or proof that all archived files are intact. A different OS image alone does not repair application defects or an existing data volume.

## Additional public exporter blockers from independent checkpoint review

- Pathname-based output writes can escape the validated destination if another actor can rename/replace its directory during publication. Descriptor-relative output ownership and race regressions remain required.
- Failed staged writes leave private staging entries that intentionally block automatic retries; recovery is currently manual.
- Generation fingerprints omit renderer implementation changes, so a renderer/security fix may leave old cached HTML until explicit invalidation.
- File fsync and atomic visibility are not proof of generation/output directory power-loss durability.
- A test-order-dependent inherited-permissions fixture fails in the ordinary full suite after CLI code changes the process umask; the isolated test passes. Do not call that ordinary full run green.

The audit found no publication secrets/backdoors in reviewed source and accepted an explicitly non-deployable archival draft, not runtime activation.

## Private report automation must remain disabled

The private bridge was reviewed before activation and needs:

- Isolated import resolution bound to the fingerprinted runtime, plus loaded-module origin checks.
- Exact exporter generation ownership before registering artifacts for retention; unchanged hashes alone do not prove ownership of unrelated files.
- The same strict path, regular-file, and alias checks for historical receipts as for current receipts.

Those private helpers and deployment settings are **not installed by cloning this public repository**. A separate credential-free private migration bundle and owner handoff preserve their current state, including their unresolved defects. Restoring them is not permission to activate them.

## Rebuild and acceptance order

1. Preserve the old system card and readable photo archive. Back up private configuration, helper source, keeper photos, review receipts, and agent state separately; never publish credentials or deployment data here.
2. Use known-good storage. A Linux-native writable data filesystem avoids the existing NTFS dependency, but no filesystem choice substitutes for real verification.
3. Rebuild isolated Python environments from reviewed source; do not copy a virtual environment to a different OS/Python version or blindly restore old mount UUIDs, personal paths, locks, or active-session files.
4. Reproduce and fix the startup/cache failure with deterministic tests. Keep scheduling paused during restoration.
5. During an approved daylight window, start a finite real camera capture, require fresh advancing health and newly saved JPEGs, decode the saved files, then stop and restart successfully. Preserve full error traces privately.
6. Test persistent storage configuration and safe refusal when storage is absent. Exercise a real reboot only with the owner's approval, and distinguish it from a remount test.
7. Only after real capture/restart acceptance, enable sunrise operation with a conservative before-sunset cutoff and visible failure reporting. Then restore sampled review, keeper archiving, and verified private digest delivery.
8. Fix and independently review the private report bridge/retention boundaries before enabling gallery automation. Individual-bird identification remains future work.

No requirement or field-validation status should be upgraded simply because this checkpoint, its tests, or its handoff exists.
