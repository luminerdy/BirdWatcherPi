# Local bird-photo review: specification and build prompt

This document describes a site someone can build for their own data. **No review website is included in this public checkout.** A separate private review interface exists, but its source, configuration, data, and current operational status are not supplied or verified here. The requirements below are targets, not evidence of an implemented or tested site. See [BW-REVIEW-001–003](SPECIFICATION.md#local-image-review-site-specification) and the private behavior in [BW-LOCAL-002–005](SPECIFICATION.md#current-recovery-and-private-review-context).

## Intended behavior

- Configure the candidate dataset and separate persistent state location; never hard-code a personal path. Display grouped photos, and allow reversible **Good**, **No bird**, and **Bird** marks. Save changes durably.
- Allow groups to be marked **Finished** or reopened. Finishing assigns Bird to previously unmarked photos, leaving Good and No bird unchanged; reopening preserves marks. Open the first unfinished visible group by default, or the first visible group if all are finished. Empty datasets should be handled clearly.
- Preserve reliable capture date/time and its provenance when available; display unknown when absent, and do not turn modification time or an assumed timezone into a capture timestamp. Stable timestamps must not change on refresh or restart.
- Export Good photos as copies to a user-selected location outside the source tree; preserve names and available timestamps, do not overwrite files, and report errors or partial completion. Never modify or delete originals.
- Operate locally and bind to loopback by default. Validate paths, prevent traversal and unsafe symlinks, protect state-changing requests against CSRF and validate host headers. Explain that these measures do not substitute for authentication, HTTPS, or protection from untrusted local filesystem races; no network exposure without appropriate separately designed safeguards. Keep private photos, state, paths, and secrets out of the repository.

## Copyable prompt

Provide the referenced documents to your AI assistant along with this prompt:

```text
Build an independent local bird-photo review site from docs/LOCAL_REVIEW.md and
requirements BW-REVIEW-001–003 in docs/SPECIFICATION.md. Treat BW-LOCAL-002–005
as a description of a separate private interface, not bundled source or proof
of a running service. Ask me for genuinely missing requirements; do not invent
photos, labels, timestamps, paths, credentials, or test results.

Use configurable dataset, persistent state, and export paths; never embed
personal data or secrets. Display grouped images with reversible Good, No bird,
and Bird choices and persistent Finished/reopen state. Finishing assigns Bird
to unmarked images while preserving existing marks; reopening retains marks.
Resume at the first unfinished visible group, or first visible if all finished.
Handle empty inputs. Show stable capture timestamps only when supported by
reliable source metadata and provenance; otherwise show unknown. Never call a
file modification time capture time or guess a timezone.

Export Good originals as non-overwriting copies outside the dataset, preserving
names and available timestamps, and report errors and partial exports. Never
modify or delete originals. Default to loopback, validate Host and paths, reject
traversal and unsafe symlinks, protect writes from CSRF, and explain local-user,
filesystem-race, authentication, TLS, and network-exposure limits. No uploads,
external services, or exposure without explicit approval.

Implement and run automated tests with synthetic fixtures covering persistence,
restart/resume, group transitions, stable/unknown timestamps, non-destructive
exports and collisions, empty inputs, traversal, symlinks, Host and CSRF checks.
Document installation, configuration, security boundaries, test commands and
actual results. Do not access the existing private app or alter its configuration.
```
