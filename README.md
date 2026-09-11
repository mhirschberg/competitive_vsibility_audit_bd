# Competitive Visibility Audit with Bright Data

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb)

Discover what traditional search and AI answer engines show potential customers about a company—and how that visibility compares with direct competitors.

This repository contains a no-code Google Colab notebook that audits competitive visibility across:

- Google or Bing Search
- Google AI Mode
- ChatGPT
- Gemini

It uses Bright Data to collect live search and AI-answer data, identify direct competitors, analyze the sources shaping AI answers, and generate downloadable Markdown and PDF competitive visibility reports.

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

No Python knowledge is required.

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
- A traditional search-engine preference
- A Bright Data SERP API zone configured for `markdown`

The notebook then:

1. Researches the target using three concurrent Google AI Mode snapshots and keeps the first valid result.
2. Identifies its market, offerings, customers, and positioning.
3. Races Gemini and ChatGPT to structure the research and generate eight non-branded buyer-intent searches.
4. Selects Google or Bing and runs eight searches in parallel.
5. Asks Google AI Mode three neutral customer questions using three-way races.
6. Identifies ten likely direct competitors using a three-way Google AI Mode race.
7. Selects the two strongest direct competitors.
8. Creates profiles for the target and both competitors using three-way Google AI Mode races.
9. Measures visibility in Google AI Mode, ChatGPT, and Gemini.
10. Analyzes which sources shape the AI answers.
11. Races Gemini and ChatGPT to produce the final report.
12. Exports the report as Markdown, PDF, JSON, and ZIP.

---

## High-level workflow

```text
Company name + website + optional audit focus
                      │
                      ▼
       3× Google AI Mode company research
               first valid wins
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
   3 Google AI Mode questions × 3 snapshots
                      │
                      ▼
     Combined search and AI source candidates
                      │
                      ▼
   3× Google AI Mode competitor research
               first valid wins
                      │
                      ▼
        2 selected direct competitors
                      │
                      ▼
 Target + 2 competitor profiles × 3 snapshots
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
       Markdown + styled PDF + JSON + ZIP
```

---

## Bright Data products used

The notebook uses:

- Bright Data SERP API for Google or Bing
- Google AI Mode
- ChatGPT
- Gemini

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

In Colab:

1. Open the **Secrets** panel using the key icon in the left sidebar.
2. Add a secret named:

   ```text
   BRIGHTDATA_API_TOKEN
   ```

3. Paste the Bright Data API token as the value.
4. Enable **Notebook access**.

Do not paste the token directly into the notebook.

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

| Field | Required | Description |
|---|---:|---|
| `COMPANY_NAME` | Yes | Company, product, brand, service, or organization to audit |
| `COMPANY_DOMAIN` | Yes | Official domain or website URL |
| `AUDIT_FOCUS` | No | Specific offering, category, audience, or customer need |
| `COUNTRY` | Yes | Two-letter country code for localized search results |
| `SEARCH_ENGINE` | Yes | `auto`, `google`, `bing`, or `none` |
| `SERP_ZONE` | Yes | Bright Data SERP API zone name |
| `AUTO_DOWNLOAD_REPORT` | No | Automatically download the ZIP when the audit finishes |
| `DEBUG_MODE` | No | Display API, snapshot, retry, prompt, and parsing diagnostics |

The domain can be entered as:

```text
example.com
www.example.com
https://www.example.com/
```

The notebook normalizes it automatically.

---

## Audit focus

`AUDIT_FOCUS` is optional.

Use it when an organization has multiple products, services, audiences, or markets.

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

- Buyer searches
- Search results
- Competitor selection
- Profiles
- Visibility comparisons
- Recommendations
- PDF title and cover

If `AUDIT_FOCUS` is empty, the notebook attempts to infer the primary offering from the website.

---

## Run the audit

After configuring the notebook, select:

```text
Runtime → Run all
```

A typical run displays:

```text
[1/6] Company analysis and buyer keywords
      ✓ Company analyzed; 8 buyer keywords generated

[2/6] Web Search and AI Mode competitor discovery
      ✓ 8/8 searches completed
      ✓ 3 Google AI Mode questions completed

[3/6] Direct competitor selection
      ✓ Competitor A
      ✓ Competitor B

[4/6] Target and competitor profiles
      ✓ 3/3 profiles available

[5/6] Cross-engine AI visibility
      ✓ ChatGPT completed
      ✓ Gemini completed

[6/6] Final report and export
      ✓ Styled PDF report generated
      ✓ Markdown, PDF, JSON, and ZIP created
```

A live audit can take several minutes. Runtime depends on snapshot availability, search-engine retries, and which concurrent research or utility result finishes first.

---

## Methodology

### Stage 1: Company analysis

Three Google AI Mode snapshots research the target’s public website and current market presence concurrently.

The first substantive result is used.

The research may cover:

- Market category
- Products or services
- Positioning
- Primary customers
- Benefits and capabilities
- Claims and attributes
- Differentiators
- Public evidence
- Comparison criteria

Gemini and ChatGPT then structure the research concurrently.

The first response that produces valid structured data is used.

The notebook generates eight non-branded buyer searches relevant to the inferred market and optional audit focus.

Generic placeholders such as `products and services` or `primary offering` are rejected before search requests are made.

If keyword completion is required, Gemini and ChatGPT race again and the first valid result is used.

### Stage 2: Web Search

The notebook selects one traditional search engine for the complete audit and runs the eight buyer searches through Bright Data SERP API.

`SEARCH_ENGINE = "auto"` tries Google first and falls back to Bing if Google remains unavailable.

The available settings are:

- `auto` — try Google and fall back to Bing
- `google` — use Google only
- `bing` — use Bing only
- `none` — continue without traditional-search measurement

The searches run in parallel.

Google can retry temporary or incomplete responses. Bing is used as a coherent fallback rather than mixing rankings from both engines in one audit.

For each audited brand, the notebook measures:

- Search coverage
- Best observed position
- Average observed position
- Queries where the domain appeared

Search coverage is treated as the primary search-visibility metric. Best and average position describe placement only when a brand appears.

If traditional search is unavailable or disabled, the report identifies it as not measured instead of treating every brand as having zero visibility.

### Stage 2: Google AI Mode questions

Alongside the traditional searches, the notebook asks Google AI Mode three neutral customer questions.

The target is not named in those questions.

Each question starts three Google AI Mode snapshots, and the first substantive result is used.

The results are used to collect:

- AI answers
- Brand mentions
- Citations
- Source URLs
- Source domains
- Citation positions

Google `/goto` citation links are resolved where possible.

### Stage 3: Competitor selection

Traditional-search domains and recurring Google AI Mode source domains are combined into a candidate list.

Three Google AI Mode snapshots research the market concurrently and return up to ten likely direct competitors.

The first valid competitor result is used.

A valid direct competitor must:

1. Sell, manufacture, operate, or provide its own offering.
2. Serve substantially the same primary buyer.
3. Operate at substantially the same value-chain level.
4. Offer a substitute in the same purchase decision.
5. Be something a customer would realistically compare with the target.

The notebook selects the first two competitors that pass the required checks.

It rejects organizations such as:

- Retailers
- Marketplaces
- Publishers
- Review sites
- Directories
- Distributors
- Resellers
- Forums
- Government organizations
- Educational resources
- Suppliers without substitute offerings
- Customers or downstream providers

For example, a clinic using a device is not automatically a competitor to the device manufacturer.

### Stage 4: Company profiles

The notebook creates three profiles:

- Target profile
- Competitor 1 profile
- Competitor 2 profile

Each profile starts three Google AI Mode snapshots, and the first valid structured profile is used.

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

A failed profile does not terminate the full audit. Where possible, the notebook uses fallback profile data.

### Stage 5: AI visibility

The notebook measures the target and selected competitors in:

- Google AI Mode
- ChatGPT
- Gemini

The visibility prompt describes the category and customer requirements without naming the audited brands.

Google AI Mode visibility is calculated across the successful customer-question answers collected during Stage 2.

For ChatGPT and Gemini, three snapshots per engine are triggered and the first valid result from each engine is used.

Both engine races run concurrently, for a total of six cross-engine visibility calls.

The notebook records:

- Answer coverage
- Brand mentions
- Mention counts
- First appearance among audited brands
- Citations
- Source URLs
- Source classifications
- Whether ChatGPT triggered web search, when reported

### Stage 6: Final report

Gemini and ChatGPT generate the final report concurrently.

The first response containing a valid report structure is used.

Both engines receive only a compact evidence packet containing the measured audit results.

The report validator recognizes and normalizes:

- Standard Markdown headings
- Different Markdown heading levels
- Bold headings
- Numbered headings
- Bulleted headings
- Setext headings
- Indented report output

The report includes:

- Executive summary
- Competitive landscape
- Traditional search visibility
- AI answer-engine visibility
- Source influence
- Positioning and information gaps
- Prioritized recommendations
- Methodology and limitations
- Observed AI sources

The report is exported as Markdown and as a styled PDF with:

- A company-specific cover
- An optional product or audit-focus label
- Page numbers
- Formatted tables
- Clickable source links
- Print-friendly typography and page breaks

The PDF title is:

```text
Competitive Visibility Report for <Company>
```

When `AUDIT_FOCUS` is provided, it becomes:

```text
Competitive Visibility Report for <Company> / <Audit Focus>
```

---

## Understanding the metrics

### Search coverage

```text
2/8 searches
```

means the brand appeared in two of the eight result sets from the search engine selected for the audit.

Coverage is the primary traditional-search visibility metric.

### Best rank

The highest organic position observed for the brand.

A single number-one result does not necessarily mean stronger overall visibility than appearing in several searches.

### Average rank

The average organic position across searches where the brand appeared.

Brands with zero appearances do not have a meaningful best or average rank.

Unavailable ranks and first-mention offsets are displayed as:

```text
—
```

instead of `NaN`.

The corresponding JSON values remain `null`.

### Answer coverage

Example:

```text
Google AI Mode: 1/3
ChatGPT: 1/1
Gemini: 0/1
```

This means the brand appeared in:

- One of three measured Google AI Mode answers
- The retained ChatGPT answer
- None of the retained Gemini answers

Answer coverage is the primary AI visibility metric.

### Mention count

Mention count is the number of detected non-overlapping references to a known brand alias.

Mention count is supporting detail. It is not market share and should not be compared without considering answer length and answer count.

### First appearance

First appearance records the character position where an audited brand was first detected.

It is not a formal recommendation rank.

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
- Other source

Citation presence does not prove that a source caused a brand to be included or excluded.

---

## Output files

Each audit creates a timestamped directory:

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
06_competitive_visibility_audit.pdf
06_competitive_visibility_audit.json
raw/
```

The notebook also creates a ZIP archive containing the complete audit.

Enable automatic download with:

```python
AUTO_DOWNLOAD_REPORT = True
```

---

## Debug mode

For a normal workshop run:

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
- Research and utility race winners
- Prompt sizes
- Selected search engine
- Search result domains
- API retries
- Google citation redirects
- JSON parsing attempts
- Competitor validation
- Profile recovery
- Temporary API errors

---

## Reliability features

The notebook includes handling for:

- Synchronous and asynchronous scraper responses
- Snapshot polling
- Temporary empty responses
- JSON and NDJSON
- Markdown-wrapped JSON
- JSON repair
- Concurrent Gemini and ChatGPT utility races
- Three-way Google AI Mode research races
- Task-specific first-valid-response validation
- Flexible Markdown report headings
- Oversized AI Markdown fields
- Prompt-size limits
- Google retries and Bing fallback
- Optional operation without traditional search
- Google redirect URLs
- Several parsed SERP URL formats
- Generic keyword rejection
- Conservative brand aliases
- Non-overlapping mention counts
- Partial profile failures
- Redundant ChatGPT and Gemini visibility snapshots
- AI response boilerplate
- Duplicate citation URLs
- Styled PDF export
- Clean display of unavailable numeric values

---

## Approximate request volume

A typical successful audit may include:

- 3 Google AI Mode company-research snapshots
- 1 Gemini and 1 ChatGPT company-structuring request
- Up to 8 Google or Bing search requests, plus a health check and any retries
- 9 Google AI Mode customer-question snapshots
- 3 Google AI Mode competitor-discovery snapshots
- 9 Google AI Mode profile snapshots
- 3 ChatGPT visibility snapshots
- 3 Gemini visibility snapshots
- 1 Gemini and 1 ChatGPT final-report request

Additional requests may occur for:

- Keyword completion
- Strict formatting retries
- Failed triggers
- Search retries
- Snapshot recovery

Research and utility races reduce elapsed time and improve reliability, but every triggered snapshot may contribute to API usage.

---

## Limitations

This is a directional audit, not a statistically significant market measurement.

Important limitations:

- Buyer searches are AI-generated.
- Competitor discovery is AI-assisted.
- Search results vary by time, country, query, selected search engine, and search-engine behavior.
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
- Medical, legal, financial, and regulated claims require independent review.

For recurring monitoring, use the same configuration, country, search engine, and audit focus across multiple dates.

---

## Security

- Never commit a Bright Data API token.
- Store the token only in the `BRIGHTDATA_API_TOKEN` Colab secret.
- Do not include credentials in exported reports.
- Review generated reports before sharing them externally.
- Use the notebook only for permitted analysis of publicly accessible information.

---

## Troubleshooting

### The API token is missing

Confirm that the secret is named exactly:

```text
BRIGHTDATA_API_TOKEN
```

Enable notebook access for the secret.

### Search requests fail

Confirm that:

- `SERP_ZONE` matches an active Bright Data SERP API zone.
- The API token has access to the zone.
- `COUNTRY` uses a valid two-letter country code.
- `SEARCH_ENGINE` is set to `auto`, `google`, `bing`, or `none`.

With `SEARCH_ENGINE = "auto"`, the notebook attempts to fall back from Google to Bing.

If neither engine is available, the audit can continue with AI visibility and source analysis.

### Buyer searches are generic

Set a specific audit focus:

```python
AUDIT_FOCUS = "specific product, service, or customer need"
```

The notebook also rejects known generic placeholder searches before launching Stage 2.

### A snapshot takes several minutes

This can happen with live answer-engine requests.

Research and utility stages start several snapshots concurrently and accept the first result that passes the relevant validation.

Losing snapshots are no longer polled after a winner is found.

Enable:

```python
DEBUG_MODE = True
```

to inspect snapshot IDs, race winners, and polling progress.

### A utility response finishes but is not used

The notebook accepts the first **valid** response, not simply the first completed response.

A response may be rejected because it:

- Is empty
- Does not contain parseable JSON
- Omits required competitor or profile fields
- Omits required report sections
- Contains only interface boilerplate
- Fails another task-specific validation rule

The remaining snapshots continue to be considered until a valid result is found or the race times out.

### Both final-report responses fail

The report validator supports:

- Standard Markdown headings
- Bold headings
- Numbered headings
- Bulleted headings
- Setext headings
- Indented output

If both responses still fail, enable debug mode and inspect the returned validation reason.

### A Google AI Mode source uses `google.com/goto`

The notebook attempts to resolve the redirect and store the final destination.

If the redirect has expired or cannot be resolved, the opaque URL may be omitted from source analysis.

### No competitors are found

Use a more specific `AUDIT_FOCUS`.

Competitor discovery works best when the offering, buyer, and market category are clear.

### Missing measurements display as an em dash

This is expected:

```text
—
```

It means the measurement is unavailable or not applicable.

For example, a brand with zero search appearances has no meaningful best or average rank.

The corresponding JSON value is `null`.

### PDF generation fails

Confirm that the dependency installation cell completed successfully and installed:

```text
markdown
weasyprint
```

If PDF rendering fails, the notebook records a warning and continues exporting the Markdown, JSON, and ZIP files.

### The notebook behaves differently after rerunning individual cells

Start a fresh runtime and select:

```text
Runtime → Run all
```

The notebook contains staged definitions and runtime utility overrides that must be loaded in order.

---

## Workshop flow

For a workshop, participants only need to:

1. Open the notebook in Colab.
2. Add the Bright Data API token to Secrets.
3. Enter the company name, domain, country, search-engine preference, SERP zone, and optional focus.
4. Select **Runtime → Run all**.
5. Review the notebook results, Markdown report, and PDF report.
6. Download the ZIP.

The final discussion can focus on three questions:

1. **Who is visible in traditional search?**
2. **Who appears in AI-generated answers?**
3. **Which pages and source types shape those answers?**

The most interesting result is often disagreement between the three:

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

Review request cost, retry behavior, data retention, and compliance requirements before adapting it for production use.

---

## Inspiration

The original staged competitive-audit concept was inspired by:

```text
https://github.com/ScrapeAlchemist/Competitive-Visibility-Audit
```

This implementation was rebuilt as a category-neutral Google Colab notebook using Bright Data for live Google or Bing Search and AI answer-engine collection.
````
