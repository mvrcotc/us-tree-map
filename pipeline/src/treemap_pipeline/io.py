"""Parquet and manifest writers (data contract: Global rules, Files and paths)."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from treemap_pipeline import config

ROW_GROUP_SIZE = 100_000


def cell_hex(cell: int) -> str:
    """15-character hex string for an H3 cell id."""
    return format(cell, "x")


def write_partitioned(table: pa.Table, name: str, res: int, out_dir: Path, sources: list[str]) -> list[dict]:
    """Write `hex/{name}/r{res}/{p3}.parquet`, one file per res-3 parent; return manifest records."""
    base = out_dir / "hex" / name / f"r{res}"
    base.mkdir(parents=True, exist_ok=True)
    sort_keys = [("h3", "ascending")] + ([("year", "ascending")] if "year" in table.column_names else [])
    records = []
    for p3 in pc.unique(table["p3"]).to_pylist():
        part = table.filter(pc.equal(table["p3"], pa.scalar(p3, pa.uint64()))).sort_by(sort_keys)
        path = base / f"{cell_hex(p3)}.parquet"
        pq.write_table(part, path, compression="zstd", row_group_size=ROW_GROUP_SIZE)
        records.append({"path": path, "table": name, "res": res, "rows": part.num_rows, "sources": sources})
    return records


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def update_manifest(out_dir: Path, records: list[dict]) -> Path:
    """Merge records into `manifest.json` (keyed by relative path) with bytes, sha256 and created_at."""
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"version": config.VERSION, "files": {}}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in records:
        rel = r["path"].relative_to(out_dir).as_posix()
        manifest["files"][rel] = {
            "table": r["table"],
            "res": r["res"],
            "rows": r["rows"],
            "bytes": r["path"].stat().st_size,
            "sha256": sha256(r["path"]),
            "sources": r["sources"],
            "created_at": now,
        }
    manifest["files"] = dict(sorted(manifest["files"].items()))
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest_path
