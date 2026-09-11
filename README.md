# Competitive Visibility Audit

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb)

**Discover what traditional search and AI answer engines show potential customers about a company—and how that visibility compares with direct competitors.**

This repository contains a form-based Google Colab notebook that audits competitive visibility across:

- Google Search or Bing Search
- Google AI Mode
- ChatGPT
- Gemini

The notebook uses Bright Data to collect live search and AI-answer data, discover buyer-intent searches, identify direct competitors, measure brand visibility, analyze citation sources, and generate a downloadable competitive audit.

The workflow is category-neutral. It can analyze:

- Consumer products
- B2B products and services
- Software platforms
- Professional practices
- Local businesses
- Medical devices
- Financial services
- Hospitality
- Education
- Retail brands
- Institutions and other organizations

No Python knowledge is required for normal use.

---

## Open the notebook

Click:

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb)

Or open the notebook directly:

```text
https://github.com/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb
```

---

## What the audit does

Enter:

- A company, product, or brand name
- Its official website
- An optional audit focus
- A target country
- A Bright Data SERP API zone
- A traditional search-engine preference

The notebook then:

1. Researches the target with Google AI Mode.
2. Identifies its market, offerings, customers, positioning, and differentiators.
3. Races Gemini and ChatGPT to structure the research.
4. Generates eight non-branded buyer-intent searches.
5. Selects Google or Bing for the complete traditional-search measurement.
6. Runs the eight searches in parallel.
7. Asks Google AI Mode three neutral customer questions.
8. Combines traditional-search domains with Google AI Mode citation domains.
9. Uses Google AI Mode to identify ten likely direct competitors.
10. Selects the two strongest valid direct competitors.
11. Creates profiles for the target and both competitors.
12. Measures visibility in Google AI Mode, ChatGPT, and Gemini.
13. Analyzes which sources and source types shape the observed AI answers.
14. Races Gemini and ChatGPT to produce the final Markdown report.
15. Exports Markdown, JSON, raw evidence, and a ZIP archive.

---

## High-level workflow

```text
Company name + website + optional audit focus
                      │
                      ▼
          Google AI Mode research
                      │
                      ▼
        Gemini ───────────── ChatGPT
                utility race
             first valid JSON wins
                      │
                      ▼
        8 non-branded buyer searches
                      │
                      ▼
       Google or Bing search selection
                      │
                      ▼
        8 parallel traditional searches
                      +
       3 Google AI Mode buyer questions
                      │
                      ▼
       Candidate aggregation and scoring
                      │
                      ▼
     Google AI Mode direct-competitor research
                      │
                      ▼
        2 selected direct competitors
                      │
                      ▼
        Target + 2 competitor profiles
                      │
                      ▼
  Google AI Mode + ChatGPT + Gemini visibility
                      │
                      ▼
        Gemini ───────────── ChatGPT
              final-report race
           first valid report wins
                      │
                      ▼
          Markdown + JSON + ZIP
```

---

## Utility races versus visibility measurement

The notebook uses Gemini and ChatGPT in two different ways.

### Internal utility work

For structured transformations and final report generation, Gemini and ChatGPT start concurrently.

The first **valid** response wins.

A response is not accepted merely because it finishes first.

For JSON tasks, the response must:

- Contain a parseable JSON object
- Pass the notebook’s normalization logic
- Supply the required data for the current stage

For final report generation, the response must:

- Be substantive
- Include all required report sections
- Contain recognizable section headings
- Avoid unusable AI-interface boilerplate

Equivalent heading formats—such as bold, numbered, bulleted, Setext, or differently leveled Markdown headings—are normalized into the expected report structure.

### Visibility measurement

ChatGPT and Gemini are also queried independently during the visibility stage.

Those results are not raced against each other because the purpose of the stage is to measure each answer engine separately.

The final audit therefore retains independent results for:

- Google AI Mode
- ChatGPT
- Gemini

---

## Bright Data products used

| Product | Purpose |
|---|---|
| SERP API | Collects live Google or Bing search results for the generated buyer-intent searches |
| Google AI Mode Scraper | Researches the target, answers neutral buyer questions, discovers competitors, and creates profiles |
| ChatGPT Scraper | Measures ChatGPT visibility and participates in utility races |
| Gemini Scraper | Measures Gemini visibility and participates in utility races |

---

## Requirements

You need:

1. A Google account with access to Google Colab.
2. A Bright Data account.
3. A Bright Data API token.
4. An active Bright Data SERP API zone.
5. Access to the required Google AI Mode, ChatGPT, and Gemini scrapers.

---

## Setup

### 1. Open the notebook in Colab

Use the **Open in Colab** button at the top of this README.

### 2. Add the Bright Data API token

In Google Colab:

1. Open the **Secrets** panel using the key icon in the left sidebar.
2. Add a secret named:

   ```text
   BRIGHTDATA_API_TOKEN
   ```

3. Paste the Bright Data API token as its value.
4. Enable **Notebook access**.

Do not paste the token directly into a notebook code cell.

### 3. Configure the audit

Use the configuration form near the beginning of the notebook:

```python
COMPANY_NAME = "Your company or brand"
COMPANY_DOMAIN = "example.com"
AUDIT_FOCUS = ""

COUNTRY = "US"
SEARCH_ENGINE = "auto"
SERP_ZONE = "serp_api1"

AUTO_DOWNLOAD_REPORT = False
DEBUG_MODE = False
```

### Configuration fields

| Field | Required | Description |
|---|---:|---|
| `COMPANY_NAME` | Yes | Company, product, brand, service, or organization to audit |
| `COMPANY_DOMAIN` | Yes | Official domain or website URL |
| `AUDIT_FOCUS` | No | Specific offering, market, audience, or customer need |
| `COUNTRY` | Yes | Two-letter country code used for localized collection |
| `SEARCH_ENGINE` | Yes | `auto`, `google`, `bing`, or `none` |
| `SERP_ZONE` | Yes | Bright Data SERP API zone name |
| `AUTO_DOWNLOAD_REPORT` | No | Automatically download the ZIP archive after completion |
| `DEBUG_MODE` | No | Display detailed API, snapshot, retry, and parsing diagnostics |

The domain can be entered as:

```text
example.com
www.example.com
https://www.example.com/
```

The notebook normalizes it automatically.

---

## Search-engine selection

The `SEARCH_ENGINE` setting controls traditional-search measurement.

### `auto`

```python
SEARCH_ENGINE = "auto"
```

The notebook:

1. Tests Google.
2. Retries Google if the response is incomplete or cannot be parsed.
3. Falls back to Bing if Google remains unavailable.
4. Uses the selected engine consistently for the complete audit.

A single audit does not intentionally mix Google and Bing rankings.

### `google`

```python
SEARCH_ENGINE = "google"
```

Only Google is considered for traditional-search measurement.

If Google remains unavailable after its retry sequence, the audit continues without traditional-search metrics.

### `bing`

```python
SEARCH_ENGINE = "bing"
```

The audit uses Bing for all eight buyer-intent searches.

### `none`

```python
SEARCH_ENGINE = "none"
```

Traditional search is disabled.

The audit continues with Google AI Mode discovery and cross-engine AI visibility measurement.

When traditional search is unavailable or disabled, the report should describe it as **not measured** rather than treating every brand as having zero search visibility.

---

## Audit focus

Use `AUDIT_FOCUS` when an organization has several products, audiences, or markets.

Example:

```python
COMPANY_NAME = "CeraVe"
COMPANY_DOMAIN = "cerave.com"
AUDIT_FOCUS = "facial moisturizer for dry and sensitive skin"
```

Another example:

```python
COMPANY_NAME = "Rayner"
COMPANY_DOMAIN = "rayner.com"
AUDIT_FOCUS = "intraocular lenses and ophthalmic surgical products"
```

A focused audit generally produces more relevant:

- Buyer-intent searches
- Search results
- Competitor selection
- Company profiles
- Visibility comparisons
- Recommendations

If `AUDIT_FOCUS` is empty, the notebook attempts to infer the primary offering from the public website.

---

## Run the audit

After configuring the notebook, select:

```text
Runtime → Run all
```

A typical run shows six stages:

```text
[1/6] Company analysis and buyer keywords
      ✓ Company analyzed; 8 buyer keywords generated

[2/6] Web Search and AI Mode competitor discovery
      ✓ Traditional searches completed
      ✓ Google AI Mode customer questions completed

[3/6] Direct competitor selection
      ✓ Competitor A
      ✓ Competitor B

[4/6] Target and competitor profiles
      ✓ 3/3 profiles available

[5/6] Cross-engine AI visibility
      ✓ ChatGPT completed
      ✓ Gemini completed
      ✓ Google AI Mode results available

[6/6] Final report and export
      ✓ Report generated
      ✓ Markdown, JSON, and ZIP saved
```

A live audit can take several minutes. Runtime depends on scraper availability, search-engine retries, snapshot completion, and whether utility responses pass validation.

---

## Methodology

### Stage 1: Company analysis and buyer searches

Google AI Mode researches the target’s public presence.

The research may cover:

- Market category
- Products or services
- Positioning
- Primary customers
- Customer needs
- Benefits and capabilities
- Claims and attributes
- Differentiators
- Public evidence
- Comparison criteria

Gemini and ChatGPT then race to structure that research.

The first parseable JSON result is passed through the notebook’s local normalization and validation logic.

The workflow generates exactly eight non-branded buyer-intent searches. Known generic placeholders such as `products and services`, `primary offering`, or `best products` are rejected.

If the first structured result does not contain eight usable searches, another utility race can complete the set.

### Stage 2: Traditional-search discovery

The notebook selects one traditional search engine and runs all eight buyer-intent searches in parallel.

For each result, it records:

- Organic position
- Title
- Description
- URL
- Root domain
- Search query

For each audited brand, it calculates:

- Search coverage
- Best observed position
- Average observed position
- Searches in which the domain appeared

Known social networks, publishers, review sites, directories, job pages, and other non-competitor domains are filtered from the initial competitor candidate set.

### Stage 2: Google AI Mode buyer questions

Alongside traditional search, the notebook asks Google AI Mode three neutral customer questions based on the generated buyer searches.

The target and selected competitors are not explicitly named in these questions.

The results are used to collect:

- AI answers
- Answer coverage
- Brand mentions
- Citations
- Source URLs
- Source domains
- Citation positions

Opaque Google citation redirects are resolved where possible so the audit can retain the actual destination URL.

### Stage 3: Direct competitor selection

Traditional-search domains and recurring Google AI Mode citation domains are combined into a candidate list.

Google AI Mode then researches the current market and returns up to ten likely direct competitors.

A valid direct competitor must:

1. Sell, manufacture, operate, or provide its own offering.
2. Serve substantially the same primary buyer.
3. Operate at substantially the same value-chain level.
4. Offer a substitute within the same purchase decision.
5. Be something a customer would realistically compare with the target.

The notebook selects the first two competitors that satisfy the required checks.

The following should not automatically be treated as direct competitors:

- Retailers
- Marketplaces
- Publishers
- Review or comparison sites
- Directories
- Distributors
- Resellers
- Forums and communities
- Industry lists
- Government organizations
- Educational resources
- Suppliers without a substitute offering
- Customers or downstream providers

For example, a clinic using a medical device is not automatically a competitor to the manufacturer of that device.

### Stage 4: Target and competitor profiles

The notebook creates three concurrent profile jobs:

- Target profile
- Competitor 1 profile
- Competitor 2 profile

Depending on the market, profile information may include:

- Products or services
- Customer segments
- Benefits
- Features
- Claims
- Ingredients
- Materials
- Specifications
- Use cases
- Pricing or price tier
- Availability
- Positioning
- Differentiators
- Public evidence

A failed profile request does not automatically terminate the other profile jobs. Where possible, the notebook recovers late snapshots or uses a limited fallback profile.

### Stage 5: AI visibility

The notebook measures the target and competitors in:

- Google AI Mode
- ChatGPT
- Gemini

The visibility prompt describes the category and customer requirements without naming the audited brands.

For ChatGPT and Gemini, three redundant snapshots per engine are triggered. The first valid snapshot from each engine is retained.

This redundancy is separate from the Gemini–ChatGPT utility race.

The notebook records:

- Answer coverage
- Brand mentions
- Mention counts
- First appearance among audited brands
- Citations
- Source URLs
- Source domains
- Source classifications
- Whether ChatGPT triggered web search, when reported

### Stage 6: Final report

Gemini and ChatGPT receive the same compact evidence packet and start concurrently.

The first valid report wins.

The validator recognizes equivalent heading formats and normalizes them into the required Markdown structure.

The report includes:

- Executive summary
- Competitive landscape
- Traditional-search visibility
- AI answer-engine visibility
- Source influence
- Positioning and information gaps
- Prioritized recommendations
- Methodology and limitations
- Observed AI sources

The generated report should use only the supplied audit evidence rather than starting a separate research process.

---

## Understanding the metrics

### Search coverage

```text
2/8 searches
```

means that a brand appeared in two of the eight measured traditional-search result sets.

Coverage is the primary traditional-search visibility metric.

The audit records whether the measured engine was Google or Bing.

### Best rank

The highest organic position observed for the brand.

A single number-one result does not necessarily indicate stronger overall visibility than appearing across several searches.

If a brand did not appear in any measured result set, best rank is unavailable.

### Average rank

The average organic position across searches in which the brand appeared.

Searches where the brand was absent are not assigned an artificial position.

If a brand did not appear, average rank is unavailable.

### Answer coverage

Example:

```text
Google AI Mode: 1/3
ChatGPT: 1/1
Gemini: 0/1
```

This means that the brand appeared in:

- One of three measured Google AI Mode answers
- The retained ChatGPT answer
- None of the retained Gemini answers

Answer coverage is the primary AI visibility metric.

### Mention count

Mention count is the number of detected, non-overlapping references to a known brand or conservative brand alias.

Mention count is supporting detail. It is not market share and should not be compared without considering answer count and answer length.

### First appearance

First appearance records the character position where an audited brand was first detected.

It describes appearance within the observed answer. It is not a formal recommendation rank or market ranking.

### Unavailable measurements

Unavailable numerical measurements are displayed as:

```text
—
```

rather than `NaN`.

Examples include:

- Best rank when a brand did not appear
- Average rank when a brand did not appear
- First-mention offset when a brand was not mentioned

The exported JSON uses `null` for these values.

### Source influence

Citations are classified into categories such as:

- Official audited brand
- Official company or product
- Publisher or editorial
- Scientific or professional
- Government or regulator
- Academic or educational
- Market research or directory
- Social or community
- Retailer or marketplace
- Publisher or other source

Citation presence does not prove that a source caused a brand to be included or excluded. Source influence should be interpreted as observed evidence, not proof of causation.

---

## Output files

Each audit creates a timestamped output directory:

```text
competitive-visibility-<name>-<timestamp>/
```

Typical contents:

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

The notebook also creates a ZIP archive containing the complete audit.

Enable automatic download with:

```python
AUTO_DOWNLOAD_REPORT = True
```

---

## Debug mode

For normal use:

```python
DEBUG_MODE = False
```

For troubleshooting:

```python
DEBUG_MODE = True
```

Debug mode may display:

- Snapshot IDs
- Snapshot status
- Polling duration
- Utility-race winners
- Trigger failures
- Prompt sizes
- Search-engine selection
- Search result domains
- API retries
- AI Mode citation redirects
- JSON parsing attempts
- Competitor-selection details
- Profile recovery
- Temporary API errors

Disable debug mode before committing a public notebook.

---

## Reliability features

The notebook includes handling for:

- Synchronous and asynchronous scraper responses
- Concurrent Gemini and ChatGPT utility requests
- First-valid-response selection
- Snapshot polling
- Temporary empty responses
- JSON and NDJSON responses
- Markdown-wrapped JSON
- JSON repair
- Flexible final-report headings
- Oversized AI Markdown fields
- Prompt-size limits
- Google retries and Bing fallback
- Optional operation without traditional search
- Google citation redirect URLs
- Multiple parsed SERP formats
- Generic keyword rejection
- Direct-competitor guardrails
- Conservative brand aliases
- Non-overlapping mention counts
- Partial profile failures
- Late profile recovery
- AI-interface boilerplate
- Duplicate citation URLs
- Clean display of unavailable numeric values

---

## Approximate request volume

A typical successful audit may trigger:

- 1 Google AI Mode company-research request
- 1 Gemini company-structuring request
- 1 ChatGPT company-structuring request
- Up to 8 traditional-search requests
- 3 Google AI Mode customer-question requests
- 1 Google AI Mode competitor-discovery request
- 3 Google AI Mode profile requests
- 3 ChatGPT visibility snapshots
- 3 Gemini visibility snapshots
- 1 Gemini final-report request
- 1 ChatGPT final-report request

Additional requests may occur for:

- Search-engine health checks
- Google retries
- Keyword completion
- Strict formatting retries
- Candidate structuring
- Snapshot recovery

Utility races optimize elapsed time and resilience, not request volume. Both Gemini and ChatGPT requests are triggered even though only the first valid response is retained.

Similarly, all redundant visibility snapshots may contribute to API usage even when only one result per engine is retained.

---

## Limitations

This is a directional audit, not a statistically significant market measurement.

Important limitations:

- Buyer searches are AI-generated.
- Competitor discovery is AI-assisted.
- Search results vary by time, country, query, localization, and search-engine behavior.
- Google and Bing results are not interchangeable.
- AI answers vary between otherwise identical requests.
- AI source selection can change between runs.
- A small number of prompts cannot represent every customer journey.
- Profiles are public-research summaries, not verified product specifications.
- Mention detection depends on known names and aliases.
- First appearance is not a formal ranking.
- Citation presence does not establish causation.
- Source classification is heuristic.
- The audit does not measure market share.
- Recommendations describe possible opportunities, not guaranteed outcomes.
- Regulated, financial, legal, and medical claims require independent review.

For recurring monitoring, use the same configuration, country, search engine, and audit focus across multiple dates.

---

## Troubleshooting

### The API token is missing

Confirm that the Colab secret is named exactly:

```text
BRIGHTDATA_API_TOKEN
```

Enable notebook access for the secret.

### Traditional-search requests fail

Confirm that:

- `SERP_ZONE` matches an active Bright Data SERP API zone.
- The API token has access to the zone.
- `COUNTRY` uses a valid two-letter country code.
- `SEARCH_ENGINE` is `auto`, `google`, `bing`, or `none`.

With `SEARCH_ENGINE = "auto"`, the notebook can fall back from Google to Bing.

If neither engine is available, the audit can continue with AI visibility and source analysis.

### Buyer searches are too generic

Set a specific audit focus:

```python
AUDIT_FOCUS = "specific product, service, audience, or customer need"
```

The notebook also rejects known generic placeholder searches before launching Stage 2.

### A snapshot takes several minutes

Live answer-engine requests can continue asynchronously.

Enable:

```python
DEBUG_MODE = True
```

to inspect snapshot IDs and polling progress.

### A utility response finishes but does not win

The utility race accepts the first **valid** response, not the first completed response.

A response may be rejected because it:

- Is empty
- Does not contain parseable JSON
- Omits required report sections
- Contains an unusable interface capture
- Fails another stage-specific validation rule

The other engine continues to be considered until a valid result is found or the race times out.

### Both final report responses fail validation

Inspect the validation error and report preview in the exception.

The flexible validator recognizes:

- Standard Markdown headings
- Different Markdown heading levels
- Bold headings
- Numbered headings
- Bulleted headings
- Setext headings
- Indented report output

If sections are genuinely missing, review the compact evidence packet and report prompt.

### A Google AI Mode source uses `google.com/goto`

The notebook attempts to resolve the redirect and store the final destination.

If the redirect has expired or cannot be resolved, the opaque URL may be omitted from source analysis.

### No competitors are found

Use a more specific `AUDIT_FOCUS`.

Competitor discovery works best when the target’s offering, primary buyer, and market category are clear.

### Missing values appear as an em dash

This is expected:

```text
—
```

It means the measurement is unavailable or not applicable.

For example, a brand with `0/8` search coverage has no meaningful best or average rank.

The corresponding JSON value is `null`.

### The notebook behaves differently after rerunning individual cells

Start a fresh runtime and select:

```text
Runtime → Run all
```

The notebook contains staged function definitions and runtime overrides that must be loaded in order.

---

## Workshop flow

For a workshop, participants only need to:

1. Open the notebook in Colab.
2. Add the Bright Data API token to Secrets.
3. Enter the company name and domain.
4. Optionally enter a focused offering or customer need.
5. Select the country, search engine, and SERP zone.
6. Select **Runtime → Run all**.
7. Review the generated tables and report.
8. Download the ZIP archive.

The final discussion can focus on three questions:

1. **Who is visible in traditional search?**
2. **Who appears in AI-generated answers?**
3. **Which pages and source types shape those answers?**

A particularly useful result is often disagreement between these measurements:

> A company can rank in traditional search but remain absent from AI answers—or appear in an AI answer despite weak measured search coverage.

---

## Repository structure

```text
competitive_vsibility_audit_bd/
├── README.md
└── competitive_visibility_audit_bd.ipynb
```

Repository:

```text
https://github.com/mhirschberg/competitive_vsibility_audit_bd
```

Notebook:

```text
https://github.com/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb
```

---

## Project status

This is a working reference implementation and workshop tool.

It is not an official Bright Data SLA, benchmark, ranking system, or production monitoring product.

Review request cost, retry behavior, data retention, output storage, validation requirements, and compliance requirements before adapting it for production use.

---

## Inspiration

The original staged competitive-audit concept was inspired by:

```text
https://github.com/ScrapeAlchemist/Competitive-Visibility-Audit
```

This implementation was rebuilt as a category-neutral Google Colab workflow using Bright Data for live traditional-search and AI answer-engine collection.
```
