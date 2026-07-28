"""
Build-time merge: merge regulations.json + overrides.json → merged.json
Also merges in seed data (jurisdictions, service_types).
"""

import hashlib
import json
from config import (
    REGULATIONS_FILE, REGULATION_METADATA_FILE, OVERRIDES_FILE, JURISDICTIONS_FILE,
    MARKETS_FILE, SERVICE_TYPES_FILE, MERGED_FILE, load_json, save_json, now_iso,
)


def merge_regulations(regulations: list[dict], overrides: list[dict]) -> list[dict]:
    """
    Merge regulations with overrides.
    
    Override semantics:
    - Same ID → override wins (full replace unless _partial=true)
    - _partial=true → shallow-merge only listed fields
    - _deleted=true → exclude from output
    """
    override_map = {o["id"]: o for o in overrides}
    
    merged = []
    seen_ids = set()
    
    for reg in regulations:
        reg_id = reg["id"]
        seen_ids.add(reg_id)
        
        if reg_id in override_map:
            ov = override_map[reg_id]
            if ov.get("_deleted"):
                continue
            if ov.get("_partial"):
                # Shallow merge: only override listed fields
                merged_reg = {**reg}
                for key, value in ov.items():
                    if key not in ("id", "_partial", "_deleted"):
                        merged_reg[key] = value
                merged.append(merged_reg)
            else:
                # Full replace (but keep id)
                merged_reg = {**ov, "id": reg_id}
                merged_reg.pop("_partial", None)
                merged_reg.pop("_deleted", None)
                merged.append(merged_reg)
        else:
            merged.append(reg)
    
    # Add new regulations from overrides that don't exist in base
    for ov in overrides:
        ov_id = ov["id"]
        if ov_id not in seen_ids and not ov.get("_deleted"):
            new_reg = {**ov}
            new_reg.pop("_partial", None)
            new_reg.pop("_deleted", None)
            # Ensure required fields
            new_reg.setdefault("obligations", [])
            new_reg.setdefault("milestones", [])
            new_reg.setdefault("litigations", [])
            new_reg.setdefault("created_at", now_iso())
            new_reg.setdefault("updated_at", now_iso())
            merged.append(new_reg)
    
    return merged


def regulation_content_hash(reg: dict) -> str:
    """Hash a regulation without volatile timestamp fields."""
    payload = {k: v for k, v in reg.items() if k not in ("created_at", "updated_at")}
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def apply_regulation_metadata(
    regulations: list[dict],
    existing_metadata: dict[str, dict],
    fallback_timestamp: str,
) -> tuple[list[dict], dict[str, dict]]:
    """Keep record timestamps stable and only bump updated_at when content changes."""
    next_metadata: dict[str, dict] = {}
    stamped: list[dict] = []
    now = now_iso()

    for reg in regulations:
        reg_copy = {**reg}
        reg_id = reg_copy["id"]
        content_hash = regulation_content_hash(reg_copy)
        prior = existing_metadata.get(reg_id)

        if prior and prior.get("content_hash") == content_hash:
            created_at = prior.get("created_at") or reg_copy.get("created_at") or fallback_timestamp
            updated_at = prior.get("updated_at") or reg_copy.get("updated_at") or created_at
        elif prior:
            created_at = prior.get("created_at") or reg_copy.get("created_at") or fallback_timestamp
            updated_at = now
        else:
            created_at = reg_copy.get("created_at") or fallback_timestamp
            updated_at = reg_copy.get("updated_at") or created_at

        reg_copy["created_at"] = created_at
        reg_copy["updated_at"] = updated_at
        stamped.append(reg_copy)
        next_metadata[reg_id] = {
            "created_at": created_at,
            "updated_at": updated_at,
            "content_hash": content_hash,
        }

    return stamped, next_metadata


def run() -> dict:
    """Main entry point: merge all data into merged.json."""
    # Load base data
    regs_data = load_json(REGULATIONS_FILE) if REGULATIONS_FILE.exists() else {
        "version": "1.0.0", "last_updated": now_iso(), "regulations": []
    }
    
    overrides_data = load_json(OVERRIDES_FILE) if OVERRIDES_FILE.exists() else {
        "version": "1.0.0", "last_updated": now_iso(), "overrides": []
    }
    
    jurisdictions_data = load_json(JURISDICTIONS_FILE) if JURISDICTIONS_FILE.exists() else {
        "version": "1.0.0", "last_updated": now_iso(), "jurisdictions": []
    }
    markets_data = load_json(MARKETS_FILE) if MARKETS_FILE.exists() else {
        "version": "1.0.0", "last_updated": now_iso(), "markets": []
    }
    
    service_types_data = load_json(SERVICE_TYPES_FILE) if SERVICE_TYPES_FILE.exists() else {
        "version": "1.0.0", "last_updated": now_iso(), "service_types": []
    }
    metadata_data = load_json(REGULATION_METADATA_FILE) if REGULATION_METADATA_FILE.exists() else {
        "version": "1.0.0", "last_updated": now_iso(), "regulations": {}
    }
    
    # Merge regulations with overrides
    merged_regulations = merge_regulations(
        regs_data.get("regulations", []),
        overrides_data.get("overrides", []),
    )
    merged_regulations, next_metadata = apply_regulation_metadata(
        merged_regulations,
        metadata_data.get("regulations", {}),
        regs_data.get("last_updated", now_iso()),
    )
    
    # Build merged output
    merged = {
        "version": markets_data.get("version", "2.0.0"),
        "last_updated": markets_data.get("last_updated", now_iso()),
        "markets": markets_data.get("markets", []),
        "regulations": merged_regulations,
        "jurisdictions": jurisdictions_data.get("jurisdictions", []),
        "service_types": service_types_data.get("service_types", []),
    }
    
    # Save to public/data/merged.json
    save_json(MERGED_FILE, merged)
    save_json(REGULATION_METADATA_FILE, {
        "version": "1.0.0",
        "last_updated": now_iso(),
        "regulations": next_metadata,
    })
    
    print(f"[merge_data] Merged {len(merged_regulations)} regulations, "
          f"{len(merged.get('markets', []))} markets → {MERGED_FILE}")
    return merged


if __name__ == "__main__":
    result = run()
    print(f"Total regulations: {len(result['regulations'])}")
    print(f"Total jurisdictions: {len(result['jurisdictions'])}")
    print(f"Total service types: {len(result['service_types'])}")
