# Competitive Visibility Audit

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb)

A Google Colab workflow for auditing how a company appears across Google Search, ChatGPT, and Gemini relative to its competitors.

The notebook uses Bright Data's SERP API and AI Search scrapers to discover buyer-intent keywords, identify competitors, create competitive profiles, measure AI answer-engine visibility, and generate an executive Markdown report.

## What it does

Given a company name, domain, and country, the notebook automatically:

1. Analyzes the company's public website with Google AI Mode.
2. Uses ChatGPT to convert the research into structured data.
3. Generates eight non-branded buyer-intent keywords.
4. Runs the eight searches through Google SERP API in parallel.
5. Aggregates ranking domains and creates a competitor shortlist.
6. Uses Google AI Mode to select five direct competitors.
7. Generates profiles for the target and five competitors in parallel.
8. Queries ChatGPT and Gemini using a neutral enterprise-buyer prompt.
9. Races three redundant snapshots per answer engine and uses the first valid result.
10. Measures known-brand mentions and appearance order.
11. Uses ChatGPT, with web search disabled, to synthesize the evidence into a final report.
12. Exports Markdown, JSON, raw evidence, and a ZIP archive.

## Workflow

```text
Company name + domain
        │
        ▼
Google AI Mode company research
        │
        ▼
ChatGPT structured profile + 8 buyer keywords
        │
        ▼
8 parallel Google SERP searches
        │
        ▼
Domain aggregation and competitor shortlist
        │
        ▼
Google AI Mode selects 5 direct competitors
        │
        ▼
6 parallel company profile analyses
        │
        ▼
ChatGPT + Gemini visibility measurement
        │
        ▼
ChatGPT final report synthesis
        │
        ▼
Markdown + JSON + ZIP export
```

## Bright Data products used

| Product | Purpose |
|---|---|
| [SERP API](https://brightdata.com/products/serp-api) | Runs the eight buyer-intent Google searches and returns structured organic results |
| [Google AI Mode Scraper](https://brightdata.com/products/web-scraper/google) | Researches the target company, validates competitors, and generates company profiles |
| [ChatGPT Scraper](https://brightdata.com/products/web-scraper/chatgpt) | Measures ChatGPT visibility, structures company research, and writes the final report |
| Gemini Scraper | Measures how Gemini recommends and discusses the target and competitors |

## Quick start

### 1. Open the notebook

Use the **Open in Colab** button at the top of this README.

Alternatively, open:

```text
competitive_visibility_audit_bd.ipynb
```

directly from the repository.

### 2. Create a Bright Data API token

You need a Bright Data account with access to:

- SERP API
- Google AI Mode scraper
- ChatGPT scraper
- Gemini scraper

You also need an active SERP API zone.

Bright Data API authentication documentation:

https://docs.brightdata.com/api-reference/authentication

### 3. Add the token to Colab Secrets

In Google Colab:

1. Open the key icon in the left sidebar.
2. Add a new secret named:

   ```text
   BRIGHTDATA_API_TOKEN
   ```

3. Paste your Bright Data API token as the value.
4. Enable **Notebook access**.

Do not paste the token directly into the notebook source.

### 4. Configure the audit

Edit the notebook's configuration form:

```python
COMPANY_NAME = "Bright Data"
COMPANY_DOMAIN = "brightdata.com"
COUNTRY = "US"
SERP_ZONE = "serp_api1"
```

The domain field accepts any of these formats:

```text
brightdata.com
www.brightdata.com
https://www.brightdata.com/
```

The notebook normalizes the value automatically.

### 5. Run the notebook

Select:

```text
Runtime → Run all
```

The audit performs live requests and may take several minutes to complete.

## User configuration

| Field | Required | Description | Example |
|---|---:|---|---|
| `COMPANY_NAME` | Yes | Company or product brand to audit | `Bright Data` |
| `COMPANY_DOMAIN` | Yes | Official domain or full website URL | `brightdata.com` |
| `COUNTRY` | Yes | Two-letter country code used for localized results | `US` |
| `SERP_ZONE` | Yes | Name of the Bright Data SERP API zone | `serp_api1` |
| `AUTO_DOWNLOAD_REPORT` | No | Automatically download the ZIP when the audit finishes | `False` |
| `DEBUG_MODE` | No | Display snapshot IDs, retries, and polling progress | `False` |

The API token is read separately from the `BRIGHTDATA_API_TOKEN` Colab secret.

## Audit stages

### 1. Company analysis and keyword generation

Google AI Mode researches the supplied company and website.

Because answer-engine output is not guaranteed to be valid JSON, ChatGPT is used with web search disabled to transform the research into:

- Canonical brand name
- Official website and domain
- Product category
- Description and positioning
- Target customers
- Products
- Key features
- Differentiators
- Eight buyer-intent keywords

### 2. Google competitor discovery

The notebook runs all eight buyer-intent searches in parallel through Bright Data SERP API.

It records:

- Organic result URLs
- Domains
- Titles and descriptions
- Ranking positions
- Keyword coverage
- Best rank
- Average rank
- Rank-weighted score

Known social networks, review sites, directories, news sites, job pages, and other non-competitor domains are filtered out.

### 3. Direct competitor selection

The highest-scoring SERP domains become a shortlist.

Google AI Mode reviews that shortlist and selects five companies that compete most directly with the target's products and buyer-intent searches.

If AI validation fails, the pipeline can continue with the strongest SERP-ranked candidates.

### 4. Company profiles

The notebook creates six independent profile jobs:

- One target-company profile
- Five competitor profiles

Each profile may contain:

- Category
- Positioning
- Target customers
- Relevant products
- Key features
- Differentiators
- Public pricing approach
- Competitive relationship
- Supporting evidence

Profile jobs run concurrently. A failed or delayed job does not automatically terminate the other jobs.

### 5. ChatGPT and Gemini visibility

The notebook creates a neutral buyer prompt using the generated category and requirements.

The prompt intentionally avoids naming the audited company or known competitors. This reduces the chance of forcing a brand mention.

For each engine, the notebook:

1. Triggers three redundant snapshots.
2. Polls the snapshots concurrently.
3. Selects the first valid completed result.
4. Stores the answer and citations.
5. Measures known-brand mentions and first appearance position.

For ChatGPT, the output also records whether live web search was triggered.

### 6. Final report

ChatGPT generates the final Markdown report using a compact evidence packet.

Web search is disabled for the final generation request so the report synthesizes the measured audit evidence rather than initiating a second competitive research process.

The final report includes:

- Executive summary
- Competitive landscape
- Google Search visibility
- ChatGPT and Gemini visibility
- Positioning and content gaps
- Prioritized recommendations
- Methodology and limitations
- Observed AI sources

## Output files

Each run creates a timestamped output directory:

```text
competitive-visibility-<company>-<timestamp>/
```

The directory contains files similar to:

```text
01_company_analysis.json
02_serp_results.json
03_competitor_selection.json
04_brand_profiles.json
05_ai_visibility.json
06_competitive_visibility_audit.md
06_competitive_visibility_audit.json
raw/
    01_company_ai_record.json
    01_company_structuring_record.json
    01_keyword_completion_record.json
    03_selection_ai_record.json
    06_final_report_record.json
```

A ZIP archive containing the complete audit is also created in `/content`.

## Debug mode

Enable detailed logging while developing or troubleshooting:

```python
DEBUG_MODE = True
```

Debug mode displays:

- Snapshot IDs
- Snapshot status approximately every 30 seconds
- Retry attempts
- Temporary API-response errors
- SERP retries
- JSON parsing errors
- Fallback behavior

For normal use, keep:

```python
DEBUG_MODE = False
```

## Reliability behavior

The notebook includes handling for:

- Synchronous scraper results
- Requests that continue asynchronously
- Snapshot polling and downloading
- Temporarily empty snapshot responses
- JSON and NDJSON API responses
- Malformed or Markdown-escaped AI JSON
- SERP retries
- Late profile snapshots
- Partial results and profile fallbacks
- Duplicate source URLs
- AI interface boilerplate

## Internal scraper configuration

The notebook currently uses these Bright Data scraper dataset IDs:

| Scraper | Dataset ID |
|---|---|
| Google AI Mode | `gd_mcswdt6z2elth3zqr2` |
| ChatGPT Search | `gd_m7aof0k82r803d5bjm` |
| Gemini | `gd_mbz66arm2mf9cu856y` |

These values are internal implementation details and normally do not need to be changed.

If a scraper template or dataset ID changes, update the constants in the core engine cell.

## Request volume

A normal audit may trigger approximately:

- 8 Google SERP requests
- 1 Google AI Mode company-research request
- 1 Google AI Mode competitor-selection request
- 6 Google AI Mode profile requests
- 1 ChatGPT structuring request
- 3 ChatGPT visibility snapshots
- 3 Gemini visibility snapshots
- 1 ChatGPT final-report snapshot

Retries or keyword-completion requests may increase this total.

Three redundant visibility snapshots are a latency and resilience strategy. They may increase usage because all three jobs are triggered even though only the first valid result is used.

## Methodology limitations

This notebook is intended as a competitive research and visibility-audit tool, not as a statistically significant measurement system.

Important limitations:

- Buyer-intent keywords are generated by an AI answer engine.
- SERP results vary by country, time, personalization, and Google behavior.
- ChatGPT and Gemini answers can vary between otherwise identical requests.
- One neutral buyer prompt does not represent every possible buyer journey.
- First text position is not necessarily the same as a formal recommendation rank.
- Mention counts use conservative text matching and may not capture every product alias.
- A brand missing from one result should not be interpreted as universally absent from that answer engine.
- AI-generated company profiles should be treated as research summaries, not verified product specifications.
- The final recommendations are evidence-based inferences, not proof of causation or business impact.

For recurring monitoring, run the same configuration on a schedule and compare results across multiple dates.

## Security

- Never commit a Bright Data API token to this repository.
- Store the token only in the `BRIGHTDATA_API_TOKEN` Colab secret.
- Clear notebook outputs before committing example runs.
- Review generated JSON and raw evidence before sharing it externally.
- Use the workflow only for permitted collection and analysis of publicly accessible information.

## Troubleshooting

### `BRIGHTDATA_API_TOKEN` is missing

Add the token through the Colab Secrets panel and enable notebook access.

### SERP requests fail

Verify:

- The SERP zone name
- API-token permissions
- Zone status
- Country configuration

Individual SERP requests are retried, and the audit can continue when some searches fail.

### A snapshot takes several minutes

Enable:

```python
DEBUG_MODE = True
```

Long-running scraper requests can continue asynchronously. The notebook polls their snapshot status until completion or timeout.

### AI output cannot be parsed

The notebook uses several recovery layers:

1. Markdown-escape cleanup
2. Standard JSON parsing
3. `json-repair`
4. ChatGPT no-web structuring for company research
5. Graceful fallback where appropriate

### The final report omits data

Inspect:

```text
06_competitive_visibility_audit.json
```

and review the `final_report.evidence` field. It contains the compact evidence packet supplied to the final ChatGPT synthesis request.

### The notebook works only after rerunning cells

Start a fresh runtime and select:

```text
Runtime → Run all
```

The notebook should not depend on variables from a previous Colab session.

## Repository structure

```text
competitive_vsibility_audit_bd/
├── README.md
└── competitive_visibility_audit_bd.ipynb
```

## Project status

This repository is a working reference implementation and demo workflow.

It is not an official Bright Data SLA, benchmark, or production monitoring service. Review request volume, error handling, data retention, and reporting requirements before adapting it for production use.

## Inspiration

The staged competitive-audit concept was inspired by:

https://github.com/ScrapeAlchemist/Competitive-Visibility-Audit

This implementation was rebuilt as a Python Google Colab workflow using Google AI Mode as the primary research engine and Bright Data for live web and answer-engine collection.
