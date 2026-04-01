import json
import os 
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(os.getenv("RESULTS_DIR", "results"))


def _ensure_dir() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)



def _make_filename(name: str, year: int | None, month: int | None) -> str:
    """
    Produces a deterministic filename so re-running the same query
    overwrites the previous result rather than creating duplicates.
    Example: davido_2024_03.json
    """
    safe_name = name.lower().replace(" ", "_")
    year_part = str(year) if year is not None else "all"
    month_part = f"{month:02d}" if month is not None else "all"
    return f"{safe_name}_{year_part}_{month_part}.json"


def save_results(data: dict) -> str:
    """
    Persists the search result dict as a JSON file.
    Returns the file path string so the API can include it in the response.
    """
    _ensure_dir()
    meta = data.get("query_meta", {})
    filename = _make_filename(
        meta.get("name", "unknown"),
        meta.get("year", 0),
        meta.get("month", 0)
    )
    filepath = RESULTS_DIR / filename
    
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        **data,
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    
    logger.info(f"[Storage] Saved to {filepath}")
    return str(filepath)


def load_results(name: str, year: int, month: int) -> dict | None:
    """
    Loads a previously saved result from disk.
    Returns None if no cached result exists.
    """
    _ensure_dir()
    filepath = RESULTS_DIR / _make_filename(name, year, month)
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)