# Screenshots for GitHub

[Back to README](../README.md#screenshots)

## Files and placement

All screenshots belong in `docs/images/`. The README already contains commented
Markdown slots for `eclipse-today.png`, `eclipse-scan-summary.png`,
`eclipse-all-tools.png`, `eclipse-files.png`, and `eclipse-recovery.png`.
Add the PNG, then remove `<!--` and `-->` around the matching image line in README.
Commit both files together. GitHub resolves those paths relative to the README.

The existing `eclipse-control-center.png` is an older screen. Keep its historical
caption until you replace or remove it; do not label it as the current overview.

## Capture a real screen

1. Launch the version being documented with `eclipse ui`.
2. Use a readable terminal font, a consistent dark theme and roughly 100–120 columns.
3. Open the desired screen. For the summary, choose `1` and wait for the report.
4. On macOS press **Shift–Command–4**, then Space to capture the Terminal window.
5. Rename the resulting PNG and place it in `docs/images/`.
6. Inspect the full image before committing. Hide your username, hostname, IPs,
   SSH paths, private filenames and process arguments. A separate macOS demo
   account is useful; setting only Eclipse's data overrides does not hide system data.
7. Keep the output readable; aim for less than 1 MB per image when practical.
8. Preview the README on GitHub and check the caption matches the screenshot.

Use a sample folder for file operations. If you stage sample data, label it as a
demo in the caption. Do not invent a security score or show edited output as a
real scan result. A scan screenshot should show its limitations as well as alerts.

## Suggested captions

- TODAY: saved findings, changes and recent local activity.
- Scan summary: passed checks, findings to review and checks not completed.
- All tools: access to the full module catalog.
- Files: sample folder preview, with personal data removed.
- Recovery: snapshots of selected Eclipse data, not a full system backup.
