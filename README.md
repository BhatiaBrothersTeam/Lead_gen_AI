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
| `MATCHMAKER_ENQUIRY_SECRET` | shared key for website enquiries (Lead Matchmaker); same value as the website's `LEADMATCH_KEY` |

Frontend build: `PORTAL_URL` (where signed-out users are sent) and
`VITE_API_URL` (the backend). Without the backend settings above, every API
route refuses access.

```powershell
.\venv\Scripts\python.exe -m unittest backend.test_lead_division backend.test_access_control backend.test_secret_exposure backend.test_matchmaker_logic backend.test_matchmaker_flow -v
npm run lint
```

`backend.test_matchmaker_flow` runs against the PostgreSQL in `DATABASE_URL`
(in a throwaway `matchmaker_test` schema) and is skipped when it can't connect.

## Lead Matchmaker module

The **Lead Matchmaker** tab (ported from the standalone LeadMatch Maker) researches
a buyer's company and matches it against the product catalogue. It uses this
app's Staff Portal sign-in and permissions; there is no separate login.

* **Inbound**: website enquiries arrive server to server at `POST /api/public/enquiry`
  (same contract as LeadMatch, header `X-LeadMatch-Key` = `MATCHMAKER_ENQUIRY_SECRET`);
  sales can also type in phone/email enquiries. Each enquiry is saved and confirmed
  first (`201` with a `LED-…` id), then analysed in the background. Requested
  products are shown apart from additional suggestions.
* **Outbound**: add a prospect by hand or upload Excel/CSV (preview first: new,
  already a prospect, duplicate in file, invalid). Each company's website (or one
  found by search, flagged for checking) is read and summarised, then matched.
* **Outreach**: WhatsApp (`wa.me` link) and email drafts from the enquiry, the
  company analysis and the chosen products; optional AI personalisation; email
  sends through the SMTP settings above, or opens in the mail app.
* Duplicates: one lead per website reference (resends return the same lead), the
  same person asking the same thing within 24 hours, and one prospect per company
  (matched by website/email domain, then name + city/country, ignoring LLC/FZE…).
* Failures: an analysis that fails is marked `failed` with the reason and can be
  retried; unreachable websites, search or AI fall back to the details provided
  and are flagged on the lead. Interrupted analyses resume at startup.

Data lives in the `matchmaker` schema of the same database (created at startup).
Lead pages have their own address, `/leads/LED-…`, which the website's admin page
links to. Point the website at this app: `LEADMATCH_API_URL` and
`LEADMATCH_APP_URL` = this app's URL, `LEADMATCH_KEY` = `MATCHMAKER_ENQUIRY_SECRET`.

| Permission | Lead Matchmaker |
|---|---|
| `leads.generate` or `leads.save` | open the module, lists, analyses, catalogue |
| `leads.generate` | add enquiries/prospects, upload, re-analyse |
| `leads.save` | feedback on suggestions, follow-up status |
| `leads.export` | CSV export |
| `outreach.send_email` | WhatsApp/email drafts, send email |
| `outreach.manage_templates` | import the product catalogue |

Load the catalogue once, from a LeadMatch database or a catalogue workbook
(Catalogue tab → Template / Import; same format as LeadMatch's and
`sync_vvsons_catalogue.py --out`):

```powershell
.\venv\Scripts\python.exe -m backend.matchmaker.import_leadmatch --sqlite C:\Lead_Matchmaker\backend\leadmatch.db
```

Settings: see the Lead Matchmaker section of `.env.example`.
