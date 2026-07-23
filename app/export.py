"""Export the session's readings and PUTS observations to Parquet and CSV.

Both readings and puts_observations are written from the same style of
query so a focus group leaves behind one dataset either university can
open in the tool of its choice. See design spec section 7 and section 10.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from app.observations import initialise_schema as initialise_puts_schema
from app.storage.db import CONNECTION_LOCK

# Design spec section 8.4, transcribed verbatim so the exported dataset
# always travels with the caveat explaining what the probe's nitrogen,
# phosphorus and potassium columns actually are. Keep this in step with
# the spec document if that section is ever revised.
NUTRIENT_CAVEAT = """SawahPintar export - read this before using the nutrient columns

Why the probe's nutrient outputs are not calibrated (design spec section 8.4)

The probe must not have its nitrogen, phosphorus and potassium outputs
calibrated against PUTS or against anything else. The reason is
structural, and three independent lines of evidence agree.

The manufacturer's own documentation states that when registers 0x0004,
0x0005 and 0x0006 have not been written, they hold f1, f2 and f3,
described as conductivity measurement values. The three nutrient outputs
are three functions of one underlying measurement.

The writable calibration registers confirm the shape of that
relationship. Each nutrient exposes an IEEE754 coefficient pair and an
integer deviation, at 0x04E8 for nitrogen, 0x04F2 for phosphorus and
0x04FC for potassium. Writing them applies a scale and an offset. That
yields three straight lines plotted against a single variable, so no
combination of coefficients can separate the three nutrients. A soil high
in nitrogen and low in potassium is indistinguishable, to this
instrument, from the reverse.

Direct measurement agrees. On 22 July 2026 the development probe read in
air with conductivity at 0 and nitrogen, phosphorus and potassium all at
0 simultaneously. They move together because they are one measurement.

Two further obstacles apply even setting the above aside. PUTS returns an
ordinal result in three classes, which cannot support fitting a
continuous calibration curve. And the two instruments measure different
physical quantities: PUTS chemically extracts plant-available nutrients,
whereas the probe reads bulk soil conductivity in situ, which is
dominated by moisture content and total dissolved salts.

PUTS therefore serves two roles in this project, neither of which is
calibration. It is the authoritative source for fertiliser
recommendations by way of Permentan status classes, and it is a
validation reference recorded alongside probe readings as described in
section 10.

Calibration effort belongs where a single physical relationship genuinely
exists: bulk conductivity to a salinity class, and volumetric moisture to
water-table depth. Both are specified elsewhere in the design spec and
both are worth doing properly.
"""


def _quote(path: Path) -> str:
    """Escape a path for use inside a DuckDB string literal.

    COPY takes its target as a literal, not a bound parameter, so this
    plain single-quote doubling is DuckDB's own escaping rule, applied to a
    path this module built itself from out_dir and a generated file name.
    """
    return str(path).replace("'", "''")


def _slugify(text: str) -> str:
    """Turn operator-entered text into a filesystem-safe file name token.

    Keeps letters and digits, collapses everything else (spaces, and the
    characters Windows forbids in a file name) into a single underscore,
    and falls back to 'site' when that leaves nothing, so a session with
    no site name entered still gets a distinct, non-empty segment.
    """
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return slug or "site"


def _copy_table(con: duckdb.DuckDBPyConnection, table: str, stem: Path) -> dict[str, str]:
    parquet_path = stem.with_suffix(".parquet")
    csv_path = stem.with_suffix(".csv")
    with CONNECTION_LOCK:
        con.execute(
            f"COPY (SELECT * FROM {table} ORDER BY ts) TO '{_quote(parquet_path)}' (FORMAT PARQUET)"
        )
        con.execute(
            f"COPY (SELECT * FROM {table} ORDER BY ts) TO '{_quote(csv_path)}' (FORMAT CSV, HEADER)"
        )
    return {"parquet": str(parquet_path), "csv": str(csv_path)}


def export_session(
    con: duckdb.DuckDBPyConnection,
    out_dir: str | Path,
    site_name: str = "",
    now: datetime | None = None,
) -> dict[str, str]:
    """Write this session's readings, and its PUTS observations if any were
    recorded, into out_dir, plus a README carrying the nutrient caveat.

    File names carry a UTC timestamp and the site name, for example
    readings_20260723T050000Z_Blok_A.parquet, so a second focus group's
    export never silently overwrites the first group's; each export lands
    at its own path, and nothing already in out_dir is touched or deleted.

    Returns the written paths, keyed 'parquet' and 'csv' for readings,
    'puts_parquet' and 'puts_csv' for PUTS observations if any were
    exported, and 'readme'.

    Raises ValueError if the readings table is empty, since an empty
    export would leave a focus group with nothing and is more likely a
    mistake than an intentional export.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with CONNECTION_LOCK:
        row_count = con.execute("SELECT count(*) FROM readings").fetchone()[0]
    if row_count == 0:
        raise ValueError("no readings to export")

    moment = now if now is not None else datetime.now(timezone.utc)
    tag = f"{moment.strftime('%Y%m%dT%H%M%SZ')}_{_slugify(site_name)}"

    paths = _copy_table(con, "readings", out_dir / f"readings_{tag}")

    # puts_observations is created lazily by app.observations, normally the
    # first time POST /api/puts runs. Ensuring the schema here means this
    # export never fails just because no PUTS result happens to have been
    # entered yet in this connection's lifetime.
    initialise_puts_schema(con)
    with CONNECTION_LOCK:
        puts_count = con.execute("SELECT count(*) FROM puts_observations").fetchone()[0]
    if puts_count > 0:
        puts_paths = _copy_table(con, "puts_observations", out_dir / f"puts_observations_{tag}")
        paths["puts_parquet"] = puts_paths["parquet"]
        paths["puts_csv"] = puts_paths["csv"]

    readme_path = out_dir / "README.txt"
    readme_path.write_text(NUTRIENT_CAVEAT, encoding="utf-8")
    paths["readme"] = str(readme_path)

    return paths
