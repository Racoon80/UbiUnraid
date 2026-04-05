# UbiUnraid Release Notes

## v1.2
- **Docker SDK 7.1.0:** Fixed `"Not supported URL scheme http+docker"` error with `requests>=2.32`.
- **Sorted view:** Unapproved containers now appear at the top.
- **Color-coded buttons:** Orange "Approve" for pending, green "Approved" for synced, gray "Info" for containers not in UniFi.
- **Action header:** Properly aligned above buttons.
- **All containers:** Shows all Docker containers, including those not yet in UniFi.

## v1.1
- UI: search + filter controls, larger headers, green status text.
- Compose: fixed container name (`container_name: UbiUnraid`).
- Auth: API key preferred; README updated with auth/security notes.
- Security: `requests` bumped to 2.32.4 (CVE-2024-35195, CVE-2024-47081); pip-audit clean.

## v1.0
- Initial release with MAC-aligned UI and UniFi update/approve flow.
