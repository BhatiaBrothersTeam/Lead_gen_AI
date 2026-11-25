import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Download, Inbox, Loader2, RefreshCw, Search, Target } from "lucide-react";
import { useCan } from "../../auth/permissions";
import { download, formatDate, mm } from "./api";
import { Empty, StatusBadge, inputCls, secondaryBtn } from "./ui";

export type LeadType = "inbound" | "outbound";

/** Inbound enquiries or outbound prospects, newest first. Refreshes itself while analyses run. */
export function LeadList({ type, onOpen, refreshKey }: { key?: string; type: LeadType; onOpen: (id: string) => void; refreshKey: number }) {
  const can = useCan();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ items: any[]; total: number; page_size: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const params = new URLSearchParams({ type, page: String(page), page_size: "20" });
      if (query) params.set("q", query);
      if (status) params.set("status", status);
      const res = await mm(`/leads?${params}`);
      setData(res);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [type, page, query, status]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  // While anything on this page is still being analysed, check again every few seconds.
  useEffect(() => {
    window.clearTimeout(timer.current);
    if (data?.items.some((l) => l.status === "pending" || l.status === "researching")) {
      timer.current = window.setTimeout(() => load(true), 4000);
    }
    return () => window.clearTimeout(timer.current);
  }, [data, load]);

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="bg-white rounded-2xl border border-[#EDEDF4] shadow-sm">
      <div className="flex flex-wrap items-center gap-2.5 px-5 py-3.5 border-b border-[#EDEDF4]">
        <form
          className="relative flex-1 min-w-[220px]"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(q.trim());
          }}
        >
          <Search className="w-4 h-4 text-[#A0A0B2] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            className={`${inputCls} pl-9`}
            placeholder={type === "inbound" ? "Search company, contact, product, LED-… or website reference" : "Search company, contact or LED-…"}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </form>
        <select className={`${inputCls.replace("w-full ", "")} w-auto`} value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }}>
          <option value="">All statuses</option>
          <option value="pending">Queued</option>
          <option value="researching">Analysing</option>
          <option value="analysed">Analysed</option>
          <option value="failed">Failed</option>
        </select>
        <button className={secondaryBtn} onClick={() => load()} title="Refresh">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
        {can("leads.export") && (
          <button
            className={secondaryBtn}
            onClick={() => download(`/export/leads.csv?type=${type}`, `matchmaker_${type}.csv`).catch((e) => toast.error(e.message))}
          >
            <Download className="w-4 h-4" /> CSV
          </button>
        )}
      </div>

      {error && <div className="px-5 py-4 text-[13px] text-red-600">{error}</div>}
      {!data && loading && (
        <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-[#6B2BFF]" /></div>
      )}
      {data && data.items.length === 0 && (
        <Empty icon={type === "inbound" ? <Inbox className="w-5 h-5" /> : <Target className="w-5 h-5" />} title={query || status ? "Nothing matches" : type === "inbound" ? "No enquiries yet" : "No prospects yet"}>
          {query || status
            ? "Try another search or status."
            : type === "inbound"
              ? "Website enquiries appear here automatically. You can also add one received by phone or email."
              : "Add a prospect or upload a list to find suitable products for each company."}
        </Empty>
      )}
      {data && data.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-left text-[11.5px] uppercase tracking-wide text-[#8A8AA3] border-b border-[#EDEDF4]">
                <th className="px-5 py-2.5 font-semibold">Company</th>
                <th className="px-3 py-2.5 font-semibold">{type === "inbound" ? "Asked for" : "Industry"}</th>
                <th className="px-3 py-2.5 font-semibold">Contact</th>
                <th className="px-3 py-2.5 font-semibold">Status</th>
                <th className="px-3 py-2.5 font-semibold">Matches</th>
                <th className="px-5 py-2.5 font-semibold">Received</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => (
                <tr key={l.id} onClick={() => onOpen(l.id)} className="border-b border-[#F3F3F8] last:border-0 hover:bg-[#FAFAFD] cursor-pointer">
                  <td className="px-5 py-3">
                    <div className="font-semibold text-[#111118]">{l.company_name}</div>
                    <div className="text-[11.5px] text-[#9A9AAD]">
                      {l.id}
                      {l.external_reference ? ` · ${l.external_reference}` : ""}
                      {l.company_country ? ` · ${l.company_country}` : ""}
                    </div>
                  </td>
                  <td className="px-3 py-3 text-[#3A3A4A] max-w-[240px] truncate">
                    {type === "inbound"
                      ? [l.interested_product || l.interested_division, l.quantity].filter(Boolean).join(" · ") || <span className="text-[#A0A0B2]">Not stated</span>
                      : l.company_industry || <span className="text-[#A0A0B2]">Unknown</span>}
                  </td>
                  <td className="px-3 py-3 text-[#3A3A4A]">
                    <div>{l.contact_person || "—"}</div>
                    <div className="text-[11.5px] text-[#9A9AAD]">{l.contact_email || l.contact_phone || ""}</div>
                  </td>
                  <td className="px-3 py-3">
                    <StatusBadge status={l.status} />
                    {l.status === "failed" && l.error_message && <div className="text-[11px] text-red-500 mt-1 max-w-[200px] truncate" title={l.error_message}>{l.error_message}</div>}
                  </td>
                  <td className="px-3 py-3 text-[#3A3A4A] whitespace-nowrap">
                    {l.status === "analysed" ? (
                      <>
                        {type === "inbound" && <span className="font-semibold">{l.primary_count} requested</span>}
                        {type === "inbound" && " · "}
                        {l.suggestion_count} {type === "inbound" ? "more" : "suggested"}
                      </>
                    ) : "—"}
                  </td>
                  <td className="px-5 py-3 text-[#7A7A8F] whitespace-nowrap">{formatDate(l.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between px-5 py-3 border-t border-[#EDEDF4] text-[12.5px] text-[#7A7A8F]">
          <span>{data.total} total</span>
          <div className="flex items-center gap-2">
            <button className={secondaryBtn} disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="w-4 h-4" /></button>
            <span>Page {page} of {pages}</span>
            <button className={secondaryBtn} disabled={page >= pages} onClick={() => setPage(page + 1)}><ChevronRight className="w-4 h-4" /></button>
          </div>
        </div>
      )}
    </div>
  );
}
