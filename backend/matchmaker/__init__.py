"""
Lead Matchmaker module of the Lead Gen Agent.

Researches a buyer's company and matches it against the product catalogue:

* Inbound: enquiries from the website (POST /api/public/enquiry) or typed in by
  sales are saved first, then analysed in the background. Requested products
  are shown apart from additional suggestions.
* Outbound: prospects added by hand or uploaded from Excel/CSV are researched
  and matched to suitable catalogue lines.
* Outreach: WhatsApp and email drafts built from the enquiry, the company
  analysis and the chosen products, for sales to review and send.

It runs inside the Lead Gen backend and reuses its pieces: the PostgreSQL pool
(tables live in their own schema, see db.py), the Staff Portal sign-in and
permissions (routes.py), the activity log, the SMTP email service, the AI
provider settings (AI_PROVIDER / ANTHROPIC_API_KEY / GROQ_API_KEY) and Serper
search. Ported from the standalone LeadMatch Maker app.
"""
