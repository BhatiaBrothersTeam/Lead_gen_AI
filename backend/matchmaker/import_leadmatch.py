"""
Copy the product catalogue from a standalone LeadMatch Maker database into the
Lead Gen Agent's Lead Matchmaker module. Safe to re-run: divisions and lines
are matched by name and updated, never duplicated.

    .\\venv\\Scripts\\python.exe -m backend.matchmaker.import_leadmatch --sqlite C:\\Lead_Matchmaker\\backend\\leadmatch.db

Only active divisions are copied unless --include-inactive is given. Uses
DATABASE_URL from .env / .env.local, like the API.
"""
from __future__ import annotations

import argparse
import asyncio
import sqlite3

from dotenv import load_dotenv

PRODUCT_COLUMNS = (
    "sku", "category", "description", "applications", "target_industries", "ideal_buyer_types", "specifications",
    "complementary_products", "service_area", "exclusions", "product_url", "image_url",
)


async def run(sqlite_path: str, include_inactive: bool) -> dict:
    import os

    from backend.database.connection import close_db_pool, init_db_pool

    from .db import initialize_matchmaker_tables, new_id, t

    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    divisions = src.execute(
        "SELECT * FROM divisions" + ("" if include_inactive else " WHERE is_active = 1")
    ).fetchall()
    summary = {"divisions": 0, "products_inserted": 0, "products_updated": 0}
    await init_db_pool(os.getenv("DATABASE_URL"))
    try:
        await initialize_matchmaker_tables()
        from backend.database.connection import get_pool

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                for d in divisions:
                    div_id = await conn.fetchval(
                        f"""INSERT INTO {t('divisions')} (id, name, name_normalized, description, target_countries, is_active)
                            VALUES ($1,$2,$3,$4,$5,$6)
                            ON CONFLICT (name_normalized) DO UPDATE SET description = EXCLUDED.description,
                                target_countries = EXCLUDED.target_countries, is_active = EXCLUDED.is_active, updated_at = now()
                            RETURNING id""",
                        new_id("DIV"), d["name"], d["name_normalized"], d["description"], d["target_countries"], bool(d["is_active"]),
                    )
                    summary["divisions"] += 1
                    for p in src.execute("SELECT * FROM products_services WHERE division_id = ?", (d["id"],)).fetchall():
                        values = [p[c] for c in PRODUCT_COLUMNS]
                        existing = await conn.fetchval(
                            f"SELECT id FROM {t('products')} WHERE division_id = $1 AND name_normalized = $2", div_id, p["name_normalized"]
                        )
                        if existing:
                            sets = ", ".join(f"{c} = ${i + 3}" for i, c in enumerate(PRODUCT_COLUMNS))
                            await conn.execute(
                                f"UPDATE {t('products')} SET {sets}, is_active = $2, updated_at = now() WHERE id = $1",
                                existing, bool(p["is_active"]), *values,
                            )
                            summary["products_updated"] += 1
                        else:
                            cols = ["id", "division_id", "name", "name_normalized", "is_active", *PRODUCT_COLUMNS]
                            await conn.execute(
                                f"INSERT INTO {t('products')} ({', '.join(cols)}) VALUES ({', '.join(f'${i + 1}' for i in range(len(cols)))})",
                                new_id("PRD"), div_id, p["name"], p["name_normalized"], bool(p["is_active"]), *values,
                            )
                            summary["products_inserted"] += 1
    finally:
        await close_db_pool()
        src.close()
    return summary


def main() -> None:
    load_dotenv()
    load_dotenv(".env.local", override=True)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sqlite", required=True, help="Path to LeadMatch's leadmatch.db")
    parser.add_argument("--include-inactive", action="store_true", help="Also copy inactive divisions")
    args = parser.parse_args()
    print(asyncio.run(run(args.sqlite, args.include_inactive)))


if __name__ == "__main__":
    main()
