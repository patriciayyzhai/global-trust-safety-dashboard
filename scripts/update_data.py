"""
Step 4: Update regulations.json based on classified monitoring inputs.
High-confidence items are auto-committed; lower-confidence items are logged for review.
"""

import hashlib
from config import (
    CONFIDENCE_AUTO_THRESHOLD, CONFIDENCE_REVIEW_THRESHOLD,
    REGULATIONS_FILE, SEEN_URLS_FILE, NEWS_ITEMS_FILE, load_json, save_json, now_iso,
)

MAX_MONITORING_ITEMS = 250


def generate_id(prefix: str, name: str) -> str:
    """Generate a stable ID from a prefix and name."""
    hash_part = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"{prefix}-{hash_part}"


def normalize_url(url: str) -> str:
    """Normalize a URL for stable deduplication."""
    return url.strip().lower().rstrip("/")


def build_monitoring_record(item: dict, *, auto_applied: bool) -> dict:
    """Normalize a classified monitoring item into the internal monitoring log shape."""
    classification = item["classification"]
    norm_url = normalize_url(item.get("url", ""))
    record_id = generate_id("MON", norm_url or item.get("title", ""))
    action_type = classification["action_type"]

    proposed_name = None
    proposed_jurisdiction = None
    proposed_status = None
    linked_regulation_id = classification.get("matched_regulation_id")

    if action_type == "new_regulation_proposed":
        proposed_name = classification.get("regulation_name")
        proposed_jurisdiction = classification.get("jurisdiction")
        proposed_status = classification.get("status_change") or "proposed"

    return {
        "id": record_id,
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "source": item.get("source", "Unknown"),
        "published_at": item.get("published_at", ""),
        "snippet": item.get("snippet", ""),
        "classification": {
            "action_type": action_type,
            "confidence": classification.get("confidence", 0),
            "reasoning": classification.get("reasoning"),
            "regulation_id": linked_regulation_id,
            "proposed_regulation_name": proposed_name,
            "proposed_jurisdiction_id": proposed_jurisdiction,
            "proposed_status": proposed_status,
            "status_change": classification.get("status_change"),
            "summary": classification.get("summary"),
            "auto_applied": auto_applied,
        },
        "processed_at": now_iso(),
    }


def update_monitoring_log(records: list[dict]) -> dict:
    """Persist classified monitoring records for internal review and audit."""
    news_data = load_json(NEWS_ITEMS_FILE) if NEWS_ITEMS_FILE.exists() else {
        "version": "1.0.0",
        "last_updated": now_iso(),
        "news_items": [],
    }

    by_url = {
        normalize_url(item.get("url", "")): item
        for item in news_data.get("news_items", [])
        if item.get("url")
    }

    for record in records:
        by_url[normalize_url(record["url"])] = record

    merged_items = sorted(
        by_url.values(),
        key=lambda item: item.get("published_at", ""),
        reverse=True,
    )[:MAX_MONITORING_ITEMS]

    news_data["last_updated"] = now_iso()
    news_data["news_items"] = merged_items
    save_json(NEWS_ITEMS_FILE, news_data)
    return news_data


def update_seen_urls(articles: list[dict], classified_items: list[dict]) -> dict:
    """Update the seen_urls.json file with new URLs."""
    seen_data = load_json(SEEN_URLS_FILE) if SEEN_URLS_FILE.exists() else {
        "version": "1.0.0",
        "last_updated": now_iso(),
        "total_count": 0,
        "urls": {},
    }
    
    # Add all fetched article URLs to seen (whether classified or not)
    for article in articles:
        url = article.get("url", "")
        if not url:
            continue
        norm_url = url.strip().lower().rstrip("/")
        if norm_url not in seen_data["urls"]:
            seen_data["urls"][norm_url] = {
                "url": url,
                "first_seen": now_iso(),
                "linked_record_id": None,
            }
            seen_data["total_count"] += 1
    
    # Link processed URLs to the associated updated record when available
    for item in classified_items:
        url = item.get("url", "")
        if not url:
            continue
        norm_url = url.strip().lower().rstrip("/")
        if norm_url in seen_data["urls"]:
            seen_data["urls"][norm_url]["linked_record_id"] = item.get("id")
    
    seen_data["last_updated"] = now_iso()
    save_json(SEEN_URLS_FILE, seen_data)
    return seen_data


def apply_update_to_regulation(regulations_data: dict, news_item: dict) -> dict | None:
    """
    Apply a high-confidence update to the regulations database.
    Returns the updated regulation dict, or None if no update was made.
    """
    classification = news_item["classification"]
    action_type = classification["action_type"]
    
    regs = regulations_data.get("regulations", [])
    now = now_iso()
    
    if action_type == "new_regulation_proposed":
        # Create a new regulation entry
        new_reg = {
            "id": generate_id("REG", news_item["title"]),
            "name": classification.get("regulation_name") or news_item["title"],
            "jurisdiction_id": classification.get("jurisdiction", "Unknown"),
            "summary": classification.get("summary", news_item.get("snippet", "")),
            "status": "proposed",
            "service_type_ids": [],
            "year": int(news_item.get("published_at", now)[:4]),
            "source_url": news_item.get("url"),
            "tags": [],
            "obligations": [],
            "milestones": [
                {
                    "id": generate_id("MS", news_item["url"]),
                    "regulation_id": generate_id("REG", news_item["title"]),
                    "type": "proposed",
                    "date": news_item.get("published_at", now)[:10],
                    "description": classification.get("summary", news_item["title"]),
                    "source_url": news_item.get("url"),
                }
            ],
            "litigations": [],
            "created_at": now,
            "updated_at": now,
        }
        regs.append(new_reg)
        regulations_data["regulations"] = regs
        return new_reg
    
    elif action_type == "existing_regulation_development":
        # Update an existing regulation's status or add a milestone
        reg_id = classification.get("matched_regulation_id")
        status_change = classification.get("status_change")
        
        # Find the regulation
        target_reg = None
        for reg in regs:
            if reg_id and reg["id"] == reg_id:
                target_reg = reg
                break
        
        if not target_reg:
            # Try to match by name
            reg_name = classification.get("regulation_name", "")
            if reg_name:
                for reg in regs:
                    if reg_name.lower() in reg["name"].lower() or reg["name"].lower() in reg_name.lower():
                        target_reg = reg
                        break
        
        if not target_reg:
            print(f"  → Could not find matching regulation for: {classification.get('regulation_name')}")
            return None

        target_reg.setdefault("created_at", now)
        target_reg.setdefault("updated_at", target_reg["created_at"])
        
        # Add a milestone
        milestone = {
            "id": generate_id("MS", news_item["url"]),
            "regulation_id": target_reg["id"],
            "type": status_change or "amended",
            "date": news_item.get("published_at", now)[:10],
            "description": classification.get("summary", news_item["title"]),
            "source_url": news_item.get("url"),
        }
        target_reg["milestones"].append(milestone)
        
        # Update status if there's a status change
        if status_change:
            target_reg["status"] = status_change
        
        target_reg["updated_at"] = now
        return target_reg
    
    return None


def run(classified_items: list[dict], all_articles: list[dict]) -> dict:
    """
    Main entry point: update regulations based on classified news.
    Returns a summary of what was updated.
    """
    # Load current regulations
    regulations_data = load_json(REGULATIONS_FILE) if REGULATIONS_FILE.exists() else {
        "version": "1.0.0",
        "last_updated": now_iso(),
        "regulations": [],
    }
    
    auto_updates = []
    review_items = []
    discarded = []
    
    for item in classified_items:
        confidence = item["classification"]["confidence"]
        action_type = item["classification"]["action_type"]
        
        if action_type == "not_relevant":
            discarded.append(item)
            continue
        
        if confidence >= CONFIDENCE_AUTO_THRESHOLD:
            # Auto-apply
            result = apply_update_to_regulation(regulations_data, item)
            if result:
                item["id"] = result["id"]
                item["classification"]["auto_applied"] = True
                auto_updates.append({
                    "news_item": item,
                    "regulation": result,
                })
            else:
                discarded.append(item)
        elif confidence >= CONFIDENCE_REVIEW_THRESHOLD:
            # Queue for PR review
            item["classification"]["auto_applied"] = False
            review_items.append(item)
        else:
            discarded.append(item)
    
    # Save updated regulations if there were auto-updates
    if auto_updates:
        regulations_data["last_updated"] = now_iso()
        save_json(REGULATIONS_FILE, regulations_data)

    persisted_monitoring_records = [
        build_monitoring_record(entry["news_item"], auto_applied=True)
        for entry in auto_updates
    ] + [
        build_monitoring_record(item, auto_applied=False)
        for item in review_items
    ]

    if persisted_monitoring_records:
        update_monitoring_log(persisted_monitoring_records)

    # Update seen URLs
    update_seen_urls(all_articles, persisted_monitoring_records)
    
    summary = {
        "auto_updates": auto_updates,
        "review_items": review_items,
        "discarded": discarded,
        "total_classified": len(classified_items),
    }
    
    print(f"\n[update_data] Auto-applied: {len(auto_updates)}")
    print(f"[update_data] Queued for review: {len(review_items)}")
    print(f"[update_data] Discarded: {len(discarded)}")
    
    return summary


if __name__ == "__main__":
    print("Run via pipeline.py")
