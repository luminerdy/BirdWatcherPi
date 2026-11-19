# Local bird-photo review (experimental)

The optional local server reviews already-saved files. It does not run the camera, analyze images, or change source photographs. Provide your own candidate directory and SQLite state path; do not commit either or publish personal paths or photographs. Use one state file per candidate tree.

Create a directory with one immediate subdirectory per group, e.g. `candidates/2026-01-01/120000.jpg`. Only JPEG and PNG files immediately within a group are shown; nested directories and symlinks are excluded. Names are sorted lexicographically. A group can represent a date, event, or other operator-defined batch; use date/time in group and image names if you want those carried into exports. The program does not extract or infer capture time from image metadata.

```sh
python -m birdwatcher.local_review_web --candidates ./candidates --state ./review.sqlite
```

Open `http://127.0.0.1:8000/`. The first unfinished group opens by default. Choose **good**, **no bird**, or **bird** for each image. Decisions persist immediately. Use the group links to navigate and mark a group finished or reopen it; marking finished does not require every image to be classified. Restarting resumes at the first unfinished group. If all are finished, the first group opens.

To copy files marked **good**, preserving their group and filename, run:

```sh
python -m birdwatcher.local_review_web --candidates ./candidates --state ./review.sqlite --export ./keepers
```

The destination must be outside the candidate tree. Existing destination files are never overwritten. Export can stop partway on an error: check the destination before retrying. Each copy preserves its source file's modification time, which is not necessarily capture time. No dates or times are invented, and originals are never intentionally modified or deleted. Back up the SQLite file and source images separately.

The default bind is loopback only. `--host` can opt into a specific IPv4 interface address (use that same address in the browser; wildcard `0.0.0.0` does not authorize other Host headers), but **there is no authentication or HTTPS**; anyone able to connect can see images and change decisions. Do not expose this server to the internet or an untrusted network. The app uses a per-process CSRF token and host validation, but they do not replace authentication, a firewall, or trusted local OS users. Keep candidate and export directories protected from concurrent modification by untrusted users; symlink checks are not a defense against local filesystem races. Stop the server before moving its candidate tree or state database. This is an experimental local tool, not the existing private review deployment.
