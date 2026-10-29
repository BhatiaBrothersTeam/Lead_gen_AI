## Access control (Staff Portal)

Who may use this app, and what they may do in it, is managed in the Bhatia
Brothers Staff Portal (`/dashboard/users` and `/dashboard/applications`), not
here. Users arrive from the portal through a one-time sign-in link
(`/auth/sso`); there is no separate login. Every API route checks the
signed-in person's permission live with the portal
(`backend/api/routes/access.py`, cached for at most 60 seconds; bulk email and
page loads always ask fresh). If the portal can't be reached, access is
refused. The UI hides features the person's role doesn't include.

| Permission | Routes |
|---|---|
| `leads.generate` | generate leads, product lookups, upload product file |
| `leads.save` | save leads, filter existing leads |
| `leads.export` | Excel export (UI only) |
| `outreach.send_email` | send one email, list templates |
| `outreach.send_bulk` | bulk email |
| `outreach.manage_templates` | create and delete templates |
| `outreach.test_smtp` | SMTP connection test |

### Settings

Backend (e.g. Render environment variables; never in the frontend):

| Variable | Value |
|---|---|
| `STAFF_PORTAL_URL` | the portal's public URL; access checks and the activity log go here |
| `PORTAL_URL` | the same URL (allowed origin for the portal's "Sign out of all apps") |
| `ACTIVITY_LOG_API_KEY` | this app's key from the portal's `/dashboard/api-keys` |
| `JWT_SECRET` | equal to the portal's `JWT_SECRET` (verifies sign-in links) |
| `SESSION_SECRET` | this app's own random secret, 32+ characters, different from `JWT_SECRET` |
| `SESSION_COOKIE_SAMESITE` | `none` when the frontend and backend are on different sites (e.g. vercel.app and onrender.com); forces Secure |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | outgoing mail; email routes answer 503 without them |

Frontend build: `PORTAL_URL` (where signed-out users are sent) and
`VITE_API_URL` (the backend). Without the backend settings above, every API
route refuses access.

```powershell
.\venv\Scripts\python.exe -m unittest backend.test_lead_division backend.test_access_control backend.test_secret_exposure -v
npm run lint
```
