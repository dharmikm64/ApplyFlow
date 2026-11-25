# Manual verification with real Google sign-in and Gmail (T109, T110)

**Designated test account:** the developer's allowlisted Gmail (Google OAuth in Testing mode).
**Procedure:** quickstart.md → "Manual real-Gmail verification", steps 0–13.

## Status: PENDING. Needs the developer's Google Cloud OAuth client and Gmail account

These steps can't be automated. They require a real Google consent screen and a real mailbox.
Fill in `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `ALLOWED_GOOGLE_EMAILS` in `.env`, start the
dev servers, and tick each item.

- [ ] 0. Onboarding time (SC-001): ____ min (target < 5 min, excluding the scan)
- [ ] 1. Sign in requests only `openid email profile`
- [ ] 2. Connect shows ApplyFlow's explanation first; Google consent lists read-only Gmail only
- [ ] 3. Unticking the Gmail box → denied state with "Try again"
- [ ] 4. Scan completes; real recruiting emails produce sensible rows; job alerts don't
- [ ] 5. Detail view shows excerpts and the Date Applied explanation; no raw HTML
- [ ] 6. A correction persists across "Sync now"; last sync time updates
- [ ] 7. Removing access in Google Account → reconnect state, rows intact; reconnect works
- [ ] 8. Disconnect → table kept, scanning unavailable, no `gmail_connections` row
- [ ] 9. Logs contain no tokens or email bodies
- [ ] 10. Delete imported data → empty table, connection unchanged
- [ ] 11. Disconnect during a running scan → "Gmail disconnected", rows kept, no further Gmail requests
- [ ] 12. Delete account → signed out; fresh onboarding; no rows remain
- [ ] 13. Gmail itself unchanged (no read-state, labels, archive, or deletion changes)

## Performance (T110): synthetic results recorded 2026-11-25

Measured with `backend/scripts/perf_synthetic_scan.py`. It runs the real pipeline and database
against an in-memory Gmail with simulated latency.

| Measure | Result | Target |
|---|---|---|
| Scan of 3,000 messages, 50 ms per Gmail request, concurrency 8 | **26.4 s** (3,606 Gmail calls, 600 candidates, 120 applications) | SC-002: ≤ 10 min |
| Dashboard data load (`/api/me` + `/api/applications`, 120 rows) | **13 ms** | SC-007: ≤ 3 s |

Real-account timing: ____ (record during step 4 above). `GMAIL_CONCURRENCY` (default 8) did not
need tuning.
