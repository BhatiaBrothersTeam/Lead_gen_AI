import { Groq } from "groq-sdk";
import { SerperSearchProvider } from "./searchService";
import { ExtractedLead } from "./leadExtractor";

/**
 * Enriches a list of leads by searching for missing contact info.
 */
export async function enrichLeads(
  leads: ExtractedLead[],
  progressCallback?: (msg: string) => void
): Promise<ExtractedLead[]> {
  const apiKey = process.env.GROQ_API_KEY;
  const serperKey = process.env.SERPER_API_KEY;

  if (!apiKey || !serperKey) {
    console.warn("GROQ_API_KEY or SERPER_API_KEY environment variable is not defined. Skipping lead enrichment.");
    return leads;
  }

  const searchProvider = new SerperSearchProvider(serperKey);
  const groq = new Groq({ apiKey, dangerouslyAllowBrowser: true });

  const enrichedLeads: ExtractedLead[] = [];
  const batchSize = 3; // Keep batch size small to avoid overloading rate limits and stay highly responsive

  for (let i = 0; i < leads.length; i += batchSize) {
    const batch = leads.slice(i, i + batchSize);
    const progressMsg = `Enriching contact info for companies ${i + 1} to ${Math.min(i + batchSize, leads.length)} of ${leads.length}...`;
    console.log(progressMsg);
    progressCallback?.(progressMsg);

    const enrichmentPromises = batch.map(async (lead) => {
      // Check if we actually need enrichment
      const hasEmail = lead.email && lead.email.trim() !== "";
      const hasPhone = lead.phone && lead.phone.trim() !== "";
      const hasName = lead.name && lead.name.trim() !== "";
      const hasLinkedIn = lead.linkedIn && lead.linkedIn.trim() !== "";

      const needsEnrichment = !hasEmail || !hasPhone || !hasName || !hasLinkedIn;
      if (!needsEnrichment) {
        return lead;
      }

      try {
        // Build search query targeting company's contact and LinkedIn profiles
        const cleanWebsite = lead.website ? lead.website.replace(/^(https?:\/\/)?(www\.)?/, "").split("/")[0] : "";
        const siteFilter = cleanWebsite ? `site:${cleanWebsite} OR ` : "";
        const query = `"${lead.company}" ${siteFilter}contact email phone procurement linkedin`;

        console.log(`Enriching "${lead.company}" using query: ${query}`);
        const results = await searchProvider.search(query);

        if (results.length === 0) {
          console.log(`No search results found for "${lead.company}" contact info.`);
          return lead;
        }

        const formattedResults = results
          .map((res, index) => `[Result #${index + 1}]\nTitle: ${res.title}\nURL: ${res.url}\nSnippet: ${res.snippet}`)
          .join("\n\n");

        const prompt = `Act as an expert B2B lead researcher.
We need to enrich contact details for the company: "${lead.company}" (Website: "${lead.website || "N/A"}").
Below are search results from Google containing contact and decision maker info for this company.

SEARCH RESULTS:
${formattedResults}

Based ON THE SEARCH RESULTS ABOVE, extract the missing contact information.
CRITICAL REQUIREMENTS:
1. ONLY extract information that is explicitly present or directly mentioned in the search results text above.
2. DO NOT invent, hallucinate, or generate any details (e.g. do not guess emails or linkedin URLs).
3. If a field is not found in the text, set it to an empty string "". Do not use placeholders like "N/A", "Unknown", or templates.
4. For "email", look for a corporate email address (like purchasing@company.com, info@company.com, contact@company.com, sales@company.com etc.).
5. For "phone", extract the phone number, prioritizing GCC numbers (+971 for UAE, +966 for KSA, +974 for Qatar, etc.).
6. For "name" and "title", look for a contact person, preferably a procurement manager, purchasing manager, supply chain manager, general manager, owner, or other decision-makers.
7. For "linkedIn", look for the LinkedIn profile URL of the contact person or the company LinkedIn page URL.

Return the response STRICTLY as a JSON object matching the format below. Do not include any wrapper or comments.

JSON Output Format:
{
  "name": "Contact Name or empty string",
  "title": "Contact Job Title or empty string",
  "email": "Contact Email or empty string",
  "phone": "Contact Phone or empty string",
  "linkedIn": "LinkedIn URL or empty string"
}
`;

        const modelName = process.env.GROQ_MODEL || "llama-3.3-70b-versatile";

        const response = await groq.chat.completions.create({
          model: modelName,
          messages: [
            {
              role: "system",
              content: "You are a precise data-enrichment assistant. You only output valid JSON based strictly on the provided context."
            },
            {
              role: "user",
              content: prompt,
            },
          ],
          response_format: { type: "json_object" },
        });

        let text = response.choices[0]?.message?.content?.trim() || "";
        if (!text) return lead;

        // Strip markdown code block wrappers
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

        const updatedLead = {
          ...lead,
          name: lead.name && lead.name.trim() !== "" ? lead.name : (parsed.name || ""),
          title: lead.title && lead.title.trim() !== "" ? lead.title : (parsed.title || ""),
          email: lead.email && lead.email.trim() !== "" ? lead.email : (parsed.email || ""),
          phone: lead.phone && lead.phone.trim() !== "" ? lead.phone : (parsed.phone || ""),
          linkedIn: lead.linkedIn && lead.linkedIn.trim() !== "" ? lead.linkedIn : (parsed.linkedIn || ""),
        };

        console.log(`Enriched lead for "${lead.company}":`, {
          name: updatedLead.name,
          title: updatedLead.title,
          email: updatedLead.email,
          phone: updatedLead.phone,
          linkedIn: updatedLead.linkedIn,
        });

        return updatedLead;
      } catch (err) {
        console.error(`Error enriching lead for "${lead.company}":`, err);
        return lead;
      }
    });

    const enrichedBatch = await Promise.all(enrichmentPromises);
    enrichedLeads.push(...enrichedBatch);
  }

  return enrichedLeads;
}
