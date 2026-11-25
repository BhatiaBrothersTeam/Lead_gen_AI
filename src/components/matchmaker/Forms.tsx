import * as React from "react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Download, FileSpreadsheet, Loader2, Upload, X } from "lucide-react";
import { download, mm, upload } from "./api";
import { Field, Warning, inputCls, primaryBtn, secondaryBtn } from "./ui";

function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 bg-[#111118]/50 backdrop-blur-sm z-50 flex items-start md:items-center justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div
        className={`bg-white rounded-2xl border border-[#EDEDF4] shadow-2xl w-full ${wide ? "max-w-5xl" : "max-w-2xl"} max-h-[92vh] flex flex-col`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#EDEDF4]">
          <h3 className="text-[16px] font-bold text-[#111118]">{title}</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-[#5A5A6D]" aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-6 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

type Saved = { lead_id: string; duplicate: boolean; message: string };

function Confirmation({ saved, onOpen, onAnother, anotherLabel }: { saved: Saved; onOpen: () => void; onAnother: () => void; anotherLabel: string }) {
  return (
    <div className="flex flex-col items-center text-center gap-3 py-4">
      <div className={`w-12 h-12 rounded-full flex items-center justify-center ${saved.duplicate ? "bg-amber-50 text-amber-600" : "bg-green-50 text-green-600"}`}>
        <CheckCircle2 className="w-6 h-6" />
      </div>
      <h4 className="text-[16px] font-bold text-[#111118]">{saved.duplicate ? "Already saved" : "Saved"}</h4>
      <p className="text-[13px] text-[#5A5A6D] max-w-sm">{saved.message}</p>
      <p className="text-[12px] text-[#9A9AAD]">Reference {saved.lead_id}</p>
      <div className="flex gap-2 mt-2">
        <button className={primaryBtn} onClick={onOpen}>Open {saved.duplicate ? "existing" : ""} record</button>
        <button className={secondaryBtn} onClick={onAnother}>{anotherLabel}</button>
      </div>
    </div>
  );
}

const EMPTY_ENQUIRY = {
  company_name: "", contact_person: "", business_email: "", phone_number: "", country: "", city: "",
  company_website: "", industry: "", interested_division: "", product_service: "", quantity: "",
  requirement_description: "", additional_notes: "",
};

/** An enquiry received by phone, email or at the counter, typed in by sales. */
export function InboundForm({ onClose, onOpen, divisions }: { onClose: () => void; onOpen: (id: string) => void; divisions: string[] }) {
  const [form, setForm] = useState({ ...EMPTY_ENQUIRY });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<Saved | null>(null);
  const set = (k: keyof typeof EMPTY_ENQUIRY) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.business_email.trim() && !form.phone_number.trim()) {
      toast.error("Add an email address or a phone number so sales can reply.");
      return;
    }
    setSaving(true);
    try {
      const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, (v as string).trim() || null]));
      const res = await mm<Saved>("/inbound", { method: "POST", json: { ...body, source: "manual", whatsapp_same_as_phone: Boolean(form.phone_number.trim()) } });
      setSaved(res);
      if (res.duplicate) toast.warning("This enquiry was already saved."); else toast.success("Enquiry saved.");
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Add an inbound enquiry" onClose={onClose}>
      {saved ? (
        <Confirmation saved={saved} onOpen={() => onOpen(saved.lead_id)} onAnother={() => { setSaved(null); setForm({ ...EMPTY_ENQUIRY }); }} anotherLabel="Add another" />
      ) : (
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Company"><input className={inputCls} value={form.company_name} onChange={set("company_name")} placeholder="Leave empty for an individual" /></Field>
          <Field label="Contact person"><input className={inputCls} value={form.contact_person} onChange={set("contact_person")} /></Field>
          <Field label="Email" hint="Email or phone is required"><input type="email" className={inputCls} value={form.business_email} onChange={set("business_email")} /></Field>
          <Field label="Phone / WhatsApp"><input className={inputCls} value={form.phone_number} onChange={set("phone_number")} placeholder="+971 50 123 4567" /></Field>
          <Field label="Country"><input className={inputCls} value={form.country} onChange={set("country")} placeholder="United Arab Emirates" /></Field>
          <Field label="City / Emirate"><input className={inputCls} value={form.city} onChange={set("city")} /></Field>
          <Field label="Website"><input className={inputCls} value={form.company_website} onChange={set("company_website")} placeholder="https://…" /></Field>
          <Field label="Industry"><input className={inputCls} value={form.industry} onChange={set("industry")} placeholder="e.g. Automotive workshop" /></Field>
          <Field label="Division">
            <select className={inputCls} value={form.interested_division} onChange={set("interested_division")}>
              <option value="">Not stated</option>
              {divisions.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </Field>
          <Field label="Product asked for"><input className={inputCls} value={form.product_service} onChange={set("product_service")} placeholder="e.g. AA Batteries" /></Field>
          <Field label="Quantity"><input className={inputCls} value={form.quantity} onChange={set("quantity")} /></Field>
          <div className="md:col-span-2"><Field label="Requirement"><textarea className={`${inputCls} min-h-[80px]`} value={form.requirement_description} onChange={set("requirement_description")} placeholder="What the customer asked for, in their words" /></Field></div>
          <div className="md:col-span-2 flex justify-end gap-2 pt-1">
            <button type="button" className={secondaryBtn} onClick={onClose}>Cancel</button>
            <button type="submit" className={primaryBtn} disabled={saving}>{saving && <Loader2 className="w-4 h-4 animate-spin" />} Save enquiry</button>
          </div>
        </form>
      )}
    </Modal>
  );
}

const EMPTY_PROSPECT = {
  company_name: "", country: "", city: "", website: "", industry: "", description: "",
  contact_person: "", designation: "", email: "", phone: "", notes: "",
};

/** One outbound prospect typed in by hand. */
export function ProspectForm({ onClose, onOpen }: { onClose: () => void; onOpen: (id: string) => void }) {
  const [form, setForm] = useState({ ...EMPTY_PROSPECT });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<Saved | null>(null);
  const set = (k: keyof typeof EMPTY_PROSPECT) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, (v as string).trim() || null]));
      const res = await mm<Saved>("/outbound", { method: "POST", json: body });
      setSaved(res);
      if (res.duplicate) toast.warning("This company is already a prospect."); else toast.success("Prospect saved.");
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Add a prospect" onClose={onClose}>
      {saved ? (
        <Confirmation saved={saved} onOpen={() => onOpen(saved.lead_id)} onAnother={() => { setSaved(null); setForm({ ...EMPTY_PROSPECT }); }} anotherLabel="Add another" />
      ) : (
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="md:col-span-2"><Field label="Company name" required><input required className={inputCls} value={form.company_name} onChange={set("company_name")} /></Field></div>
          <Field label="Website" hint="Best source for the analysis"><input className={inputCls} value={form.website} onChange={set("website")} placeholder="https://…" /></Field>
          <Field label="Industry"><input className={inputCls} value={form.industry} onChange={set("industry")} /></Field>
          <Field label="Country"><input className={inputCls} value={form.country} onChange={set("country")} placeholder="United Arab Emirates" /></Field>
          <Field label="City / Emirate"><input className={inputCls} value={form.city} onChange={set("city")} /></Field>
          <div className="md:col-span-2"><Field label="What the company does"><textarea className={`${inputCls} min-h-[70px]`} value={form.description} onChange={set("description")} placeholder="e.g. Fleet of 80 delivery vans with an in-house workshop" /></Field></div>
          <Field label="Contact person"><input className={inputCls} value={form.contact_person} onChange={set("contact_person")} /></Field>
          <Field label="Designation"><input className={inputCls} value={form.designation} onChange={set("designation")} /></Field>
          <Field label="Email"><input type="email" className={inputCls} value={form.email} onChange={set("email")} /></Field>
          <Field label="Phone / WhatsApp"><input className={inputCls} value={form.phone} onChange={set("phone")} /></Field>
          <div className="md:col-span-2 flex justify-end gap-2 pt-1">
            <button type="button" className={secondaryBtn} onClick={onClose}>Cancel</button>
            <button type="submit" className={primaryBtn} disabled={saving}>{saving && <Loader2 className="w-4 h-4 animate-spin" />} Save and analyse</button>
          </div>
        </form>
      )}
    </Modal>
  );
}

const ROW_STATUS: Record<string, string> = {
  new: "bg-green-50 text-green-700",
  existing: "bg-blue-50 text-blue-700",
  duplicate: "bg-amber-50 text-amber-700",
  invalid: "bg-red-50 text-red-600",
};

/** Upload a prospect list: preview (new / existing / duplicate / invalid), then confirm. */
export function UploadProspects({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<any | null>(null);
  const [result, setResult] = useState<any | null>(null);

  const pick = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    try {
      setPreview(await upload("/outbound/preview", file));
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const confirm = async () => {
    setBusy(true);
    try {
      const res = await mm(`/outbound/batches/${preview.batch_id}/confirm`, { method: "POST" });
      setResult(res);
      toast.success(res.message);
      onDone();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const importable = preview ? preview.new + preview.existing : 0;

  return (
    <Modal title="Upload prospects" onClose={onClose} wide>
      {result ? (
        <div className="flex flex-col items-center text-center gap-3 py-6">
          <CheckCircle2 className="w-10 h-10 text-green-600" />
          <p className="text-[15px] font-bold text-[#111118]">{result.message}</p>
          <p className="text-[13px] text-[#7A7A8F]">Each company is analysed in the background; results appear in the list as they finish.</p>
          <button className={primaryBtn} onClick={onClose}>Done</button>
        </div>
      ) : !preview ? (
        <div className="flex flex-col items-center text-center gap-4 py-6">
          <FileSpreadsheet className="w-10 h-10 text-[#6B2BFF]" />
          <p className="text-[13.5px] text-[#5A5A6D] max-w-md">
            Excel (.xlsx) or CSV, one company per row. Only <strong>Company_Name</strong> is required; Website, Industry, Country, email and phone make the
            analysis much better. Nothing is saved until you confirm the preview.
          </p>
          <div className="flex gap-2">
            <button className={secondaryBtn} onClick={() => download("/outbound/template", "Outbound_Prospects_Template.xlsx").catch((e) => toast.error(e.message))}>
              <Download className="w-4 h-4" /> Template
            </button>
            <button className={primaryBtn} onClick={() => fileRef.current?.click()} disabled={busy}>
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />} Choose file
            </button>
          </div>
          <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2 text-[12.5px]">
            <span className="px-2.5 py-1 rounded-full bg-green-50 text-green-700 font-semibold">{preview.new} new</span>
            <span className="px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 font-semibold">{preview.existing} already prospects (merged)</span>
            <span className="px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 font-semibold">{preview.duplicate} duplicates in file (skipped)</span>
            <span className="px-2.5 py-1 rounded-full bg-red-50 text-red-600 font-semibold">{preview.invalid} invalid (skipped)</span>
          </div>
          {preview.total > preview.rows.length && <Warning>Showing the first {preview.rows.length} of {preview.total} rows.</Warning>}
          <div className="overflow-x-auto border border-[#EDEDF4] rounded-xl max-h-[50vh]">
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0 bg-[#FAFAFD]">
                <tr className="text-left text-[#8A8AA3]">
                  <th className="px-3 py-2">Row</th><th className="px-3 py-2">Company</th><th className="px-3 py-2">Country</th>
                  <th className="px-3 py-2">Website / email</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Notes</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r: any) => (
                  <tr key={r.row} className="border-t border-[#F3F3F8]">
                    <td className="px-3 py-2 text-[#9A9AAD]">{r.row}</td>
                    <td className="px-3 py-2 font-semibold text-[#111118]">{r.company_name || "—"}</td>
                    <td className="px-3 py-2">{r.country || "—"}</td>
                    <td className="px-3 py-2">{r.website || r.email || "—"}</td>
                    <td className="px-3 py-2"><span className={`px-2 py-0.5 rounded-full font-semibold ${ROW_STATUS[r.status] || ""}`}>{r.status}</span></td>
                    <td className="px-3 py-2 text-[#7A7A8F]">{[r.reason, ...(r.warnings || [])].filter(Boolean).join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-end gap-2">
            <button className={secondaryBtn} onClick={() => setPreview(null)} disabled={busy}>Choose another file</button>
            <button className={primaryBtn} onClick={confirm} disabled={busy || importable === 0}>
              {busy && <Loader2 className="w-4 h-4 animate-spin" />} Import {importable} and analyse
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
