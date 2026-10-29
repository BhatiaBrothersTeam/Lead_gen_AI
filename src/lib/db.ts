import { Pool } from "pg";
import { ExtractedLead } from "./types";

// Create a pool using the DATABASE_URL environment variable
export const pool = new Pool({
  connectionString: process.env.DATABASE_URL || "postgres://postgres:root@localhost:5432/Lead_DB",
});

export interface SaveLeadsResult {
  totalFound: number;
  newLeadsAdded: number;
  existingLeadsUpdated: number;
  duplicatesSkipped: number;
  leads: any[];
}

/**
 * Saves a batch of leads to PostgreSQL, applying deduplication and updating missing fields.
 */
export async function saveOrUpdateLeads(leads: ExtractedLead[]): Promise<SaveLeadsResult> {
  let newLeadsAdded = 0;
  let existingLeadsUpdated = 0;
  let duplicatesSkipped = 0;
  const processedLeads: any[] = [];

  // Enforce table creation with EXACTLY the expected structure
  await pool.query(`
    CREATE TABLE IF NOT EXISTS public.leads (
        id SERIAL PRIMARY KEY,
        name text,
        title text,
        company text,
        email text,
        phone text,
        website text,
        location text,
        linkedin text,
        segment text,
        priority text,
        channel text,
        created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
        verified boolean DEFAULT true
    )
  `);

  for (const lead of leads) {
    const matchConditions: string[] = [];
    const params: any[] = [];

    // Formulate search conditions ignoring empty values
    if (lead.company && lead.company.trim() !== "") {
      params.push(lead.company.trim());
      matchConditions.push(`(company IS NOT NULL AND LOWER(company) = LOWER($${params.length}))`);
    }
    if (lead.email && lead.email.trim() !== "") {
      params.push(lead.email.trim());
      matchConditions.push(`(email IS NOT NULL AND LOWER(email) = LOWER($${params.length}))`);
    }
    if (lead.website && lead.website.trim() !== "") {
      params.push(lead.website.trim());
      matchConditions.push(`(website IS NOT NULL AND LOWER(website) = LOWER($${params.length}))`);
    }

    let existingRecord: any = null;
    if (matchConditions.length > 0) {
      const checkQuery = `SELECT * FROM public.leads WHERE ${matchConditions.join(" OR ")} LIMIT 1`;
      try {
        const { rows } = await pool.query(checkQuery, params);
        if (rows.length > 0) {
          existingRecord = rows[0];
        }
      } catch (err) {
        console.error("Error querying duplicate leads in database:", err);
      }
    }

    if (existingRecord) {
      // Duplicate lead found in database
      const fieldsToUpdate: { column: string; value: string }[] = [];
      
      // Fields we want to check and partially update
      const schemaFields = [
        { key: "name", col: "name" },
        { key: "title", col: "title" },
        { key: "company", col: "company" },
        { key: "email", col: "email" },
        { key: "phone", col: "phone" },
        { key: "website", col: "website" },
        { key: "location", col: "location" },
        { key: "linkedIn", col: "linkedin" }, // mapped from linkedIn property to linkedin column
        { key: "segment", col: "segment" },
        { key: "priority", col: "priority" },
        { key: "channel", col: "channel" },
      ];

      for (const field of schemaFields) {
        const dbValue = existingRecord[field.col];
        const inputValue = (lead as any)[field.key] || (lead as any)[field.col];

        // If database value is currently empty/null, but input has a value, schedule a partial update
        if (
          (dbValue === null || dbValue === undefined || dbValue.toString().trim() === "") &&
          inputValue &&
          inputValue.trim() !== ""
        ) {
          fieldsToUpdate.push({ column: field.col, value: inputValue.trim() });
        }
      }

      if (fieldsToUpdate.length > 0) {
        // Build dynamic UPDATE query
        const setClauses = fieldsToUpdate.map((f, idx) => `${f.column} = $${idx + 2}`);
        const updateParams = [existingRecord.id, ...fieldsToUpdate.map((f) => f.value)];
        const updateQuery = `UPDATE public.leads SET ${setClauses.join(", ")} WHERE id = $1 RETURNING *`;
        
        try {
          const { rows } = await pool.query(updateQuery, updateParams);
          existingLeadsUpdated++;
          processedLeads.push(rows[0]);
        } catch (updateErr) {
          console.error(`Error partially updating lead ID ${existingRecord.id}:`, updateErr);
          processedLeads.push(existingRecord); // Fallback to unmodified record
        }
      } else {
        duplicatesSkipped++;
        processedLeads.push(existingRecord);
      }
    } else {
      // No duplicate exists, insert new lead
      const insertQuery = `
        INSERT INTO public.leads (name, title, company, email, phone, website, location, linkedin, segment, priority, channel, verified)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, true)
        RETURNING *
      `;
      try {
        const { rows } = await pool.query(insertQuery, [
          lead.name || "",
          lead.title || "",
          lead.company || "",
          lead.email || "",
          lead.phone || "",
          lead.website || "",
          lead.location || "",
          lead.linkedIn || "",
          lead.segment || "",
          lead.priority || "",
          lead.channel || "",
        ]);
        newLeadsAdded++;
        processedLeads.push(rows[0]);
      } catch (insertErr) {
        console.error(`Error inserting new lead:`, insertErr);
      }
    }
  }

  return {
    totalFound: leads.length,
    newLeadsAdded,
    existingLeadsUpdated,
    duplicatesSkipped,
    leads: processedLeads,
  };
}
