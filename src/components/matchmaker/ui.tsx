import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Loader2, XCircle, Clock } from "lucide-react";

/** Small building blocks styled like the rest of Lead Gen. */

export function Panel({ title, action, children, className = "" }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`bg-white rounded-2xl border border-[#EDEDF4] shadow-sm ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-[#EDEDF4]">
          <h3 className="text-[14px] font-bold text-[#111118]">{title}</h3>
          {action}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

const STATUS: Record<string, { label: string; cls: string; icon: ReactNode }> = {
  pending: { label: "Queued", cls: "bg-slate-100 text-slate-600", icon: <Clock className="w-3 h-3" /> },
  researching: { label: "Analysing", cls: "bg-[#F1ECFF] text-[#6B2BFF]", icon: <Loader2 className="w-3 h-3 animate-spin" /> },
  analysed: { label: "Analysed", cls: "bg-green-50 text-green-700", icon: <CheckCircle2 className="w-3 h-3" /> },
  failed: { label: "Failed", cls: "bg-red-50 text-red-600", icon: <XCircle className="w-3 h-3" /> },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] || { label: status, cls: "bg-slate-100 text-slate-600", icon: null };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11.5px] font-semibold ${s.cls}`}>
      {s.icon}
      {s.label}
    </span>
  );
}

export function ConfidenceBadge({ value }: { value: string }) {
  const cls = value === "High" ? "bg-green-50 text-green-700" : value === "Medium" ? "bg-amber-50 text-amber-700" : "bg-slate-100 text-slate-600";
  return <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${cls}`}>{value}</span>;
}

export function Warning({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-[12.5px] text-amber-900">
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
      <span>{children}</span>
    </div>
  );
}

export const inputCls =
  "w-full rounded-xl border border-[#E3E3EE] bg-white px-3 py-2 text-[13px] text-[#111118] placeholder:text-[#A0A0B2] focus:outline-none focus:ring-2 focus:ring-[#6B2BFF]/25 focus:border-[#6B2BFF]";

export const primaryBtn =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl bg-[#111118] px-4 py-2 text-[13px] font-semibold text-white shadow-sm hover:bg-[#2A2A35] disabled:opacity-50 disabled:cursor-not-allowed transition-colors";

export const secondaryBtn =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl border border-[#E3E3EE] bg-white px-3.5 py-2 text-[13px] font-semibold text-[#3A3A4A] hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";

export function Field({ label, required, hint, children }: { label: string; required?: boolean; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12px] font-semibold text-[#5A5A6D]">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </span>
      {children}
      {hint && <span className="text-[11.5px] text-[#9A9AAD]">{hint}</span>}
    </label>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="py-12 flex flex-col items-center text-center gap-2">
      <div className="w-11 h-11 rounded-xl bg-[#F5F3FF] text-[#6B2BFF] flex items-center justify-center">{icon}</div>
      <p className="text-[14px] font-bold text-[#111118]">{title}</p>
      {children && <div className="text-[12.5px] text-[#7A7A8F] max-w-md">{children}</div>}
    </div>
  );
}
