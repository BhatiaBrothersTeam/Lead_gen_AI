"""
Excel / CSV handling (ported from LeadMatch, same workbook formats):

* Catalogue workbook: sheets "Divisions" and "Products_Services" (LeadMatch's
  master catalogue template, also what scripts/sync_vvsons_catalogue.py --out
  writes). Re-importing upserts: insert new, update changed, skip unchanged.
* Outbound prospects: Excel or CSV with Company_Name (required), Country,
  Website, Industry, City, Business_Email, Business_Phone, Contact_Person ...
"""
from __future__ import annotations

import csv
import io

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .db import new_id, row, t
from .utils import normalize_name, sanitize_excel_value

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(color="FFFFFF", bold=True)
REQUIRED_FILL = PatternFill("solid", fgColor="F4C430")
SAMPLE_FILL = PatternFill("solid", fgColor="E8F0FE")

OUTBOUND_HEADERS = [
    "Company_Name", "Country", "Website", "Industry", "Sub_Industry", "City", "State", "Business_Email",
    "Business_Phone", "WhatsApp_Number", "Contact_Person", "Designation", "Company_Description", "Source", "Notes",
]
DIVISION_HEADERS = ["Division_Name", "Division_Description", "Target_Countries", "Active"]
PRODUCT_HEADERS = [
    "Division_Name", "Product_Service_Name", "Category", "Description", "Applications", "Target_Industries",
    "Ideal_Buyer_Types", "Specifications_or_Capabilities", "Complementary_Products", "Service_Area",
    "Exclusions_or_Not_Suitable_For", "Product_URL", "Image_URL", "Active", "SKU",
]
PRODUCT_COLUMNS = {
    "category": "Category",
    "description": "Description",
    "applications": "Applications",
    "target_industries": "Target_Industries",
    "ideal_buyer_types": "Ideal_Buyer_Types",
    "specifications": "Specifications_or_Capabilities",
    "complementary_products": "Complementary_Products",
    "service_area": "Service_Area",
    "exclusions": "Exclusions_or_Not_Suitable_For",
    "product_url": "Product_URL",
    "image_url": "Image_URL",
    "sku": "SKU",
}
# Headers people commonly use instead of the template's.
OUTBOUND_ALIASES = {
    "company": "Company_Name", "company_name": "Company_Name", "name": "Company_Name", "business_name": "Company_Name",
    "country": "Country", "website": "Website", "url": "Website", "web": "Website", "industry": "Industry",
    "sub_industry": "Sub_Industry", "city": "City", "emirate": "City", "state": "State",
    "email": "Business_Email", "business_email": "Business_Email", "phone": "Business_Phone",
    "business_phone": "Business_Phone", "mobile": "Business_Phone", "whatsapp": "WhatsApp_Number",
    "whatsapp_number": "WhatsApp_Number", "contact": "Contact_Person", "contact_person": "Contact_Person",
    "contact_name": "Contact_Person", "designation": "Designation", "title": "Designation",
    "description": "Company_Description", "company_description": "Company_Description", "source": "Source",
    "notes": "Notes",
}


def _style_header(ws, headers, required):
    for idx, name in enumerate(headers, 1):
        cell = ws.cell(1, idx, name)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
        if name in required:
            cell.fill, cell.font = REQUIRED_FILL, Font(color="000000", bold=True)
        ws.column_dimensions[get_column_letter(idx)].width = max(18, len(name) + 4)


def _save(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_outbound_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Companies"
    _style_header(ws, OUTBOUND_HEADERS, {"Company_Name"})
    sample = [
        "Acme Auto Services LLC", "United Arab Emirates", "https://example-auto.invalid", "Automotive workshops", "",
        "Dubai", "", "purchase@example-auto.invalid", "+971500000000", "+971500000000", "Ravi Kumar",
        "Purchase Manager", "Multi-brand car service centre with 12 bays", "Trade directory", "",
    ]
    for c, val in enumerate(sample, 1):
        ws.cell(2, c, val).fill = SAMPLE_FILL
    notes = wb.create_sheet("Instructions")
    notes["A1"] = "Outbound prospects upload - Lead Matchmaker"
    notes["A3"] = "Only Company_Name is mandatory (yellow). Country defaults to the module's default country."
    notes["A4"] = "Website or a business email makes the analysis much better; without them the company is looked up by name."
    notes["A5"] = "Rows already in the system are matched to the existing company instead of creating duplicates."
    notes["A6"] = "Do not include personal data obtained in violation of privacy laws."
    notes.column_dimensions["A"].width = 110
    return _save(wb)


def build_catalogue_template() -> bytes:
    wb = Workbook()
    info = wb.active
    info.title = "Instructions"
    info["A1"] = "Lead Matchmaker - Product Catalogue Workbook"
    info["A1"].font = Font(size=16, bold=True)
    for i, line in enumerate([
        "Sheets 'Divisions' and 'Products_Services' are required. Yellow columns are required.",
        "Division_Name on Products_Services must match a row in Divisions (or an existing division).",
        "Re-uploading upserts: insert new lines, update changed ones, skip unchanged.",
        "Active accepts Yes/No. Set No to stop suggesting a line without deleting it.",
        "Target_Industries and Applications drive matching: list buyer industries and uses, comma-separated.",
    ], 3):
        info[f"A{i}"] = line
    info.column_dimensions["A"].width = 110
    ws1 = wb.create_sheet("Divisions")
    _style_header(ws1, DIVISION_HEADERS, {"Division_Name"})
    for c, v in enumerate(["Lighting", "Professional and automotive lighting", "United Arab Emirates", "Yes"], 1):
        ws1.cell(2, c, v).fill = SAMPLE_FILL
    ws2 = wb.create_sheet("Products_Services")
    _style_header(ws2, PRODUCT_HEADERS, {"Division_Name", "Product_Service_Name"})
    sample = [
        "Lighting", "LED High Bay Lighting", "Lighting", "High bay luminaires from OSRAM. Examples: ...",
        "Warehouse lighting, Workshop lighting", "Warehouses, Logistics, Manufacturing, Workshops",
        "Facility managers, MEP contractors", "", "Emergency lighting", "United Arab Emirates", "Residential decor",
        "", "", "Yes", "",
    ]
    for c, v in enumerate(sample, 1):
        ws2.cell(2, c, v).fill = SAMPLE_FILL
    return _save(wb)


def _row_dict(headers, values):
    return {h: (sanitize_excel_value(values[i]) if i < len(values) else None) for i, h in enumerate(headers)}


def parse_workbook(content: bytes) -> dict[str, list[dict]]:
    wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    sheets: dict[str, list[dict]] = {}
    for ws in wb.worksheets:
        data = list(ws.iter_rows(values_only=True))
        sheets[ws.title] = []
        if not data:
            continue
        headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(data[0])]
        for values in data[1:]:
            if not values or all(v is None or str(v).strip() == "" for v in values):
                continue
            sheets[ws.title].append(_row_dict(headers, list(values)))
    return sheets


def _canonical_outbound(row_in: dict) -> dict:
    out = {}
    for key, value in row_in.items():
        k = str(key).strip()
        canon = k if k in OUTBOUND_HEADERS else OUTBOUND_ALIASES.get(k.lower().replace(" ", "_").replace("-", "_"))
        if canon and value not in (None, "") and not out.get(canon):
            out[canon] = str(value).strip()
    return out


def parse_outbound_file(content: bytes, filename: str) -> list[dict]:
    if filename.lower().endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        raw = [{k: sanitize_excel_value(v) for k, v in r.items() if k} for r in csv.DictReader(io.StringIO(text))]
    else:
        sheets = parse_workbook(content)
        # The sheet whose header has a company-name column (skips an "Instructions" sheet).
        raw = next(
            (v for v in sheets.values() if v and any(_canonical_outbound({k: "x"}).get("Company_Name") for k in v[0])),
            [],
        )
    return [_canonical_outbound(r) for r in raw]


def _as_bool(value) -> bool:
    if value is None or value == "":
        return True
    return str(value).strip().lower() in {"yes", "y", "true", "1", "active"}


async def import_catalogue(conn, content: bytes) -> dict:
    """Upsert divisions and product lines from a catalogue workbook. Runs in the caller's transaction."""
    sheets = parse_workbook(content)
    if "Products_Services" not in sheets and "Divisions" not in sheets:
        raise ValueError("The workbook needs a 'Divisions' and a 'Products_Services' sheet (download the template).")
    summary = {
        "divisions": {"inserted": 0, "updated": 0, "skipped": 0},
        "products": {"inserted": 0, "updated": 0, "skipped": 0},
        "errors": [],
    }
    divisions: dict[str, dict] = {
        r["name_normalized"]: dict(r) for r in await conn.fetch(f"SELECT * FROM {t('divisions')}")
    }
    for i, r in enumerate(sheets.get("Divisions", []), 2):
        name = r.get("Division_Name")
        if not name:
            summary["errors"].append(f"Divisions row {i}: Division_Name is missing")
            continue
        nname = normalize_name(name)
        desc, countries, active = r.get("Division_Description"), r.get("Target_Countries"), _as_bool(r.get("Active"))
        existing = divisions.get(nname)
        if existing:
            if (desc and desc != existing["description"]) or (countries and countries != existing["target_countries"]) or existing["is_active"] != active:
                updated = await conn.fetchrow(
                    f"""UPDATE {t('divisions')} SET description = COALESCE($2, description),
                        target_countries = COALESCE($3, target_countries), is_active = $4, updated_at = now()
                        WHERE id = $1 RETURNING *""",
                    existing["id"], desc, countries, active,
                )
                divisions[nname] = dict(updated)
                summary["divisions"]["updated"] += 1
            else:
                summary["divisions"]["skipped"] += 1
        else:
            created = await conn.fetchrow(
                f"""INSERT INTO {t('divisions')} (id, name, name_normalized, description, target_countries, is_active)
                    VALUES ($1,$2,$3,$4,$5,$6) RETURNING *""",
                new_id("DIV"), name.strip(), nname, desc, countries, active,
            )
            divisions[nname] = dict(created)
            summary["divisions"]["inserted"] += 1

    for i, r in enumerate(sheets.get("Products_Services", []), 2):
        dname, pname = r.get("Division_Name"), r.get("Product_Service_Name")
        if not dname or not pname:
            summary["errors"].append(f"Products_Services row {i}: Division_Name and Product_Service_Name are required")
            continue
        div = divisions.get(normalize_name(dname))
        if not div:
            summary["errors"].append(f"Products_Services row {i}: unknown division '{dname}'")
            continue
        nprod = normalize_name(pname)
        fields = {col: r.get(header) for col, header in PRODUCT_COLUMNS.items()}
        active = _as_bool(r.get("Active"))
        existing = row(await conn.fetchrow(
            f"SELECT * FROM {t('products')} WHERE division_id = $1 AND name_normalized = $2", div["id"], nprod
        ))
        if existing:
            changes = {k: v for k, v in fields.items() if v not in (None, "") and v != existing.get(k)}
            if existing.is_active != active:
                changes["is_active"] = active
            if changes:
                sets = ", ".join(f"{k} = ${n + 2}" for n, k in enumerate(changes))
                await conn.execute(f"UPDATE {t('products')} SET {sets}, updated_at = now() WHERE id = $1", existing.id, *changes.values())
                summary["products"]["updated"] += 1
            else:
                summary["products"]["skipped"] += 1
        else:
            cols = ["id", "division_id", "name", "name_normalized", "is_active", *fields.keys()]
            await conn.execute(
                f"INSERT INTO {t('products')} ({', '.join(cols)}) VALUES ({', '.join(f'${n + 1}' for n in range(len(cols)))})",
                new_id("PRD"), div["id"], pname.strip(), nprod, active, *fields.values(),
            )
            summary["products"]["inserted"] += 1
    return summary
