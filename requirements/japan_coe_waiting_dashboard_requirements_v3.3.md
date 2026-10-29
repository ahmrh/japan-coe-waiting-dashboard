# Japan COE Waiting Dashboard

**Project:** `japan_coe_waiting_dashboard`  
**Requirements version:** 3.3  
**Last updated:** 29 October 2026

## What we're building

Build a public dashboard showing how Certificate of Eligibility (COE) applications move through Japan's regional immigration offices each month. The main view must make it easy to see how many cases were carried into a month, how many new cases arrived, how many were completed, what those completions were, and how many cases may still be waiting at month-end. Every figure should be broken down by the immigration bureau or jurisdiction reported in the official statistics.

The primary source is the monthly e-Stat table for COE applications received and processed. Processing-time reports and applicant experiences are supporting context; they must not displace the monthly queue-and-outcome view.

This is an information tool, not an immigration prediction service. Aggregate workload figures can describe the flow of cases through offices, but they cannot determine when an individual applicant's COE will arrive.

## 1. Main requirements

1. Use **Vue 3, TypeScript and Vite** for the frontend.
2. Keep the app easy to run locally. Use **Python with FastAPI** for the backend and **SQLite** as the default database. PostgreSQL can be supported for a hosted deployment. Do not introduce Spring Boot unless the repository already depends on it and switching would create unnecessary work.
3. Make the monthly COE workload and outcome visualization the main feature. Use the official e-Stat table listed below as the primary dataset, classified by processing bureau/jurisdiction.
4. Check for new source data when a user opens the dashboard. Use caching and request limits so opening the page does not trigger a full scrape every time.
5. Save validated data locally so the dashboard remains usable when a source is down.
6. Clearly show each source's publication date, the period covered, the last successful fetch, and any limitations.
7. Use the published monthly count categories faithfully. Do not call the derived month-end balance an official published figure unless the source explicitly publishes it, and never derive duration statistics from these count tables.
8. Follow Google's current Material Design guidance for a modern, accessible interface.
9. Include tests for calculations, ingestion, refresh failures, and the main user flows.
10. Keep the product general-purpose. Do not include any individual applicant's personal COE timeline, employer, salary, location, immigration office, or career plan.

## 2. Data sources

### 2.1 Official processing-time reports

Use the Immigration Services Agency of Japan (ISA) as the primary source for published processing periods:

- Official site: <https://www.moj.go.jp/isa/>
- COE / status-of-residence information: <https://www.moj.go.jp/isa/applications/status/gijinkoku.html>
- Find the latest published processing-period tables or reports from the ISA, including relevant monthly reports.

The ingestion code must discover and verify the actual current page, file links, formats, units and reporting periods. Do not assume that a PDF or page will keep the same URL or layout forever. If a source changes format, report the failure rather than silently importing incorrect values.

### 2.2 Primary dataset: monthly COE applications received and processed

Use this e-Stat table first:

<https://www.e-stat.go.jp/dbview?sid=0004049310>

The official table is titled **地方出入国在留管理局管内別 在留資格認定証明書交付申請の受理及び処理人員**. It is published monthly and separates the figures by regional immigration bureau / jurisdiction and, where available, subordinate offices or branches.

The currently listed monthly categories include:

| Official field | Required display meaning | Japanese label |
|---|---|---|
| `受理_旧受` | Cases carried into the month from earlier periods / opening workload, after confirming the official table notes | Old receipts / carried-over cases |
| `受理_新受` | Newly received cases in the month; the official definition may include transfers from other offices | New receipts |
| `受理_総数` | Total cases available in the month's receipt/workload count; validate against old + new | Total workload received |
| `既済_総数` | Total cases processed/closed during the month | Total completed |
| `既済_交付` | Cases resulting in COE issuance | Issued |
| `既済_不交付` | Cases resulting in non-issuance/refusal | Not issued |
| `既済_その他` | Other completed cases; may include transfers to another office and cases no longer requiring processing | Other closures / transfers |

Before hardcoding labels or formulas, fetch the source metadata and its official notes. Preserve the original Japanese field names in the data model so a future source change can be detected. Preserve the unit exactly as published (the current table reports `人`). In the UI, describe the figures using the source's own definition; do not silently relabel a count of people as a count of application forms if the metadata does not support that interpretation.

The table's regional dimension includes aggregate jurisdictions such as a bureau's `管内` as well as individual bureaus, branches or offices. The UI must preserve this hierarchy. It must not add a parent jurisdiction total to its child office totals, since that would double-count cases.

The bureau value describes the office/jurisdiction used in the official statistics. Do not imply that it identifies an applicant's home prefecture or nationality.

At the time this requirement was revised (29 October 2026), e-Stat listed August 2026 as the latest monthly COE table, published on 26 October 2026. This is only a verification snapshot; the implementation must discover newer periods automatically. The table is an operational count dataset, not a case-level duration dataset. It is the source for the dashboard's core monthly queue and outcome charts, not for average or median personal waiting times. If an official API is suitable, prefer it over scraping the rendered page. The API may require an e-Stat application ID; keep credentials in environment variables and document setup. If the public download is usable without an API key, support that path for an easy local setup.

### 2.3 Other official sources

The app may use other Japanese government or immigration sources if they add relevant information. Each source needs a record containing:

- Source name and owner
- Original URL
- What it measures
- Unit and population covered
- Publication frequency, if known
- Most recent period available
- Date last checked successfully
- Known gaps or comparability issues

Official sources should take priority over commentary. If two sources use different definitions, keep them separate unless a documented, defensible mapping is possible.

### 2.4 Applicant reports and public discussion

Applicant experiences can provide context that official aggregates do not, but they are not a representative sample by default.

The first release can link to public discussions or summarise them manually with citations. Automated collection is optional and should only be added when the site permits it and the collection method respects its terms, robots rules, rate limits, privacy expectations and copyright. Do not bypass login restrictions, access controls or anti-bot measures.

If the app later accepts user-submitted experiences, participation must be voluntary. Explain what will be stored and how it will be used. Do not collect names, passport details, application numbers, addresses, employer contact details or uploaded immigration documents. Allow users to submit only the minimum dates and categories needed for analysis.

Keep applicant reports separate from official statistics in charts, calculations and written summaries.

## 3. Statistical approach

There is no single statistic that fully describes COE waiting times. The dashboard should choose a useful measure based on what each source actually provides.

### 3.1 Classify data before analysing it

Every imported dataset must be identified as one of the following:

- **Published aggregate:** for example, an official monthly average processing period.
- **Completed case records:** each eligible application has a start date and a known completion date.
- **Pending case records:** the start date is known, but the application has not completed by the observation date.
- **Counts or workload measures:** applications received, processed, issued, refused or withdrawn, where published.
- **Self-reported experiences:** voluntarily supplied or publicly reported cases with varying completeness and selection bias.

Store the classification and definitions with the source metadata. Only enable calculations supported by that data type.

### 3.2 Statistics for completed case durations

When valid case-level durations are available, consider these measures:

| Measure | Why it may help |
|---|---|
| Mean | Overall arithmetic average; sensitive to unusually long cases |
| Median (P50) | The middle observed duration; less affected by extreme values |
| Mode | Most common duration or duration band, if meaningful |
| Minimum and maximum | Observed range; particularly sensitive to unusual records |
| Quantiles (P10, P25, P50, P75, P80, P90, P95) | Show how duration varies across cases |
| Interquartile range (IQR) | Spread of the middle half of cases |
| Standard deviation and variance | Describe dispersion when the distribution makes them useful |
| Median absolute deviation (MAD) | Robust measure of spread |
| Trimmed or winsorised mean | Optional sensitivity checks when extreme values distort the ordinary mean |
| Skewness | Helps show whether a small number of long cases stretch the distribution |

Do not display every measure just because it can be calculated. Prioritise metrics that users can interpret, and put less familiar measures behind a short explanation.

### 3.3 Useful charts for duration data

Use the chart that matches the question:

- **Line chart:** changes in an official published processing-time figure over time.
- **Histogram:** how many completed cases fall into each duration range.
- **ECDF:** the proportion of completed cases finished by each number of days.
- **Box plot:** compare medians, quartiles and outliers across clearly comparable groups.
- **Quantile chart:** show how the middle and slower parts of the distribution change over time.
- **Cohort comparison:** compare cases filed in the same period, if reliable case-level dates exist.

A chart based on case-level records must state its sample size, date range, eligibility rules and whether it includes only completed applications.

### 3.4 Pending cases and survival analysis

Pending applications matter because a dataset containing only completed cases can make waiting times look shorter than they are. If reliable records include both pending and completed cases, treat pending durations as right-censored observations rather than as completed waiting times.

Possible methods include:

- Kaplan–Meier estimates of the probability an application remains pending after a given number of days
- Estimated time-to-event quantiles, when they can be estimated from the data
- Restricted mean survival time (RMST) over a clearly stated time horizon
- Competing-risk analysis for issuance, refusal and withdrawal, if dates and outcome categories are sufficiently complete

These methods are optional, not a requirement to force into the first release. They must not be used on aggregate tables that lack individual start dates, event dates and outcome information. Explain censoring in plain language wherever it appears. Do not present a survival estimate as a personal prediction.

### 3.5 Trends and comparisons

Where the data supports them, the dashboard may show:

- Month-to-month and year-to-year changes
- Rolling averages or medians
- Changes in quantiles
- Differences between application categories or regions
- Confidence intervals or other uncertainty ranges
- Seasonal patterns, provided there is enough historical data

Compare like with like. A change in the mix of application categories can affect an overall figure, even when the processing time within each category has not changed. Show category definitions and the time period alongside comparisons.

### 3.6 Core monthly queue-and-outcome calculations

This section takes priority over optional waiting-time analysis in the first release. Use the official monthly COE table and calculate separately for every reported bureau/jurisdiction and month.

The primary concepts are:

- **Opening workload / carried-over cases:** `受理_旧受`, once its definition is confirmed from the official notes.
- **New arrivals:** `受理_新受`.
- **Total workload available during the month:** `受理_総数`; check whether it equals `受理_旧受 + 受理_新受` for each bureau-month.
- **Completed cases:** `既済_総数`.
- **Issued:** `既済_交付`.
- **Not issued:** `既済_不交付`.
- **Other closures / transfers:** `既済_その他`.
- **End-of-month cases still pending:** use a directly published `未済` value if the monthly source provides one. If it does not, calculate `受理_総数 - 既済_総数` only after confirming that the table's definitions support this balance and validating the calculation against source totals and adjacent months. Label this value **calculated pending balance**, not an official published figure.

Validate the following identities where applicable:

- `受理_総数 = 受理_旧受 + 受理_新受`
- `既済_総数 = 既済_交付 + 既済_不交付 + 既済_その他`
- `calculated pending balance = 受理_総数 - 既済_総数`

If any identity fails because of source definitions, missing values, rounding, transfers or a revised table, do not silently force the values to reconcile. Record the discrepancy and withhold the affected derived figure until the reason is understood.

The official definitions may count transfers into a jurisdiction under new receipts and transfers out under completed/other. Explain this in the chart notes. Never interpret `既済_その他` as only withdrawals: it can include transfers and other cases where processing is no longer required. Do not treat processed divided by workload as an approval rate or as the probability that an individual application will finish.

### 3.7 Rules for reporting results

- Mean and average refer to the same arithmetic measure; do not present them as separate metrics.
- If the source publishes only a mean, show the published mean and mark unsupported measures as unavailable.
- Do not infer a median, percentile, standard deviation, confidence interval or distribution from an aggregate mean alone.
- Label observed sample statistics separately from official published values and model-based estimates.
- Display the number of records and the period covered wherever a statistic is shown.
- Do not hide missing data or silently replace it with zero.
- Explain whether the duration starts at application submission, acceptance by immigration, or another defined point, and whether it ends at COE issuance or a different event.
- Keep calendar days and business days distinct. Do not convert between them without a documented rule.
- Use sensible rounding; avoid implying more precision than the source provides.
- If a sample is too small or too biased for a reliable comparison, say so instead of ranking it.

## 4. Dashboard layout

The main page must focus on **COE Processing — Monthly Workload and Outcomes**. A visitor should be able to answer, for any month and bureau: how many cases were carried in, how many arrived, how many were completed, what happened to those cases, and how many remained pending or are estimated to remain pending.

### 4.1 Main chart: monthly workload versus completed outcomes

Provide a month selector and a bureau/jurisdiction selector. The default view should show the latest month with validated data and a national overview, followed by a comparison of the reported bureau jurisdictions.

For each selected bureau and month, show these values together:

1. **Carried-over cases** (`受理_旧受`).
2. **New arrivals** (`受理_新受`).
3. **Total workload available** (`受理_総数`).
4. **COEs issued** (`既済_交付`).
5. **Not issued / refused** (`既済_不交付`).
6. **Other closures or transfers** (`既済_その他`).
7. **Total completed** (`既済_総数`).
8. **Pending at month-end** (`未済` if directly published, otherwise the validated derived balance described in section 3.6).

Use paired stacked bars rather than one misleading stack: one bar represents workload available (carried-over + new); a second represents monthly completions split into issued, not issued, and other. Show pending at month-end as a separate KPI or line, not as another completion outcome.

The chart legend must spell out the outcomes. Do not use vague labels such as “success” and “failure”. Keep “not issued” consistent with the source wording; a tooltip can say “the official category is 不交付” rather than implying more detail than the data provides.

### 4.2 Bureau comparison table

Include a sortable table with one row per selected bureau/jurisdiction and the latest available month as columns:

| Column | Meaning |
|---|---|
| Bureau / jurisdiction | Name as provided by the source |
| Carried-over | `受理_旧受` |
| New arrivals | `受理_新受` |
| Total workload | `受理_総数` |
| Issued | `既済_交付` |
| Not issued | `既済_不交付` |
| Other closures / transfers | `既済_その他` |
| Total completed | `既済_総数` |
| Pending at month-end | Official `未済`, or a clearly marked calculated balance |
| Change in pending | Difference from the previous comparable month, only if both values are valid |
| Throughput ratio | `既済_総数 / 受理_総数`, labelled as share of available workload completed, **not** an approval rate or probability of completion |

Sort by any numeric column. Let users select a row to open that bureau's monthly history. Use a clear indication for unavailable or invalid values instead of displaying zero.

### 4.3 Monthly trends

For the selected bureau, provide a monthly trend view with separate series for:

- Carried-over cases
- New arrivals
- Total workload available
- Total completed
- Issued, not issued and other completions
- Pending balance at month-end, if available or validly derived

Use a line chart for trend comparison and grouped/stacked bars for monthly counts. Keep the axis unit and selected period visible, using the source-defined unit (currently `人`). Users must be able to switch between the national total, jurisdiction-level totals and detail-office views where provided by the dataset.

### 4.4 Bureau heatmap

Add a bureau-by-month heatmap with a metric selector. Suggested metrics are new arrivals, completed cases, pending balance and throughput ratio. The default should be pending balance if valid data exists; otherwise default to new arrivals. Include the raw value on hover and provide an accessible table alternative.

### 4.5 Hierarchy and double-counting rules

The source includes regional aggregate rows (for example, a bureau's whole jurisdiction) as well as office/branch details. Provide two clearly separated modes:

- **Bureau comparison:** show non-overlapping jurisdiction totals only.
- **Office details:** show the child offices/branches under the selected jurisdiction, without including the parent total as another item in sums or rankings.

The national total is supplied by the official table when available. Prefer that source-defined total over adding together hierarchy rows. If the total is recalculated, define the included categories and prove there is no overlap.

### 4.6 Source notes on the page

Place a short “How to read this chart” link beside the main visualization. It must explain:

- `旧受` represents cases carried from an earlier period, using the source's published definition.
- `新受` represents new receipts and may include transfers from another office.
- `既済` means processed/completed for statistical purposes; transfers to another office may be included.
- `その他` is broader than withdrawals and can include transfers or cases that no longer require processing.
- A derived pending balance is calculated by the app and is not represented as directly published by e-Stat.
- These are workload counts. They do not show the average number of days an individual waits and cannot predict the decision or completion date of a specific case.

### 4.7 Supporting pages

Keep the rest of the site small and secondary to the monthly workload page:

- **Processing time:** official published duration reports and historical trends, if available.
- **Waiting-time distribution:** only if there is a reliable dataset with appropriate case-level durations.
- **Applicant experiences:** optional community reports, visibly separated from official statistics.
- **Sources and methods:** source URLs, definitions, update history, formulas and known limitations.

### Filters

Filters should reflect fields that actually exist in the source. At minimum, support month/year and bureau/jurisdiction. Category, visa status or nationality filters must not appear unless an official source provides those dimensions for the relevant chart.

## 5. “Current conditions” summary

The dashboard should produce a concise, evidence-based summary from the latest validated data. It should not make up an explanation for a change.

A summary might cover:

- The latest month available in the COE workload table
- New arrivals, carried-over workload, total completed, and the latest pending balance by bureau
- Whether workload or pending cases rose or fell compared with the previous comparable month
- The mix of monthly completions: issued, not issued, and other
- Whether a pending figure is directly published or calculated by the application
- Whether the data is delayed, incomplete or fails a reconciliation check
- The main limitations of the evidence

Avoid saying an office is “faster”, “slower” or “backlogged” on the strength of one count alone. Explain which measured quantity changed and over what period.

Generate statements from defined rules and the actual stored observations. For example, a statement that a metric increased must include the comparison period and the measured change. If the data is too incomplete to support a conclusion, say that no reliable conclusion can be drawn.

An LLM is not required for this feature. If one is used later to improve wording, it must only receive validated facts, must not invent causes or forecasts, and must retain links to the supporting sources.

## 6. Refresh pipeline

The dashboard should check for updates when a session opens, while avoiding repeated downloads and unnecessary load on source websites.

### Refresh behaviour

1. When the frontend starts, request the dashboard data and source-status summary from the backend.
2. The backend checks the database to see when each source was last checked.
3. If a source is due for a check, queue or run a refresh using a per-source lock so two requests do not fetch the same source at once.
4. Fetch the source politely, respecting published API guidance, rate limits and cache headers.
5. Parse the source and validate the results before changing the stored dataset.
6. Save a successful new snapshot and update the dashboard cache.
7. If fetching or parsing fails, retain the last known good data and show a clear stale-data notice.
8. Return available data immediately where possible; users should not have to wait for every source to finish refreshing before seeing the dashboard.

A request to the dashboard must not start an unlimited or unbounded scrape. Use a short refresh timeout and allow longer work to continue in a background task if needed.

### Scheduled checks

Session-open refresh is not a substitute for scheduled checks. Add a lightweight scheduled job so the dataset can update even when nobody visits the site. Start with a conservative daily check, then use the source's publication schedule to adjust it.

The scheduler must not run twice accidentally when multiple backend workers are started. SQLite is fine for a single-instance local app; if deploying multiple instances, use a shared database and a proper scheduler/lock strategy.

### Source-specific handling

- Prefer official APIs or downloadable data files over scraping rendered HTML.
- Keep parsing code separate for each source.
- Store the raw response or a reproducible snapshot where permitted, plus fetch time, source URL, content hash and parser version.
- Detect whether a source has actually changed before rebuilding its observations.
- Validate field names, periods, units, row counts and required values.
- Do not overwrite a good snapshot with an empty response, malformed table or suspicious partial extract.
- If the source changes layout, mark the source as needing attention and preserve the last successful data.
- Never hardcode the latest month as a permanent constant; discover the latest period from the source.
- Do not bypass authentication, paywalls, robots restrictions, anti-bot controls or access permissions.

### Freshness indicators

For every source, store and show:

- Last checked
- Last successful fetch
- Latest publication date, if known
- Latest data period
- Current status: current, stale, refresh failed, parser needs attention, or not yet configured
- Error summary that is useful to maintainers but does not expose secrets

A source is not necessarily stale just because its data period is old. Some official reports are released with a lag. Show the publication date and period so visitors can judge this themselves.

## 7. Technical design

### Frontend

Use Vue 3 with TypeScript and Vite. Use a maintained charting library that supports responsive layouts, tooltips, accessible labels and table alternatives. Keep data fetching and chart components separate so chart changes do not affect ingestion logic.

Suggested frontend structure:

```text
src/
  components/
    charts/
    layout/
    status/
    data-tables/
  pages/
    OverviewPage.vue
    ProcessingTimesPage.vue
    DistributionPage.vue
    ApplicationVolumePage.vue
    SourcesPage.vue
  services/
    api.ts
  composables/
  types/
  styles/
```

The exact file structure can change if the repository already has a sensible convention.

### Backend

Use Python and FastAPI for a small, straightforward API. Use SQLite by default so a developer can clone the project and run it without setting up a database server. SQLAlchemy and Alembic are suitable for database access and migrations. Keep PostgreSQL support as an option for a hosted multi-user deployment.

Suggested backend structure:

```text
backend/
  app/
    main.py
    api/
    models/
    schemas/
    services/
      sources/
      statistics/
      refresh/
    repositories/
    jobs/
    config.py
  tests/
```

Use a supported Python version and pin dependencies. Choose well-maintained libraries for HTTP requests, HTML/PDF parsing and statistics. Avoid adding a queue service or extra infrastructure until the workload requires it.

### Running the app

A new developer should be able to run it with a small number of documented commands. Provide:

- `.env.example` with safe defaults and no secrets
- One-command Docker Compose startup for the full app
- Native setup instructions for frontend and backend
- Automatic database creation/migrations in development
- A command to refresh all configured sources manually
- A command to run tests
- Clear logs when a source cannot be fetched or parsed

The app should work without API keys for official sources unless an official service explicitly requires one. Optional community integrations must remain disabled until configured.

### API

At minimum, provide endpoints equivalent to:

- `GET /api/overview` — latest figures, summary and source freshness
- `GET /api/processing-times` — published processing-time observations
- `GET /api/distributions` — supported case-level distribution metrics, or a clear unavailable response
- `GET /api/application-volumes` — e-Stat and other count observations
- `GET /api/sources` — source definitions and status
- `GET /api/refresh/status` — current and recent refresh activity
- `POST /api/refresh` — request a refresh, with rate limiting and duplicate-job protection

Document the endpoints with FastAPI's OpenAPI support. Do not expose a public endpoint that allows arbitrary URLs to be fetched; that would create a server-side request forgery risk.

## 8. Minimum data model

Use a small schema that records where each value came from. Adjust it after inspecting the source data; do not force incompatible sources into identical columns.

### `data_source`

Stores the source name, owner, URL, source type, parser identifier, update policy and current health status.

### `source_snapshot`

Stores each successful fetch or publication snapshot, including the fetch time, publication date if known, reporting period, source URL, content hash, parser version and validation result.

### `processing_time_observation`

Stores a published processing-time value, its unit, application category, reporting period and source snapshot. Record whether the value was published or calculated.

### `coe_monthly_workload_observation`

Stores the exact monthly COE count fields by source-defined bureau/jurisdiction and reporting month. Keep each source category as a separate measure, with the original Japanese category code/name, value, unit, row hierarchy, and snapshot reference. It must be possible to store at least:

- `accepted_total` (`受理_総数`)
- `old_receipts` (`受理_旧受`)
- `new_receipts` (`受理_新受`)
- `completed_total` (`既済_総数`)
- `issued` (`既済_交付`)
- `not_issued` (`既済_不交付`)
- `completed_other` (`既済_その他`)
- `pending_official` (`未済`, when the source supplies it)
- `pending_calculated` (nullable; only filled after the balance is validated)

Also store whether a row is a national total, bureau-jurisdiction aggregate, or subordinate office/branch. Do not store a parent and its child rows as if they were additive peers.

### `coe_volume_observation`

Use for other count measures not covered by the specific monthly workload table, with reporting period, geography, measure name, value, unit and source snapshot.

### `community_case_report` (optional)

If community submissions are added, store only the minimum fields needed for analysis: a random record ID, application category, relevant dates or duration, outcome status, submission date and consent/quality flags. Do not store names or immigration identifiers. Establish retention and deletion rules before launching this feature.

### `refresh_run`

Records the start and finish time, source, status, number of rows imported, validation result and a safe error summary.

Use database migrations. Keep a source reference on every observation so a displayed value can be traced back to its origin.

## 9. Validation and data quality

Do not treat a successful HTTP response as proof that the data is correct.

For every import, check:

- Required fields exist
- Dates and reporting periods can be parsed
- Units are known
- Numeric values are valid and within plausible bounds
- Rows are not duplicated
- The newest period is not older than the existing data without an explanation
- The import is not suspiciously empty or incomplete
- The resulting observations can be traced to a source snapshot

For processing-time reports, check that values use the correct unit and application category. For e-Stat, validate the meanings of each count and regional label before calculating comparisons.

For the monthly COE workload table, validate these relationships for each bureau and month before publishing the figures:

- The published total received agrees with old receipts plus new receipts, when the source definitions say it should.
- The published total completed agrees with issued + not issued + other, when all components are present.
- Any calculated pending balance is non-negative and reconciles across adjacent months where the data definitions allow that check.
- Transfer-in and transfer-out categories are handled according to the official notes.
- Parent jurisdiction rows are not added to child office/branch rows.

When a check fails, show the source's published values but mark the derived figure as unavailable and record the discrepancy for review. Do not silently alter source figures to make a balance work.

When a validation check fails, do not publish the suspect observations. Keep the previous validated data and surface a source-health warning.

## 10. Material Design and visual style

The dashboard should look like a polished, current Google Material Design application—not a generic admin template. Follow current Material Design 3 guidance and use a maintained Vue-compatible component library if it meets the requirements. Verify its maintenance status, accessibility and licence before committing to it.

Aim for a calm, modern interface:

- Clear hierarchy and readable typography
- Material 3 colour roles and tonal surfaces
- Rounded cards and controls used consistently
- Comfortable spacing without wasting screen space
- Subtle motion only where it helps explain an interaction
- Light and dark themes
- Responsive navigation and charts
- Consistent loading, empty, error and stale-data states

Avoid excessive gradients, decorative animations, oversized KPI cards and unnecessary glass effects. The data should be the focus.

### Charts and tables

- Give every chart a descriptive title, units, reporting period and source.
- Label axes and explain unfamiliar statistical terms.
- Include tooltips, but do not rely on colour alone to convey meaning.
- Use consistent scales when comparing groups.
- Provide a table or text summary for every important chart.
- Distinguish official published values, app-calculated statistics and community reports.
- Show missing data as missing, not zero.
- Make chart controls usable on touch screens and with a keyboard.

Aim for WCAG 2.2 AA accessibility, including readable contrast, keyboard navigation, visible focus indicators, sensible heading order and screen-reader labels. Respect reduced-motion settings.

A component library is a starting point, not a reason to ignore the design. Keep reusable tokens for colour, spacing, typography, elevation and shape.

## 11. Privacy and safe use

The public dashboard should not require accounts.

- Do not embed private details from an individual applicant's immigration case.
- Do not collect personal information unless a later feature genuinely needs it and the user is clearly informed.
- Never request passport numbers, residence-card numbers, application IDs or scans of immigration documents.
- Do not log secrets or submitted personal information.
- Keep API keys and configuration in environment variables.
- Add rate limits to refresh endpoints and any community submission form.
- If community reports are implemented, provide a privacy notice and a way to request deletion.
- Follow the source site's terms and applicable privacy and copyright rules.

Add a visible disclaimer that the dashboard provides general information and is not legal advice. Users should contact the relevant immigration office or their employer for case-specific questions.

## 12. Testing

Tests should cover the data and the user experience, not just whether the pages render.

### Unit tests

Test:

- Parsing dates, durations, units and reporting periods
- Each supported statistical calculation
- Quantiles and spread measures on known example data
- Right-censoring logic and survival analysis, if implemented
- Validation of malformed, duplicate and incomplete rows
- Comparison and trend calculations
- Freshness-state rules

Include tests proving that an aggregate mean does not produce a fake median, percentile or distribution.

Also test the monthly COE queue calculations with fixtures containing old receipts, new receipts, all completion outcomes, transfers and missing values. Verify that totals reconcile, a calculated month-end pending count is labelled as derived, and it is withheld when the source fails validation. Include fixtures where parent and sub-office rows overlap to prove that bureau charts do not double-count them.

### Integration tests

Use saved sample responses or fixtures from each source. Do not depend on a live government site for every test run.

Test:

- Source fetch and parsing
- Database persistence and migrations
- Duplicate refresh prevention
- Failed downloads and parser changes
- Retaining the last good data after a failure
- Discovering a newer publication period
- API response schemas and error handling

### Browser tests

Use Playwright or a comparable tool to verify:

1. A new developer can start the app using the documented instructions.
2. The overview displays the latest stored data and source freshness.
3. Charts show units, periods and source links.
4. Filters only show available categories.
5. Missing or stale data is explained clearly.
6. The layout works on desktop and mobile.
7. Keyboard users can navigate controls and inspect equivalent data tables.
8. A failed refresh does not blank the dashboard or erase previously validated data.
9. The dashboard never labels e-Stat volume counts as waiting-time statistics.
10. The dashboard never presents an aggregate statistic as a guaranteed individual outcome.

## 13. Deployment and maintenance

Keep deployment simple. A single small server is enough for an initial public release. Use PostgreSQL if the application later needs multiple instances or higher write concurrency.

Document:

- Environment variables and configuration
- Database backup and restore
- How to run a manual refresh
- How to inspect failed refresh jobs
- How to update dependencies
- How to add or repair a source parser
- How to disable a broken source without taking down the dashboard

Log source failures with enough detail to diagnose them, but do not expose credentials or private information. Add a basic health endpoint and a visible source-status page.

## 14. Suggested build order

Build the smallest reliable version first. The advanced statistics and community features can wait until there is suitable data.

### Phase 1 — Inspect and verify sources

- Inspect the existing repository before changing its structure.
- Open the current ISA and e-Stat pages and confirm their latest available data, formats, fields, units and definitions.
- Save representative source fixtures for tests.
- Write down what each source can and cannot support statistically.

**Deliverable:** a source inventory and a working parser for the monthly COE workload table, including official field definitions and bureau hierarchy.

### Phase 2 — Backend and storage

- Set up FastAPI, SQLite, migrations and the source metadata model.
- Import and validate official processing-time and application-volume data.
- Add the initial API endpoints.
- Test the ingestion process against saved fixtures.

**Deliverable:** repeatable imports and API responses for carried-over cases, new arrivals, workload totals, completed outcomes and validated pending balance, by bureau and month.

### Phase 3 — Dashboard

- Build the overview, processing-time and application-volume views in Vue.
- Add clear source citations, reporting periods and freshness indicators.
- Apply the Material Design system and test responsive layouts.
- Include table alternatives for charts.

**Deliverable:** a usable bureau-by-month dashboard based on real official data, with workload-versus-outcomes bars, bureau comparison table, monthly trends and a metric heatmap.

### Phase 4 — Refresh and reliability

- Add refresh-on-session-open with caching and duplicate-job protection.
- Add a scheduled source check.
- Test network failures, malformed source data and stale-data states.
- Document local startup and maintenance.

**Deliverable:** an app that updates safely and remains usable when a source is unavailable.

### Phase 5 — Further analysis

- Add distribution and survival-analysis charts only if suitable case-level records become available.
- Consider voluntary community submissions after privacy, sampling and moderation requirements are settled.
- Add more official sources when they materially improve coverage.

**Deliverable:** additional analysis backed by suitable data, rather than speculative charts.

## 15. Acceptance criteria

The first public version is ready when:

- The main page shows monthly COE workload and outcomes from the e-Stat table, classified by source-reported bureau/jurisdiction.
- Users can distinguish carried-over cases, new arrivals, total workload, issued, not issued, other closures/transfers, total completed and month-end pending cases.
- The app shows an explicit month-end pending value only when it is officially published or the defined calculation has passed validation; calculated values are labelled as such.
- Bureau totals and subordinate office/branch values are shown in separate hierarchy modes and never double-counted.
- The main visualization includes the paired workload/completion chart, a bureau comparison table, monthly trends and a bureau-by-month heatmap.
- The chart notes explain that transfers may count as new receipts or completed/other and that `その他` is not limited to withdrawals.

- A developer can run it locally using the documented steps without setting up a Java runtime or a separate database server.
- The overview uses imported official data, not hardcoded demo values.
- Every displayed statistic has a clear definition, unit, period and source.
- Visitors can tell when the data was published and when the app last checked it.
- Opening the dashboard checks for updates without causing repeated or unbounded downloads.
- Failed refreshes leave the last validated data available.
- The ISA processing-time series and e-Stat volume series are kept distinct.
- Unsupported statistics are marked unavailable rather than inferred from insufficient data.
- The interface follows current Material Design guidance and works on mobile and desktop.
- The main statistical, ingestion, API and browser tests pass.
- The app does not store or display any one applicant's private immigration history.
- Source limitations and the non-predictive nature of aggregate statistics are explained clearly.

## 16. Instructions for the coding agent

Before writing code, inspect the repository and verify the live source formats. Do not assume this document has already resolved every implementation detail.

Build the official monthly COE workload parser first, then implement the bureau-by-month workload and outcome visuals before optional duration analysis. Use real data as soon as the parser works, and keep source-specific parsing separate from calculation and presentation code.

If a source cannot support a requested metric, explain the limitation and leave that metric unavailable. Do not substitute invented values or generated sample data in production. Sample fixtures are fine for automated tests and clearly labelled development previews.

Prefer the smallest design that meets the requirements. Do not add accounts, a message queue, complex cloud infrastructure or an LLM summarisation service unless there is a demonstrated need. If an implementation choice differs from this document, record the reason and update the documentation.

## Source links

- e-Stat COE statistics table: <https://www.e-stat.go.jp/dbview?sid=0004049310>
- Immigration Services Agency of Japan: <https://www.moj.go.jp/isa/>
- Immigration statistics terminology (official glossary): <https://www.moj.go.jp/isa/policies/statistics/toukei_nyukan_yougo.html>
- Status of residence / Engineer, Specialist in Humanities, International Services information: <https://www.moj.go.jp/isa/applications/status/gijinkoku.html>
- Material Design: <https://m3.material.io/>
- FastAPI documentation: <https://fastapi.tiangolo.com/>
- Vue documentation: <https://vuejs.org/>
