import Anthropic from "@anthropic-ai/sdk";
import { API_BASE_URL } from "../apiConfig";

const anthropic = new Anthropic({
    apiKey: process.env.ANTHROPIC_API_KEY || "",
    dangerouslyAllowBrowser: true
});

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

export async function generateLeads(
    productName: string,
    sku: string,
    brand: string,
    category?: string,
    type?: string,
    name?: string,
    division?: string,
    description?: string
): Promise<Lead[]> {
    const isDropdown = !!(category && type && name);

    const dropdownPrompt = `I want you to act like a B2B lead generation and sales research assistant for UAE market.

My goal is to generate a targeted lead list for a specific industrial or technical service that my company provides.

Category / Offering:
${category}

Type - Name:
${type} - ${name}

Target Country:
UAE only
Keep Dubai and Abu Dhabi separate , like first all leads for dubai then for abu dhabi

Target Segments:
Manufacturing
Industrial
Facility Management
Hotels
F&B (Food & Beverage)
Aviation
Govt.
Real Estate
Engineering
Service
Publishing
Leisure
Dental
Construction
Chemicals
Internal

Important Exclusion:
Do NOT include Oil & Gas companies unless I specifically ask for them.

Your task:
Create a structured lead list in the same format as before, focused only on companies that are likely to need the selected service.

Find decision-makers responsible for facility maintenance, procurement, or engineering services:
Supply Chain Manager
Procurement Manager
Project Manager
Production Manager
Maintenance Head
Engineering Manager
Facility Manager
Purchase Manager
Maintenance Manager
Technical Buyer
Mechanical Engineer

Lead Selection Rules:
Choose only relevant UAE companies that are likely to require this service.
Prioritize companies where this service has a practical use case.
Working Area should clearly explain why the company is relevant for this service.
If exact email is not publicly available, use the best official public contact email where possible.
If no direct contact is available, still include search links so the company can be researched further.
Do not add random companies just to fill the list.
Do not include duplicate companies.
Keep industry classification practical and easy to understand.
Prioritize real target accounts over generic names.

Output Requirements:
Give results in a clean Excel-style table format.
Keep the format consistent across all companies.
If I ask for batches, split them into batches like Batch 1, Batch 2, Batch 3.
If I ask for all combined, merge all batches into one master sheet.
Make the data sales-ready and easy to use for outreach.

Working Area Instructions:
For the “Working Area” column, mention the operational reason the company may need the selected service.
Examples:
Manufacturing plant operations
HVAC and facility upkeep
Utility and maintenance operations
Industrial equipment support
Building services and MEP maintenance
Hospitality engineering operations
Production line support
Mechanical maintenance
Engineering and technical services

Special Intelligence Layer:
Before choosing companies, think about where the selected service is most commonly needed.
For example:
Compressor Maintenance / Repair → manufacturing, industrial, FM, F&B, hotels, aviation, construction, chemicals
Chiller / HVAC → hotels, FM, real estate, hospitals, malls, construction
DG Set Repair → facilities, construction, aviation, govt, engineering, industrial
Pump Repair → FM, utilities, manufacturing, construction, chemicals
Motor Rewinding → industrial plants, engineering, manufacturing, utilities
Crane Maintenance → construction, industrial, manufacturing, ports, engineering

Make sure the list matches the selected service, not just general companies.

Final instruction:
Generate 50-60 leads in this exact format for:
${type} - ${name}

For any areas missed out for packages not covered in my prompt
Give the leads

OUTPUT FORMAT (STRICT JSON):
Return a JSON object containing a "leads" array. Each object in the "leads" array MUST have the exact keys: name, title, company, email, phone, website, location, linkedIn, segment (e.g. Retail, Healthcare, Construction), priority (High, Medium, Low), channel (e.g. Distributor, End User, Wholesaler).`;

    const productDescription = description;
    const manualPrompt = `Act as a senior B2B Market Intelligence, Lead Generation, and Business Research Specialist.

Your objective is to identify REAL companies and VERIFIED decision-makers who are potential buyers, distributors, wholesalers, retailers, contractors, workshops, fleet operators, industrial users, project owners, or end users for the supplied product or service.

INPUTS

Division:
${division || "Not Specified"}

Product Name:
${productName}

Brand:
${brand || "Not Specified"}

Product Description:
${productDescription || "Not Specified"}

---

## PHASE 1 – PRODUCT ANALYSIS

First analyse the supplied information and determine:

• Industry
• Sub Industry
• Product Category
• Product Applications
• End Use Cases
• Relevant Market Segments
• Competitor Brands
• Product Synonyms
• Industry Keywords
• Alternative Search Terms

Use Division as additional context when available.

Examples:

CPD:
Consumer Products, Retail, FMCG, Batteries, Lighting

ISD:
Industrial Equipment, Compressors, Chillers, Generators, Pumps, Motors

Auto Division:
Automotive Parts, Lubricants, Workshops, Fleet Operators

TPC FZE:
Industrial Trading, Equipment Distribution, Project Supply

---

## PHASE 2 – BUYER IDENTIFICATION

Automatically determine the most relevant buyer types.

Possible buyer groups include:

• Distributors
• Wholesalers
• Retail Chains
• Supermarkets
• Trading Companies
• Contractors
• EPC Companies
• Facility Management Companies
• Manufacturing Plants
• Industrial Companies
• Oil & Gas Companies
• Utilities
• Workshops
• Fleet Operators
• Project Owners
• Government Organisations
• Hospitality Companies
• Healthcare Organisations
• End Users

Determine the most relevant buyer groups based on the supplied product information.

---

## PHASE 3 – DECISION MAKER IDENTIFICATION

Identify relevant decision makers such as:

• Procurement Manager
• Purchase Manager
• Category Manager
• Supply Chain Manager
• Operations Manager
• Engineering Manager
• Maintenance Manager
• Technical Manager
• Workshop Manager
• Fleet Manager
• Facility Manager
• Project Manager
• Business Development Manager
• General Manager
• Director
• CEO

Select only roles relevant to the product and buyer type.

---

## PHASE 4 – TARGET MARKET

Automatically target GCC countries:

• United Arab Emirates (UAE)
• Saudi Arabia
• Qatar
• Oman
• Kuwait
• Bahrain

---

## PHASE 5 – LEAD DISCOVERY

Prioritise data collection from:

1. Company Websites
2. Google Maps Business Listings
3. LinkedIn Company Pages
4. LinkedIn Professional Profiles
5. Trade Directories
6. Business Directories
7. Industry Associations
8. Distributor Networks
9. Manufacturer Partner Networks

---

## PHASE 6 – LEAD VERIFICATION

Only return companies that have at least one of:

• Website
• Phone Number
• Business Email
• WhatsApp Number
• LinkedIn Company Page
• Google Maps Listing

Prioritise companies that have:

• Website
• Business Email
• WhatsApp Number
• Decision Maker Information

Reject:

• Duplicate companies
• Fake contacts
• Unverified businesses
• Generic directory entries
• Placeholder data
• Invented information

Always provide complete, actual, and best-effort details:

• Do NOT use placeholders, masking, or generic templates (e.g., do NOT use "+971-4-XXX-XXXX" or "Not Available").
• Provide the actual, full name of the decision maker.
• Provide the actual, full working website of the company (e.g., "alfuttaim.com").
• Provide the actual, active phone number of the company office or decision maker (e.g., "+971-4-2551111").
• Provide the actual, direct LinkedIn profile URL of the decision maker (e.g., "linkedin.com/in/name").

---

## PHASE 7 – LEAD SCORING

Automatically classify each lead:

Segment:
• Distributor
• Wholesaler
• Retail
• Contractor
• Industrial
• Manufacturing
• Facility Management
• Government
• Healthcare
• Hospitality
• Enterprise
• End User
• Other

Priority:
• High
• Medium
• Low

Channel:
• Distributor
• Direct Customer
• Contractor
• Retail
• Project
• Service
• Workshop
• Fleet

---

## OUTPUT REQUIREMENTS

Return STRICT JSON only.

{
"industry": "",
"subIndustry": "",
"productCategory": "",
"buyerTypes": [],
"competitorBrands": [],
"searchKeywords": [],
"leads": [
{
"name": "",
"title": "",
"company": "",
"email": "",
"phone": "",
"website": "",
"location": "",
"linkedIn": "",
"segment": "",
"priority": "",
"channel": ""
}
]
}

Target 30–50 verified leads.

If fewer than 30 verified leads are available, return the maximum number of verifiable leads available.

Never invent data to reach the target count.`;

    const prompt = isDropdown ? dropdownPrompt : manualPrompt;

    try {
        const response = await anthropic.messages.create({
            model: "claude-haiku-4-5",
            max_tokens: 4096,
            system: "You are a helpful data-extraction assistant. You must extract and output data strictly in JSON format. Do not return any conversational text.",
            messages: [
                {
                    role: "user",
                    content: prompt,
                },
                {
                    role: "assistant",
                    content: "{"
                }
            ],
        });

        // Parse returned text block and prepend the open brace we fed to Claude
        let text = "";
        if (response.content[0].type === "text") {
            text = "{" + response.content[0].text;
        }

        if (!text) return [];

        // Parse the JSON object securely and extract the leads array
        let rawData;
        try {
            rawData = JSON.parse(text);
        } catch (e) {
            console.warn("JSON parsing failed, attempting to recover truncated JSON...", e);
            // Try to find the last complete object in the array to recover partial data
            const lastBraceIndex = text.lastIndexOf("}");
            if (lastBraceIndex !== -1) {
                const truncatedText = text.substring(0, lastBraceIndex + 1) + "]}";
                try {
                    rawData = JSON.parse(truncatedText);
                } catch (e2) {
                    console.error("Could not recover JSON:", e2);
                    return [];
                }
            } else {
                return [];
            }
        }

        let rawLeads: any[] = [];
        if (Array.isArray(rawData)) {
            rawLeads = rawData;
        } else if (rawData.leads && Array.isArray(rawData.leads)) {
            rawLeads = rawData.leads;
        } else {
            // Fallback: look for the first array in the JSON values
            const arrayValue = Object.values(rawData).find(val => Array.isArray(val));
            if (arrayValue) {
                rawLeads = arrayValue as any[];
            }
        }

        // Filter against existing PostgreSQL database leads to avoid duplicates
        try {
            const filterResponse = await fetch(`${API_BASE_URL}/api/filter-existing-leads`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ leads: rawLeads })
            });
            if (filterResponse.ok) {
                const filterData = await filterResponse.json();
                rawLeads = filterData.uniqueLeads;
            }
        } catch (dbError) {
            console.error("Could not filter against database", dbError);
        }

        return rawLeads.map((lead: any, index: number) => ({
            ...lead,
            srNo: index + 1,
        }));
    } catch (error) {
        console.error("Claude API Error:", error);
        throw error;
    }
}
