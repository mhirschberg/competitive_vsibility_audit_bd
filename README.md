# Competitive Visibility Audit

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb)

Find out what Google, ChatGPT, and Gemini tell potential customers about a brand, product, service, or organization—and which competitors appear alongside it.

This repository contains a no-code Google Colab notebook powered by Bright Data's SERP API and AI Search scrapers.

## What the audit does

Enter:

- A company or brand name
- Its website
- An optional product or service focus
- A target country

The notebook then:

1. Researches the public website with Google AI Mode.
2. Identifies the market, audience, offering, and relevant evaluation criteria.
3. Generates eight non-branded buyer-intent searches.
4. Runs the searches through Google SERP API in parallel.
5. Identifies the domains competing for those searches.
6. Selects five direct competitors.
7. Creates profiles for the target and competitors.
8. Measures how ChatGPT and Gemini discuss the category.
9. Compares brand mentions and order of appearance.
10. Produces a competitive visibility report with recommendations.
11. Exports the full audit as Markdown, JSON, and ZIP.

No Python knowledge is required to run the notebook.

## Open the notebook

Click:

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb)

Alternatively, open:

```text
competitive_visibility_audit_bd.ipynb
```

directly in Google Colab.

## Supported audit types

The notebook is designed to adapt its research and comparison criteria to the market being analyzed.

Examples include:

| Audit type | Example focus |
|---|---|
| Consumer product | Facial moisturizer for sensitive skin |
| B2B product | Enterprise data collection platform |
| Professional service | International payroll provider |
| Local business | Family dentist in Berlin |
| Financial product | Business checking account |
| Education | Online data science course |
| Hospitality | Boutique hotel in central Berlin |
| Technology | Managed cloud database |
| Health and beauty | Retinol night cream |
| Retail | Sustainable running shoes |

The first analysis stage determines which attributes matter in the category, such as:

- Benefits and suitability
- Features and capabilities
- Ingredients or materials
- Claims and supporting evidence
- Price and price tier
- Availability
- Reputation and trust signals
- Specifications
- Service model
- Performance
- Location
- Deployment and scalability, when relevant

Irrelevant comparison criteria are excluded.

## Requirements

You need:

1. A Google account with access to Google Colab.
2. A Bright Data account.
3. A Bright Data API token.
4. An active Bright Data SERP API zone.
5. Access to the following Bright Data scrapers:
   - Google AI Mode
   - ChatGPT
   - Gemini

Bright Data documentation:

- [API authentication](https://docs.brightdata.com/api-reference/authentication)
- [SERP API](https://brightdata.com/products/serp-api)
- [Google Scraper API](https://brightdata.com/products/web-scraper/google)
- [ChatGPT Scraper](https://brightdata.com/products/web-scraper/chatgpt)

## Setup

### 1. Add the API token to Colab Secrets

Open the notebook in Colab.

In the left sidebar:

1. Click the key icon.
2. Add a secret named:

   ```text
   BRIGHTDATA_API_TOKEN
   ```

3. Paste your Bright Data API token.
4. Enable **Notebook access**.

Do not paste the token directly into the notebook source.

### 2. Configure the audit

Use the configuration form in the notebook:

```python
COMPANY_NAME = "Your brand or organization"
COMPANY_DOMAIN = "example.com"
AUDIT_FOCUS = ""
COUNTRY = "US"
SERP_ZONE = "serp_api1"
```

### Configuration fields

| Field | Required | Description |
|---|---:|---|
| `COMPANY_NAME` | Yes | Brand, company, product, service, or organization to audit |
| `COMPANY_DOMAIN` | Yes | Official domain or full website URL |
| `AUDIT_FOCUS` | No | Specific product, service, category, or customer need to analyze |
| `COUNTRY` | Yes | Two-letter country code used for localized results |
| `SERP_ZONE` | Yes | Name of your Bright Data SERP API zone |
| `AUTO_DOWNLOAD_REPORT` | No | Automatically downloads the result ZIP when complete |
| `DEBUG_MODE` | No | Shows snapshot IDs, polling, retries, and API diagnostics |

The domain can be entered as:

```text
example.com
www.example.com
https://www.example.com/
```

The notebook normalizes it automatically.

### When to use `AUDIT_FOCUS`

Use `AUDIT_FOCUS` when a brand has multiple products or serves multiple markets.

For example:

```python
COMPANY_NAME = "Example Skincare Brand"
COMPANY_DOMAIN = "example.com"
AUDIT_FOCUS = "Facial moisturizer for dry and sensitive skin"
```

Without a focus, the notebook analyzes the organization's primary offering as inferred from its website.

## Run the audit

After configuring the notebook, select:

```text
Runtime → Run all
```

The audit performs live requests and can take several minutes.

Typical progress:

```text
[1/6] Company analysis and buyer keywords
      ✓ Company analyzed; 8 buyer searches generated

[2/6] Google search competitor discovery
      ✓ 8/8 searches completed

[3/6] Direct competitor selection
      ✓ Five competitors selected

[4/6] Target and competitor profiles
      ✓ 6/6 profiles available

[5/6] ChatGPT and Gemini visibility
      ✓ ChatGPT completed
      ✓ Gemini completed

[6/6] Final report and export
      ✓ Report generated
      ✓ Markdown, JSON, and ZIP saved
```

## How the audit works

### Stage 1: Market research and buyer questions

Google AI Mode analyzes the public website and determines:

- What the organization offers
- The market category
- The intended audience
- The primary customer need
- Products or services
- Features, benefits, claims, or attributes
- Relevant differentiators
- Category-specific evaluation criteria

ChatGPT then structures this research with web search disabled.

The result includes eight non-branded searches representing how a customer might look for, compare, or buy alternatives.

### Stage 2: Google visibility

The notebook runs the eight buyer searches through Bright Data SERP API.

Requests run in parallel and retry automatically when needed.

The notebook initially applies a strict filter to remove obvious non-competitor domains.

If strict filtering removes every result, it switches to relaxed candidate collection. Google AI Mode then classifies the resulting domains rather than allowing the audit to fail.

### Stage 3: Competitor selection

Google AI Mode evaluates the candidate domains and selects five direct competitors.

A direct competitor should address substantially the same:

- Customer need
- Buyer intent
- Product or service category
- Use case
- Purchase decision

The selection stage distinguishes competitors from:

- Retailers
- Marketplaces
- Publishers
- Review sites
- Directories
- Forums and communities
- Distributors
- Informational resources
- Loosely related organizations

### Stage 4: Target and competitor profiles

The notebook generates six profiles in parallel:

- One target profile
- Five competitor profiles

Depending on the category, a profile may include:

- Products or services
- Target customers
- Benefits
- Features
- Claims
- Ingredients
- Materials
- Specifications
- Use cases
- Pricing or price tier
- Availability
- Trust signals
- Differentiators

If a profile snapshot is delayed, the notebook continues polling it independently. A failed profile does not automatically stop the entire audit.

### Stage 5: ChatGPT and Gemini visibility

The notebook builds a neutral category prompt using the generated buyer searches.

The audited brand and selected competitors are not named in the prompt. This avoids forcing the answer engines to mention them.

For both ChatGPT and Gemini, the notebook:

1. Triggers three redundant snapshots.
2. Waits for the first valid result.
3. Records the answer.
4. Records available citations.
5. Detects audited-brand and competitor mentions.
6. Measures order of first appearance.

For ChatGPT, the audit also records whether web search was triggered.

### Stage 6: Final report

ChatGPT generates the final report using a compact evidence packet.

Web search is disabled for this request. The final report therefore synthesizes the measured audit data rather than launching a new research process.

The report contains:

- Executive summary
- Competitive landscape
- Google Search visibility
- ChatGPT and Gemini visibility
- Positioning and information gaps
- Prioritized recommendations
- Methodology and limitations
- Observed AI sources

## Output files

Each run creates a timestamped directory:

```text
competitive-visibility-<name>-<timestamp>/
```

Example contents:

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

A ZIP archive containing the complete audit is created separately in:

```text
/content/
```

Enable automatic download with:

```python
AUTO_DOWNLOAD_REPORT = True
```

## Debug mode

For normal use:

```python
DEBUG_MODE = False
```

For development and troubleshooting:

```python
DEBUG_MODE = True
```

Debug mode displays:

- Snapshot IDs
- Snapshot status
- Polling progress
- Prompt sizes
- API retries
- SERP result domains
- Strict or relaxed filtering
- Temporary response errors
- Profile recovery
- JSON parsing problems

## Reliability features

The notebook handles:

- Synchronous and asynchronous scraper responses
- Snapshot polling
- Late snapshots
- Temporarily empty API responses
- JSON and NDJSON responses
- Markdown-escaped JSON
- Malformed AI output
- Oversized AI Markdown captures
- SERP retries
- Different SERP result URL formats
- Relative and redirect URLs
- Strict and relaxed candidate filtering
- Partial profile failures
- Duplicate citations
- Conversational AI boilerplate

## Internal scraper configuration

The notebook currently contains the following Bright Data dataset IDs:

| Scraper | Dataset ID |
|---|---|
| Google AI Mode | `gd_mcswdt6z2elth3zqr2` |
| ChatGPT | `gd_m7aof0k82r803d5bjm` |
| Gemini | `gd_mbz66arm2mf9cu856y` |

These are implementation details and normally do not need to be edited.

## Approximate request volume

A complete run normally includes:

- 8 Google SERP requests
- 1 Google AI Mode market-research request
- 1 ChatGPT structuring request
- 1 Google AI Mode competitor-selection request
- 6 Google AI Mode profile requests
- 3 ChatGPT visibility snapshots
- 3 Gemini visibility snapshots
- 1 ChatGPT final-report snapshot

Retries or keyword-completion requests may increase the total.

Redundant visibility snapshots improve the chance of receiving a result quickly, but all triggered snapshots may contribute to usage.

## Understanding the metrics

### SERP coverage

```text
4/8 SERPs
```

means the domain appeared in four of the eight Google result sets.

### Best rank

The highest organic position observed across the measured searches.

### Average rank

The average organic position for searches where the domain appeared.

A domain that appears once at position 1 does not necessarily have stronger overall visibility than a domain appearing in six searches at positions 3–6.

### AI mention count

The number of non-overlapping known-brand references found in an answer.

Mention counts should not be interpreted as market share.

### First mention offset

The character position where a known brand first appears in an answer.

The notebook uses first appearance to describe the order of known audited brands. This is not necessarily the same as a formal recommendation ranking.

### Absent

The known brand did not appear in the measured answer.

It does not mean that the brand can never appear in that answer engine.

## Methodology limitations

This is a directional competitive research tool, not a statistically significant measurement platform.

Important limitations:

- Buyer searches are AI-generated.
- Google results vary by date, country, query, and Google behavior.
- AI answers vary between requests.
- A single AI prompt does not represent every customer journey.
- Competitor selection is partly AI-generated.
- Company profiles are research summaries, not verified specifications.
- Mention detection depends on known names and aliases.
- First appearance is not always recommendation rank.
- Citation presence does not prove that every statement came from that source.
- The audit does not establish causation between content and visibility.
- Expected impact in recommendations is an inference, not a measured forecast.

For recurring monitoring, rerun the same configuration on a regular schedule and compare results over time.

## Security

- Never commit a Bright Data API token.
- Store the token only in the `BRIGHTDATA_API_TOKEN` Colab secret.
- Clear notebook outputs before committing changes.
- Review generated reports before sharing them externally.
- Use the workflow only for permitted collection and analysis of publicly accessible information.

## Troubleshooting

### API token missing

Confirm the Colab secret is named exactly:

```text
BRIGHTDATA_API_TOKEN
```

and that notebook access is enabled.

### SERP zone error

Confirm that `SERP_ZONE` matches the zone name in your Bright Data account.

### Snapshot appears stuck

Enable:

```python
DEBUG_MODE = True
```

Some answer-engine requests take several minutes. The notebook displays snapshot status approximately every 30 seconds.

### SERP results have no domains

The notebook supports multiple parsed-result URL formats and includes fallbacks for display domains and redirect URLs.

Use debug mode to inspect fields returned for unrecognized records.

### No competitors remain after filtering

The notebook automatically switches from strict to relaxed filtering and asks Google AI Mode to classify the broader candidate list.

### AI response is not valid JSON

The notebook uses:

1. Standard JSON parsing
2. Markdown cleanup
3. `json-repair`
4. ChatGPT structuring with web search disabled
5. A second formatting attempt when necessary

## Workshop use

For a workshop, participants only need to:

1. Add their Bright Data token to Colab Secrets.
2. Enter their name, domain, country, and optional audit focus.
3. Click **Runtime → Run all**.
4. Review and download the report.

For a shorter group discussion, focus on the target and the first two selected competitors even though the full audit retains five competitors.

## Project status

This repository is a working reference implementation and workshop tool.

It is not an official Bright Data SLA, benchmark, or production monitoring product. Review request volume, retention, retry behavior, and reporting requirements before adapting it for production use.

## Inspiration

The original staged competitive-audit concept was inspired by:

https://github.com/ScrapeAlchemist/Competitive-Visibility-Audit

This implementation was rebuilt as a category-neutral Python Google Colab notebook using Bright Data for live Google and AI answer-engine collection.
