import { Groq } from "groq-sdk";

// Initialize Groq client using the key from process.env
const groq = new Groq({
  apiKey: process.env.GROQ_API_KEY || "",
  dangerouslyAllowBrowser: true
});

export interface ProductAnalysisInput {
  division: string;
  productName: string;
  brand?: string;
  description?: string;
}

export interface ProductAnalysisResult {
  industry: string;
  subIndustry: string;
  productCategory: string;
  buyerTypes: string[];
  competitorBrands: string[];
  competitors: string[]; // Aligned with the example JSON
  searchKeywords: string[];
  keywords: string[]; // Aligned with the example JSON
  alternativeSearchTerms: string[];
}

/**
 * Analyzes the product input using Claude to identify industries, buyer types, competitors, and keywords.
 */
export async function analyzeProduct(input: ProductAnalysisInput): Promise<ProductAnalysisResult> {
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) {
    throw new Error("GROQ_API_KEY is not defined in the environment.");
  }

  const prompt = `Act as an expert B2B product researcher and market analyst specializing in the Middle East / GCC market.
Analyze the following product/service details to help us find high-quality sales leads:

- Division: ${input.division || "Not Specified"}
- Product Name: ${input.productName}
- Brand: ${input.brand || "Not Specified"}
- Description: ${input.description || "Not Specified"}

Based on this information, determine the following:
1. Industry (e.g. Automotive Chemicals, Industrial Equipment)
2. Sub Industry
3. Product Category
4. Buyer Types (e.g. workshops, fleet companies, auto parts distributors)
5. Competitor Brands (e.g. STP, Liqui Moly)
6. Search Keywords (specific search terms to find suppliers, distributors, wholesalers, or buyers of this product type in UAE/GCC, e.g. "fuel additive distributor UAE", "octane booster supplier Dubai")
7. Alternative Search Terms (e.g. "automotive chemical wholesaler GCC")

You MUST return the output strictly as a JSON object matching the format below.
Do not include any wrapper (like markdown code blocks \`\`\`json), comments, or introductory text. Return ONLY the raw JSON string.

JSON format:
{
  "industry": "Industry name",
  "subIndustry": "Sub Industry name",
  "productCategory": "Product Category name",
  "buyerTypes": ["Buyer Type 1", "Buyer Type 2"],
  "competitorBrands": ["Brand 1", "Brand 2"],
  "competitors": ["Brand 1", "Brand 2"],
  "searchKeywords": ["Keyword 1", "Keyword 2"],
  "keywords": ["Keyword 1", "Keyword 2"],
  "alternativeSearchTerms": ["Alternative Term 1", "Alternative Term 2"]
}`;

  try {
    const response = await groq.chat.completions.create({
      model: "llama-3.3-70b-versatile",
      messages: [
        {
          role: "system",
          content: "You are a precise B2B market intelligence data extraction assistant. You only output valid raw JSON."
        },
        {
          role: "user",
          content: prompt,
        },
      ],
      response_format: { type: "json_object" },
    });

    let text = response.choices[0]?.message?.content?.trim() || "";
    if (!text) {
      throw new Error("Empty response from Anthropic Claude API");
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

    // Parse the JSON output
    const parsed: ProductAnalysisResult = JSON.parse(text);
    return parsed;
  } catch (error) {
    console.error("Error in product analyzer:", error);
    throw error;
  }
}
