import * as React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  ArrowLeft, Building2, Copy, ExternalLink, Globe, Loader2, Mail, MessageCircle, PackageCheck, RefreshCw,
  Send, Sparkles, ThumbsDown, ThumbsUp, Wand2,
} from "lucide-react";
import { useCan } from "../../auth/permissions";
import { formatDate, mm } from "./api";
import { ConfidenceBadge, Empty, Panel, StatusBadge, Warning, inputCls, primaryBtn, secondaryBtn } from "./ui";

const FOLLOW_UP = [
  ["new", "New"], ["contacted", "Contacted"], ["in_discussion", "In discussion"], ["quoted", "Quoted"],
  ["won", "Won"], ["lost", "Lost"], ["not_relevant", "Not relevant"],
];

function Info({ label, value }: { label: string; value?: React.ReactNode }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] uppercase tracking-wide font-semibold text-[#9A9AAD]">{label}</span>
      <span className="text-[13px] text-[#1A1A24] whitespace-pre-wrap break-words">{value}</span>
    </div>
  );
}

// `key` is listed because this project has no @types/react (JSX props are checked as written).
function RecRow({ rec, selectable, selected, onToggle, onFeedback, canFeedback }: {
  key?: string; rec: any; selectable: boolean; selected: boolean; onToggle: () => void; onFeedback: (v: string) => void; canFeedback: boolean;
}) {
  return (
    <div className={`rounded-xl border p-3.5 flex gap-3 ${selected ? "border-[#6B2BFF] bg-[#FBFAFF]" : "border-[#EDEDF4]"}`}>
      {selectable && (
        <input type="checkbox" className="mt-1 accent-[#6B2BFF] w-4 h-4 shrink-0" checked={selected} onChange={onToggle} aria-label={`Include ${rec.product_name} in drafts`} />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-[13.5px] text-[#111118]">{rec.product_name}</span>
          <span className="text-[11.5px] text-[#9A9AAD]">{rec.division}</span>
          <ConfidenceBadge value={rec.confidence} />
          {rec.product_url && (
            <a href={rec.product_url} target="_blank" rel="noopener noreferrer" className="text-[#6B2BFF] hover:underline text-[11.5px] inline-flex items-center gap-0.5">
              View <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
        <p className="text-[12.5px] text-[#3A3A4A] mt-1">{rec.reason}</p>
        {rec.sales_verify && <p className="text-[11.5px] text-[#9A9AAD] mt-1">Check: {rec.sales_verify}</p>}
      </div>
      {canFeedback && (
        <div className="flex flex-col gap-1 shrink-0">
          <button
            title="Relevant"
            onClick={() => onFeedback(rec.feedback === "relevant" ? "" : "relevant")}
            className={`p-1.5 rounded-lg ${rec.feedback === "relevant" ? "bg-green-100 text-green-700" : "text-[#A0A0B2] hover:bg-slate-100"}`}
          ><ThumbsUp className="w-3.5 h-3.5" /></button>
          <button
            title="Not relevant"
            onClick={() => onFeedback(rec.feedback === "irrelevant" ? "" : "irrelevant")}
            className={`p-1.5 rounded-lg ${rec.feedback === "irrelevant" ? "bg-red-100 text-red-600" : "text-[#A0A0B2] hover:bg-slate-100"}`}
          ><ThumbsDown className="w-3.5 h-3.5" /></button>
        </div>
      )}
    </div>
  );
}

function copy(text: string) {
  navigator.clipboard.writeText(text).then(() => toast.success("Copied"), () => toast.error("Could not copy"));
}

/** Drafts for WhatsApp and email, editable before use. */
function Outreach({ detail, selected, onSent }: { detail: any; selected: string[]; onSent: () => void }) {
  const leadId = detail.lead.id;
  const [personalize, setPersonalize] = useState(false);
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState<any | null>(null);
  const [wa, setWa] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [recipient, setRecipient] = useState("");
  const [sending, setSending] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const res = await mm(`/leads/${leadId}/drafts`, { method: "POST", json: { recommendation_ids: selected, personalize } });
      setDrafts(res);
      setWa(res.whatsapp.message);
      setSubject(res.email.subject);
      setBody(res.email.body);
      setRecipient(res.email.recipient || "");
      if (res.ai_error) toast.warning(res.ai_error);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const openWhatsApp = () => {
    const url = `https://wa.me/${drafts.whatsapp.number}?text=${encodeURIComponent(wa)}`;
    window.open(url, "_blank", "noopener,noreferrer");
    mm(`/leads/${leadId}/whatsapp-opened`, { method: "POST", json: { number: drafts.whatsapp.number } }).then(onSent).catch(() => {});
  };

  const sendEmail = async () => {
    if (!window.confirm(`Send this email to ${recipient}?`)) return;
    setSending(true);
    try {
      const res = await mm(`/leads/${leadId}/send-email`, { method: "POST", json: { recipient, subject, body } });
      if (res.success) {
        toast.success(`Email sent to ${recipient}`);
        onSent();
      } else {
        toast.error(`Email failed: ${res.error}`);
      }
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setSending(false);
    }
  };

  const mailto = `mailto:${recipient}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;

  return (
    <Panel
      title="WhatsApp & email drafts"
      action={
        <div className="flex items-center gap-3">
          {detail.ai_configured && (
            <label className="flex items-center gap-1.5 text-[12.5px] text-[#5A5A6D] cursor-pointer">
              <input type="checkbox" className="accent-[#6B2BFF]" checked={personalize} onChange={(e) => setPersonalize(e.target.checked)} />
              <Wand2 className="w-3.5 h-3.5" /> Personalise with AI
            </label>
          )}
          <button className={primaryBtn} onClick={generate} disabled={loading || detail.lead.status !== "analysed"}>
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />} {drafts ? "Regenerate" : "Create drafts"}
          </button>
        </div>
      }
    >
      {!drafts ? (
        <p className="text-[13px] text-[#7A7A8F]">
          {detail.lead.status !== "analysed"
            ? "Drafts are available once the analysis has finished."
            : detail.lead.lead_type === "inbound"
              ? "Drafts thank the customer for their enquiry and confirm the requested products. Tick suggestions above to offer them in the same message."
              : "Drafts introduce your company and the products ticked above (or the best matches)."}
        </p>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center gap-2 text-[13px] font-bold text-[#111118]"><MessageCircle className="w-4 h-4 text-green-600" /> WhatsApp</div>
            {drafts.whatsapp.available ? (
              <span className="text-[12px] text-[#7A7A8F]">To +{drafts.whatsapp.number}{drafts.contact_name ? ` (${drafts.contact_name})` : ""}</span>
            ) : (
              <Warning>{drafts.whatsapp.reason}</Warning>
            )}
            {drafts.whatsapp.warning && <Warning>{drafts.whatsapp.warning}</Warning>}
            <textarea className={`${inputCls} min-h-[220px] font-normal`} value={wa} onChange={(e) => setWa(e.target.value)} />
            <div className="flex gap-2">
              <button className={primaryBtn} onClick={openWhatsApp} disabled={!drafts.whatsapp.available || !wa.trim()}>
                <MessageCircle className="w-4 h-4" /> Open in WhatsApp
              </button>
              <button className={secondaryBtn} onClick={() => copy(wa)}><Copy className="w-4 h-4" /> Copy</button>
            </div>
            <p className="text-[11.5px] text-[#9A9AAD]">Opening WhatsApp does not send anything: review and press Send there.</p>
          </div>
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center gap-2 text-[13px] font-bold text-[#111118]"><Mail className="w-4 h-4 text-[#6B2BFF]" /> Email</div>
            {!drafts.email.available && <Warning>{drafts.email.reason}</Warning>}
            <input className={inputCls} value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="Recipient email" />
            <input className={inputCls} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject" />
            <textarea className={`${inputCls} min-h-[220px] font-normal`} value={body} onChange={(e) => setBody(e.target.value)} />
            <div className="flex flex-wrap gap-2">
              {detail.smtp_configured && (
                <button className={primaryBtn} onClick={sendEmail} disabled={sending || !recipient.trim() || !subject.trim() || !body.trim()}>
                  {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Send email
                </button>
              )}
              <a className={`${secondaryBtn} ${recipient.trim() ? "" : "pointer-events-none opacity-50"}`} href={mailto}>
                <Mail className="w-4 h-4" /> Open in mail app
              </a>
              <button className={secondaryBtn} onClick={() => copy(`Subject: ${subject}\n\n${body}`)}><Copy className="w-4 h-4" /> Copy</button>
            </div>
            {!detail.smtp_configured && <p className="text-[11.5px] text-[#9A9AAD]">Sending from here needs SMTP settings on the server; use your mail app meanwhile.</p>}
          </div>
        </div>
      )}
      {drafts?.personalized && <p className="text-[11.5px] text-[#9A9AAD] mt-3">Personalised with AI from the enquiry and company analysis. Check every detail before sending.</p>}
    </Panel>
  );
}

export function LeadDetail({ leadId, onBack }: { leadId: string; onBack: () => void }) {
  const can = useCan();
  const [detail, setDetail] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      setDetail(await mm(`/leads/${encodeURIComponent(leadId)}`));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [leadId]);

  useEffect(() => {
    setDetail(null);
    setSelected([]);
    load();
  }, [load]);

  // Follow the analysis while it runs.
  useEffect(() => {
    window.clearTimeout(timer.current);
    if (detail && (["pending", "researching"].includes(detail.lead.status) || detail.queued)) {
      timer.current = window.setTimeout(load, 2500);
    }
    return () => window.clearTimeout(timer.current);
  }, [detail, load]);

  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <button className={`${secondaryBtn} self-start`} onClick={onBack}><ArrowLeft className="w-4 h-4" /> Back</button>
        <Panel><p className="text-[13px] text-red-600">{error}</p></Panel>
      </div>
    );
  }
  if (!detail) return <div className="py-24 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-[#6B2BFF]" /></div>;

  const { lead, company, research } = detail;
  const inbound = lead.lead_type === "inbound";
  const running = ["pending", "researching"].includes(lead.status);

  const reanalyse = async () => {
    try {
      const res = await mm(`/leads/${lead.id}/reanalyse`, { method: "POST" });
      toast.success(res.message);
      load();
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  const setFollowUp = async (value: string) => {
    try {
      await mm(`/leads/${lead.id}/follow-up`, { method: "PATCH", json: { follow_up_status: value } });
      setDetail({ ...detail, lead: { ...lead, follow_up_status: value } });
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  const feedback = async (recId: string, verdict: string) => {
    try {
      await mm(`/recommendations/${recId}/feedback`, { method: "POST", json: { verdict } });
      const patch = (list: any[]) => list.map((r) => (r.id === recId ? { ...r, feedback: verdict || null } : r));
      setDetail({ ...detail, requested: patch(detail.requested), suggestions: patch(detail.suggestions) });
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const contact = detail.contacts[0] || {};

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <button className={secondaryBtn} onClick={onBack} aria-label="Back"><ArrowLeft className="w-4 h-4" /></button>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[20px] font-bold text-[#111118]">{company.name}</h2>
              <StatusBadge status={lead.status} />
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#F5F3FF] text-[#6B2BFF]">{inbound ? "Inbound enquiry" : "Outbound prospect"}</span>
            </div>
            <p className="text-[12.5px] text-[#7A7A8F] mt-0.5">
              {lead.id}{lead.external_reference ? ` · Website ref ${lead.external_reference}` : ""} · {formatDate(lead.created_at)}
              {lead.source ? ` · ${lead.source}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {can("leads.save") && (
            <select className={`${inputCls.replace("w-full ", "")} w-auto`} value={lead.follow_up_status} onChange={(e) => setFollowUp(e.target.value)} aria-label="Follow-up status">
              {FOLLOW_UP.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          )}
          {can("leads.generate") && (
            <button className={secondaryBtn} onClick={reanalyse} disabled={running}>
              <RefreshCw className={`w-4 h-4 ${running ? "animate-spin" : ""}`} /> {lead.status === "failed" ? "Retry analysis" : "Re-analyse"}
            </button>
          )}
        </div>
      </div>

      {lead.status === "failed" && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
          <strong>The analysis failed.</strong> {lead.error_message} The enquiry itself is saved; use Retry analysis.
        </div>
      )}
      {running && (
        <div className="rounded-xl border border-[#E4DAFF] bg-[#FBFAFF] px-4 py-3 text-[13px] text-[#4B2AA8] flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Researching the company and matching the catalogue. This page updates by itself.
        </div>
      )}
      {lead.status === "analysed" && lead.error_message && <Warning>{lead.error_message}</Warning>}
      {detail.warnings.map((w: string) => <div key={w}><Warning>{w}</Warning></div>)}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Panel title={inbound ? "Enquiry" : "Prospect"} className="lg:col-span-1">
          <div className="flex flex-col gap-3">
            <Info label="Contact" value={[lead.contact_person || contact.contact_person, contact.designation].filter(Boolean).join(", ")} />
            <Info label="Email" value={lead.contact_email || contact.email} />
            <Info label="Phone" value={lead.contact_phone || contact.whatsapp || contact.phone} />
            {lead.submitted_company_name && lead.submitted_company_name !== company.name && <Info label="Company as submitted" value={lead.submitted_company_name} />}
            <Info label="Division" value={lead.interested_division} />
            <Info label="Product asked for" value={lead.interested_product} />
            <Info label="Quantity" value={lead.quantity} />
            <Info label="Application" value={lead.application} />
            <Info label="Requirement" value={lead.requirement_description} />
            <Info label="Notes" value={lead.additional_notes} />
            {(lead.utm_source || lead.landing_page) && <Info label="Campaign" value={[lead.utm_source, lead.utm_medium, lead.utm_campaign].filter(Boolean).join(" / ") || lead.landing_page} />}
          </div>
        </Panel>

        <Panel title={<span className="flex items-center gap-2"><Building2 className="w-4 h-4 text-[#6B2BFF]" /> Company analysis</span>} className="lg:col-span-2">
          {!research ? (
            <p className="text-[13px] text-[#7A7A8F]">{running ? "Analysis in progress…" : "No analysis yet."}</p>
          ) : (
            <div className="flex flex-col gap-3">
              <p className="text-[13.5px] text-[#1A1A24] leading-relaxed">{research.summary || company.description}</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Info label="Industry" value={company.industry || research.industry} />
                <Info label="Location" value={[company.city, company.country].filter(Boolean).join(", ")} />
                <Info label="Business activities" value={research.business_activities} />
                <Info label="Likely purchases" value={research.procurement_areas} />
                <Info label="Facilities / equipment" value={research.facilities} />
                <Info label="Products / services" value={[research.products_manufactured, research.services_offered].filter(Boolean).join("; ")} />
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-[#9A9AAD]">
                {company.website && (
                  <a href={company.website.startsWith("http") ? company.website : `https://${company.website}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[#6B2BFF] hover:underline">
                    <Globe className="w-3 h-3" /> {company.website}
                  </a>
                )}
                <span>{research.website_read ? "Website read" : "Website not read"} · {research.method === "ai" ? "AI summary" : "Rule-based summary"} · {formatDate(research.researched_at)}</span>
                {(research.sources || []).slice(1, 4).map((s: string) => (
                  <a key={s} href={s} target="_blank" rel="noopener noreferrer" className="hover:underline truncate max-w-[220px]">{s}</a>
                ))}
              </div>
            </div>
          )}
        </Panel>
      </div>

      {inbound && (
        <Panel title={<span className="flex items-center gap-2"><PackageCheck className="w-4 h-4 text-green-600" /> Requested products</span>}>
          <div className="flex flex-col gap-2.5">
            {detail.requested_items.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                <span className="text-[12px] text-[#7A7A8F] mr-1">The customer asked for:</span>
                {detail.requested_items.map((i: string) => <span key={i} className="px-2 py-0.5 rounded-lg bg-green-50 text-green-800 text-[12px] font-semibold">{i}</span>)}
              </div>
            )}
            {detail.requested.length === 0 ? (
              <p className="text-[13px] text-[#7A7A8F]">{running ? "Matching…" : "No catalogue line matched the request."}</p>
            ) : (
              detail.requested.map((r: any) => (
                <RecRow key={r.id} rec={r} selectable={false} selected={false} onToggle={() => {}} onFeedback={(v) => feedback(r.id, v)} canFeedback={can("leads.save")} />
              ))
            )}
          </div>
        </Panel>
      )}

      <Panel
        title={<span className="flex items-center gap-2"><Sparkles className="w-4 h-4 text-[#6B2BFF]" /> {inbound ? "Additional suggestions" : "Suggested products"}</span>}
        action={detail.suggestions.length > 0 && can("outreach.send_email") ? <span className="text-[12px] text-[#9A9AAD]">Tick to include in drafts</span> : undefined}
      >
        {detail.suggestions.length === 0 ? (
          <Empty icon={<Sparkles className="w-5 h-5" />} title={running ? "Matching…" : "No other suitable products found"}>
            {!running && "Add the company's website or more detail about what it does, then re-analyse."}
          </Empty>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-2.5">
            {detail.suggestions.map((r: any) => (
              <RecRow
                key={r.id}
                rec={r}
                selectable={can("outreach.send_email")}
                selected={selected.includes(r.id)}
                onToggle={() => toggle(r.id)}
                onFeedback={(v) => feedback(r.id, v)}
                canFeedback={can("leads.save")}
              />
            ))}
          </div>
        )}
      </Panel>

      {can("outreach.send_email") && <Outreach detail={detail} selected={selected} onSent={load} />}

      {detail.outreach.length > 0 && (
        <Panel title="Outreach history">
          <ul className="flex flex-col gap-1.5 text-[12.5px] text-[#3A3A4A]">
            {detail.outreach.map((o: any) => (
              <li key={o.id}>
                {formatDate(o.created_at)} · {o.channel === "email" ? `Email "${o.subject}" to ${o.recipient}` : `WhatsApp opened for +${o.recipient}`} ·{" "}
                <span className={o.status === "failed" ? "text-red-600" : "text-green-700"}>{o.status}</span>
                {o.error ? ` (${o.error})` : ""} · {o.created_by}
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
