"""
CI validation: validate JSON files against their schemas.
"""

import sys
from jsonschema import validate, ValidationError
from config import (
    REGULATIONS_FILE, OVERRIDES_FILE, SEEN_URLS_FILE, NEWS_ITEMS_FILE,
    REGULATIONS_SCHEMA, OVERRIDES_SCHEMA, SEEN_URLS_SCHEMA, NEWS_ITEMS_SCHEMA,
    load_json,
)


def validate_file(filepath, schema_path, label) -> bool:
    """Validate a JSON file against its schema."""
    if not filepath.exists():
        print(f"[validate] ⚠ {label}: file not found ({filepath})")
        return True  # Not an error if file doesn't exist yet
    
    if not schema_path.exists():
        print(f"[validate] ⚠ {label}: schema not found ({schema_path})")
        return True
    
    try:
        data = load_json(filepath)
        schema = load_json(schema_path)
        validate(instance=data, schema=schema)
        print(f"[validate] ✓ {label}: valid")
        return True
    except ValidationError as e:
        print(f"[validate] ✗ {label}: INVALID")
        print(f"  Path: {' -> '.join(str(p) for p in e.absolute_path)}")
        print(f"  Error: {e.message}")
        return False
    except Exception as e:
        print(f"[validate] ✗ {label}: ERROR — {e}")
        return False


def run() -> bool:
    """Validate all JSON data files."""
    all_valid = True
    
    all_valid &= validate_file(REGULATIONS_FILE, REGULATIONS_SCHEMA, "regulations.json")
    all_valid &= validate_file(OVERRIDES_FILE, OVERRIDES_SCHEMA, "overrides.json")
    all_valid &= validate_file(SEEN_URLS_FILE, SEEN_URLS_SCHEMA, "seen_urls.json")
    all_valid &= validate_file(NEWS_ITEMS_FILE, NEWS_ITEMS_SCHEMA, "news_items.json (monitoring log)")
    
    if all_valid:
        print("\n[validate] All files valid ✓")
    else:
        print("\n[validate] Validation FAILED ✗")
    
    return all_valid


if __name__ == "__main__":
    if not run():
        sys.exit(1)
