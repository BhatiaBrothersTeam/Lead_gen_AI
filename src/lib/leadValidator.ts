import { ExtractedLead } from "./types";

/**
 * Validates a batch of extracted leads based on rules.
 * Rejects invalid leads and returns only the clean leads.
 */
export function validateLeads(leads: ExtractedLead[]): ExtractedLead[] {
  const seenCompanies = new Set<string>();
  const validatedLeads: ExtractedLead[] = [];

  for (const lead of leads) {
    // 1. Company name missing
    if (!lead.company || lead.company.trim() === "") {
      console.log(`Lead Validation: Rejected lead (Company Name missing)`);
      continue;
    }

    // 2. Website missing
    if (!lead.website || lead.website.trim() === "") {
      console.log(`Lead Validation: Rejected lead for "${lead.company}" (Website missing)`);
      continue;
    }

    // 3. Reject duplicate companies in the current batch (case-insensitive)
    const companyKey = lead.company.trim().toLowerCase();
    if (seenCompanies.has(companyKey)) {
      console.log(`Lead Validation: Rejected lead for "${lead.company}" (Duplicate company in current batch)`);
      continue;
    }

    // Check placeholder company name
    const companyLower = lead.company.toLowerCase();
    if (
      companyLower.includes("placeholder") ||
      companyLower.includes("unknown") ||
      companyLower.includes("test company") ||
      companyLower.includes("dummy") ||
      companyLower.trim() === "n/a"
    ) {
      console.log(`Lead Validation: Rejected lead for "${lead.company}" (Placeholder company name)`);
      continue;
    }

    // 4. Invalid domain check
    let domain = lead.website.trim().toLowerCase();
    // Normalize domain by stripping protocols and subdomains if necessary
    domain = domain.replace(/^(https?:\/\/)?(www\.)?/, "");
    // Remove query params and paths
    domain = domain.split("/")[0];

    if (
      !domain.includes(".") ||
      domain.startsWith(".") ||
      domain.endsWith(".") ||
      domain.includes(" ") ||
      domain.length < 4
    ) {
      console.log(`Lead Validation: Rejected lead for "${lead.company}" (Invalid domain "${lead.website}")`);
      continue;
    }

    // Check placeholder website
    const websiteLower = lead.website.toLowerCase();
    if (
      websiteLower.includes("example.com") ||
      websiteLower.includes("test.com") ||
      websiteLower.includes("sample.com") ||
      websiteLower.includes("dummy.com") ||
      websiteLower.includes("placeholder")
    ) {
      console.log(`Lead Validation: Rejected lead for "${lead.company}" (Placeholder website "${lead.website}")`);
      continue;
    }

    // Reject emails containing: example.com, test.com, sample.com, dummy.com, or placeholder values
    if (lead.email) {
      const emailLower = lead.email.trim().toLowerCase();
      if (
        emailLower.includes("example.com") ||
        emailLower.includes("test.com") ||
        emailLower.includes("sample.com") ||
        emailLower.includes("dummy.com") ||
        emailLower.includes("placeholder") ||
        emailLower.includes("email@") ||
        emailLower.includes("xxx") ||
        emailLower === "n/a"
      ) {
        // Clear invalid email instead of rejecting the whole lead
        lead.email = "";
      }
    }

    // Clean optional fields containing placeholder strings
    if (lead.phone) {
      const phoneLower = lead.phone.trim().toLowerCase();
      if (
        phoneLower.includes("xxx") ||
        phoneLower.includes("placeholder") ||
        phoneLower.includes("12345") ||
        phoneLower.includes("000000") ||
        phoneLower === "n/a"
      ) {
        lead.phone = "";
      }
    }

    if (lead.linkedIn) {
      const liLower = lead.linkedIn.trim().toLowerCase();
      if (
        liLower.includes("placeholder") ||
        liLower.includes("linkedin.com/in/xxx") ||
        liLower.includes("linkedin.com/company/xxx") ||
        liLower === "n/a"
      ) {
        lead.linkedIn = "";
      }
    }

    // 5. Only save leads that have at least one: Website, Phone Number, Business Email, LinkedIn Company Page
    // Since website is validated as required above, this will always be true. We enforce it explicitly.
    const hasContactChannel = !!(
      (lead.website && lead.website.trim() !== "") ||
      (lead.phone && lead.phone.trim() !== "") ||
      (lead.email && lead.email.trim() !== "") ||
      (lead.linkedIn && lead.linkedIn.trim() !== "")
    );

    if (!hasContactChannel) {
      console.log(`Lead Validation: Rejected lead for "${lead.company}" (No valid contact channels)`);
      continue;
    }

    seenCompanies.add(companyKey);
    validatedLeads.push(lead);
  }

  return validatedLeads;
}
