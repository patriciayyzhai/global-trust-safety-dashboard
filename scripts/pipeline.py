"""
Pipeline orchestrator: runs all steps in sequence.
1. Fetch news → 2. Classify → 3. Update data → 4. Notify → 5. Merge data
"""

import sys
import os
from config import now_iso
from fetch_news import (
    run as fetch_news,
    FetchNewsRequestError,
)
from classify_news import run as classify_news
from update_data import run as update_data
from notify import run as notify
from merge_data import run as merge_data
from validate_schemas import run as validate_schemas


def run():
    """Run the full pipeline."""
    summary = {
        "fetch_status": "not_started",
        "fetch_count": 0,
        "classified_count": 0,
        "auto_updates": [],
        "review_items": [],
        "discarded": [],
    }
    print("=" * 60)
    print("  Age Assurance Regulation Pipeline")
    print(f"  Started: {now_iso()}")
    print("=" * 60)
    
    # Step 0: Validate existing data
    print("\n--- Step 0: Validate existing data ---")
    if not validate_schemas():
        print("ERROR: Existing data is invalid. Aborting pipeline.")
        sys.exit(1)
    
    # Step 1: Fetch monitoring signals
    print("\n--- Step 1: Fetch monitoring signals ---")
    try:
        articles = fetch_news()
        summary["fetch_status"] = "ok"
        summary["fetch_count"] = len(articles)
    except FetchNewsRequestError as exc:
        summary["fetch_status"] = "request_error"
        print(f"[pipeline] REQUEST ERROR: {exc}")
        sys.exit(1)
    
    if not articles:
        print("\nNo new articles found. Pipeline complete.")
        # Still merge data to ensure merged.json is up to date
        print("\n--- Step 5: Merge data ---")
        merge_data()
        return
    
    # Step 2-3: Classify news
    print("\n--- Step 2-3: Classify news ---")
    classified = classify_news(articles)
    summary["classified_count"] = len(classified)
    
    if not classified:
        print("\nNo relevant articles found. Pipeline complete.")
        print("\n--- Step 5: Merge data ---")
        merge_data()
        return
    
    # Step 4: Update data
    print("\n--- Step 4: Update data ---")
    summary = update_data(classified, articles)
    summary["fetch_status"] = "ok"
    summary["fetch_count"] = len(articles)
    summary["classified_count"] = len(classified)
    
    # Step 5: Notify
    print("\n--- Step 5: Notify ---")
    notify(summary)
    
    # Step 6: Merge data for frontend
    print("\n--- Step 6: Merge data ---")
    merge_data()
    
    # Final validation
    print("\n--- Step 7: Final validation ---")
    if not validate_schemas():
        print("ERROR: Updated data failed validation. Aborting before downstream success is reported.")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print(f"  Pipeline complete: {now_iso()}")
    print(f"  Auto-applied: {len(summary['auto_updates'])}")
    print(f"  Pending review: {len(summary['review_items'])}")
    print(f"  Discarded: {len(summary['discarded'])}")
    print("=" * 60)
    
    # Output summary for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"fetch_status={summary.get('fetch_status', 'unknown')}\n")
            fh.write(f"fetch_count={summary.get('fetch_count', 0)}\n")
            fh.write(f"classified_count={summary.get('classified_count', 0)}\n")
            fh.write(f"auto_updates={len(summary['auto_updates'])}\n")
            fh.write(f"review_items={len(summary['review_items'])}\n")


if __name__ == "__main__":
    run()
