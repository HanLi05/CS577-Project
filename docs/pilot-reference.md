# Preserved pilot

- **Reference branch:** `reference/pilot`
- **Snapshot commit:** `68a982e` — three-tournament pilot, mappings, tests, reports, and statistics-only experiment.
- **Working branch:** `data-prep/matching`, currently the pilot plus a matching-review proposal. The lean extraction has not happened yet.
- **Local data backup:** `.local/pilot-2026-11-01/data-and-reports.tar.gz`
- **Backup file hashes:** `.local/pilot-2026-11-01/manifest.json`

The archive contains all 283 files present in `data/` and `reports/` when the pilot was preserved. Every archived file was checked against its SHA-256 hash. The original data folders remain in place. The archive, cached source pages, derived datasets, review samples, and Python environment are ignored by Git. The code snapshot passed all 40 tests before it was committed.

Nothing has been pushed or published. Git was initialized locally because this folder was not already a repository. The pilot mappings are preserved as AI-generated records, not promoted to human approvals.

To inspect pilot code without switching branches:

```bash
git show reference/pilot:src/golf_interviews/matching.py
```

To revisit the pilot checkout, first commit or otherwise save any current edits, then:

```bash
git switch reference/pilot
# Return to the matching work afterward:
git switch data-prep/matching
```

Ignored datasets do not switch with Git branches. If future work changes the local data, restore the archived files into a separate empty folder and inspect them there; do not extract over current work. A future clone will get the committed code/reports but not this local data backup.

The reference branch is a saved baseline. Make new work on the working branch; do not advance the reference branch.
