// Lead shapes shared by the UI. Leads are generated on the backend
// (POST /api/generate-leads), which holds the AI provider keys; the browser
// never calls an AI provider directly.

export interface Lead {
  srNo: number;
  name: string;
  title: string;
  company: string;
  email: string;
  phone: string;
  website: string;
  location: string;
  linkedIn: string;
  segment: string;
  priority: string;
  channel: string;
  division?: string;
}

export interface ExtractedLead {
  company: string;
  name: string;
  title: string;
  email: string;
  phone: string;
  website: string;
  linkedIn: string;
  location: string;
  segment: string;
  priority: string;
  channel: string;
}
