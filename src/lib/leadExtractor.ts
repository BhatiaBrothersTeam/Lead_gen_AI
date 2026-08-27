import { Groq } from "groq-sdk";
import { SearchResult } from "./searchService";

const groq = new Groq({
  apiKey: process.env.GROQ_API_KEY || "",
  dangerouslyAllowBrowser: true
});

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

/**
 * Sends search results to Claude to extract B2B leads based STRICTLY on the search data.
 */
export async function extractLeads(searchResults: SearchResult[]): Promise<ExtractedLead[]> {
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) {
    throw new Error("GROQ_API_KEY is not defined in the environment.");
  }

  if (searchResults.length === 0) {
    return [];
  }

  // Format search results to send to Claude
  const formattedResults = searchResults
    .map((res, index) => {
      return `[Search Result #${index + 1}]
Title: ${res.title}
URL: ${res.url}
Snippet: ${res.snippet}`;
    })
    .join("\n\n");

  const prompt = `Act as an expert B2B lead generation specialist and data miner.
Extract real business contacts and companies from the following search results.

---
SEARCH RESULTS:
${formattedResults}
---

CRITICAL REQUIREMENTS:
1. ONLY extract information that is explicitly present or directly mentioned in the search results text above.
2. DO NOT invent, hallucinate, or generate any leads from your memory.
3. If a field (e.g. email, phone, name, title, linkedIn) is not found in the search results, set it to an empty string "". Do not use placeholders like "N/A", "Unknown", "Not Available", or generic templates like "xxx".
4. The "website" field MUST be the actual domain name of the company derived from the search result URL or snippet (e.g. "alghanim.com").
5. Based on the business details, classify each lead into the following classifications:
   - segment: MUST be one of: "Distributor", "Wholesaler", "Retail", "Contractor", "Industrial", "Manufacturing", "Facility Management", "Government", "Healthcare", "Hospitality", "Enterprise", "End User", "Other".
   - priority: MUST be one of: "High", "Medium", "Low". (High if the company is highly relevant and has contacts, Low if fit is general).
   - channel: MUST be one of: "Distributor", "Direct Customer", "Contractor", "Retail", "Project", "Service", "Workshop", "Fleet".
6. Return the response STRICTLY as a JSON object containing a "leads" array.

You MUST return the output strictly as a JSON object matching the format below.
Do not include any wrapper (like markdown code blocks \`\`\`json), comments, or introductory text. Return ONLY the raw JSON string.

JSON Output Format:
{
  "leads": [
    {
      "company": "Company Name",
      "name": "Decision Maker/Contact Person Name (or empty string if not found)",
      "title": "Job Title (or empty string if not found)",
      "email": "Email Address (or empty string if not found)",
      "phone": "Phone Number (or empty string if not found)",
      "website": "Company Website URL or Domain (must be present)",
      "linkedIn": "LinkedIn Profile URL or Company Page URL (or empty string if not found)",
      "location": "City/Region, Country (e.g. Dubai, UAE)",
      "segment": "Segment Category",
      "priority": "Priority Level",
      "channel": "Channel Category"
    }
  ]
}`;

  const modelName = process.env.GROQ_MODEL || "openai/gpt-oss-20b";

  try {
    const response = await groq.chat.completions.create({
      model: modelName,
      messages: [
        {
          role: "system",
          content: "You are a precise data-extraction assistant. You only output valid JSON based strictly on the provided context."
        },
        {
          role: "user",
          content: prompt,
        },
      ],
      response_format: { type: "json_object" },
      max_tokens: 4096
    });

    let text = response.choices[0]?.message?.content?.trim() || "";
    if (!text) {
      return [];
    }

    // Strip markdown code block wrappers if present
    if (text.startsWith("```json")) {
      text = text.substring(7);
    } else if (text.startsWith("```")) {
      text = text.substring(3);
    }
    if (text.endsWith("```")) {
      text = text.substring(0, text.length - 3);
    }
    text = text.trim();

    const parsed = JSON.parse(text);
    if (parsed.leads && Array.isArray(parsed.leads)) {
      return parsed.leads;
    }
    
    return [];
  } catch (error) {
    console.error("Error extracting leads using Claude:", error);
    throw error;
  }
}
