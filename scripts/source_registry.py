"""
Monitoring source registry.

Combines curated regulator/newsroom sources with official-looking source URLs
already present in the market and regulation databases.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from config import (
    MARKETS_FILE,
    MONITORING_SOURCES_FILE,
    REGULATIONS_FILE,
    load_json,
)


@dataclass(frozen=True)
class MonitoringSource:
    id: str
    label: str
    url: str
    source_type: str
    jurisdiction_id: str | None = None
    priority: int = 50
    discovery_only: bool = False
    emit_landing_page: bool = False


OFFICIAL_HOST_MARKERS = (
    ".gov",
    "gov.",
    "legislation.gov",
    "legifrance.gouv.fr",
    "eur-lex.europa.eu",
    "commission.europa.eu",
    "digital-strategy.ec.europa.eu",
    "canada.ca",
    "parl.ca",
    "law.go.kr",
    "npc.gov.cn",
    "imda.gov.sg",
    "pdpc.gov.sg",
    "sso.agc.gov.sg",
    "ofcom.org.uk",
    "ico.org.uk",
    "esafety.gov.au",
    "gov.br",
    "mcmc.gov.my",
    "komdigi.go.id",
)


def is_official_source_url(url: str) -> bool:
    """Heuristic for identifying official or regulator-hosted URLs."""
    if not url:
        return False
    host = (urlparse(url).netloc or "").lower()
    if not host:
        return False
    return any(marker in host for marker in OFFICIAL_HOST_MARKERS)


def _load_curated_sources() -> list[MonitoringSource]:
    tracked_jurisdictions = load_existing_regulation_jurisdictions()
    if not MONITORING_SOURCES_FILE.exists():
        return []
    data = load_json(MONITORING_SOURCES_FILE)
    sources = []
    for item in data.get("sources", []):
        url = (item.get("url") or "").strip()
        if not url:
            continue
        jurisdiction_id = item.get("jurisdiction_id")
        if jurisdiction_id and jurisdiction_id not in tracked_jurisdictions:
            continue
        sources.append(
            MonitoringSource(
                id=item["id"],
                label=item.get("label") or item["id"],
                url=url,
                source_type=item.get("source_type") or "official_source",
                jurisdiction_id=jurisdiction_id,
                priority=int(item.get("priority", 50)),
                discovery_only=bool(item.get("discovery_only", False)),
                emit_landing_page=bool(item.get("emit_landing_page", False)),
            )
        )
    return sources


def _derive_market_sources() -> list[MonitoringSource]:
    tracked_jurisdictions = load_existing_regulation_jurisdictions()
    if not MARKETS_FILE.exists():
        return []
    data = load_json(MARKETS_FILE)
    sources = []
    for market in data.get("markets", []):
        url = (market.get("source_url") or "").strip()
        if not is_official_source_url(url):
            continue
        jurisdiction_id = market.get("jurisdiction_id") or market.get("id")
        if jurisdiction_id not in tracked_jurisdictions:
            continue
        sources.append(
            MonitoringSource(
                id=f"{jurisdiction_id}-MARKET-SOURCE",
                label=f"{market.get('country', jurisdiction_id)} primary market source",
                url=url,
                source_type="market_primary_source",
                jurisdiction_id=jurisdiction_id,
                priority=60,
                discovery_only=True,
                emit_landing_page=False,
            )
        )
    return sources


def _derive_regulation_sources() -> list[MonitoringSource]:
    if not REGULATIONS_FILE.exists():
        return []
    data = load_json(REGULATIONS_FILE)
    sources = []
    for reg in data.get("regulations", []):
        url = (reg.get("source_url") or "").strip()
        if not is_official_source_url(url):
            continue
        sources.append(
            MonitoringSource(
                id=f"{reg['id']}-REG-SOURCE",
                label=f"{reg['name']} official source",
                url=url,
                source_type="regulation_primary_source",
                jurisdiction_id=reg.get("jurisdiction_id"),
                priority=55,
                discovery_only=False,
                emit_landing_page=True,
            )
        )
    return sources


def load_existing_regulation_jurisdictions() -> set[str]:
    """Return the set of jurisdictions already represented in the regulation database."""
    if not REGULATIONS_FILE.exists():
        return set()
    data = load_json(REGULATIONS_FILE)
    return {
        reg.get("jurisdiction_id")
        for reg in data.get("regulations", [])
        if reg.get("jurisdiction_id")
    }


def load_monitoring_sources(limit: int | None = None) -> list[MonitoringSource]:
    """Return unique monitoring sources ordered by priority."""
    unique: dict[str, MonitoringSource] = {}
    for source in (
        _load_curated_sources()
        + _derive_market_sources()
        + _derive_regulation_sources()
    ):
        key = source.url.rstrip("/").lower()
        current = unique.get(key)
        if current is None or source.priority > current.priority:
            unique[key] = source

    ordered = sorted(
        unique.values(),
        key=lambda source: (-source.priority, source.label.lower(), source.url.lower()),
    )
    if limit is not None:
        return ordered[:limit]
    return ordered
