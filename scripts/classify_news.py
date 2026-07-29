"""
Step 2-3: Two-stage LLM classification of news articles.

Stage 1: Binary filter — "Is this about age assurance regulation?"
Stage 2: Full classification + structured data extraction
"""

import json
from pydantic import BaseModel, Field
from typing import Optional, Literal
from openai import OpenAI
from config import OPENAI_API_KEY, LLM_MODEL, load_json, REGULATIONS_FILE

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# --- Pydantic Models for Structured Output ---

class Stage1Result(BaseModel):
    is_regulatory: bool = Field(description="Whether this article is about age assurance regulation, online safety law, or child protection regulation affecting online platforms")
    reasoning: str = Field(description="Brief explanation of the decision")


class Stage2Result(BaseModel):
    action_type: Literal[
        "new_regulation_proposed",
        "existing_regulation_development",
        "existing_regulation_report",
        "not_relevant",
    ] = Field(description="Classification of the news item")
    confidence: float = Field(ge=0, le=1, description="Confidence score 0-1")
    reasoning: str = Field(description="Brief explanation of the classification")
    regulation_name: Optional[str] = Field(default=None, description="Name of the regulation discussed")
    jurisdiction: Optional[str] = Field(default=None, description="ISO 3166-1 alpha-2 country code or sub-national code (e.g., US-CA)")
    status_change: Optional[str] = Field(default=None, description="New status if this represents a status change")
    summary: Optional[str] = Field(default=None, description="One-sentence summary of the key regulatory development")
    matched_regulation_id: Optional[str] = Field(default=None, description="ID of an existing regulation this article relates to (if identifiable)")


# --- Prompt Templates ---

STAGE1_SYSTEM = """You are a regulatory news classifier specializing in age assurance and online safety regulations.

Age assurance regulations include:
- Underage social media bans (banning children from social media platforms)
- Online safety laws that require platforms to implement child access restrictions
- Age verification or age estimation mandates for online services
- Parental consent requirements for minors using online platforms
- Upstream age control obligations (e.g., OS-level or app-store-level age gates)
- Design restrictions for services likely to be accessed by children
- Content moderation obligations specifically protecting minors

You will receive a news article title and optional snippet. Determine if it is about age assurance regulation or online child safety regulation affecting online platforms."""

STAGE1_USER = """Article Title: {title}
Article Snippet: {snippet}
Source: {source}
Published: {published_at}

Is this article about age assurance regulation, online safety law, or child protection regulation affecting online platforms?"""


STAGE2_SYSTEM = """You are a regulatory intelligence analyst specializing in age assurance and online safety regulations worldwide.

Classify this news article into one of these categories:

1. "new_regulation_proposed" — A NEW regulation or bill has been proposed, introduced, or announced for the first time.
2. "existing_regulation_development" — There is a DEVELOPMENT regarding an EXISTING regulation: a status change (e.g., bill passed, law signed, enforcement began, law challenged in court, injunction granted, law repealed).
3. "existing_regulation_report" — This is a REPORT or ANALYSIS about an existing regulation, with NO new development or status change. News coverage of existing law without new action.
4. "not_relevant" — Not actually about age assurance regulation (false positive from keyword search).

Guidelines:
- If a law is being challenged in court, that is "existing_regulation_development" with status_change="challenged" or "enjoined".
- If a law takes effect or begins enforcement, that is "existing_regulation_development" with appropriate status_change.
- Opinion pieces and analyses about existing laws without new actions are "existing_regulation_report".
- Only classify as "new_regulation_proposed" if this is genuinely the first report of a new legislative proposal.
- Do not infer exact age thresholds unless the article clearly states them.
- Do not convert broad minors-protection duties into "age verification" or "parental consent" unless the article explicitly describes those mechanisms.
- Treat "minimum age", "under X", and "X or older" carefully; do not reverse the direction of the threshold.
- If the article is about a law that protects minors generally but does not give a concrete age threshold, describe it in broad terms rather than inventing a number.
- If only high-level reporting is available, keep the summary conservative and avoid legal-detail hallucinations.

Provide a confidence score (0-1) reflecting how certain you are of the classification.

Here is the current database of existing regulations for reference:
{regulations_context}"""

STAGE2_USER = """Article Title: {title}
Article Snippet: {snippet}
Source: {source}
Published: {published_at}
URL: {url}

Classify this article according to the instructions."""


# --- Functions ---

def build_regulations_context() -> str:
    """Build a context string of existing regulations for the LLM."""
    if not REGULATIONS_FILE.exists():
        return "No existing regulations in database."
    
    data = load_json(REGULATIONS_FILE)
    regs = data.get("regulations", [])
    
    lines = []
    for reg in regs:
        line = f"- ID: {reg['id']} | Name: {reg['name']} | Jurisdiction: {reg['jurisdiction_id']} | Status: {reg['status']} | Year: {reg['year']}"
        lines.append(line)
    
    return "\n".join(lines) if lines else "No existing regulations in database."


def classify_stage1(article: dict) -> Stage1Result | None:
    """Stage 1: Binary filter — is this regulatory?"""
    if not client:
        return None
    
    title = article.get("title", "")
    snippet = article.get("description", "") or article.get("content", "") or ""
    source = article.get("source", {}).get("name", "Unknown")
    published_at = article.get("publishedAt", "")
    
    completion = client.beta.chat.completions.parse(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": STAGE1_SYSTEM},
            {"role": "user", "content": STAGE1_USER.format(
                title=title, snippet=snippet[:500], source=source, published_at=published_at
            )},
        ],
        response_format=Stage1Result,
        temperature=0.1,
    )
    
    return completion.choices[0].message.parsed


def classify_stage2(article: dict, regulations_context: str) -> Stage2Result | None:
    """Stage 2: Full classification + structured extraction."""
    if not client:
        return None
    
    title = article.get("title", "")
    snippet = article.get("description", "") or article.get("content", "") or ""
    source = article.get("source", {}).get("name", "Unknown")
    published_at = article.get("publishedAt", "")
    url = article.get("url", "")
    
    completion = client.beta.chat.completions.parse(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": STAGE2_SYSTEM.format(regulations_context=regulations_context)},
            {"role": "user", "content": STAGE2_USER.format(
                title=title, snippet=snippet[:1000], source=source, published_at=published_at, url=url
            )},
        ],
        response_format=Stage2Result,
        temperature=0.1,
    )
    
    return completion.choices[0].message.parsed


def run(articles: list[dict]) -> list[dict]:
    """
    Main entry point: classify articles through two-stage pipeline.
    Returns list of classified news items.
    """
    if not client:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Classification cannot run without an OpenAI API key."
        )
    
    regulations_context = build_regulations_context()
    
    classified = []
    stage1_passed = 0
    
    for i, article in enumerate(articles):
        title = article.get("title", "Untitled")
        print(f"[classify_news] [{i+1}/{len(articles)}] Stage 1: {title[:60]}...")
        
        # Stage 1: Binary filter
        try:
            s1 = classify_stage1(article)
        except Exception as e:
            print(f"  → Stage 1 ERROR: {e}")
            continue
        
        if not s1 or not s1.is_regulatory:
            print(f"  → Stage 1: NOT regulatory ({s1.reasoning if s1 else 'no response'})")
            continue
        
        stage1_passed += 1
        print(f"  → Stage 1: REGULATORY — {s1.reasoning}")
        
        # Stage 2: Full classification
        try:
            s2 = classify_stage2(article, regulations_context)
        except Exception as e:
            print(f"  → Stage 2 ERROR: {e}")
            continue
        
        if not s2:
            continue
        
        print(f"  → Stage 2: {s2.action_type} (confidence={s2.confidence:.2f}) — {s2.reasoning}")
        
        news_item = {
            "title": title,
            "url": article.get("url", ""),
            "source": article.get("source", {}).get("name", "Unknown"),
            "published_at": article.get("publishedAt", ""),
            "snippet": article.get("description", ""),
            "classification": {
                "action_type": s2.action_type,
                "confidence": s2.confidence,
                "reasoning": s2.reasoning,
                "regulation_name": s2.regulation_name,
                "jurisdiction": s2.jurisdiction,
                "status_change": s2.status_change,
                "summary": s2.summary,
                "matched_regulation_id": s2.matched_regulation_id,
            },
        }
        classified.append(news_item)
    
    print(f"\n[classify_news] Stage 1 passed: {stage1_passed}/{len(articles)}")
    print(f"[classify_news] Stage 2 classified: {len(classified)}")
    if stage1_passed and not classified:
        print("[classify_news] Articles passed Stage 1 but none completed Stage 2 classification.")
    elif articles and not stage1_passed:
        print("[classify_news] All fetched articles were filtered out at Stage 1.")
    
    return classified


if __name__ == "__main__":
    # Test with mock articles
    test_articles = [
        {
            "title": "Australia passes social media ban for under-16s",
            "description": "The Australian parliament has passed landmark legislation banning children under 16 from social media.",
            "source": {"name": "BBC"},
            "publishedAt": "2024-11-29T10:00:00Z",
            "url": "https://example.com/test1",
        }
    ]
    results = run(test_articles)
    print(json.dumps(results, indent=2))
