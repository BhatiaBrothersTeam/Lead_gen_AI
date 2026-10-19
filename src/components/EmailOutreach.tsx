import * as React from "react";
import { useRef } from "react";
import { toast } from "sonner";
import { Mail, Upload, Send } from "lucide-react";
import * as XLSX from "xlsx";
import { Button } from "@/components/ui/button";

interface EmailOutreachProps {
  key?: React.Key;
  outreachLeads: any[];
  setOutreachLeads: React.Dispatch<React.SetStateAction<any[]>>;
  setActiveTab: React.Dispatch<React.SetStateAction<"generate" | "outreach">>;
  leads: any[];
  setLeads: React.Dispatch<React.SetStateAction<any[]>>;
  openComposeModal: (lead: any) => void;
  openBulkComposeModal: (targetLeads: any[]) => void;
  clearOutreachState?: () => void;
}

export function EmailOutreach({ outreachLeads, setOutreachLeads, setActiveTab, leads, setLeads, openComposeModal, openBulkComposeModal, clearOutreachState }: EmailOutreachProps) {
  const outreachFileRef = useRef<HTMLInputElement>(null);

  const handleOutreachUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const bstr = evt.target?.result;
        const wb = XLSX.read(bstr, { type: 'binary' });
        const wsname = wb.SheetNames[0];
        const ws = wb.Sheets[wsname];
        const data = XLSX.utils.sheet_to_json(ws);
        if (data.length > 0) {
          setOutreachLeads(data);
          toast.success(`Loaded ${data.length} verified leads for outreach!`);
          setActiveTab("outreach");
        } else {
          toast.error("No valid leads found in file");
        }
      } catch (error) {
        toast.error("Failed to read excel file.");
      }
    };
    reader.readAsBinaryString(file);
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center">
      {outreachLeads.length === 0 ? (
        <div className="bg-white rounded-2xl border border-[#EDEDF4] shadow-sm max-w-2xl w-full p-12 text-center">
          <div className="w-20 h-20 bg-gradient-to-br from-[#F5F3FF] to-[#EAE5FF] rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-inner border border-[#D0B8FF]/30">
            <Mail className="w-10 h-10 text-[#6B2BFF]" />
          </div>
          <h2 className="text-2xl font-bold text-[#111118] mb-3">Email Outreach Sandbox</h2>
          <p className="text-[15px] font-medium text-[#7A7A8F] mb-10 max-w-md mx-auto">
            Transform your verified Excel exports into actionable, one-click email inquiries connected directly to your mail client.
          </p>

          <div
            onClick={() => outreachFileRef.current?.click()}
            className="border-[2px] border-dashed border-[#D2D2E0] bg-[#FAFAFC] hover:bg-[#F9F7FF] hover:border-[#6B2BFF] rounded-xl p-10 cursor-pointer transition-all mx-auto max-w-lg group"
          >
            <input type="file" ref={outreachFileRef} className="hidden" accept=".xlsx, .xls" onChange={handleOutreachUpload} />
            <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center mx-auto mb-4 border border-[#E5E5EB] shadow-sm group-hover:scale-110 transition-transform">
              <Upload className="w-5 h-5 text-[#6B2BFF]" />
            </div>
            <p className="text-[15px] font-bold text-[#111118] mb-1">Click to browse your files</p>
            <p className="text-[13px] text-[#7A7A8F]">Upload the B2B_Leads.xlsx you exported</p>
          </div>
        </div>
      ) : (
        <div className="w-full h-full flex flex-col gap-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 shrink-0">
            <div>
              <h2 className="text-xl font-bold text-[#111118]">Outreach Queue ({outreachLeads.length})</h2>
              <p className="text-[13px] text-[#7A7A8F] font-medium">Outreach emails are sent securely using FastAPI SMTP.</p>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <Button
                onClick={() => {
                  const validLeads = outreachLeads.filter(l => l.email);
                  if (validLeads.length === 0) {
                    toast.error("No valid emails found for bulk outreach.");
                    return;
                  }
                  openBulkComposeModal(validLeads);
                }}
                className="h-9 px-4 text-[13px] font-semibold bg-[#6B2BFF] hover:bg-[#5A20E6] text-white"
              >
                <Send className="w-3.5 h-3.5 mr-2" /> Run Bulk Outreach
              </Button>
              <Button variant="outline" onClick={() => clearOutreachState ? clearOutreachState() : setOutreachLeads([])} className="h-9 px-4 text-[13px] font-semibold border-[#E5E5EB] text-[#111118]">Clear Session</Button>
            </div>
          </div>

          <div className="flex-1 overflow-auto custom-scroll">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5 pb-10">
              {outreachLeads.map((lead, idx) => {
                const initials = lead.name ? lead.name.split(' ').map((n: string) => n[0]).join('').substring(0, 2).toUpperCase() : '?';
                return (
                  <div key={idx} className="bg-white rounded-xl border border-[#EDEDF4] shadow-sm hover:shadow-md transition-all p-5 flex flex-col">
                    <div className="flex items-start gap-4 mb-5">
                      <div className="w-12 h-12 rounded-[10px] bg-gradient-to-br from-[#111118] to-[#2A2A35] flex items-center justify-center text-lg font-bold text-white shrink-0 shadow-sm">
                        {initials}
                      </div>
                      <div className="overflow-hidden">
                        <h3 className="font-bold text-[#111118] text-[15px] truncate">{lead.name || 'Unknown'}</h3>
                        <p className="text-[12px] text-[#7A7A8F] font-medium truncate">{lead.title}</p>
                        <p className="text-[12px] font-semibold text-[#111118] truncate mt-0.5">{lead.company}</p>
                        <p className="text-[12px] text-[#7A7A8F] font-medium break-words mt-0.5">Division: {lead.division || "Not Specified"}</p>
                      </div>
                    </div>

                    <div className="bg-[#FAFAFC] p-3 rounded-lg border border-[#E5E5EB] mb-5 flex items-center justify-between">
                      <p className="text-[13px] font-semibold text-[#6B2BFF] flex items-center gap-2 truncate">
                        <Mail className="w-3.5 h-3.5 text-[#A0A0B2]" /> {lead.email || 'No email'}
                      </p>
                      {lead.email_status && (
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1 ${
                          lead.email_status === 'sent' 
                            ? 'bg-green-50 text-green-600 border-green-100' 
                            : 'bg-red-50 text-red-600 border-red-100'
                        }`} title={lead.email_error}>
                          {lead.email_status === 'sent' ? 'Sent' : 'Failed'}
                        </span>
                      )}
                    </div>

                    <div className="mt-auto">
                      <button
                        disabled={!lead.email}
                        onClick={() => {
                          if (lead.email) {
                            openComposeModal(lead);
                          }
                        }}
                        className={`w-full flex items-center justify-center h-10 rounded-lg text-[13px] font-bold transition-all gap-2 ${lead.email ? 'bg-[#111118] hover:bg-[#6B2BFF] text-white shadow-sm' : 'bg-[#FAFAFC] text-[#A0A0B2] cursor-not-allowed border border-[#E5E5EB]'}`}
                      >
                        <Send className="w-3.5 h-3.5" /> COMPOSE EMAIL
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
