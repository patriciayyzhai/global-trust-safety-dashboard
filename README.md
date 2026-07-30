# Global Trust & Safety Dashboard

A web-based dashboard for tracking age assurance-related regulations worldwide. Features a global risk heatmap, a filterable regulation database, and an automated daily monitoring pipeline that folds relevant developments directly into regulation records.

Live site: [https://patriciayyzhai.github.io/global-trust-safety-dashboard/](https://patriciayyzhai.github.io/global-trust-safety-dashboard/)

## Features

- **Global Risk Heatmap** — Choropleth world map showing regulatory risk severity by country, based on platform obligations and implementation status. Filter by service type, click to drill down.
- **Regulation Database** — Sortable, filterable table of age assurance regulations with expandable detail rows showing obligations, milestones, litigation history, and monitoring-driven updates.
- **Automated Daily Monitoring** — GitHub Actions pipeline runs at 9:00 AM SGT (Mon–Fri) to collect signals from both official regulator/government sources and news coverage, classify with OpenAI, update regulation records and labels, and redeploy.
- **Source Registry** — A curated regulator-source registry, seeded from the market tracker and the database's primary sources, keeps monitoring focused on the right agencies and legislative pages.
- **Failure Visibility** — The daily workflow now exposes fetch status and article counts in the GitHub Actions step summary, and fails when all configured monitoring sources are unavailable.
- **Manual Override System** — JSON-based override file ensures manual corrections are never overwritten by automated updates.
- **Internal Monitoring Log** — Low-confidence or audit-worthy monitoring items are retained in data files for review, without a separate end-user news tab.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19 + TypeScript + Vite |
| Styling | Tailwind CSS v4 |
| Visualization | ECharts (choropleth heatmap) |
| Data Pipeline | Python (OpenAI GPT-4o-mini, GNews + official sources) |
| CI/CD | GitHub Actions + GitHub Pages |
| Notifications | WeCom Webhook |

## Project Structure

```
├── data/                    # JSON database (source of truth)
│   ├── regulations.json     # Base regulation data
│   ├── overrides.json       # Manual corrections (never auto-overwritten)
│   ├── seen_urls.json       # URL deduplication tracker
│   ├── news_items.json      # Internal monitoring log / review queue
│   ├── seed/                # Static reference data
│   │   ├── jurisdictions.json
│   │   ├── monitoring_sources.json
│   │   └── service_types.json
│   └── schema/              # JSON Schema validators
├── scripts/                 # Python data pipeline
│   ├── config.py            # Shared configuration
│   ├── pipeline.py          # Orchestrator
│   ├── fetch_news.py        # Mixed official-source + news fetcher
│   ├── source_registry.py   # Curated + derived monitoring source loader
│   ├── classify_news.py     # LLM two-stage classifier
│   ├── update_data.py       # Database updater
│   ├── notify.py            # WeCom notifications
│   ├── merge_data.py        # Build-time data merge
│   └── validate_schemas.py  # JSON schema validator
├── src/                     # React frontend
│   ├── components/          # UI components
│   ├── context/             # React contexts
│   ├── data/                # Data loading & utilities
│   ├── pages/               # Route pages
│   └── types/               # TypeScript definitions
├── .github/workflows/       # CI/CD pipelines
└── public/                  # Static assets
```

## Local Development

### Prerequisites

- Node.js 22+
- Python 3.12+

### Setup

```bash
# Install frontend dependencies
npm install

# Generate merged data for development
cd scripts && python merge_data.py && cd ..

# Start dev server
npm run dev
```

### Build

```bash
npm run build    # Type-check + production build
npm run preview  # Preview production build locally
```

## Data Pipeline

The automated pipeline runs daily and follows this flow:

1. **Validate** — Check all JSON files against schemas
2. **Fetch** — Pull monitoring inputs from:
   - Official regulator / government sources from `data/seed/monitoring_sources.json`
   - Official-looking primary source URLs already present in `data/markets.json` and `data/regulations.json`
   - GNews `search` across 8 keyword sets as a secondary signal
3. **Classify** — Two-stage LLM classification:
   - Stage 1: Binary "is this regulatory?" filter
   - Stage 2: Full classification with structured data extraction
4. **Update** — Apply classified monitoring results to the regulation database:
   - Confidence ≥ 0.7: Auto-commit
   - Confidence 0.5–0.7: Preserve in monitoring log and create PR for manual review
   - Confidence < 0.5: Discard
5. **Notify** — Send WeCom webhook (daily digest + urgent alerts)
6. **Merge** — Combine regulations.json + overrides.json → merged.json
7. **Deploy** — Build and deploy to GitHub Pages

If all configured source requests fail, the pipeline fails instead of silently treating the day as "no news". If `GNEWS_API_KEY` is missing or degraded, the run can still proceed on official sources alone.

## Manual Overrides

Edit `data/overrides.json` to correct or add regulations without fear of automated overwrites:

```json
{
  "overrides": [
    {
      "id": "AU-OSA-2024",
      "_partial": true,
      "status": "effective",
      "summary": "Corrected summary text..."
    },
    {
      "id": "OUTDATED-REG-001",
      "_deleted": true
    },
    {
      "id": "NEW-REG-2025",
      "name": "New Regulation",
      "jurisdiction_id": "GB",
      "status": "proposed",
      "summary": "...",
      "service_type_ids": ["social_media"],
      "year": 2025,
      "obligations": [],
      "milestones": [],
      "litigations": []
    }
  ]
}
```

## GitHub Secrets

Configure these in your repository settings:

| Secret | Description |
|--------|-------------|
| `GNEWS_API_KEY` | GNews API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `WECOM_WEBHOOK_URL` | WeCom group webhook URL |

## GitHub Actions

| Workflow | Trigger | Description |
|----------|---------|-------------|
| `daily-update.yml` | Cron (9 AM SGT, Mon–Fri) + Manual | Full monitoring pipeline: fetch → classify → update regulations → notify → deploy |
| `deploy.yml` | Push to `main` | Build and deploy to GitHub Pages |
| `validate.yml` | Pull request | Validate JSON schemas + type check + build |

## License

MIT
