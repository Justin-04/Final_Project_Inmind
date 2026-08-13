"""
MCP Tool: lookup_dji_error_code_db

Exact-match lookup against the structured error resolution dataset
stored in data/error_codes.json.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to error codes JSON (mounted or copied into container)
ERROR_CODES_PATH = os.getenv(
    "ERROR_CODES_PATH",
    str(Path(__file__).parent.parent / "data" / "error_codes.json"),
)

# In-memory cache loaded once
_error_db: Optional[Dict[str, Any]] = None


def _load_error_db() -> Dict[str, Any]:
    """Load error codes from JSON file into memory."""
    global _error_db
    if _error_db is not None:
        return _error_db

    try:
        with open(ERROR_CODES_PATH, "r", encoding="utf-8") as f:
            _error_db = json.load(f)
        logger.info(f"Loaded error codes from {ERROR_CODES_PATH} "
                    f"({len(_error_db.get('error_codes', []))} codes)")
    except FileNotFoundError:
        logger.warning(f"Error codes file not found at {ERROR_CODES_PATH}")
        _error_db = {"error_codes": []}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in error codes file: {e}")
        _error_db = {"error_codes": []}

    return _error_db


def lookup_dji_error_code_db(error_code: str) -> Dict[str, Any]:
    """
    Look up a DJI error code with resolution steps and severity.

    Performs case-insensitive exact matching against the error database.

    Args:
        error_code: DJI error code string (e.g., "E001", "COMPASS_ERR").

    Returns:
        dict: Error information including:
            - code: str
            - name: str
            - description: str
            - severity: "critical" | "warning" | "info"
            - resolution_steps: list[str]
            - related_codes: list[str]
            - affected_models: list[str]

        If not found:
            - code: str
            - found: False
            - message: str
    """
    logger.info(f"lookup_dji_error_code_db: code='{error_code}'")

    db = _load_error_db()
    error_code_upper = error_code.upper().strip()

    # Search by code field (exact match, case-insensitive)
    for entry in db.get("error_codes", []):
        if entry.get("code", "").upper() == error_code_upper:
            return {
                "code": entry["code"],
                "name": entry.get("name", ""),
                "description": entry.get("description", ""),
                "severity": entry.get("severity", "info"),
                "resolution_steps": entry.get("resolution_steps", []),
                "related_codes": entry.get("related_codes", []),
                "affected_models": entry.get("affected_models", []),
                "found": True,
            }

    # Also search by name field (e.g., "Compass Error")
    for entry in db.get("error_codes", []):
        name = entry.get("name", "").upper().replace(" ", "_")
        if name == error_code_upper or error_code_upper in name:
            return {
                "code": entry["code"],
                "name": entry.get("name", ""),
                "description": entry.get("description", ""),
                "severity": entry.get("severity", "info"),
                "resolution_steps": entry.get("resolution_steps", []),
                "related_codes": entry.get("related_codes", []),
                "affected_models": entry.get("affected_models", []),
                "found": True,
            }

    # Not found
    logger.info(f"Error code '{error_code}' not found in database")
    return {
        "code": error_code,
        "found": False,
        "message": f"Error code '{error_code}' not found in database. "
                   f"Available codes: {[e['code'] for e in db.get('error_codes', [])[:10]]}",
    }
