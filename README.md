# Competitive Visibility Audit

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb)

**Find out what Google and AI answer engines tell potential customers about you—and your competitors.**

This repository contains a no-code Google Colab notebook that audits competitive visibility across:

- Google Search
- Google AI Mode
- ChatGPT
- Gemini

It uses Bright Data to collect live search and AI-answer data, identify direct competitors, analyze the sources shaping AI answers, and generate a downloadable competitive visibility report.

The notebook is category-neutral. It can analyze companies, products, services, consumer brands, professional practices, local businesses, institutions, and other organizations.

## Open the notebook

Click the button:

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb)

Or open the notebook directly:

```text
https://github.com/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb
```

## What the audit does

Enter:

- A company or brand name
- Its official website
- An optional audit focus
- A target country
- A Bright Data SERP API zone

The notebook then:

1. Researches the target using Google AI Mode.
2. Identifies its market, offerings, customers, and positioning.
3. Generates eight non-branded buyer-intent searches.
4. Runs eight Google SERPs in parallel.
5. Asks Google AI Mode three neutral customer questions.
6. Identifies ten likely direct competitors using Google AI Mode.
7. Selects the two strongest direct competitors.
8. Creates profiles for the target and both competitors.
9. Measures visibility in Google AI Mode, ChatGPT, and Gemini.
10. Analyzes which sources shape the AI answers.
11. Produces a final Markdown report.
12. Exports the underlying data as JSON and ZIP.

No Python knowledge is required to run the notebook.

## Example audit types

The notebook adapts its research and comparison criteria to the market being analyzed.

| Type | Example audit focus |
|---|---|
| Consumer product | Facial moisturizer for dry and sensitive skin |
| Medical device | Intraocular lenses and ophthalmic surgical products |
| B2B service | International payroll services |
| Software | Managed web data collection platform |
| Local business | Family dentist in Berlin |
| Hospitality | Boutique hotel in central Berlin |
| Education | Online data science course |
| Financial service | Business checking account |
| Retail | Sustainable running shoes |
| Professional service | Intellectual-property law firm |

Relevant comparison criteria may include:

- Customer needs
- Benefits and suitability
- Features and capabilities
- Ingredients or materials
- Specifications
- Claims and supporting evidence
- Price or price tier
- Availability
- Reputation and trust
- Location
- Service model
- Performance
- Deployment and scalability, when relevant

The notebook is designed not to apply software-specific criteria to unrelated categories.

## Requirements

You need:

1. A Google account with access to Google Colab.
2. A Bright Data account.
3. A Bright Data API token.
4. An active Bright Data SERP API zone.
5. Access to the required Bright Data AI Search scrapers.

The notebook uses:

- Bright Data Google SERP API
- Google AI Mode
- ChatGPT
- Gemini

## Setup

### 1. Open the notebook in Colab

Use the Open in Colab button at the top of this README.

### 2. Add the Bright Data API token

In Google Colab:

1. Open the **Secrets** panel using the key icon in the left sidebar.
2. Add a new secret named:

   ```text
   BRIGHTDATA_API_TOKEN
   ```

3. Paste your Bright Data API token.
4. Enable **Notebook access**.

Do not paste the token directly into a notebook code cell.

### 3. Configure the audit

Use the configuration form near the beginning of the notebook:

```python
COMPANY_NAME = "Your company or brand"
COMPANY_DOMAIN = "example.com"
AUDIT_FOCUS = ""
COUNTRY = "US"
SERP_ZONE = "serp_api1"

AUTO_DOWNLOAD_REPORT = False
DEBUG_MODE = False
```

### Configuration fields

| Field | Required | Description |
|---|---:|---|
| `COMPANY_NAME` | Yes | Company, brand, product, service, or organization to audit |
| `COMPANY_DOMAIN` | Yes | Official domain or website URL |
| `AUDIT_FOCUS` | No | Specific offering, category, audience, or customer need |
| `COUNTRY` | Yes | Two-letter country code for localized Google results |
| `SERP_ZONE` | Yes | Bright Data SERP API zone name |
| `AUTO_DOWNLOAD_REPORT` | No | Automatically download the ZIP when the audit finishes |
| `DEBUG_MODE` | No | Display API, snapshot, retry, prompt, and parsing diagnostics |

The domain can be entered as:

```text
example.com
www.example.com
https://www.example.com/
```

It is normalized automatically.

## Audit focus

Use `AUDIT_FOCUS` when the organization has several products, audiences, or markets.

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

A focused audit generally produces more useful buyer searches, competitor selection, and recommendations.

If `AUDIT_FOCUS` is empty, the notebook attempts to infer the primary offering from the public website.

## Run the audit

After setting the configuration, select:

```text
Runtime → Run all
```

A typical run shows six stages:

```text
[1/6] Company analysis and buyer keywords
      ✓ Company analyzed; 8 buyer keywords generated

[2/6] Google Search and AI Mode competitor discovery
      ✓ 8/8 searches completed
      ✓ 3 Google AI Mode questions completed

[3/6] Direct competitor selection
      ✓ Competitor A
      ✓ Competitor B

[4/6] Target and competitor profiles
      ✓ 3/3 profiles available

[5/6] Cross-engine AI visibility
      ✓ Google AI Mode available
      ✓ ChatGPT completed
      ✓ Gemini completed

[6/6] Final report and export
      ✓ Markdown, JSON, and ZIP created
```

A live audit can take several minutes. Runtime depends on snapshot availability and whether retries are required.

## Methodology

### Stage 1: Company analysis

Google AI Mode researches the target’s public presence.

The research covers:

- Market category
- Products or services
- Positioning
- Primary customers
- Benefits and capabilities
- Relevant claims and attributes
- Differentiators
- Evidence available from public sources

ChatGPT structures the research with web search disabled.

The notebook then generates eight non-branded buyer searches relevant to the inferred market and optional audit focus.

Generic placeholders such as `products and services` or `primary offering` are rejected before search requests are made.

### Stage 2: Google Search

The notebook runs the eight buyer searches through Bright Data SERP API.

The searches run in parallel and can retry temporary response failures.

For each audited brand, the notebook measures:

- SERP coverage
- Best observed position
- Average observed position
- Searches in which the domain appeared

SERP coverage is treated as the primary search-visibility metric. Best and average position describe placement only when a brand appears.

### Stage 2: Google AI Mode questions

Alongside the Google searches, the notebook asks Google AI Mode three neutral customer questions.

The target is not named in those questions.

The results are used to measure:

- Answer coverage
- Brand mentions
- Available citations
- Source domains
- Source types
- First appearance among audited brands

Google AI Mode citation redirects are resolved where possible so that the report can use the actual destination URL rather than an opaque `google.com/goto` URL.

### Stage 3: Competitor selection

Google AI Mode researches and returns ten likely direct competitors.

The selection prompt requires competitors to:

1. Sell or provide their own offering.
2. Serve substantially the same primary buyer.
3. Operate at substantially the same value-chain level.
4. Offer a substitute within the same purchase decision.
5. Be something a customer would realistically compare with the target.

The notebook selects the first two valid direct competitors.

The following should not be treated as direct competitors:

- Retailers
- Marketplaces
- Publishers
- Review sites
- Directories
- Distributors
- Resellers
- Forums and communities
- Industry lists
- Government organizations
- Educational resources
- Customers or downstream providers

For example, a clinic using a medical device is not automatically a competitor to the manufacturer of that device.

### Stage 4: Profiles

The notebook creates three profiles:

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

### Stage 5: AI visibility

The notebook measures the target and competitors in:

- Google AI Mode
- ChatGPT
- Gemini

The audited brands are not named in the neutral visibility prompt.

For ChatGPT and Gemini, three redundant snapshots are triggered and the first valid result is used.

The notebook records:

- Answer coverage
- Brand mentions
- First appearance among audited brands
- Citations
- Source domains
- Source classifications
- Whether ChatGPT used web search

### Stage 6: Final report

ChatGPT generates the final Markdown report with web search disabled.

It receives only a compact evidence packet containing the measured audit results.

The report includes:

- Executive summary
- Competitive landscape
- Google Search visibility
- AI answer-engine visibility
- Source influence
- Positioning and information gaps
- Prioritized recommendations
- Methodology and limitations
- Observed AI sources

## Understanding the metrics

### SERP coverage

```text
2/8 SERPs
```

means the brand appeared in two of the eight measured Google result sets.

Coverage is the primary Google Search metric.

### Best rank

The highest organic position observed for the brand.

A single #1 appearance does not necessarily indicate stronger overall visibility than appearing across several searches.

### Average rank

The average position across searches where the brand appeared.

Brands with zero appearances do not have a meaningful best or average rank.

### Answer coverage

```text
Google AI Mode: 1/3
ChatGPT: 1/1
Gemini: 0/1
```

means the brand appeared in:

- One of three measured Google AI Mode answers
- The measured ChatGPT answer
- None of the measured Gemini answers

Answer coverage is the primary AI visibility metric.

### Mention count

The number of non-overlapping references to a known brand in an answer.

Mention count is supporting detail. It is not market share and should not be compared without considering the number and length of measured answers.

### First appearance

First appearance describes the order in which audited brands appeared in an answer.

It is not a formal market ranking or recommendation rank.

For Google AI Mode, which uses several customer questions, answer coverage should be interpreted before any aggregate first-appearance ordering.

### Source influence

Citations are classified into categories such as:

- Official audited brand
- Official company or product
- Publisher or editorial
- Scientific or professional
- Government or regulator
- Market research or directory
- Social or community
- Retailer or marketplace
- Publisher or other source

Source presence does not prove that a particular source caused a brand to be included or excluded.

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
```

The raw directory may include the underlying records used during research, structuring, competitor discovery, profiling, and reporting.

The notebook also creates a ZIP archive containing the complete audit.

Enable automatic download with:

```python
AUTO_DOWNLOAD_REPORT = True
```

## Debug mode

For public or workshop use:

```python
DEBUG_MODE = False
```

For troubleshooting:

```python
DEBUG_MODE = True
```

Debug mode displays:

- Snapshot IDs
- Snapshot status
- Polling duration
- Prompt sizes
- SERP result domains
- API retries
- AI Mode citation redirects
- JSON parsing attempts
- Competitor-selection details
- Profile recovery
- Temporary API errors

Disable debug mode before committing the public notebook.

## Reliability features

The notebook includes handling for:

- Synchronous and asynchronous scraper responses
- Snapshot polling
- Temporary empty responses
- JSON and NDJSON
- Markdown-wrapped JSON
- JSON repair
- Oversized AI Markdown fields
- Prompt-size limits
- SERP retries
- Google redirect URLs
- Several parsed SERP URL formats
- Generic keyword rejection
- Conservative brand aliases
- Non-overlapping mention counts
- Partial profile failures
- Redundant ChatGPT and Gemini snapshots
- AI response boilerplate
- Duplicate citation URLs

## Approximate request volume

A typical successful audit may include:

- 1 Google AI Mode company-research request
- 1 ChatGPT company-structuring request
- 8 Google SERP requests
- 3 Google AI Mode customer questions
- 1 Google AI Mode competitor-discovery request
- 3 Google AI Mode profile requests
- 3 ChatGPT visibility snapshots
- 3 Gemini visibility snapshots
- 1 ChatGPT report request

Retries can increase these numbers.

Redundant visibility snapshots improve reliability, but every triggered snapshot may contribute to API usage.

## Limitations

This is a directional audit, not a statistically significant market measurement.

Important limitations:

- Buyer searches are AI-generated.
- Competitor discovery is AI-assisted.
- Search results vary by time, country, query, and Google behavior.
- AI answers vary between requests.
- AI source selection can change between runs.
- A small number of prompts cannot represent every customer journey.
- Profiles are public-research summaries, not verified specifications.
- Mention detection depends on known names and aliases.
- First appearance is not a formal ranking.
- Citation presence does not establish causation.
- Source classification is heuristic.
- The audit does not measure market share.
- Recommendations describe possible opportunities, not guaranteed outcomes.
- Regulated, financial, legal, and medical claims require independent review.

Use the same configuration and audit focus for recurring comparisons.

## Security

- Never commit a Bright Data API token.
- Store the token only in the `BRIGHTDATA_API_TOKEN` Colab secret.
- Do not include credentials in exported reports.
- Clear all notebook outputs before committing changes.
- Review generated reports before sharing them externally.
- Use the notebook only for permitted analysis of publicly accessible information.

## Troubleshooting

### The API token is missing

Confirm that the Colab secret is named exactly:

```text
BRIGHTDATA_API_TOKEN
```

Enable notebook access for the secret.

### SERP requests fail

Confirm that:

- `SERP_ZONE` matches an active Bright Data SERP API zone.
- The API token has access to the zone.
- `COUNTRY` uses a valid two-letter country code.

### Buyer searches are too generic

Set a specific audit focus:

```python
AUDIT_FOCUS = "specific product, service, audience, or customer need"
```

The notebook also rejects known generic placeholder searches before Stage 2.

### A snapshot takes several minutes

This can happen with live answer-engine requests.

Enable:

```python
DEBUG_MODE = True
```

to inspect polling progress.

### A Google AI Mode source uses `google.com/goto`

The notebook attempts to follow the redirect and store the final destination.

If the redirect has expired or cannot be resolved, the opaque Google URL may be omitted from the source appendix.

### No competitors are found

Use a more specific `AUDIT_FOCUS`.

Competitor discovery works best when the target’s offering, primary buyer, and market category are clear.

### AI output is not valid JSON

The notebook attempts:

1. Standard JSON parsing
2. Markdown cleanup
3. JSON repair
4. A stricter retry where configured

## Workshop flow

For a workshop, participants only need to:

1. Open the notebook in Colab.
2. Add the Bright Data API token to Secrets.
3. Enter the company name, domain, country, SERP zone, and optional focus.
4. Select **Runtime → Run all**.
5. Review the report.
6. Download the ZIP.

The final discussion can focus on three questions:

1. **Who is visible in Google Search?**
2. **Who appears in AI-generated answers?**
3. **Which pages and source types shape those answers?**

The most interesting result is often disagreement between the three:

> A company can rank in Google but remain absent from AI answers—or appear in an AI answer despite weak measured Google coverage.

## Repository

```text
https://github.com/mhirschberg/competitive_vsibility_audit_bd
```

Notebook:

```text
https://github.com/mhirschberg/competitive_vsibility_audit_bd/blob/main/competitive_visibility_audit_bd.ipynb
```

## Project status

This is a working reference implementation and workshop tool.

It is not an official Bright Data SLA, benchmark, ranking system, or production monitoring product.

Review cost, retry behavior, data retention, output storage, and compliance requirements before adapting it for production use.

## Inspiration

The original staged competitive-audit concept was inspired by:

```text
https://github.com/ScrapeAlchemist/Competitive-Visibility-Audit
```

This implementation was rebuilt as a category-neutral Google Colab notebook using Bright Data for live Google Search and AI answer-engine collection.
