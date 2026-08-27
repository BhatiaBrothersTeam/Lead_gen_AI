import { useState, useRef, useMemo, useEffect } from "react";
import * as React from "react";
import { motion, AnimatePresence } from "motion/react";
import { generateLeads, type Lead } from "@/src/lib/claude";
import { toast } from "sonner";
import {
  Download, Loader2, Upload, Search, Building2, User, Mail, Phone, Globe,
  MapPin, Linkedin, Database, Send, SlidersHorizontal, LayoutGrid, LayoutList,
  SplitSquareHorizontal, Maximize2, Command, Settings2, Plus, GripVertical, Check,
  MoreHorizontal, ChevronDown, AlignLeft, Sparkles, FolderDown, ArrowUpDown, ChevronRight, Share, Inbox, Tag, Copy, HelpCircle, Columns, Filter, PhoneCall, Trash2, Settings, RefreshCw
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { API_BASE_URL } from "../apiConfig";

export const badgeStyles = {
  priority: {
    High: "bg-red-50 text-red-600 border-red-100",
    Medium: "bg-amber-50 text-amber-600 border-amber-100",
    Low: "bg-blue-50 text-blue-600 border-blue-100"
  },
  segment: {
    Enterprise: "bg-violet-50 text-violet-700 border-violet-100",
    Distributor: "bg-blue-50 text-blue-700 border-blue-100",
    Retail: "bg-green-50 text-green-700 border-green-100"
  }
};

interface GenerateLeadsProps {
  leads: Lead[];
  setLeads: React.Dispatch<React.SetStateAction<Lead[]>>;
  selectedLeads: Set<number>;
  setSelectedLeads: React.Dispatch<React.SetStateAction<Set<number>>>;
  saveToDatabase: () => Promise<void>;
  exportToExcel: () => void;
  savingDB: boolean;
  openComposeModal: (lead: Lead) => void;
  openBulkComposeModal: (targetLeads: Lead[]) => void;
}

const FilterSelect = ({ label, allLabel, options, value, onChange }: any) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative inline-flex items-center" ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 h-8 px-3 text-[12px] font-semibold bg-white border border-[#EDEDF4] hover:border-[#D2D2E0] active:bg-[#FAFAFD] rounded-lg shadow-sm text-[#5A5A6D] transition-colors w-full whitespace-nowrap cursor-pointer z-10"
      >
        {label} <span className="text-[#111118] font-bold ml-1 inline-block max-w-[100px] truncate align-bottom">{value === allLabel ? allLabel : value}</span>
        <ChevronDown className={`w-3 h-3 text-[#A0A0B2] ml-1 shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.95 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute top-full left-0 mt-1.5 min-w-[180px] bg-white border border-[#EDEDF4] rounded-xl shadow-[0_10px_30px_rgba(0,0,0,0.08)] py-1.5 z-50 max-h-60 overflow-y-auto custom-scroll"
          >
            <button
              type="button"
              onClick={() => {
                onChange(allLabel);
                setIsOpen(false);
              }}
              className={`w-full text-left px-3.5 py-2 text-[12px] font-semibold flex items-center justify-between transition-colors cursor-pointer ${value === allLabel
                ? "bg-[#6B2BFF]/5 text-[#6B2BFF]"
                : "text-[#5A5A6D] hover:bg-[#FAFAFC] hover:text-[#111118]"
                }`}
            >
              <span>{allLabel}</span>
              {value === allLabel && <Check className="w-3.5 h-3.5 text-[#6B2BFF] shrink-0" />}
            </button>
            {options.map((opt: string) => {
              const isSelected = value === opt;
              return (
                <button
                  key={opt}
                  type="button"
                  onClick={() => {
                    onChange(opt);
                    setIsOpen(false);
                  }}
                  className={`w-full text-left px-3.5 py-2 text-[12px] font-semibold flex items-center justify-between transition-colors cursor-pointer ${isSelected
                    ? "bg-[#6B2BFF]/5 text-[#6B2BFF]"
                    : "text-[#5A5A6D] hover:bg-[#FAFAFC] hover:text-[#111118]"
                    }`}
                >
                  <span className="truncate max-w-[150px]">{opt}</span>
                  {isSelected && <Check className="w-3.5 h-3.5 text-[#6B2BFF] shrink-0" />}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const FormSelect = ({
  value,
  onChange,
  options,
  disabled,
  placeholder,
}: {
  value: string;
  onChange: (val: string) => void;
  options: { label: string; value: string }[];
  disabled?: boolean;
  placeholder: string;
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedOption = options.find(opt => opt.value === value);

  return (
    <div className="relative w-full" ref={containerRef}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className="w-full h-10 text-[13px] bg-[#FAFAFD] border border-[#E5E5EB] rounded-lg focus:border-[#6B2BFF] focus:ring-1 focus:ring-[#6B2BFF] px-3 outline-none flex items-center justify-between transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer bg-white"
      >
        <span className={selectedOption ? "text-[#111118] font-medium" : "text-[#A0A0B2]"}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown className={`w-4 h-4 text-[#A0A0B2] transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {isOpen && !disabled && (
          <motion.div
            initial={{ opacity: 0, y: 4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.95 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute left-0 right-0 mt-1.5 bg-white border border-[#E5E5EB] rounded-xl shadow-[0_10px_30px_rgba(0,0,0,0.08)] py-1.5 z-50 max-h-60 overflow-y-auto custom-scroll"
          >
            <button
              type="button"
              onClick={() => {
                onChange("");
                setIsOpen(false);
              }}
              className="w-full text-left px-3.5 py-2 text-[13px] font-medium text-[#A0A0B2] hover:bg-[#FAFAFC] transition-colors cursor-pointer"
            >
              {placeholder}
            </button>
            {options.map((opt) => {
              const isSelected = value === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => {
                    onChange(opt.value);
                    setIsOpen(false);
                  }}
                  className={`w-full text-left px-3.5 py-2 text-[13px] font-semibold flex items-center justify-between transition-colors cursor-pointer ${isSelected
                    ? "bg-[#6B2BFF]/5 text-[#6B2BFF]"
                    : "text-[#5A5A6D] hover:bg-[#FAFAFC] hover:text-[#111118]"
                    }`}
                >
                  <span className="truncate">{opt.label}</span>
                  {isSelected && <Check className="w-3.5 h-3.5 text-[#6B2BFF] shrink-0" />}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export function GenerateLeads({ leads, setLeads, selectedLeads, setSelectedLeads, saveToDatabase, exportToExcel, savingDB, openComposeModal, openBulkComposeModal }: GenerateLeadsProps) {
  const [loading, setLoading] = useState(false);
  const [progressStatus, setProgressStatus] = useState<string>("");
  const [generationStats, setGenerationStats] = useState<{
    totalFound: number;
    newLeadsAdded: number;
    existingLeadsUpdated: number;
    duplicatesSkipped: number;
  } | null>(null);
  const [showRefresh, setShowRefresh] = useState(leads.length > 0);
  const [manualInput, setManualInput] = useState({ division: "", productName: "", brand: "", productDescription: "" });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleRefresh = () => {
    setShowRefresh(false);
    setLeads([]);
    setSelectedLeads(new Set());
    setGenerationStats(null);
    window.location.reload();
  };

  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedType, setSelectedType] = useState("");
  const [selectedName, setSelectedName] = useState("");
  const [categoryTypes, setCategoryTypes] = useState<{ id: number, type: string }[]>([]);
  const [serviceNames, setServiceNames] = useState<string[]>([]);

  useEffect(() => {
    if (selectedCategory) {
      fetch(`${API_BASE_URL}/api/product-service-types?category=${selectedCategory}`)
        .then(res => res.json())
        .then(data => setCategoryTypes(data.types || []))
        .catch(console.error);
      setSelectedType("");
      setSelectedName("");
      setServiceNames([]);
    } else {
      setCategoryTypes([]);
      setSelectedType("");
      setServiceNames([]);
      setSelectedName("");
    }
  }, [selectedCategory]);

  useEffect(() => {
    if (selectedType && selectedCategory) {
      fetch(`${API_BASE_URL}/api/product-service-names?typeId=${selectedType}&category=${selectedCategory}`)
        .then(res => res.json())
        .then(data => setServiceNames(data.names || []))
        .catch(console.error);
      setSelectedName("");
    } else {
      setServiceNames([]);
      setSelectedName("");
    }
  }, [selectedType, selectedCategory]);

  const [inputMode, setInputMode] = useState<"manual" | "file">("manual");
  const [viewMode, setViewMode] = useState<"table" | "split" | "expand" | "cards">("table");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedLeadData, setSelectedLeadData] = useState<Lead | null>(null);

  const [filters, setFilters] = useState({
    location: "All locations",
    company: "All companies",
    segment: "All segments",
    priority: "All priorities",
    channel: "All channels"
  });

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  const toggleSelectAll = () => {
    if (selectedLeads.size === leads.length) {
      setSelectedLeads(new Set());
    } else {
      setSelectedLeads(new Set(leads.map(l => l.srNo)));
    }
  };

  const toggleSelect = (id: number) => {
    const newSet = new Set(selectedLeads);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedLeads(newSet);
  };

  // Helper to call generate leads API and consume the SSE stream synchronously for file upload
  const callGenerateLeadsApi = async (payload: any): Promise<Lead[]> => {

    const response = await fetch(`${API_BASE_URL}/api/generate-leads`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Failed to generate leads: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalLeads: Lead[] = [];

    if (reader) {
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
              const event = JSON.parse(rawJson);
              if (event.status === "error") {
                throw new Error(event.message);
              }
              if (event.status === "completed") {
                finalLeads = event.leads;
              }
            }
          }
        }
      }
    }

    return finalLeads;
  };

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const isDropdownSelected = !!selectedCategory;

    if (isDropdownSelected && !selectedName) {
      toast.error("Please select a name from the dropdown");
      return;
    }

    if (!isDropdownSelected && !manualInput.productName) {
      toast.error("Product name is required");
      return;
    }

    setLoading(true);
    setProgressStatus("Analyzing Product...");
    setGenerationStats(null);
    setLeads([]);

    try {
      let payload;
      if (isDropdownSelected) {
        const typeString = categoryTypes.find(t => t.id.toString() === selectedType)?.type || "";
        payload = {
          division: "ISD",
          productName: selectedName,
          brand: selectedCategory,
          description: `${typeString} - ${selectedName} services under ${selectedCategory} category.`,
        };
      } else {
        payload = {
          division: manualInput.division,
          productName: manualInput.productName,
          brand: manualInput.brand,
          description: manualInput.productDescription,
        };
      }

      const response = await fetch(`${API_BASE_URL}/api/generate-leads`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`Server returned error: ${response.status} ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      if (!reader) {
        throw new Error("No readable response body stream from server.");
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
                  throw new Error(event.message);
                } else if (event.status === "completed") {
                  setProgressStatus("");
                  setLeads(event.leads.map((l: any, idx: number) => ({ ...l, srNo: idx + 1 })));
                  setGenerationStats(event.stats);
                  setShowRefresh(true);
                  toast.success(`Generated ${event.leads.length} verified leads successfully!`);
                } else {
                  setProgressStatus(event.message);
                }
              } catch (parseErr) {
                console.error("Failed to parse event chunk:", rawJson, parseErr);
              }
            }
          }
        }
      }
    } catch (error: any) {
      console.error("Failed to generate leads:", error);
      toast.error(error.message || "Failed to generate leads. Please try again.");
    } finally {
      setLoading(false);
      setProgressStatus("");
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);
    setProgressStatus("Uploading file...");
    setGenerationStats(null);
    setLeads([]);
    try {
      const response = await fetch(`${API_BASE_URL}/api/upload-file`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error("Upload failed");

      const { products } = await response.json();

      if (products.length === 0) {
        toast.error("No products found in the file");
        setLoading(false);
        return;
      }

      toast.info(`Processing ${products.length} products...`);

      let allLeads: Lead[] = [];
      let currentIdx = 1;
      for (const product of products) {
        try {
          setProgressStatus(`Processing product: ${product.product_name} (${currentIdx++}/${products.length})`);
          const productLeads = await callGenerateLeadsApi({
            productName: product.product_name,
            brand: product.brand,
            division: "Auto Division",
            description: `SKU: ${product.sku}`
          });
          allLeads = [...allLeads, ...productLeads];
        } catch (err) {
          console.error(`Failed for ${product.product_name}`, err);
        }
      }

      const indexedLeads = allLeads.map((lead, index) => ({ ...lead, srNo: index + 1 }));
      setLeads(indexedLeads);
      setShowRefresh(true);
      toast.success(`Generated ${indexedLeads.length} leads from file!`);
    } catch (error) {
      toast.error("Failed to process file. Ensure it's a valid Excel file.");
    } finally {
      setLoading(false);
      setProgressStatus("");
    }
  };

  const stats = useMemo(() => {
    const highPriority = leads.filter(l => l.priority?.toLowerCase() === 'high').length;
    const regions = new Set(leads.map(l => l.location)).size;
    return {
      total: leads.length,
      highPriority,
      regions,
      selected: selectedLeads.size
    };
  }, [leads, selectedLeads]);

  const filterOptions = useMemo(() => {
    return {
      locations: Array.from(new Set(leads.map(l => l.location).filter(Boolean))),
      companies: Array.from(new Set(leads.map(l => l.company).filter(Boolean))),
      segments: Array.from(new Set(leads.map(l => l.segment).filter(Boolean))),
      priorities: Array.from(new Set(leads.map(l => l.priority).filter(Boolean))),
      channels: Array.from(new Set(leads.map(l => l.channel).filter(Boolean))),
    };
  }, [leads]);

  const filteredLeads = useMemo(() => {
    return leads.filter(lead => {
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const matches = (
          (lead.name || "").toLowerCase().includes(query) ||
          (lead.company || "").toLowerCase().includes(query) ||
          (lead.email || "").toLowerCase().includes(query) ||
          (lead.location || "").toLowerCase().includes(query)
        );
        if (!matches) return false;
      }
      if (filters.location !== "All locations" && lead.location !== filters.location) return false;
      if (filters.company !== "All companies" && lead.company !== filters.company) return false;
      if (filters.segment !== "All segments" && lead.segment !== filters.segment) return false;
      if (filters.priority !== "All priorities" && lead.priority !== filters.priority) return false;
      if (filters.channel !== "All channels" && lead.channel !== filters.channel) return false;
      return true;
    });
  }, [leads, searchQuery, filters]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, filters, leads]);

  const paginatedLeads = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return filteredLeads.slice(startIndex, startIndex + itemsPerPage);
  }, [filteredLeads, currentPage]);

  const totalPages = Math.max(1, Math.ceil(filteredLeads.length / itemsPerPage));

  useEffect(() => {
    if (viewMode === 'split' && paginatedLeads.length > 0) {
      const leadOnPage = paginatedLeads.find(l => l.srNo === selectedLeadData?.srNo);
      if (!leadOnPage) {
        setSelectedLeadData(paginatedLeads[0]);
      }
    }
  }, [viewMode, paginatedLeads, selectedLeadData]);

  return (
    <>
      {/* 2. TARGET PARAMETERS BAR */}
      <motion.div
        initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: "easeOut" }}
        className="bg-white/90 backdrop-blur-md rounded-2xl border border-[#EDEDF4]/60 shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-6 shrink-0 flex flex-col gap-5 relative overflow-visible z-30"
      >
        <div className="absolute inset-0 rounded-2xl overflow-hidden pointer-events-none">
          <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-br from-[#6B2BFF]/5 to-transparent rounded-full blur-3xl pointer-events-none" />
        </div>
        <div className="flex items-center justify-between relative z-10">
          <div className="flex items-center gap-2.5">
            <div className="w-1.5 h-5 bg-gradient-to-b from-[#6B2BFF] to-[#A880FF] rounded-full shadow-[0_0_8px_rgba(107,43,255,0.4)]"></div>
            <h2 className="text-[16px] font-bold text-[#111118] tracking-tight">Target Parameters</h2>
            <span className="text-[13px] font-medium text-[#8A8AA3] ml-2 tracking-wide">Configure AI market scanner properties</span>
          </div>

          <div className="flex bg-[#F4F4F8]/80 backdrop-blur-md rounded-xl p-1 border border-[#EBEBF2]/80">
            <button
              onClick={() => setInputMode("manual")}
              className={`text-[12px] font-bold px-3.5 py-1.5 rounded-[8px] transition-all flex items-center gap-1.5 ${inputMode === "manual" ? 'bg-white text-[#111118] shadow-sm' : 'text-[#7A7A8F] hover:text-[#111118]'}`}
            >
              <User className="w-3.5 h-3.5" /> Manual
            </button>
            <button
              onClick={() => setInputMode("file")}
              className={`text-[12px] font-bold px-3.5 py-1.5 rounded-[8px] transition-all flex items-center gap-1.5 ${inputMode === "file" ? 'bg-white text-[#111118] shadow-sm' : 'text-[#7A7A8F] hover:text-[#111118]'}`}
            >
              <Upload className="w-3.5 h-3.5" /> File Upload
            </button>
          </div>
        </div>

        {inputMode === "manual" ? (
          <form onSubmit={handleManualSubmit} className="flex flex-col gap-4 w-full">
            {/* DROPDOWNS ROW */}
            <div className="flex flex-col md:flex-row gap-4">
              <div className="flex-1 flex flex-col gap-1.5">
                <Label className="text-[12px] font-semibold text-[#5A5A6D]">Category</Label>
                <FormSelect
                  value={selectedCategory}
                  onChange={val => {
                    setSelectedCategory(val);
                    setManualInput({ division: "", productName: "", brand: "", productDescription: "" });
                  }}
                  options={[
                    { label: "Package", value: "PACKAGE" },
                    { label: "Service", value: "SERVICE" }
                  ]}
                  placeholder="Select Category..."
                />
              </div>
              <div className="flex-1 flex flex-col gap-1.5">
                <Label className="text-[12px] font-semibold text-[#5A5A6D]">Type</Label>
                <FormSelect
                  value={selectedType}
                  onChange={val => {
                    setSelectedType(val);
                    setManualInput({ division: "", productName: "", brand: "", productDescription: "" });
                  }}
                  disabled={!selectedCategory || categoryTypes.length === 0}
                  options={categoryTypes.map(t => ({ label: t.type, value: t.id.toString() }))}
                  placeholder="Select Type..."
                />
              </div>
              <div className="flex-1 flex flex-col gap-1.5">
                <Label className="text-[12px] font-semibold text-[#5A5A6D]">Name</Label>
                <FormSelect
                  value={selectedName}
                  onChange={val => {
                    setSelectedName(val);
                    setManualInput({ division: "", productName: "", brand: "", productDescription: "" });
                  }}
                  disabled={!selectedType || serviceNames.length === 0}
                  options={serviceNames.map(n => ({ label: n, value: n }))}
                  placeholder="Select Name..."
                />
              </div>
            </div>

            {/* ROW 1: Division & Product Name */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 w-full">
              <div className="md:col-span-1 flex flex-col gap-1.5">
                <Label className="text-[12px] font-semibold text-[#5A5A6D]">Division</Label>
                <FormSelect
                  disabled={!!selectedCategory}
                  value={manualInput.division}
                  onChange={val => setManualInput({ ...manualInput, division: val })}
                  options={[
                    { label: "CPD", value: "CPD" },
                    { label: "ISD", value: "ISD" },
                    { label: "Auto Division", value: "Auto Division" },
                    { label: "TPC FZE", value: "TPC FZE" },
                    { label: "Other", value: "Other" }
                  ]}
                  placeholder="Select Division (Optional)"
                />
              </div>
              <div className="md:col-span-3 flex flex-col gap-1.5">
                <Label className={`text-[12px] font-semibold ${selectedCategory ? 'text-[#A0A0B2]' : 'text-[#5A5A6D]'}`}>Product Name <span className="text-[#6B2BFF]">*</span></Label>
                <Input
                  disabled={!!selectedCategory}
                  value={manualInput.productName}
                  onChange={e => setManualInput({ ...manualInput, productName: e.target.value })}
                  placeholder="Enter product or service name"
                  className={`h-10 text-[14px] bg-[#FAFAFD] border-[#E5E5EB] rounded-lg focus-visible:ring-[#6B2BFF] focus-visible:ring-offset-0 px-3 font-semibold ${selectedCategory ? 'opacity-50 cursor-not-allowed bg-[#F4F4F8]' : ''}`}
                />
              </div>
            </div>

            {/* ROW 2: Brand */}
            <div className="flex flex-col gap-1.5 w-full md:w-1/2">
              <Label className={`text-[12px] font-semibold ${selectedCategory ? 'text-[#A0A0B2]' : 'text-[#5A5A6D]'}`}>Brand</Label>
              <Input
                disabled={!!selectedCategory}
                value={manualInput.brand}
                onChange={e => setManualInput({ ...manualInput, brand: e.target.value })}
                placeholder="Enter brand name"
                className={`h-10 text-[13px] bg-[#FAFAFD] border-[#E5E5EB] rounded-lg focus-visible:ring-[#6B2BFF] focus-visible:ring-offset-0 px-3 ${selectedCategory ? 'opacity-50 cursor-not-allowed bg-[#F4F4F8]' : ''}`}
              />
            </div>

            {/* ROW 3: Product Description */}
            <div className="flex flex-col gap-1.5 w-full">
              <Label className={`text-[12px] font-semibold ${selectedCategory ? 'text-[#A0A0B2]' : 'text-[#5A5A6D]'}`}>Product Description</Label>
              <textarea
                rows={4}
                disabled={!!selectedCategory}
                value={manualInput.productDescription}
                onChange={e => setManualInput({ ...manualInput, productDescription: e.target.value })}
                placeholder="Provide additional product details, specifications, applications, model numbers, capacity, industry usage, or service information."
                className={`w-full text-[13px] bg-[#FAFAFD] border border-[#E5E5EB] rounded-lg focus:border-[#6B2BFF] focus:ring-1 focus:ring-[#6B2BFF] p-3 outline-none transition-all disabled:opacity-50 disabled:cursor-not-allowed resize-none ${selectedCategory ? 'opacity-50 cursor-not-allowed bg-[#F4F4F8]' : ''}`}
              />
            </div>

            {/* PROGRESS STATUS */}
            {loading && progressStatus && (
              <div className="flex items-center gap-2.5 px-4 py-3 bg-[#6B2BFF]/5 border border-[#6B2BFF]/10 rounded-xl text-[13px] font-semibold text-[#6B2BFF] animate-pulse w-full">
                <Loader2 className="w-4 h-4 animate-spin text-[#6B2BFF]" />
                <span>{progressStatus}</span>
              </div>
            )}

            {/* GENERATION STATS SUMMARY */}
            {generationStats && !loading && (
              <div className="p-4 rounded-xl border border-[#EDEDF4] bg-[#FAFAFD] flex flex-col gap-3 w-full animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="flex items-center gap-1.5 text-[12px] font-bold text-[#111118]">
                  <Sparkles className="w-4 h-4 text-[#6B2BFF]" /> Generation Summary
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-2.5 bg-white rounded-lg border border-[#EDEDF4] shadow-sm">
                    <p className="text-[10px] font-bold text-[#8A8AA3] uppercase tracking-wider">Leads Found</p>
                    <p className="text-lg font-extrabold text-[#111118] mt-0.5">{generationStats.totalFound}</p>
                  </div>
                  <div className="p-2.5 bg-green-50/50 rounded-lg border border-green-100 shadow-sm">
                    <p className="text-[10px] font-bold text-green-600 uppercase tracking-wider">New Leads</p>
                    <p className="text-lg font-extrabold text-green-700 mt-0.5">{generationStats.newLeadsAdded}</p>
                  </div>
                  <div className="p-2.5 bg-blue-50/50 rounded-lg border border-blue-100 shadow-sm">
                    <p className="text-[10px] font-bold text-blue-600 uppercase tracking-wider">Updated</p>
                    <p className="text-lg font-extrabold text-blue-700 mt-0.5">{generationStats.existingLeadsUpdated}</p>
                  </div>
                  <div className="p-2.5 bg-amber-50/50 rounded-lg border border-amber-100 shadow-sm">
                    <p className="text-[10px] font-bold text-amber-600 uppercase tracking-wider">Skipped</p>
                    <p className="text-lg font-extrabold text-amber-700 mt-0.5">{generationStats.duplicatesSkipped}</p>
                  </div>
                </div>
              </div>
            )}

            {/* BUTTONS CONTAINER ALIGNED BOTTOM-RIGHT */}
            <div className="flex flex-wrap justify-end items-center gap-2 w-full mt-2">
              {showRefresh && leads.length > 0 && (
                <Button
                  type="button"
                  onClick={handleRefresh}
                  className="h-10 px-4 border border-[#EDEDF4] hover:bg-[#FAFAFD] text-[#5A5A6D] hover:text-[#111118] rounded-lg text-[13px] font-semibold transition-all flex items-center gap-2 whitespace-nowrap bg-white shadow-sm"
                >
                  <RefreshCw className="w-4 h-4 text-[#5A5A6D]" />
                  Refresh
                </Button>
              )}
              <Button
                type="submit"
                disabled={loading || (selectedCategory ? !selectedName : !manualInput.productName)}
                className="h-10 px-5 bg-[#6B2BFF] hover:bg-[#5A1AE5] text-white rounded-lg text-[13px] font-semibold shadow-[0_2px_8px_rgba(107,43,255,0.25)] transition-all flex items-center gap-2 whitespace-nowrap"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4 text-white/80" />}
                Generate Verified Leads
              </Button>
            </div>

            {/* HELP CARD BELOW THE FORM */}
            <div className="p-4 rounded-xl border border-[#EDEDF4] bg-[#FAFAFD] flex flex-col md:flex-row md:items-center justify-between gap-4 text-[12px] mt-2">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-[#6B2BFF]/10 flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles className="w-4 h-4 text-[#6B2BFF]" />
                </div>
                <div>
                  <p className="font-semibold text-[#111118]">The AI automatically identifies:</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1 mt-2 text-[#5A5A6D] font-medium">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#6B2BFF]">•</span> Industry
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#6B2BFF]">•</span> Sub Industry
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#6B2BFF]">•</span> Buyer Types
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#6B2BFF]">•</span> Competitor Brands
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#6B2BFF]">•</span> Search Keywords
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#6B2BFF]">•</span> Decision Makers
                    </div>
                  </div>
                </div>
              </div>
              <div className="text-[12px] font-semibold text-[#6B2BFF] md:text-right self-end md:self-center">
                and generates verified GCC business leads.
              </div>
            </div>
          </form>
        ) : (
          <div className="flex items-center w-full gap-4 pb-1">
            <div
              onClick={() => fileInputRef.current?.click()}
              className="flex-1 border border-dashed border-[#D2D2E0] bg-[#FAFAFC] rounded-lg h-16 flex items-center justify-center gap-3 cursor-pointer hover:bg-[#F4F4F8] hover:border-[#6B2BFF]/50 transition-all text-[#5A5A6D]"
            >
              <input type="file" ref={fileInputRef} className="hidden" accept=".xlsx, .xls" onChange={handleFileUpload} />
              <div className="w-8 h-8 rounded-full bg-white shadow-sm flex items-center justify-center border border-[#E5E5EB]">
                <Upload className="w-4 h-4 text-[#6B2BFF]" />
              </div>
              <div>
                <p className="text-[13px] font-bold text-[#111118]">Click to upload .xlsx</p>
                <p className="text-[11px]">Supports multiple products per sheet</p>
              </div>
            </div>
            {showRefresh && leads.length > 0 && (
              <Button
                type="button"
                onClick={handleRefresh}
                className="h-16 px-6 bg-white border border-dashed border-[#D2D2E0] hover:bg-[#FAFAFD] text-[#5A5A6D] hover:text-[#111118] rounded-lg text-[13px] font-semibold transition-all flex items-center gap-2 whitespace-nowrap shadow-sm"
              >
                <RefreshCw className="w-4 h-4 text-[#5A5A6D]" />
                Refresh
              </Button>
            )}
          </div>
        )}
      </motion.div>

      {/* 3. STATS STRIP */}
      <motion.div
        initial="hidden" animate="visible"
        variants={{ visible: { transition: { staggerChildren: 0.08 } } }}
        className="grid grid-cols-2 lg:grid-cols-4 gap-5 shrink-0"
      >
        {[
          { label: "Leads Acquired", value: stats.total.toString(), icon: User, color: "text-[#3B82F6]", bg: "bg-blue-50/80 border-blue-100", gradient: "from-blue-500/10" },
          { label: "High Priority", value: stats.highPriority.toString(), icon: Sparkles, color: "text-[#EF4444]", bg: "bg-red-50/80 border-red-100", gradient: "from-red-500/10" },
          { label: "Regions Scanned", value: stats.regions.toString(), icon: Globe, color: "text-[#8B5CF6]", bg: "bg-violet-50/80 border-violet-100", gradient: "from-violet-500/10" },
          { label: "Selected Items", value: stats.selected.toString(), icon: Check, color: "text-[#10B981]", bg: "bg-emerald-50/80 border-emerald-100", gradient: "from-emerald-500/10" },
        ].map((stat, i) => (
          <motion.div
            key={i}
            variants={{ hidden: { opacity: 0, scale: 0.95, y: 10 }, visible: { opacity: 1, scale: 1, y: 0 } }}
            whileHover={{ y: -4, scale: 1.02 }}
            className="bg-white/80 backdrop-blur-md rounded-2xl border border-[#EDEDF4]/60 shadow-[0_4px_20px_rgb(0,0,0,0.03)] p-5 flex items-center justify-between group transition-shadow hover:shadow-[0_8px_30px_rgb(107,43,255,0.08)] cursor-default overflow-hidden relative"
          >
            <div className={`absolute -right-6 -bottom-6 w-24 h-24 bg-gradient-to-br ${stat.gradient} to-transparent rounded-full blur-xl pointer-events-none transition-transform duration-500 group-hover:scale-150`} />
            <div className="relative z-10">
              <p className="text-[11px] font-bold text-[#8A8AA3] uppercase tracking-widest mb-1">{stat.label}</p>
              <p className="text-3xl font-extrabold tracking-tight text-[#111118]">{stat.value}</p>
            </div>
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center border shadow-sm relative z-10 transition-transform group-hover:rotate-6 ${stat.bg} ${stat.color}`}>
              <stat.icon className="w-5 h-5" />
            </div>
          </motion.div>
        ))}
      </motion.div>

      {/* 4. FILTER / TOOLBAR */}
      <div className="shrink-0 flex flex-col md:flex-row md:items-center md:justify-between border-b border-[#E5E5EB] pb-4 sticky top-0 bg-[#FAFAFC]/95 backdrop-blur-sm pt-2 z-20 gap-3 will-change-transform">
        {selectedLeads.size > 0 ? (
          // Bulk Actions Toolbar
          <div className="flex flex-col md:flex-row md:items-center justify-between w-full gap-3 animate-in fade-in zoom-in duration-200">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="bg-[#6B2BFF]/10 text-[#6B2BFF] text-[12px] font-bold px-2 py-0.5 rounded-[4px]">
                {selectedLeads.size} selected
              </div>
              <span className="text-[13px] font-medium text-[#7A7A8F]">Apply action to selected leads:</span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {selectedLeads.size === 1 ? (
                <Button onClick={() => {
                  const srNo = Array.from(selectedLeads)[0];
                  const lead = leads.find(l => l.srNo === srNo);
                  if (lead) openComposeModal(lead);
                }} className="h-8 shadow-sm text-[12px] font-semibold bg-[#6B2BFF] text-white hover:bg-[#5A1AE5] gap-1.5 border-none">
                  <Send className="w-3.5 h-3.5" /> Send Email
                </Button>
              ) : (
                <Button onClick={() => {
                  const targetLeads = leads.filter(l => selectedLeads.has(l.srNo));
                  openBulkComposeModal(targetLeads);
                }} className="h-8 shadow-sm text-[12px] font-semibold bg-[#6B2BFF] text-white hover:bg-[#5A1AE5] gap-1.5 border-none">
                  <Send className="w-3.5 h-3.5" /> Send Bulk Email
                </Button>
              )}
              <Button onClick={() => {
                setLeads(prev => prev.filter(l => !selectedLeads.has(l.srNo)));
                setSelectedLeads(new Set());
              }} variant="outline" className="h-8 shadow-sm text-[12px] font-semibold border-[#FEE2E2] text-[#DC2626] hover:bg-[#FEF2F2] hover:text-[#EF4444] gap-1.5">
                <Trash2 className="w-3.5 h-3.5" /> Remove
              </Button>
              <Button onClick={saveToDatabase} disabled={savingDB} variant="outline" className="h-8 shadow-sm text-[12px] font-semibold border-[#E5E5EB] text-[#111118] hover:bg-[#F4F4F8] hover:text-[#111118] gap-1.5">
                {savingDB ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Database className="w-3.5 h-3.5" />} Save to database
              </Button>
              <Button onClick={exportToExcel} variant="outline" className="h-8 shadow-sm text-[12px] font-semibold bg-[#111118] text-white hover:bg-[#22222A] gap-1.5 border-none">
                <FolderDown className="w-3.5 h-3.5" /> Export (.xlsx)
              </Button>
              <div className="w-px h-4 bg-[#E5E5EB] mx-1"></div>
              <Button variant="ghost" onClick={() => setSelectedLeads(new Set())} className="h-8 px-2 text-[12px] font-semibold text-[#7A7A8F]">Cancel</Button>
            </div>
          </div>
        ) : (
          // Standard Toolbar
          <>
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex bg-white rounded-lg p-0.5 border border-[#EDEDF4] shadow-sm">
                {[
                  { id: "table", icon: LayoutList, label: "Table" },
                  { id: "split", icon: SplitSquareHorizontal, label: "Split" },
                  { id: "expand", icon: Maximize2, label: "Expand" },
                  { id: "cards", icon: LayoutGrid, label: "Cards" }
                ].map((v) => (
                  <button
                    key={v.id}
                    onClick={() => setViewMode(v.id as any)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-[6px] text-[12px] font-semibold transition-all ${viewMode === v.id ? 'bg-[#F4F4F8] text-[#111118]' : 'text-[#7A7A8F] hover:text-[#111118]'}`}
                  >
                    <v.icon className="w-3.5 h-3.5" /> <span className="hidden sm:inline">{v.label}</span>
                  </button>
                ))}
              </div>

              <div className="w-px h-4 bg-[#D2D2E0] hidden sm:block"></div>

              <div className="relative w-64 hidden sm:block">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#A0A0B2]" />
                <Input
                  id="search-input"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search names, companies, emails..."
                  className="h-8 pl-9 pr-8 text-[12px] bg-white border-[#EDEDF4] rounded-lg shadow-sm focus-visible:ring-1 focus-visible:ring-[#6B2BFF]"
                />
                <div className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-bold text-[#A0A0B2] bg-[#F4F4F8] px-1.5 py-0.5 rounded">/</div>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <div className="hidden lg:flex items-center gap-2">
                <FilterSelect
                  label="Location"
                  allLabel="All locations"
                  options={filterOptions.locations}
                  value={filters.location}
                  onChange={(val: string) => setFilters(f => ({ ...f, location: val }))}
                />
                <FilterSelect
                  label="Company"
                  allLabel="All companies"
                  options={filterOptions.companies}
                  value={filters.company}
                  onChange={(val: string) => setFilters(f => ({ ...f, company: val }))}
                />
                <FilterSelect
                  label="Segment"
                  allLabel="All segments"
                  options={filterOptions.segments}
                  value={filters.segment}
                  onChange={(val: string) => setFilters(f => ({ ...f, segment: val }))}
                />
              </div>

              <div className="w-px h-4 bg-[#D2D2E0] hidden lg:block"></div>

              {leads.length > 0 && (
                <>
                  <button onClick={saveToDatabase} disabled={savingDB} className="text-[12px] font-semibold text-[#5A5A6D] hover:text-[#111118] flex items-center gap-1.5 transition-colors px-2">
                    {savingDB ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Database className="w-3.5 h-3.5" />}
                    Save to database
                  </button>
                  <button onClick={exportToExcel} className="flex items-center gap-1.5 bg-[#111118] text-white px-3 py-1.5 rounded-lg text-[12px] font-semibold hover:bg-[#22222A] transition-colors shadow-sm ml-1 mr-2">
                    <FolderDown className="w-3.5 h-3.5" /> Export
                  </button>
                  {/* <div className="w-px h-4 bg-[#D2D2E0] hidden lg:block"></div> */}
                </>
              )}

              {/* <button className="h-8 w-8 flex items-center justify-center bg-white border border-[#EDEDF4] rounded-lg shadow-sm text-[#5A5A6D] hover:border-[#D2D2E0] hover:text-[#111118]">
                <ArrowUpDown className="w-3.5 h-3.5" />
              </button>
              <button className="h-8 w-8 flex items-center justify-center bg-white border border-[#EDEDF4] rounded-lg shadow-sm text-[#5A5A6D] hover:border-[#D2D2E0] hover:text-[#111118]">
                <Columns className="w-3.5 h-3.5" />
              </button> */}
            </div>
          </>
        )}
      </div>

      {/* Secondary Filters Bar */}
      {selectedLeads.size === 0 && (
        <motion.div
          initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
          className="shrink-0 flex items-center gap-4 hidden lg:flex"
        >
          <FilterSelect
            label="Priority"
            allLabel="All priorities"
            options={filterOptions.priorities}
            value={filters.priority}
            onChange={(val: string) => setFilters(f => ({ ...f, priority: val }))}
          />
          <FilterSelect
            label="Channel"
            allLabel="All channels"
            options={filterOptions.channels}
            value={filters.channel}
            onChange={(val: string) => setFilters(f => ({ ...f, channel: val }))}
          />
        </motion.div>
      )}

      {/* 5. DYNAMIC VIEWS */}
      <div className="h-[calc(100vh-380px)] min-h-[480px] bg-white/85 backdrop-blur-sm rounded-2xl border border-[#EDEDF4]/80 shadow-[0_4px_24px_rgb(0,0,0,0.02)] overflow-hidden flex flex-col relative transform-gpu">

        {leads.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-10">
            <div className="w-16 h-16 bg-[#FAFAFD] border border-[#E5E5EB] rounded-2xl flex items-center justify-center mb-4">
              <Inbox className="w-6 h-6 text-[#A0A0B2]" />
            </div>
            <h3 className="text-[15px] font-bold text-[#111118] mb-1">No leads yet</h3>
            <p className="text-[13px] text-[#7A7A8F] max-w-[280px]">Generate leads manually or upload a file to start building your database.</p>
          </div>
        ) : (
          <>
            <div className="flex-1 flex min-h-0 relative">
              {/* TABLE VIEW */}
              {viewMode === "table" && (
                <div className="w-full h-full overflow-auto custom-scroll relative">
                  <table className="w-full text-left border-collapse text-[13px]">
                    <thead className="sticky top-0 bg-[#FAFAFD] text-[11px] font-bold text-[#8A8AA3] uppercase tracking-wider border-b border-[#E5E5EB] z-10 backdrop-blur-md">
                      <tr>
                        <th className="px-4 py-3 w-10 text-center">
                          <input type="checkbox" checked={selectedLeads.size === leads.length && leads.length > 0} onChange={toggleSelectAll} className="w-[14px] h-[14px] rounded-[4px] border-[#D2D2E0] text-[#6B2BFF] cursor-pointer" />
                        </th>
                        <th className="px-3 py-3 w-10">#</th>
                        <th className="px-3 py-3 text-[#5A5A6D]">Name</th>
                        <th className="px-3 py-3 text-[#5A5A6D] hidden md:table-cell">Title</th>
                        <th className="px-3 py-3 text-[#5A5A6D]">Company</th>
                        <th className="px-3 py-3 text-[#5A5A6D] hidden lg:table-cell">Email</th>
                        <th className="px-3 py-3 text-[#5A5A6D] hidden xl:table-cell">Website</th>
                        <th className="px-3 py-3 text-[#5A5A6D] hidden xl:table-cell">LinkedIn</th>
                        <th className="px-3 py-3 text-[#5A5A6D] hidden xl:table-cell">Location</th>
                        <th className="px-3 py-3 text-[#5A5A6D]">Segment</th>
                        <th className="px-3 py-3 text-[#5A5A6D]">Priority</th>
                        <th className="px-3 py-3 text-[#5A5A6D] hidden sm:table-cell">Channel</th>
                        <th className="px-3 py-3 text-[#5A5A6D]">Email Status</th>
                        <th className="px-3 py-3"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E5E5EB]/60">
                      {paginatedLeads.map((lead, idx) => {
                        const isSelected = selectedLeads.has(lead.srNo);
                        // @ts-ignore
                        const pBadge = badgeStyles.priority[lead.priority] || "bg-slate-50 text-slate-600 border-slate-100";
                        // @ts-ignore
                        const sBadge = badgeStyles.segment[lead.segment] || "bg-slate-50 text-slate-600 border-slate-100";
                        const initials = lead.name ? lead.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() : '?';

                        return (
                          <tr key={lead.srNo} className={`group hover:bg-[#FAFAFD] transition-colors relative ${isSelected ? 'bg-[#F9F7FF] hover:bg-[#F3EFFF]' : ''}`}>
                            {isSelected && <td className="absolute left-0 top-0 bottom-0 w-0.5 bg-[#6B2BFF]"></td>}
                            <td className="px-4 py-3.5 w-10 text-center" onClick={(e) => e.stopPropagation()}>
                              <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(lead.srNo)} className="w-[14px] h-[14px] rounded-[4px] border-[#D2D2E0] text-[#6B2BFF] cursor-pointer" />
                            </td>
                            <td className="px-3 py-3 w-10 text-[#A0A0B2] font-mono text-[11px]">{lead.srNo.toString().padStart(2, '0')}</td>
                            <td className="px-3 py-3 font-semibold text-[#111118]">
                              <div className="flex items-center gap-2.5">
                                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold ${isSelected ? 'bg-[#6B2BFF] text-white' : 'bg-[#EAE5FF] text-[#6B2BFF]'}`}>{initials}</div>
                                {lead.name}
                              </div>
                            </td>
                            <td className="px-3 py-3 text-[#5A5A6D] hidden md:table-cell whitespace-nowrap">{lead.title}</td>
                            <td className="px-3 py-3 font-semibold text-[#111118]">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <Building2 className="w-3.5 h-3.5 text-[#A0A0B2]" /> {lead.company}
                              </div>
                            </td>
                            <td className="px-3 py-3 text-[#5A5A6D] hidden lg:table-cell hover:text-[#6B2BFF] transition-colors" onClick={(e) => e.stopPropagation()}>
                              <a href={`mailto:${lead.email}`}>{lead.email}</a>
                            </td>
                            <td className="px-3 py-3 text-[#5A5A6D] hidden xl:table-cell" onClick={(e) => e.stopPropagation()}>
                              {lead.website ? (
                                <div className="flex items-center gap-1.5">
                                  <a href={lead.website.startsWith('http') ? lead.website : `https://${lead.website}`} target="_blank" rel="noreferrer" className="hover:text-[#6B2BFF] truncate max-w-[120px] inline-flex items-center gap-1" title={lead.website}>
                                    <Globe className="w-3.5 h-3.5 shrink-0" />
                                    <span className="truncate">{lead.website.replace(/^https?:\/\/(www\.)?/, '')}</span>
                                  </a>
                                  <a href={`https://www.google.com/search?q=${encodeURIComponent(lead.company + ' website')}`} target="_blank" rel="noreferrer" className="text-[#A0A0B2] hover:text-[#6B2BFF] transition-colors shrink-0 p-0.5" title="Search on Google">
                                    <Search className="w-3 h-3" />
                                  </a>
                                </div>
                              ) : '—'}
                            </td>
                            <td className="px-3 py-3 text-[#5A5A6D] hidden xl:table-cell" onClick={(e) => e.stopPropagation()}>
                              {lead.linkedIn ? (
                                <a href={lead.linkedIn.startsWith('http') ? lead.linkedIn : `https://${lead.linkedIn}`} target="_blank" rel="noreferrer" className="hover:text-[#0077B5] transition-colors truncate max-w-[150px] inline-flex items-center gap-1">
                                  <Linkedin className="w-3.5 h-3.5" />
                                  <span className="truncate">Profile</span>
                                </a>
                              ) : '—'}
                            </td>
                            <td className="px-3 py-3 text-[#5A5A6D] hidden xl:table-cell whitespace-nowrap">{lead.location}</td>
                            <td className="px-3 py-3">
                              <span className={`px-2 py-0.5 rounded-[4px] text-[11px] font-bold border ${sBadge}`}>{lead.segment || 'Unknown'}</span>
                            </td>
                            <td className="px-3 py-3">
                              <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold border flex w-max items-center gap-1.5 ${pBadge}`}>
                                <div className={`w-1.5 h-1.5 rounded-full ${lead.priority === 'High' ? 'bg-red-500' : lead.priority === 'Medium' ? 'bg-amber-500' : 'bg-blue-500'}`}></div>
                                {lead.priority || 'Unknown'}
                              </span>
                            </td>
                            <td className="px-3 py-3 text-[#5A5A6D] hidden sm:table-cell">
                              <div className="flex items-center gap-1.5">
                                {lead.channel?.toLowerCase().includes('email') ? <Mail className="w-3.5 h-3.5" /> : lead.channel?.toLowerCase().includes('phone') ? <Phone className="w-3.5 h-3.5" /> : <Linkedin className="w-3.5 h-3.5" />}
                                {lead.channel}
                              </div>
                            </td>
                            <td className="px-3 py-3">
                              {lead.email_status ? (
                                <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold border flex w-max items-center gap-1 ${lead.email_status.toLowerCase() === 'sent'
                                  ? 'bg-green-50 text-green-600 border-green-100'
                                  : 'bg-red-50 text-red-600 border-red-100'
                                  }`} title={lead.email_error || undefined}>
                                  <div className={`w-1 h-1 rounded-full ${lead.email_status.toLowerCase() === 'sent' ? 'bg-green-500' : 'bg-red-500'}`}></div>
                                  {lead.email_status.toLowerCase() === 'sent' ? 'Sent' : 'Failed'}
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 rounded-full text-[11px] font-bold border flex w-max items-center gap-1 bg-slate-50 text-slate-500 border-slate-100">
                                  <div className="w-1 h-1 rounded-full bg-slate-400"></div>
                                  Unsent
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-3 text-right">
                              <button className="opacity-0 group-hover:opacity-100 text-[#A0A0B2] hover:text-[#111118] transition-opacity p-1">
                                <MoreHorizontal className="w-4 h-4" />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* SPLIT VIEW */}
              {viewMode === "split" && (
                <div className="w-full h-full flex flex-col lg:flex-row overflow-hidden">
                  {/* Split List */}
                  <div className="w-full lg:w-[380px] h-[250px] lg:h-full shrink-0 border-b lg:border-b-0 lg:border-r border-[#E5E5EB] bg-[#FAFAFC] flex flex-col overflow-auto custom-scroll">
                    <div className="p-3 border-b border-[#E5E5EB] flex items-center justify-between text-[11px] font-bold text-[#8A8AA3] uppercase tracking-wider sticky top-0 bg-[#FAFAFC] z-10">
                      <span className="flex items-center gap-2"><ArrowUpDown className="w-3 h-3" /> LEADS · {filteredLeads.length}</span>
                    </div>
                    <div className="flex-1 p-2 flex flex-col gap-1">
                      {paginatedLeads.map((lead) => {
                        const isActive = selectedLeadData?.srNo === lead.srNo;
                        const initials = lead.name ? lead.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() : '?';
                        return (
                          <div
                            key={lead.srNo}
                            onClick={() => setSelectedLeadData(lead)}
                            className={`p-3 rounded-lg flex items-center justify-between cursor-pointer transition-all border group ${isActive ? 'bg-white border-[#D0B8FF] shadow-[0_2px_8px_rgba(107,43,255,0.08)]' : 'border-transparent hover:bg-white hover:border-[#E5E5EB]'}`}
                          >
                            <div className="flex items-center gap-3 overflow-hidden">
                              {isActive ? (
                                <div className="w-1.5 h-6 bg-[#6B2BFF] rounded-r-full absolute left-0" />
                              ) : null}

                              <input type="checkbox" checked={selectedLeads.has(lead.srNo)} onChange={(e) => { e.stopPropagation(); toggleSelect(lead.srNo); }} className="w-3.5 h-3.5 rounded-[4px] border-[#D2D2E0] text-[#6B2BFF] opacity-0 group-hover:opacity-100 transition-opacity" />
                              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${isActive ? 'bg-[#F3EFFF] text-[#6B2BFF]' : 'bg-[#EBEBF2] text-[#5A5A6D]'}`}>{initials}</div>
                              <div className="overflow-hidden">
                                <p className="text-[13px] font-bold text-[#111118] truncate pr-2">{lead.name}</p>
                                <p className="text-[12px] font-medium text-[#7A7A8F] truncate pr-2">{lead.title} · {lead.company}</p>
                              </div>
                            </div>
                            <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${lead.priority === 'High' ? 'bg-red-500' : lead.priority === 'Medium' ? 'bg-amber-500' : 'bg-blue-500'}`}></div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Split Detail */}
                  <div className="flex-1 bg-white h-full overflow-auto custom-scroll p-8">
                    {selectedLeadData ? (
                      <div className="max-w-[700px] mx-auto animate-in fade-in slide-in-from-bottom-4 duration-300">
                        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-8">
                          <div className="flex items-center gap-5">
                            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-[#EAE5FF] to-[#D0B8FF] flex items-center justify-center text-xl font-bold text-[#6B2BFF] border border-[#CBB8FF]">
                              {selectedLeadData.name ? selectedLeadData.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() : '?'}
                            </div>
                            <div>
                              <div className="flex items-center gap-2 mb-1">
                                <h2 className="text-2xl font-bold text-[#111118]">{selectedLeadData.name}</h2>
                                <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold border flex items-center gap-1.5 ${badgeStyles.priority[selectedLeadData.priority as keyof typeof badgeStyles.priority] || "bg-slate-50 text-slate-600 border-slate-100"}`}>
                                  <div className={`w-1.5 h-1.5 rounded-full ${selectedLeadData.priority === 'High' ? 'bg-red-500' : selectedLeadData.priority === 'Medium' ? 'bg-amber-500' : 'bg-blue-500'}`}></div>
                                  {selectedLeadData.priority || 'Unknown'}
                                </span>
                              </div>
                              <p className="text-[15px] font-medium text-[#5A5A6D]">{selectedLeadData.title} at <span className="font-bold text-[#111118]">{selectedLeadData.company}</span></p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <Button onClick={() => openComposeModal(selectedLeadData)} className="h-9 px-4 bg-[#111118] text-white rounded-lg text-[13px] font-semibold hover:bg-[#22222A] gap-2">
                              <Send className="w-3.5 h-3.5" /> Compose Email
                            </Button>
                            <Button variant="outline" className="h-9 w-9 p-0 rounded-lg border-[#E5E5EB] text-[#5A5A6D] hover:bg-[#FAFAFC]"><PhoneCall className="w-4 h-4" /></Button>
                            <Button variant="outline" className="h-9 w-9 p-0 rounded-lg border-[#E5E5EB] text-[#5A5A6D] hover:bg-[#FAFAFC]"><Copy className="w-4 h-4" /></Button>
                          </div>
                        </div>

                        <div className="space-y-8">
                          <div>
                            <h3 className="text-[11px] font-bold text-[#8A8AA3] uppercase tracking-wider mb-3">Contact</h3>
                            <div className="bg-[#FAFAFC] border border-[#E5E5EB] rounded-xl overflow-hidden divide-y divide-[#E5E5EB]">
                              <div className="flex items-center px-4 py-3">
                                <Mail className="w-4 h-4 text-[#A0A0B2] w-24 shrink-0" />
                                <span className="text-[14px] font-medium text-[#111118] flex-1">{selectedLeadData.email}</span>
                                <button className="text-[#A0A0B2] hover:text-[#6B2BFF]"><Copy className="w-3.5 h-3.5" /></button>
                              </div>
                              <div className="flex items-center px-4 py-3">
                                <Phone className="w-4 h-4 text-[#A0A0B2] w-24 shrink-0" />
                                <span className="text-[14px] font-medium text-[#111118] flex-1">{selectedLeadData.phone || '—'}</span>
                                {selectedLeadData.phone && <button className="text-[#A0A0B2] hover:text-[#6B2BFF]"><Copy className="w-3.5 h-3.5" /></button>}
                              </div>
                              <div className="flex items-center px-4 py-3" onClick={(e) => e.stopPropagation()}>
                                <Globe className="w-4 h-4 text-[#A0A0B2] w-24 shrink-0" />
                                {selectedLeadData.website ? (
                                  <div className="flex items-center gap-2 flex-1 overflow-hidden">
                                    <a
                                      href={selectedLeadData.website.startsWith('http') ? selectedLeadData.website : `https://${selectedLeadData.website}`}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="text-[14px] font-medium text-[#6B2BFF] hover:underline truncate"
                                      title={selectedLeadData.website}
                                    >
                                      {selectedLeadData.website}
                                    </a>
                                    <a
                                      href={`https://www.google.com/search?q=${encodeURIComponent(selectedLeadData.company + ' website')}`}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="text-[#A0A0B2] hover:text-[#6B2BFF] transition-colors p-0.5 inline-flex"
                                      title="Search on Google"
                                    >
                                      <Search className="w-3.5 h-3.5" />
                                    </a>
                                  </div>
                                ) : (
                                  <span className="text-[14px] font-medium text-[#A0A0B2] flex-1">—</span>
                                )}
                              </div>
                              <div className="flex items-center px-4 py-3" onClick={(e) => e.stopPropagation()}>
                                <Linkedin className="w-4 h-4 text-[#A0A0B2] w-24 shrink-0" />
                                {selectedLeadData.linkedIn ? (
                                  <a
                                    href={selectedLeadData.linkedIn.startsWith('http') ? selectedLeadData.linkedIn : `https://${selectedLeadData.linkedIn}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-[14px] font-medium text-[#0077B5] hover:underline flex-1 truncate"
                                    title={selectedLeadData.linkedIn}
                                  >
                                    {selectedLeadData.linkedIn.replace(/^https?:\/\/(www\.)?linkedin\.com\/in\//, 'in/')}
                                  </a>
                                ) : (
                                  <span className="text-[14px] font-medium text-[#A0A0B2] flex-1">in/{selectedLeadData.name?.toLowerCase().replace(/\s+/g, '')}</span>
                                )}
                              </div>
                              <div className="flex items-center px-4 py-3">
                                <MapPin className="w-4 h-4 text-[#A0A0B2] w-24 shrink-0" />
                                <span className="text-[14px] font-medium text-[#111118] flex-1">{selectedLeadData.location || '—'}</span>
                              </div>
                            </div>
                          </div>

                          <div>
                            <h3 className="text-[11px] font-bold text-[#8A8AA3] uppercase tracking-wider mb-3">Classification</h3>
                            <div className="bg-[#FAFAFC] border border-[#E5E5EB] rounded-xl overflow-hidden divide-y divide-[#E5E5EB]">
                              <div className="flex items-center px-4 py-3">
                                <span className="text-[13px] font-medium text-[#7A7A8F] w-24 shrink-0">Segment</span>
                                <span className={`px-2 py-0.5 rounded-[4px] text-[12px] font-bold border ${badgeStyles.segment[selectedLeadData.segment as keyof typeof badgeStyles.segment] || "bg-slate-50 text-slate-600 border-slate-100"}`}>{selectedLeadData.segment || 'Unknown'}</span>
                              </div>
                              <div className="flex items-center px-4 py-3">
                                <span className="text-[13px] font-medium text-[#7A7A8F] w-24 shrink-0">Priority</span>
                                <span className={`px-2 py-0.5 rounded-full text-[12px] font-bold border flex w-max items-center gap-1.5 ${badgeStyles.priority[selectedLeadData.priority as keyof typeof badgeStyles.priority] || "bg-slate-50 text-slate-600 border-slate-100"}`}>
                                  <div className={`w-1.5 h-1.5 rounded-full ${selectedLeadData.priority === 'High' ? 'bg-red-500' : selectedLeadData.priority === 'Medium' ? 'bg-amber-500' : 'bg-blue-500'}`}></div>
                                  {selectedLeadData.priority || 'Unknown'}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center h-full text-[#A0A0B2] text-[13px]">Select a lead to view details</div>
                    )}
                  </div>
                </div>
              )}

              {/* CARDS VIEW */}
              {viewMode === "cards" && (
                <motion.div
                  initial="hidden" animate="visible"
                  variants={{ visible: { transition: { staggerChildren: 0.05 } } }}
                  className="w-full h-full overflow-auto custom-scroll p-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5 bg-transparent"
                >
                  {paginatedLeads.map((lead) => {
                    const initials = lead.name ? lead.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() : '?';
                    return (
                      <motion.div
                        key={lead.srNo}
                        variants={{ hidden: { opacity: 0, y: 15, scale: 0.98 }, visible: { opacity: 1, y: 0, scale: 1 } }}
                        whileHover={{ y: -6 }}
                        className="bg-white rounded-[20px] border border-[#EDEDF4] shadow-sm hover:shadow-[0_16px_40px_rgb(107,43,255,0.08)] hover:border-[#6B2BFF]/30 transition-shadow duration-300 p-5 flex flex-col group relative overflow-hidden"
                      >
                        <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-transparent to-[#6B2BFF]/5 rounded-full blur-2xl pointer-events-none group-hover:to-[#6B2BFF]/10 transition-colors" />
                        <div className="absolute top-4 right-4 z-10">
                          <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold border flex items-center gap-1.5 shadow-sm ${badgeStyles.priority[lead.priority as keyof typeof badgeStyles.priority] || "bg-slate-50 text-slate-600 border-slate-100"}`}>
                            {lead.priority}
                          </span>
                        </div>
                        <div className="w-11 h-11 rounded-2xl flex items-center justify-center text-[13px] font-bold bg-gradient-to-br from-[#F3EFFF] to-[#E5DBFF] text-[#6B2BFF] mb-5 shadow-sm shadow-[#6B2BFF]/10 border border-[#D0B8FF]/30">
                          {initials}
                        </div>
                        <h3 className="text-[16px] font-bold text-[#111118] line-clamp-1 group-hover:text-[#6B2BFF] transition-colors relative z-10">{lead.name}</h3>
                        <p className="text-[13px] font-medium text-[#7A7A8F] mb-5 line-clamp-1 relative z-10">{lead.title}</p>

                        <div className="bg-[#FAFAFC]/80 backdrop-blur-sm rounded-xl p-3 border border-[#E5E5EB]/60 mb-5 relative z-10">
                          <div className="flex items-center gap-2 text-[12px] font-medium text-[#111118] mb-2 line-clamp-1">
                            <Building2 className="w-3.5 h-3.5 text-[#A0A0B2]" /> {lead.company}
                          </div>
                          <div className="flex items-center gap-2 text-[12px] text-[#5A5A6D] line-clamp-1">
                            <MapPin className="w-3.5 h-3.5 text-[#A0A0B2]" /> {lead.location}
                          </div>
                        </div>

                        <div className="mt-auto flex items-center justify-between pt-3 border-t border-[#E5E5EB]/60 relative z-10">
                          <div className="flex items-center gap-1.5">
                            <button onClick={() => openComposeModal(lead)} className="w-8 h-8 rounded-lg shrink-0 flex items-center justify-center text-[#A0A0B2] hover:bg-[#F3EFFF] hover:text-[#6B2BFF] transition-colors"><Mail className="w-4 h-4" /></button>
                            <button className="w-8 h-8 rounded-lg shrink-0 flex items-center justify-center text-[#A0A0B2] hover:bg-[#F0F7FA] hover:text-[#0077B5] transition-colors"><Linkedin className="w-4 h-4" /></button>
                          </div>
                          <Button onClick={() => openComposeModal(lead)} className="h-9 px-4 text-[13px] bg-[#111118] text-white font-semibold rounded-lg hover:bg-[#6B2BFF] shadow-sm transition-colors group/btn overflow-hidden relative">
                            <span className="relative z-10 flex items-center gap-2">Reach out <Send className="w-3 h-3 group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5 transition-transform" /></span>
                          </Button>
                        </div>
                      </motion.div>
                    );
                  })}
                </motion.div>
              )}

              {/* EXPAND VIEW placeholder */}
              {viewMode === "expand" && (
                <div className="flex items-center justify-center h-full text-[#A0A0B2]">Expand view mode matches table but with more columns (implemented using standard Table). Switching back to Table.</div>
              )}
            </div>

            {/* Pagination Bar */}
            {filteredLeads.length > 0 && (
              <div className="shrink-0 flex items-center justify-between border-t border-[#E5E5EB] px-6 py-4 bg-[#FAFAFD]/60 backdrop-blur-md">
                <div className="text-[13px] font-medium text-[#7A7A8F]">
                  Showing <span className="font-bold text-[#111118]">{Math.min(filteredLeads.length, (currentPage - 1) * itemsPerPage + 1)}</span> to{" "}
                  <span className="font-bold text-[#111118]">{Math.min(filteredLeads.length, currentPage * itemsPerPage)}</span> of{" "}
                  <span className="font-bold text-[#111118]">{filteredLeads.length}</span> leads
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    className="h-8 px-3 border-[#E5E5EB] hover:bg-[#FAFAFD] text-[#5A5A6D] hover:text-[#111118] rounded-lg text-[12px] font-semibold transition-all flex items-center gap-1.5 whitespace-nowrap bg-white shadow-sm disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                  >
                    <ChevronRight className="w-3.5 h-3.5 rotate-180" />
                    Previous
                  </Button>
                  <div className="text-[12px] font-semibold text-[#5A5A6D] px-2">
                    Page {currentPage} of {totalPages}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={currentPage === totalPages}
                    onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                    className="h-8 px-3 border-[#E5E5EB] hover:bg-[#FAFAFD] text-[#5A5A6D] hover:text-[#111118] rounded-lg text-[12px] font-semibold transition-all flex items-center gap-1.5 whitespace-nowrap bg-white shadow-sm disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                  >
                    Next
                    <ChevronRight className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
