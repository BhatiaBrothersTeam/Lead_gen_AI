# Lead Division Tracking

Each generated lead stores the division from the generation request. Manual
generation uses the selected division, dropdown generation uses `ISD`, and file
generation uses `Auto Division`.

## Database Migration

Run this against the existing PostgreSQL database before deploying the updated
application, or restart the backend to let its schema initialization add it:

```sql
ALTER TABLE public.leads
ADD COLUMN IF NOT EXISTS division text NOT NULL DEFAULT 'Not Specified';
```

`Not Specified` is the recommended default: existing records have no recorded
division, and an omitted or blank division must not imply a real business unit.
The migration fills existing rows with this value; it cannot reconstruct their
original divisions. New generated leads use the request's division instead.

Duplicate matching is case-insensitive and scoped to division. The same company
can have separate lead records for different divisions; matching leads within
one division still receive missing-field updates. Generating a previously
unclassified company with a known division creates a separate record rather than
assigning an unverified division to its historical record.

Division is visible in lead tables, cards, details, and Excel outreach imports,
and is included in Excel exports and generated-lead search.

## Focused Checks

```powershell
.\venv\Scripts\python.exe -m unittest backend.test_lead_division -v
npm run lint
```

