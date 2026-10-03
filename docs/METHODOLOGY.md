# Methodology and Architecture

This document describes the technical workflow behind the Competitive Visibility Audit. For setup and the shorter project overview, see the [README](../README.md).

## Measurement principle

The audit asks neutral questions about a product category or customer need without naming the audited company or its competitors.

This distinction is fundamental. A prompt such as "What are the best options for this need?" measures whether a brand appears naturally. A prompt that contains the brand name measures how an engine describes a brand it was already instructed to discuss.

The audit keeps several signals separate:

- Traditional-search visibility
- AI answer coverage
- Brand mentions and first appearance
- Cited source domains and source types
- Optional public Reddit conversation

It does not combine them into a synthetic market-share or reputation score.

## Pipeline overview

```mermaid
flowchart TD
    A[Configuration] --> B[Target research]
    B --> C[Neutral buyer queries]
    C --> D[Traditional search]
    C --> E[Google AI Mode questions]
    D --> F[Competitor candidates]
    E --> F
    F --> G[Competitor validation]
    G --> H[Target and competitor profiles]
    H --> I[ChatGPT and Gemini visibility]
    G -. optional early start .-> J[Reddit discovery]
    H --> K[Comparable social scope]
    J --> K
    K --> L[Reddit hydration and classification]
    I --> M[Deterministic report]
    L --> M
```

The core audit has six visible stages. When Reddit is enabled, social analysis becomes Stage 6 and final reporting becomes Stage 7.

## Stage 1: Target research and buyer queries

One ChatGPT and one Gemini snapshot research the target concurrently. The first substantive, task-valid answer wins. The provider and both snapshot IDs are retained in the audit record; Google AI Mode is no longer a required research provider.

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

Gemini and ChatGPT then run concurrently to structure the research. The first response that satisfies the expected JSON schema is retained.

The structured result contains eight non-branded buyer-intent queries. Generic placeholders such as `products and services` and `primary offering` are rejected. If keyword completion is required, Gemini and ChatGPT race again.

The optional audit focus narrows the purchase decision used throughout the audit. Without a focus, the engine infers the target's primary offering from public research.

## Stage 2: Traditional search and Google AI Mode

### Traditional search

The eight buyer queries run through Bright Data SERP API in two bounded waves of four. The second wave is skipped only if every query in the first wave fails; one failure does not prevent the remaining measurements.

`SEARCH_ENGINE = "auto"` tries Google first. If more than one buyer query fails, it tries the complete set on Bing and keeps whichever single engine measured more queries; rankings are never mixed. A partial single-engine result remains usable: the report states the measurement count (for example, 7/8), identifies the missing queries, and calculates each brand's coverage only over successful searches. Search is unavailable only when neither engine returns a usable result. Bright Data's Google `#main` selector timeout is treated as a provider failure, not an empty search result, and is not repeated three times for the same query.

Available settings:

- `auto`: try Google, then fall back to Bing
- `google`: use Google only
- `bing`: use Bing only
- `none`: continue without traditional-search measurement

For each audited brand, the engine records:

- Search coverage
- Best observed organic position
- Average observed organic position
- Queries in which the domain appeared

Coverage is the primary signal. Best and average position describe placement only when a brand appears. Failed or unattempted queries are excluded from coverage denominators and shown as a measurement limitation, never as evidence that a brand was absent. If search is disabled or wholly unavailable, the report marks it as not measured rather than assigning zero visibility.

### Google AI Mode questions

Three neutral customer questions are asked without naming the audited brands. First, one three-snapshot Google AI Mode race acts as a bounded health check (120 seconds on a new run). If it fails, the other two questions are not triggered and Google AI Mode is marked unavailable rather than scored as zero. If it succeeds, the other two questions run normally, each retaining its first substantive response. The notebook's **Wait longer** option deliberately extends this check; continuation polls previously saved snapshots.

The retained results provide:

- Answer text
- Brand mentions
- Citations
- Source URLs and domains
- Citation order

Google `/goto` citation links are resolved when possible. Expired or unresolved opaque redirects may be omitted from source analysis.

## Stage 3: Competitor discovery and validation

Traditional-search domains and, when available, Google AI Mode source domains become observed candidates. ChatGPT and Gemini research the market; the first structurally valid response proposes likely competitors. Each candidate is then checked against the locked target scope by another ChatGPT/Gemini race. Provider identity is retained rather than treating either answer as Google AI Mode evidence.

A valid direct competitor must:

1. Sell, manufacture, operate, or provide its own offering.
2. Serve substantially the same primary buyer.
3. Operate at substantially the same value-chain level.
4. Offer a substitute within the same purchase decision.
5. Be something a customer would realistically compare with the target.

The validator rejects publishers, review sites, directories, retailers, distributors, resellers, forums, government organizations, educational resources, and suppliers without a substitutable offering. A marketplace can compete directly with another marketplace when both satisfy the locked scope.

Candidate-validation answers must contain all required yes/no checks and a direct-competitor verdict. Known provider field variants are normalized, but an incomplete answer is treated as inconclusive, not as a series of negative checks; the other provider can still return a complete answer. When discovery independently proposes at least two well-supported direct candidates, a domain seen only in search cannot displace them on the strength of one validation answer. Search presence alone does not establish a shared buyer decision.

The two strongest eligible candidates are selected. If fewer than two pass, the audit stops rather than broadening the scope or silently substituting a search result. Raw discovery and validation responses are saved in the audit's private `raw/` directory before this stop, so a failed run can be diagnosed and resumed.

When Reddit analysis is enabled, social discovery starts immediately after these competitors are known.

## Stage 4: Comparable profiles

The engine creates profiles for:

- Target company
- Competitor 1
- Competitor 2

Each profile uses a first-valid ChatGPT/Gemini research race with structured validation. Depending on the market, fields may describe offerings, customer segments, benefits, features, claims, materials, specifications, use cases, pricing, availability, positioning, differentiators, and public evidence.

A failed profile does not terminate the complete audit. Conservative fallback data is used where possible. Fallback profiles preserve the identity and scope of the corresponding competitor rather than inheriting the target's product name.

## Stage 5: Cross-engine AI visibility

The target and selected competitors are measured in:

- Google AI Mode
- ChatGPT
- Gemini
- Public-web Copilot, when enabled

Google AI Mode visibility is calculated only from its own neutral customer-question answers retained during Stage 2. A ChatGPT or Gemini research answer never substitutes for a Google AI Mode measurement. If the Google sample is incomplete or unavailable, it is excluded from comparative counts and source analysis.

ChatGPT and Gemini each start three snapshots. The two engine races run concurrently, and the first valid response from each engine is retained.

Copilot starts one snapshot in parallel and waits up to three minutes. Its plain `answer_text` is measured rather than the product-card-heavy `answer_text_markdown` field. Only cited `sources` are retained; their `position` values are not interpreted as search ranks. Copilot is a separate buyer-facing answer surface, but its web grounding can draw on Bing, so its evidence is not independent of Bing search. If it times out or fails, it contributes no zero-visibility observations. Perplexity is not used because live scraper tests did not produce timely results.

The audit records:

- Answer coverage
- Brand mentions
- Non-overlapping mention counts
- First appearance among the audited brands
- Citations and source URLs
- Source classifications
- Whether ChatGPT reported using web search

Conservative aliases reduce false positives from common words or overlapping product names.

## Optional Stage 6: Reddit conversation analysis

The social branch is optional because it increases runtime and request usage.

### Comparable cohorts

Four cohorts receive equivalent treatment:

1. Target company
2. Competitor 1
3. Competitor 2
4. Neutral category

When an explicit audit focus is supplied, one same-type comparison offering is chosen for each competitor. When no focus is supplied, the same inferred category is applied to all three brands.

This prevents an audit of a specific product type from silently comparing one company's product with another company's entire portfolio or with an unrelated item.

### Discovery

Three discovery paths are combined:

- Native Reddit keyword discovery
- Google searches restricted to `reddit.com`
- Reddit URLs already present in the buyer-search results

For each cohort, the strongest early native query uses `REDDIT_NATIVE_RACE_WIDTH` identical snapshots. The default width is three. The first successful snapshot wins, while the wider query set continues through site-restricted search discovery.

Results are deduplicated by Reddit post ID. The strongest candidates are hydrated through the Reddit posts dataset. Selection limits community concentration during the first pass so one subreddit does not dominate the sample.

Comment collection is off by default. When selected, `REDDIT_COMMENT_POSTS_PER_COHORT` sends only the first 1–10 selected posts per cohort to the comments dataset; up to three representative comments per post are retained for classification. The collector may return many more billable comment records than are retained, so this is not a strict cost ceiling. Native discovery and enabled comment collection use a one-year lookback by default.

### Classification

Selected threads are classified in small batches. Gemini and ChatGPT race on each batch.

A valid classification response must:

- Return the complete expected schema
- Cover every supplied thread
- Use evidence excerpts that occur verbatim in the supplied thread text
- Preserve the distinction between relevant, irrelevant, and unclassified material

Failed batches are retried one thread at a time. Threads that still cannot be classified remain visible as unclassified and do not contribute to relevance, stance, theme, pain-point, desired-outcome, or experience counts.

Aggregation after classification is deterministic.

### Partial completion

Failure of one discovery path, hydration call, comment collection, or classifier does not terminate the complete audit. Remaining evidence is retained.

The report displays a concise completeness warning. Detailed causes remain in:

- `05_reddit_social.json`
- `05_reddit_snapshot_manifest.json`

The manifest maps every recorded social snapshot to its brand or category, operation, dataset, status, and race outcome.

## Final reporting

The final report is assembled deterministically from validated structured data. No answer engine is asked to rewrite the complete report at the end of the run.

This design prevents a late formatting failure from discarding a successful collection run and makes repeated output easier to compare.

The final artifacts include:

- Markdown report
- Styled PDF
- Structured JSON
- Complete ZIP archive
- Intermediate stage JSON
- Raw retained records and diagnostics

## Concurrency and validation

Concurrency serves two different purposes:

1. Independent work runs in parallel to reduce elapsed time.
2. Identical or equivalent requests race to reduce unpredictable long-tail snapshot latency.

A completed request does not automatically win. Each race accepts the first response that passes task-specific validation. Losing snapshots are no longer polled after a winner has been selected, although every triggered request may still contribute to usage.

Examples of rejected responses include:

- Empty content
- Interface or consent boilerplate
- Unparseable JSON
- Missing required fields
- Generic competitor or product placeholders
- Incomplete classification batches
- Unsupported profile identity or scope

## Approximate request volume

A successful core audit may trigger (each nonwinning successful snapshot can still count toward usage):

- 1 ChatGPT and 1 Gemini target-research snapshot
- 1 Gemini and 1 ChatGPT structuring request
- 8 Google or Bing searches, plus health checks and bounded retries; automatic fallback can run a second complete eight-query batch
- 3 Google AI Mode health-check snapshots; if it works, up to 6 more for the remaining two questions
- 1 ChatGPT and 1 Gemini competitor-discovery snapshot
- Up to 24 ChatGPT/Gemini candidate-validation snapshots: 12 candidates by 2 providers, plus any consistency retries
- 6 ChatGPT/Gemini profile snapshots: 3 brands by 2 providers
- 3 ChatGPT visibility snapshots
- 3 Gemini visibility snapshots

Additional requests may occur for keyword completion, strict-format recovery, retries, or snapshot recovery.

With Reddit enabled, the audit may also trigger:

- Up to 12 native discovery snapshots by default: 4 cohorts by a race width of 3
- Site-restricted Reddit searches for the wider cohort query sets
- Reddit post hydration and, only when selected, separate comment collection
- Gemini and ChatGPT classification requests for each batch
- Per-thread classification retries for failed batches

Exact usage depends on availability, retries, generated queries, selected samples, and validation outcomes. Set `REDDIT_NATIVE_RACE_WIDTH=1` to reduce native discovery usage. Leave `REDDIT_COMMENT_POSTS_PER_COHORT=0` to avoid the unbounded comment-dataset output.

## Interpretation limits

The audit is a directional snapshot, not a statistically significant measurement.

- Search results vary by time, country, query, and engine behavior.
- AI answers can vary between identical requests.
- Citation presence does not establish why a brand was included or excluded.
- First appearance is not a formal recommendation rank.
- Reddit samples are selected evidence, not platform-wide sentiment.
- AI-assisted labels and competitor choices can be wrong.
- Public profiles are not verified product specifications.
- The audit does not measure market share.
- Regulated claims require independent review.

For longitudinal comparison, keep the company, domain, focus, country, and search-engine selection consistent across runs.
