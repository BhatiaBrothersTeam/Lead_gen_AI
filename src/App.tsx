import { useState, useEffect } from "react";
import * as React from "react";
import { motion, AnimatePresence } from "motion/react";
import { type Lead } from "@/src/lib/groq";
import { toast, Toaster } from "sonner";
import {
  Loader2, Search, Mail, Command, Database, FolderDown, Sparkles, Settings,
  Send, X, AlertCircle, Trash2, ChevronDown, Building2, MapPin, Linkedin, Phone, Globe, Copy, Menu
} from "lucide-react";
import * as XLSX from "xlsx";
import { GenerateLeads } from "./components/GenerateLeads";
import { EmailOutreach } from "./components/EmailOutreach";
import { API_BASE_URL } from "./apiConfig";
export default function App() {
  const [savingDB, setSavingDB] = useState(false);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [outreachLeads, setOutreachLeads] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<"generate" | "outreach">("generate");
  const [selectedLeads, setSelectedLeads] = useState<Set<number>>(new Set());
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Gmail SMTP & Outreach State
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailModalMode, setEmailModalMode] = useState<"single" | "bulk">("single");
  const [emailTargetLeads, setEmailTargetLeads] = useState<Lead[]>([]);
  const [smtpChecking, setSmtpChecking] = useState(false);
  const [smtpStatus, setSmtpStatus] = useState<"idle" | "success" | "error">("idle");
  const [smtpError, setSmtpError] = useState("");

  const [emailSubject, setEmailSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [emailDelay, setEmailDelay] = useState(2.0);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [templates, setTemplates] = useState<any[]>([]);
  const [newTemplateName, setNewTemplateName] = useState("");
  const [saveAsTemplateMode, setSaveAsTemplateMode] = useState(false);

  // Bulk Sending state
  const [sendingProgress, setSendingProgress] = useState(false);
  const [progressMessage, setProgressMessage] = useState("");
  const [progressCurrent, setProgressCurrent] = useState(0);
  const [progressTotal, setProgressTotal] = useState(0);
  const [sendLogs, setSendLogs] = useState<{ email: string; status: "sent" | "failed"; error?: string }[]>([]);
  const [sendStats, setSendStats] = useState<{ total: number; sent: number; failed: number } | null>(null);

  const [outreachKey, setOutreachKey] = useState(0);

  const clearOutreachState = () => {
    setOutreachLeads([]);
    setEmailSubject("");
    setEmailBody("");
    setEmailTargetLeads([]);
    setSendingProgress(false);
    setProgressMessage("");
    setProgressCurrent(0);
    setProgressTotal(0);
    setSendLogs([]);
    setSendStats(null);
    setOutreachKey(prev => prev + 1);
  };

  const fetchTemplates = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/email-templates`);
      const data = await res.json();
      setTemplates(data.templates || []);
    } catch (e) {
      console.error("Failed to load templates:", e);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, []);

  // Lock body scroll when mobile sidebar drawer is open
  useEffect(() => {
    if (sidebarOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [sidebarOpen]);

  const handleTestSmtp = async () => {
    setSmtpChecking(true);
    setSmtpStatus("idle");
    setSmtpError("");
    try {
      const res = await fetch(`${API_BASE_URL}/api/test-smtp`, { method: "POST" });
      const data = await res.json();
      if (data.status === "success") {
        setSmtpStatus("success");
        toast.success("SMTP connection verified successfully!");
      } else {
        setSmtpStatus("error");
        setSmtpError(data.message || "Failed to verify SMTP connection");
        toast.error("SMTP verification failed.");
      }
    } catch (e: any) {
      setSmtpStatus("error");
      setSmtpError(e.message || "Network error");
      toast.error("SMTP verification failed.");
    } finally {
      setSmtpChecking(false);
    }
  };

  const handleSaveTemplate = async () => {
    if (!newTemplateName.trim()) {
      toast.error("Template name is required");
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/api/email-templates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_name: newTemplateName,
          subject: emailSubject,
          body: emailBody
        })
      });
      const data = await res.json();
      if (data.success) {
        toast.success("Template saved successfully!");
        setNewTemplateName("");
        setSaveAsTemplateMode(false);
        fetchTemplates();
        setSelectedTemplateId(data.template.id.toString());
      } else {
        toast.error("Failed to save template");
      }
    } catch (e) {
      toast.error("Error saving template");
    }
  };

  const handleDeleteTemplate = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this template?")) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/email-templates/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        toast.success("Template deleted!");
        fetchTemplates();
        if (selectedTemplateId === id.toString()) {
          setSelectedTemplateId("");
        }
      }
    } catch (e) {
      toast.error("Error deleting template");
    }
  };

  const handleTemplateChange = (templateId: string) => {
    setSelectedTemplateId(templateId);
    if (templateId) {
      const selected = templates.find(t => t.id.toString() === templateId);
      if (selected) {
        setEmailSubject(selected.subject);
        setEmailBody(selected.body);
      }
    }
  };

  const openComposeModal = (lead: Lead) => {
    if (!lead.email) {
      toast.error("This lead does not have a valid email address");
      return;
    }

    setEmailModalMode("single");
    setEmailTargetLeads([lead]);
    setEmailSubject("Partnership Inquiry - Product Supply");
    setEmailBody(`Hi {name},\n\nI noticed your work as {title} at {company} and wanted to reach out regarding potential product supply opportunities.\n\nBest regards,\nSales Team`);
    setSelectedTemplateId("");
    setNewTemplateName("");
    setSaveAsTemplateMode(false);

    setSendingProgress(false);
    setProgressMessage("");
    setSendLogs([]);
    setSendStats(null);
    setEmailModalOpen(true);
  };

  const openBulkComposeModal = (targetLeads: Lead[]) => {
    const validLeads = targetLeads.filter(l => l.email);
    if (validLeads.length === 0) {
      toast.error("None of the selected leads have a valid email address");
      return;
    }

    setEmailModalMode("bulk");
    setEmailTargetLeads(validLeads);
    setEmailSubject("Partnership Inquiry - Product Supply");
    setEmailBody(`Hi {name},\n\nI noticed your work as {title} at {company} and wanted to reach out regarding potential product supply opportunities.\n\nBest regards,\nSales Team`);
    setSelectedTemplateId("");
    setNewTemplateName("");
    setSaveAsTemplateMode(false);
    setEmailDelay(2.0);

    setSendingProgress(false);
    setProgressMessage("");
    setSendLogs([]);
    setSendStats(null);
    setEmailModalOpen(true);
  };

  const handleSendSingleEmail = async () => {
    const lead = emailTargetLeads[0];
    if (!lead) return;

    setSendingProgress(true);
    setProgressMessage("Sending email...");

    const formattedSubject = emailSubject
      .replace(/{name}/g, lead.name || "")
      .replace(/{company}/g, lead.company || "")
      .replace(/{title}/g, lead.title || "");
    const formattedBody = emailBody
      .replace(/{name}/g, lead.name || "")
      .replace(/{company}/g, lead.company || "")
      .replace(/{title}/g, lead.title || "");

    try {
      const res = await fetch(`${API_BASE_URL}/api/send-email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: lead.email,
          subject: formattedSubject,
          body: formattedBody
        })
      });
      const data = await res.json();
      if (data.success) {
        toast.success("Email sent successfully!");

        if (activeTab === "outreach") {
          setOutreachLeads(prev => prev.map(l => {
            if (l.email === lead.email) {
              return {
                ...l,
                email_sent: true,
                email_sent_date: new Date().toISOString(),
                email_status: "sent",
                email_error: ""
              };
            }
            return l;
          }));
        } else {
          setLeads(prev => prev.map(l => {
            if (l.srNo === lead.srNo) {
              return {
                ...l,
                email_sent: true,
                email_sent_date: new Date().toISOString(),
                email_status: "sent",
                email_error: ""
              };
            }
            return l;
          }));
        }

        setEmailModalOpen(false);
      } else {
        toast.error(data.error || "Failed to send email");

        if (activeTab === "outreach") {
          setOutreachLeads(prev => prev.map(l => {
            if (l.email === lead.email) {
              return {
                ...l,
                email_sent: false,
                email_sent_date: new Date().toISOString(),
                email_status: "failed",
                email_error: data.error || "SMTP failed"
              };
            }
            return l;
          }));
        } else {
          setLeads(prev => prev.map(l => {
            if (l.srNo === lead.srNo) {
              return {
                ...l,
                email_sent: false,
                email_sent_date: new Date().toISOString(),
                email_status: "failed",
                email_error: data.error || "SMTP failed"
              };
            }
            return l;
          }));
        }
      }
    } catch (e: any) {
      toast.error(e.message || "Network error");
    } finally {
      setSendingProgress(false);
    }
  };

  const handleSendBulkEmail = async () => {
    const isOutreach = activeTab === "outreach";
    let bodyPayload: any;

    if (isOutreach) {
      bodyPayload = {
        leads: emailTargetLeads,
        subject: emailSubject,
        body: emailBody,
        delay: emailDelay
      };
    } else {
      const leadIds = emailTargetLeads.map(l => l.id).filter(Boolean);
      if (leadIds.length === 0) {
        toast.error("Please click 'Save to database' to save leads before running bulk email campaign");
        return;
      }
      bodyPayload = {
        leadIds,
        subject: emailSubject,
        body: emailBody,
        delay: emailDelay
      };
    }

    setSendingProgress(true);
    setSendLogs([]);
    setSendStats(null);
    setProgressCurrent(0);
    setProgressTotal(emailTargetLeads.length);
    setProgressMessage("Initiating bulk emails...");

    try {
      const response = await fetch(`${API_BASE_URL}/api/send-bulk-email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyPayload)
      });

      if (!response.ok) {
        throw new Error(`Failed to start bulk send: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      if (!reader) {
        throw new Error("No response body stream");
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const rawJson = trimmed.slice(6).trim();
            if (rawJson) {
              try {
                const event = JSON.parse(rawJson);

                if (event.status === "error") {
                  toast.error(event.message);
                  setProgressMessage(event.message);
                  setSendingProgress(false);
                  return;
                }

                if (event.status === "start") {
                  setProgressMessage(event.message);
                  setProgressTotal(event.total);
                } else if (event.status === "progress") {
                  setProgressMessage(event.message);
                  setProgressCurrent(event.current);
                } else if (event.status === "status_update") {
                  setSendLogs(prev => [
                    ...prev,
                    {
                      email: event.email,
                      status: event.success ? "sent" : "failed",
                      error: event.error
                    }
                  ]);

                  if (isOutreach) {
                    setOutreachLeads(prev => prev.map(l => {
                      if (l.email === event.email) {
                        return {
                          ...l,
                          email_sent: event.success,
                          email_sent_date: new Date().toISOString(),
                          email_status: event.success ? "sent" : "failed",
                          email_error: event.error || ""
                        };
                      }
                      return l;
                    }));
                  } else {
                    setLeads(prev => prev.map(l => {
                      if (l.id === event.lead_id) {
                        return {
                          ...l,
                          email_sent: event.success,
                          email_sent_date: new Date().toISOString(),
                          email_status: event.success ? "sent" : "failed",
                          email_error: event.error || ""
                        };
                      }
                      return l;
                    }));
                  }
                } else if (event.status === "completed") {
                  setProgressMessage(event.message);
                  setSendStats({
                    total: event.total,
                    sent: event.sent,
                    failed: event.failed
                  });
                  setSendingProgress(false);
                  toast.success("Bulk sending complete!");
                }
              } catch (parseErr) {
                console.error("Failed to parse SSE line:", rawJson, parseErr);
              }
            }
          }
        }
      }
    } catch (e: any) {
      toast.error(e.message || "Failed during bulk sending");
      setSendingProgress(false);
    }
  };


  const previewLead = emailTargetLeads[0];
  const previewSubject = previewLead
    ? emailSubject
      .replace(/{name}/g, previewLead.name || "")
      .replace(/{company}/g, previewLead.company || "")
      .replace(/{title}/g, previewLead.title || "")
    : "";
  const previewBody = previewLead
    ? emailBody
      .replace(/{name}/g, previewLead.name || "")
      .replace(/{company}/g, previewLead.company || "")
      .replace(/{title}/g, previewLead.title || "")
    : "";

  const exportToExcel = () => {
    if (leads.length === 0) return;

    const cleanedLeads = leads.map(lead => ({
      srNo: lead.srNo,
      name: lead.name || "",
      title: lead.title || "",
      company: lead.company || "",
      email: lead.email || "",
      phone: lead.phone || "",
      location: lead.location || "",
      website: lead.website || "",
      linkedIn: lead.linkedIn || lead.linkedin || "",
      segment: lead.segment || "",
      priority: lead.priority || "",
      channel: lead.channel || ""
    }));

    const worksheet = XLSX.utils.json_to_sheet(cleanedLeads, {
      header: ["srNo", "name", "title", "company", "email", "phone", "location", "website", "linkedIn", "segment", "priority", "channel"]
    });
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Leads");
    XLSX.writeFile(workbook, "B2B_Leads.xlsx");
    toast.success("Leads exported to Excel!");
  };

  const saveToDatabase = async () => {
    if (leads.length === 0) return;
    setSavingDB(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/save-leads`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ leads }),
      });

      if (!response.ok) throw new Error("Database save failed");
      const data = await response.json();
      if (data.leads) {
        setLeads(data.leads.map((l: any, idx: number) => ({ ...l, srNo: idx + 1 })));
      }
      toast.success(`Saved ${data.count} leads to Database!`);
    } catch (error) {
      toast.error("Failed to save leads to Database.");
      console.error(error);
    } finally {
      setSavingDB(false);
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        document.getElementById('search-input')?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="min-h-screen text-[#1A1A24] font-medium font-sans selection:bg-[#6B2BFF]/20 flex flex-col items-stretch overflow-hidden bg-[#FAFAFD] relative">
      <Toaster position="top-right" />

      {/* Abstract blurred background blobs (optimized static layers for smooth 60fps scroll) */}
      <div
        className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-[#6B2BFF]/10 rounded-full blur-[100px] pointer-events-none will-change-[transform,filter]"
      />
      <div
        className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-[#A880FF]/10 rounded-full blur-[100px] pointer-events-none will-change-[transform,filter]"
      />

      {/* 1. TOP NAVBAR */}
      <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-md border-b border-[#E8E8F2] w-full px-6 py-3 flex items-center justify-between shrink-0 will-change-transform">
        <div className="flex items-center gap-3">
          {/* Mobile Sidebar Hamburger Menu Button */}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 -ml-1 rounded-lg hover:bg-slate-100 text-[#5A5A6D] md:hidden transition-colors"
            aria-label="Toggle navigation menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#6B2BFF] to-[#8C5DFF] flex items-center justify-center shadow-sm">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-[15px] font-bold text-[#111118] leading-tight">LeadGen AI</h1>
          </div>
        </div>

        {/* <div className="flex items-center gap-4 justify-end">
          <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-[#6B2BFF] to-[#D0B8FF] flex items-center justify-center text-[10px] font-bold text-white border-2 border-white shadow-sm">
            BB
          </div>
        </div> */}
      </header>

      {/* Body with Sidebar and Main */}
      <div className="flex-1 flex overflow-hidden z-10 relative mt-0.5">
        {/* Sidebar mobile overlay backdrop */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-[#111118]/40 backdrop-blur-sm z-40 md:hidden animate-in fade-in duration-200"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* SIDEBAR */}
        <aside
          className={`fixed inset-y-0 left-0 z-50 w-[260px] bg-white md:bg-white/80 md:backdrop-blur-md border-r border-[#E8E8F2]/60 p-5 flex flex-col gap-2 shrink-0 shadow-2xl md:shadow-[4px_0_24px_rgba(0,0,0,0.02)] md:static md:translate-x-0 transition-transform duration-300 ease-in-out will-change-transform ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}
        >
          <div className="flex items-center justify-between mb-4 px-2">
            <span className="text-[11px] font-bold text-[#8A8AA3] uppercase tracking-widest">Navigation</span>
            <button
              onClick={() => setSidebarOpen(false)}
              className="p-1 rounded-md hover:bg-slate-100 text-[#5A5A6D] md:hidden transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => {
              setSidebarOpen(false);
              if (activeTab === "outreach" && outreachLeads.length > 0) {
                setShowLeaveConfirm(true);
              } else {
                clearOutreachState();
                setActiveTab("generate");
              }
            }}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-[13px] font-semibold transition-all duration-300 relative overflow-hidden ${activeTab === "generate" ? "bg-[#111118] text-white shadow-md shadow-[#111118]/20" : "text-[#5A5A6D] hover:bg-white hover:shadow-sm"}`}
          >
            {activeTab === "generate" && <motion.div layoutId="sidebar-active" className="absolute inset-0 bg-[#111118] -z-10" />}
            <Search className="w-4 h-4" /> Generate Leads
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => {
              setSidebarOpen(false);
              setActiveTab("outreach");
            }}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-[13px] font-semibold transition-all duration-300 relative overflow-hidden ${activeTab === "outreach" ? "bg-[#111118] text-white shadow-md shadow-[#111118]/20" : "text-[#5A5A6D] hover:bg-white hover:shadow-sm"}`}
          >
            {activeTab === "outreach" && <motion.div layoutId="sidebar-active" className="absolute inset-0 bg-[#111118] -z-10" />}
            <Mail className="w-4 h-4" /> Email Outreach
          </motion.button>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 overflow-auto flex flex-col custom-scroll">
          <div className="max-w-[1600px] w-full mx-auto px-8 py-8 flex flex-col h-full gap-8">
            <AnimatePresence mode="wait">
              {activeTab === "generate" && (
                <motion.div
                  key="generate"
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  transition={{ duration: 0.3, ease: "easeOut" }}
                  className="flex flex-col h-full gap-6"
                >
                  <GenerateLeads
                    leads={leads}
                    setLeads={setLeads}
                    selectedLeads={selectedLeads}
                    setSelectedLeads={setSelectedLeads}
                    saveToDatabase={saveToDatabase}
                    exportToExcel={exportToExcel}
                    savingDB={savingDB}
                    openComposeModal={openComposeModal}
                    openBulkComposeModal={openBulkComposeModal}
                  />
                </motion.div>
              )}

              {activeTab === "outreach" && (
                <motion.div
                  key="outreach"
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  transition={{ duration: 0.3, ease: "easeOut" }}
                  className="flex flex-col h-full"
                >
                  <EmailOutreach
                    key={outreachKey}
                    leads={leads}
                    outreachLeads={outreachLeads}
                    setOutreachLeads={setOutreachLeads}
                    setActiveTab={setActiveTab}
                    setLeads={setLeads}
                    openComposeModal={openComposeModal}
                    openBulkComposeModal={openBulkComposeModal}
                    clearOutreachState={clearOutreachState}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </main>
      </div>

      {/* Gmail SMTP Compose & Templates Modal */}
      <AnimatePresence>
        {emailModalOpen && (
          <div className="fixed inset-0 bg-[#111118]/60 backdrop-blur-md z-50 flex items-center justify-center p-4 overflow-y-auto">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="bg-white border border-[#EDEDF4] shadow-2xl rounded-2xl w-full max-w-5xl overflow-hidden flex flex-col max-h-[90vh]"
            >
              {/* Header */}
              <div className="px-6 py-4 border-b border-[#EBEBF2] bg-[#FAFAFD] flex items-center justify-between">
                <div>
                  <h3 className="text-[16px] font-bold text-[#111118]">
                    {emailModalMode === "single" ? "Compose Email" : `Bulk Email Outreach (${emailTargetLeads.length} Leads)`}
                  </h3>
                  <p className="text-[12px] text-[#7A7A8F] font-medium mt-0.5">
                    {emailModalMode === "single"
                      ? `Sending to: ${emailTargetLeads[0]?.name || "Recipient"} (${emailTargetLeads[0]?.email})`
                      : "Controlled single-by-single sending with configurable delay to prevent rate limits"}
                  </p>
                </div>
                <button
                  disabled={sendingProgress}
                  onClick={() => setEmailModalOpen(false)}
                  className="w-8 h-8 rounded-lg flex items-center justify-center border border-[#EDEDF4] hover:bg-[#FAFAFD] text-[#A0A0B2] hover:text-[#111118] transition-all disabled:opacity-50"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto custom-scroll p-6">
                {sendingProgress || sendStats ? (
                  /* Sending Campaign Progress View */
                  <div className="flex flex-col items-center justify-center max-w-xl mx-auto py-10 gap-6">
                    <div className="text-center w-full">
                      <h4 className="text-lg font-bold text-[#111118] mb-1">
                        {sendingProgress ? "Outreach Campaign in Progress" : "Campaign Complete"}
                      </h4>
                      <p className="text-[13px] text-[#7A7A8F]">{progressMessage}</p>
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full bg-[#FAFAFD] border border-[#EDEDF4] h-3.5 rounded-full overflow-hidden relative shadow-inner">
                      <motion.div
                        className="bg-gradient-to-r from-[#6B2BFF] to-[#8C5DFF] h-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${(progressCurrent / progressTotal) * 100}%` }}
                        transition={{ duration: 0.3 }}
                      />
                    </div>

                    <div className="flex justify-between w-full text-[13px] font-bold text-[#111118]">
                      <span>{progressCurrent} sent</span>
                      <span>of {progressTotal} leads</span>
                    </div>

                    {/* Live Send Logs */}
                    <div className="w-full border border-[#EDEDF4] rounded-xl bg-[#FAFAFD] p-4 h-48 overflow-y-auto custom-scroll text-[12px] font-mono space-y-1.5 shadow-inner">
                      {sendLogs.length === 0 && (
                        <p className="text-[#A0A0B2] text-center mt-16 font-sans">Awaiting first dispatch...</p>
                      )}
                      {sendLogs.map((log, index) => (
                        <div key={index} className="flex items-start gap-2">
                          <span className={`font-bold shrink-0 ${log.status === "sent" ? "text-green-600" : "text-red-600"}`}>
                            [{log.status.toUpperCase()}]
                          </span>
                          <span className="text-[#5A5A6D] flex-1 truncate">{log.email}</span>
                          {log.error && <span className="text-red-500 text-[10px] truncate max-w-[200px]" title={log.error}>({log.error})</span>}
                        </div>
                      ))}
                    </div>

                    {/* Campaign Statistics Summary */}
                    {sendStats && (
                      <div className="w-full grid grid-cols-3 gap-4 bg-[#FAFAFD] border border-[#EDEDF4] rounded-xl p-4 shadow-sm animate-in fade-in slide-in-from-bottom-2 duration-300">
                        <div className="text-center border-r border-[#EDEDF4]">
                          <p className="text-[10px] font-bold text-[#8A8AA3] uppercase tracking-wider">Processed</p>
                          <p className="text-lg font-extrabold text-[#111118] mt-0.5">{sendStats.total}</p>
                        </div>
                        <div className="text-center border-r border-[#EDEDF4]">
                          <p className="text-[10px] font-bold text-green-600 uppercase tracking-wider">Sent</p>
                          <p className="text-lg font-extrabold text-green-700 mt-0.5">{sendStats.sent}</p>
                        </div>
                        <div className="text-center">
                          <p className="text-[10px] font-bold text-red-600 uppercase tracking-wider">Failed</p>
                          <p className="text-lg font-extrabold text-red-700 mt-0.5">{sendStats.failed}</p>
                        </div>
                      </div>
                    )}

                    {!sendingProgress && sendStats && (
                      <button
                        onClick={() => setEmailModalOpen(false)}
                        className="mt-4 px-8 py-2.5 bg-[#111118] text-white hover:bg-[#22222A] rounded-xl text-[13px] font-bold shadow-md shadow-[#111118]/10 transition-all active:scale-95"
                      >
                        Done
                      </button>
                    )}
                  </div>
                ) : (
                  /* Form Composition View */
                  <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                    {/* Left Pane - Composition Fields */}
                    <div className="lg:col-span-3 flex flex-col gap-4">
                      {/* Template Selector */}
                      <div className="flex flex-col gap-1.5">
                        <span className="text-[12px] font-bold text-[#5A5A6D]">Template Profile</span>
                        <div className="flex gap-2">
                          <div className="relative flex-1">
                            <select
                              value={selectedTemplateId}
                              onChange={(e) => handleTemplateChange(e.target.value)}
                              className="w-full h-10 text-[13px] bg-white border border-[#E5E5EB] rounded-lg focus:border-[#6B2BFF] focus:ring-1 focus:ring-[#6B2BFF] px-3 outline-none appearance-none cursor-pointer pr-10 font-medium"
                            >
                              <option value="">-- Start from scratch / Compose custom --</option>
                              {templates.map((t) => (
                                <option key={t.id} value={t.id.toString()}>
                                  {t.template_name}
                                </option>
                              ))}
                            </select>
                            <ChevronDown className="w-4 h-4 text-[#A0A0B2] absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                          </div>
                          {selectedTemplateId && (
                            <button
                              onClick={(e) => handleDeleteTemplate(parseInt(selectedTemplateId), e)}
                              className="h-10 px-3 bg-white border border-red-100 text-red-500 hover:bg-red-50 rounded-lg flex items-center justify-center transition-colors"
                              title="Delete template"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Subject */}
                      <div className="flex flex-col gap-1.5">
                        <span className="text-[12px] font-bold text-[#5A5A6D]">Subject</span>
                        <input
                          value={emailSubject}
                          onChange={(e) => setEmailSubject(e.target.value)}
                          placeholder="e.g. Partnership Inquiry - Product Supply"
                          className="h-10 text-[13px] bg-white border border-[#E5E5EB] px-3 rounded-lg focus:border-[#6B2BFF] focus:ring-1 focus:ring-[#6B2BFF] outline-none font-semibold text-[#111118]"
                        />
                      </div>

                      {/* Body */}
                      <div className="flex flex-col gap-1.5">
                        <span className="text-[12px] font-bold text-[#5A5A6D]">Email Message Body</span>
                        <textarea
                          value={emailBody}
                          onChange={(e) => setEmailBody(e.target.value)}
                          rows={8}
                          placeholder="Compose your outreach text..."
                          className="w-full text-[13px] bg-white border border-[#E5E5EB] rounded-lg focus:border-[#6B2BFF] focus:ring-1 focus:ring-[#6B2BFF] p-3 outline-none resize-none font-medium text-[#111118]"
                        />
                      </div>

                      {/* Save Template Helper */}
                      <div className="border border-[#EDEDF4] bg-[#FAFAFD] rounded-xl p-4 flex flex-col gap-3">
                        <div className="flex items-center justify-between">
                          <span className="text-[12px] font-bold text-[#111118]">Save outreach text as template?</span>
                          <button
                            type="button"
                            onClick={() => setSaveAsTemplateMode(!saveAsTemplateMode)}
                            className="text-[12px] font-bold text-[#6B2BFF] hover:underline"
                          >
                            {saveAsTemplateMode ? "Cancel" : "Yes, Save"}
                          </button>
                        </div>
                        {saveAsTemplateMode && (
                          <div className="flex gap-2 animate-in fade-in duration-200">
                            <input
                              value={newTemplateName}
                              onChange={(e) => setNewTemplateName(e.target.value)}
                              placeholder="Template name, e.g. GCC Supply Pitch"
                              className="h-9 flex-1 text-[12px] bg-white border border-[#E5E5EB] px-3 rounded-lg focus:border-[#6B2BFF] focus:ring-1 focus:ring-[#6B2BFF] outline-none"
                            />
                            <button
                              onClick={handleSaveTemplate}
                              className="h-9 px-4 text-[12px] bg-[#111118] text-white hover:bg-[#22222A] font-bold rounded-lg transition-all"
                            >
                              Save template
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Right Pane - Config & Preview */}
                    <div className="lg:col-span-2 flex flex-col gap-5 border-t lg:border-t-0 pt-6 lg:pt-0 border-[#EBEBF2] lg:border-l lg:pl-6">
                      {/* Connection Test */}
                      <div className="bg-[#FAFAFD] border border-[#EDEDF4] rounded-xl p-4 shadow-sm flex flex-col gap-3">
                        <div className="flex items-center justify-between">
                          <span className="text-[12px] font-bold text-[#111118]">Gmail SMTP Server Status</span>
                          <button
                            onClick={handleTestSmtp}
                            disabled={smtpChecking}
                            className="h-7 px-2.5 text-[11px] font-bold border border-[#EDEDF4] bg-white text-[#5A5A6D] hover:bg-[#FAFAFD] rounded-lg transition-colors flex items-center justify-center disabled:opacity-50"
                          >
                            {smtpChecking ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
                            Test Connect
                          </button>
                        </div>
                        {smtpStatus === "success" && (
                          <div className="flex items-center gap-1.5 text-[11px] font-bold text-green-600">
                            <div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>
                            Connected to smtp.gmail.com
                          </div>
                        )}
                        {smtpStatus === "error" && (
                          <div className="flex flex-col gap-1 text-[11px] font-bold text-red-600">
                            <div className="flex items-center gap-1.5">
                              <div className="w-1.5 h-1.5 bg-red-500 rounded-full"></div>
                              Verification Failed
                            </div>
                            <span className="font-mono text-[9px] font-medium text-[#7A7A8F] leading-tight mt-1 line-clamp-2">
                              {smtpError}
                            </span>
                          </div>
                        )}
                        {smtpStatus === "idle" && (
                          <span className="text-[11px] font-medium text-[#7A7A8F]">Check your Google App Password configurations</span>
                        )}
                      </div>

                      {/* Config delay for Bulk */}
                      {emailModalMode === "bulk" && (
                        <div className="bg-[#FAFAFD] border border-[#EDEDF4] rounded-xl p-4 shadow-sm flex flex-col gap-2">
                          <span className="text-[12px] font-bold text-[#111118]">Bulk Sending Delay (seconds)</span>
                          <div className="flex items-center gap-3">
                            <input
                              type="number"
                              min={1}
                              max={10}
                              value={emailDelay}
                              onChange={(e) => setEmailDelay(parseFloat(e.target.value) || 2.0)}
                              className="h-9 w-16 text-[13px] bg-white border border-[#E5E5EB] text-center font-bold rounded-lg outline-none focus:border-[#6B2BFF] focus:ring-1 focus:ring-[#6B2BFF]"
                            />
                            <span className="text-[12px] text-[#7A7A8F] font-medium">Recommended: 2s to avoid Google spam flag</span>
                          </div>
                        </div>
                      )}

                      {/* Variables Guide */}
                      <div className="bg-[#6B2BFF]/5 border border-[#6B2BFF]/10 rounded-xl p-4">
                        <span className="text-[12px] font-bold text-[#6B2BFF] flex items-center gap-1.5 mb-1.5">
                          <AlertCircle className="w-3.5 h-3.5" /> Contextual Placeholders
                        </span>
                        <p className="text-[11px] text-[#5A5A6D] leading-relaxed">
                          Placeholders are dynamic variables replaced with recipient's specific info:
                        </p>
                        <div className="grid grid-cols-3 gap-1.5 mt-2.5 font-mono text-[10px] text-center font-bold">
                          <div className="bg-white border border-[#CBB8FF]/30 text-[#6B2BFF] py-1 rounded">{"{name}"}</div>
                          <div className="bg-white border border-[#CBB8FF]/30 text-[#6B2BFF] py-1 rounded">{"{company}"}</div>
                          <div className="bg-white border border-[#CBB8FF]/30 text-[#6B2BFF] py-1 rounded">{"{title}"}</div>
                        </div>
                      </div>

                      {/* Live Preview */}
                      <div className="flex-1 flex flex-col min-h-[200px]">
                        <span className="text-[12px] font-bold text-[#5A5A6D] mb-1.5">Outreach Text Preview</span>
                        <div className="flex-1 border border-[#EDEDF4] bg-[#FAFAFD] rounded-xl p-4 text-[12px] font-medium leading-relaxed overflow-y-auto custom-scroll max-h-[200px] shadow-inner select-none">
                          <div className="border-b border-[#EDEDF4] pb-2 mb-3">
                            <span className="font-bold text-[#8A8AA3] uppercase tracking-wider text-[9px] block">Email Subject</span>
                            <span className="font-extrabold text-[#111118] text-[13px] line-clamp-1">{previewSubject || "Untitled Subject"}</span>
                          </div>
                          <div>
                            <span className="font-bold text-[#8A8AA3] uppercase tracking-wider text-[9px] block mb-1">Message Body</span>
                            <div className="whitespace-pre-wrap font-semibold text-[#5A5A6D]">{previewBody || "Compose message body to see preview..."}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Footer */}
              {!sendingProgress && !sendStats && (
                <div className="px-6 py-4 border-t border-[#EBEBF2] bg-[#FAFAFD] flex flex-wrap justify-end gap-2 shrink-0">
                  <button
                    onClick={() => setEmailModalOpen(false)}
                    className="h-10 px-4 bg-white border border-[#EDEDF4] hover:bg-[#FAFAFD] text-[#5A5A6D] font-bold rounded-lg transition-colors text-[13px]"
                  >
                    Cancel
                  </button>
                  {emailModalMode === "single" ? (
                    <button
                      onClick={handleSendSingleEmail}
                      disabled={!emailSubject.trim() || !emailBody.trim()}
                      className="h-10 px-5 bg-[#6B2BFF] hover:bg-[#5A1AE5] text-white font-bold shadow-md shadow-[#6B2BFF]/10 gap-2 border-none rounded-lg text-[13px] disabled:opacity-50 transition-all flex items-center justify-center active:scale-95"
                    >
                      <Send className="w-3.5 h-3.5" /> Dispatch Email
                    </button>
                  ) : (
                    <button
                      onClick={handleSendBulkEmail}
                      disabled={!emailSubject.trim() || !emailBody.trim()}
                      className="h-10 px-5 bg-[#6B2BFF] hover:bg-[#5A1AE5] text-white font-bold shadow-md shadow-[#6B2BFF]/10 gap-2 border-none rounded-lg text-[13px] disabled:opacity-50 transition-all flex items-center justify-center active:scale-95"
                    >
                      <Send className="w-3.5 h-3.5" /> Run Outreach Campaign ({emailTargetLeads.length} leads)
                    </button>
                  )}
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Leave Page Confirmation Modal */}
      <AnimatePresence>
        {showLeaveConfirm && (
          <div className="fixed inset-0 bg-[#111118]/60 backdrop-blur-md z-[60] flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-white border border-[#EDEDF4] shadow-2xl rounded-2xl w-full max-w-md p-6 flex flex-col gap-4 text-center"
            >
              <div className="w-12 h-12 bg-red-50 text-red-500 rounded-full flex items-center justify-center mx-auto border border-red-100 shadow-sm">
                <AlertCircle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-[16px] font-bold text-[#111118] mb-1">Unsaved Outreach Data</h3>
                <p className="text-[13px] text-[#7A7A8F] leading-relaxed">
                  You have unsaved outreach data. Do you want to discard it and leave this page?
                </p>
              </div>
              <div className="flex gap-3 justify-center mt-2">
                <button
                  onClick={() => {
                    clearOutreachState();
                    setActiveTab("generate");
                    setShowLeaveConfirm(false);
                    toast.info("Outreach state discarded.");
                  }}
                  className="h-10 px-4 bg-red-600 hover:bg-red-700 text-white font-bold rounded-xl text-[13px] transition-all flex-1"
                >
                  Discard & Leave
                </button>
                <button
                  onClick={() => setShowLeaveConfirm(false)}
                  className="h-10 px-4 bg-white border border-[#EDEDF4] hover:bg-[#FAFAFD] text-[#5A5A6D] font-bold rounded-xl text-[13px] transition-colors flex-1"
                >
                  Stay
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Floating Tweaks Panel Button */}
      {/* <button className="fixed bottom-6 right-6 h-10 pl-3 pr-4 bg-[#111118] text-white rounded-full flex items-center justify-center gap-2 shadow-[0_4px_16px_rgba(0,0,0,0.15)] hover:scale-105 active:scale-95 transition-all z-50 group border border-white/10">
        <Settings className="w-3.5 h-3.5 group-hover:rotate-45 transition-transform duration-300" />
        <span className="text-[12px] font-bold tracking-wide">Tweaks</span>
      </button> */}

      {/* Custom Styles for styling scrollbars and inputs */}
      <style>{`
        .custom-scroll::-webkit-scrollbar {
          width: 6px;
          height: 6px;
        }
        .custom-scroll::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scroll::-webkit-scrollbar-thumb {
          background: #D2D2E0;
          border-radius: 10px;
        }
        .custom-scroll::-webkit-scrollbar-thumb:hover {
          background: #A0A0B2;
        }
        ::selection {
          background: rgba(107, 43, 255, 0.2);
          color: inherit;
        }
      `}</style>
    </div>
  );
}
