import * as React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Boxes, Download, FileSpreadsheet, Inbox, LayoutGrid, Loader2, Plus, Search, Target, Upload } from "lucide-react";
import { useCan } from "../../auth/permissions";
import { download, formatDate, mm, upload } from "./api";
import { InboundForm, ProspectForm, UploadProspects } from "./Forms";
import { LeadDetail } from "./LeadDetail";
import { LeadList } from "./LeadList";
import { Empty, Panel, StatusBadge, Warning, inputCls, primaryBtn, secondaryBtn } from "./ui";

type View = "overview" | "inbound" | "outbound" | "catalogue";

/** Path of a lead's page, e.g. /leads/LED-3F9A0C1B2D4E (the website links here). */
export function leadIdFromPath(pathname: string): string | null {
  const m = pathname.match(/^\/(?:matchmaker\/)?leads\/(LED-[A-Z0-9]+)\/?$/i);
  return m ? m[1].toUpperCase() : null;
}

function Overview({ onOpen, go }: { onOpen: (id: string) => void; go: (v: View) => void }) {
  const [data, setData] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    mm("/summary").then(setData).catch((e) => setError(e.message));
  }, []);
  if (error) return <Panel><p className="text-[13px] text-red-600">{error}</p></Panel>;
  if (!data) return <div className="py-20 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-[#6B2BFF]" /></div>;
  const tiles = [
    { label: "Inbound enquiries", value: data.inbound, sub: `${data.inbound_7d} in the last 7 days`, view: "inbound" as View },
    { label: "Outbound prospects", value: data.outbound, sub: "researched and matched", view: "outbound" as View },
    { label: "Being analysed", value: data.in_progress, sub: data.failed ? `${data.failed} failed — open to retry` : "none failed", view: "inbound" as View },
    { label: "Catalogue lines", value: data.catalogue_products, sub: "active products", view: "catalogue" as View },
  ];
  return (
    <div className="flex flex-col gap-5">
      {!data.catalogue_products && <Warning>The product catalogue is empty, so nothing can be matched. Import it under Catalogue.</Warning>}
      {!data.website_enquiries_configured && (
        <Warning>Website enquiries are switched off on this server (MATCHMAKER_ENQUIRY_SECRET is not set). Enquiries typed in here still work.</Warning>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {tiles.map((t) => (
          <button key={t.label} onClick={() => go(t.view)} className="text-left bg-white rounded-2xl border border-[#EDEDF4] shadow-sm p-5 hover:border-[#D0B8FF] transition-colors">
            <div className="text-[12px] font-semibold text-[#7A7A8F]">{t.label}</div>
            <div className="text-[28px] font-bold text-[#111118] mt-1">{t.value}</div>
            <div className="text-[11.5px] text-[#9A9AAD]">{t.sub}</div>
          </button>
        ))}
      </div>
      <Panel title="Latest">
        {data.recent.length === 0 ? (
          <Empty icon={<Inbox className="w-5 h-5" />} title="Nothing yet">Website enquiries and prospects you add appear here.</Empty>
        ) : (
          <ul className="divide-y divide-[#F3F3F8]">
            {data.recent.map((l: any) => (
              <li key={l.id}>
                <button onClick={() => onOpen(l.id)} className="w-full flex flex-wrap items-center gap-3 py-2.5 text-left hover:bg-[#FAFAFD] rounded-lg px-2">
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${l.lead_type === "inbound" ? "bg-green-50 text-green-700" : "bg-blue-50 text-blue-700"}`}>{l.lead_type}</span>
                  <span className="font-semibold text-[13px] text-[#111118] flex-1 min-w-[160px]">{l.company_name}</span>
                  <span className="text-[12.5px] text-[#5A5A6D]">{l.interested_product || l.company_industry || ""}</span>
                  <StatusBadge status={l.status} />
                  <span className="text-[12px] text-[#9A9AAD]">{formatDate(l.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function Catalogue() {
  const can = useCan();
  const fileRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [data, setData] = useState<any | null>(null);
  const [importing, setImporting] = useState(false);
  const [lastImport, setLastImport] = useState<any | null>(null);

  const load = useCallback((query = "") => {
    mm(`/catalogue${query ? `?q=${encodeURIComponent(query)}` : ""}`).then(setData).catch((e) => toast.error(e.message));
  }, []);
  useEffect(() => load(), [load]);

  const importFile = async (file?: File) => {
    if (!file) return;
    setImporting(true);
    try {
      const res = await upload("/catalogue/import", file);
      setLastImport(res);
      toast.success(`Catalogue imported: ${res.products.inserted} new, ${res.products.updated} updated lines`);
      load(q);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <Panel
      title={`Product catalogue${data ? ` · ${data.items.length} lines in ${data.divisions} divisions` : ""}`}
      action={
        <div className="flex gap-2">
          <button className={secondaryBtn} onClick={() => download("/catalogue/template", "Product_Catalogue_Template.xlsx").catch((e) => toast.error(e.message))}>
            <Download className="w-4 h-4" /> Template
          </button>
          {can("outreach.manage_templates") && (
            <button className={primaryBtn} onClick={() => fileRef.current?.click()} disabled={importing}>
              {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />} Import workbook
            </button>
          )}
          <input ref={fileRef} type="file" accept=".xlsx,.xlsm" className="hidden" onChange={(e) => importFile(e.target.files?.[0])} />
        </div>
      }
    >
      <form className="relative mb-4" onSubmit={(e) => { e.preventDefault(); load(q.trim()); }}>
        <Search className="w-4 h-4 text-[#A0A0B2] absolute left-3 top-1/2 -translate-y-1/2" />
        <input className={`${inputCls} pl-9`} placeholder="Search lines, divisions, industries or uses" value={q} onChange={(e) => setQ(e.target.value)} />
      </form>
      {lastImport?.errors?.length > 0 && (
        <div className="mb-4"><Warning>{lastImport.errors.length} rows were skipped: {lastImport.errors.slice(0, 3).join("; ")}{lastImport.errors.length > 3 ? "…" : ""}</Warning></div>
      )}
      {!data ? (
        <div className="py-12 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-[#6B2BFF]" /></div>
      ) : data.items.length === 0 ? (
        <Empty icon={<Boxes className="w-5 h-5" />} title={q ? "Nothing matches" : "The catalogue is empty"}>
          {!q && "Download the template, fill in divisions and product lines (with buyer industries and uses), and import it."}
        </Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left text-[11.5px] uppercase tracking-wide text-[#8A8AA3] border-b border-[#EDEDF4]">
                <th className="py-2 pr-3">Division</th><th className="py-2 pr-3">Line</th><th className="py-2 pr-3">Buyer industries</th><th className="py-2">Uses</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p: any) => (
                <tr key={p.id} className="border-b border-[#F3F3F8] last:border-0 align-top">
                  <td className="py-2 pr-3 text-[#7A7A8F] whitespace-nowrap">{p.division}</td>
                  <td className="py-2 pr-3 font-semibold text-[#111118]">{p.name}</td>
                  <td className="py-2 pr-3 text-[#3A3A4A] max-w-[360px]">{p.target_industries}</td>
                  <td className="py-2 text-[#3A3A4A] max-w-[360px]">{p.applications}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/**
 * The Lead Matchmaker module inside Lead Gen: website/inbound enquiries,
 * outbound prospects, the product catalogue, and per-lead analysis with
 * WhatsApp/email drafts. Uses the Lead Gen sign-in and permissions.
 */
export function LeadMatchmaker({ initialLeadId }: { initialLeadId?: string | null }) {
  const can = useCan();
  const [view, setView] = useState<View>("overview");
  const [leadId, setLeadId] = useState<string | null>(initialLeadId || null);
  const [modal, setModal] = useState<"inbound" | "prospect" | "upload" | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [divisions, setDivisions] = useState<string[]>([]);

  // Keep the address bar in step, so a lead's page can be bookmarked or shared.
  useEffect(() => {
    const path = leadId ? `/leads/${leadId}` : "/";
    if (window.location.pathname !== path) window.history.pushState({ leadId }, "", path);
  }, [leadId]);
  useEffect(() => {
    const onPop = () => setLeadId(leadIdFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    mm("/catalogue").then((c) => setDivisions(Array.from(new Set<string>(c.items.map((p: any) => p.division))).sort())).catch(() => {});
  }, []);

  const open = (id: string) => {
    setModal(null);
    setLeadId(id);
  };

  const tabs: { key: View; label: string; icon: React.ReactNode }[] = [
    { key: "overview", label: "Overview", icon: <LayoutGrid className="w-4 h-4" /> },
    { key: "inbound", label: "Inbound enquiries", icon: <Inbox className="w-4 h-4" /> },
    { key: "outbound", label: "Outbound prospects", icon: <Target className="w-4 h-4" /> },
    { key: "catalogue", label: "Catalogue", icon: <Boxes className="w-4 h-4" /> },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-[22px] font-bold text-[#111118]">Lead Matchmaker</h2>
          <p className="text-[13px] text-[#7A7A8F]">Understand each buyer's business and match it to our catalogue, then reach out on WhatsApp or email.</p>
        </div>
        {!leadId && can("leads.generate") && (
          <div className="flex flex-wrap gap-2">
            {view !== "outbound" && <button className={secondaryBtn} onClick={() => setModal("inbound")}><Plus className="w-4 h-4" /> Inbound enquiry</button>}
            {view !== "inbound" && <button className={secondaryBtn} onClick={() => setModal("prospect")}><Plus className="w-4 h-4" /> Prospect</button>}
            {view !== "inbound" && <button className={primaryBtn} onClick={() => setModal("upload")}><FileSpreadsheet className="w-4 h-4" /> Upload prospects</button>}
          </div>
        )}
      </div>

      {!leadId && (
        <div className="flex flex-wrap gap-1.5 border-b border-[#E8E8F2]">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setView(t.key)}
              className={`flex items-center gap-2 px-3.5 py-2 text-[13px] font-semibold border-b-2 -mb-px transition-colors ${view === t.key ? "border-[#6B2BFF] text-[#111118]" : "border-transparent text-[#7A7A8F] hover:text-[#111118]"}`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
      )}

      {leadId ? (
        <LeadDetail leadId={leadId} onBack={() => { setLeadId(null); setRefreshKey((k) => k + 1); }} />
      ) : view === "overview" ? (
        <Overview onOpen={open} go={setView} />
      ) : view === "catalogue" ? (
        <Catalogue />
      ) : (
        <LeadList key={view} type={view} onOpen={open} refreshKey={refreshKey} />
      )}

      {modal === "inbound" && <InboundForm onClose={() => { setModal(null); setRefreshKey((k) => k + 1); }} onOpen={open} divisions={divisions} />}
      {modal === "prospect" && <ProspectForm onClose={() => { setModal(null); setRefreshKey((k) => k + 1); }} onOpen={open} />}
      {modal === "upload" && <UploadProspects onClose={() => setModal(null)} onDone={() => setRefreshKey((k) => k + 1)} />}
    </div>
  );
}
