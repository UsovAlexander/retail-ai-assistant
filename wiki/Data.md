# Data — `retail_demo`

See [[Index]]. Related: [[Text_to_SQL]], [[Qdrant_Collections]].
Source: `raw/project_spec_en.md` §3. Generator: `src/data_gen/generate.py`.

The domain is a **jewelry retail chain** (products are rings, earrings, chains,
etc.; metals gold 585 / silver 925 / platinum). All money in **RUB**.

## Tables (database `retail_demo`)

| Table | Rows (target) | Purpose |
|---|---|---|
| `stores` | ~50 | store directory |
| `departments` | ~15 | department directory (hierarchy) |
| `employees` | ~500 | staff directory |
| `products` | ~2,000 | product catalog |
| `sales` | ~1,000,000 | sales fact table, 2 years |
| `plans` | ~1,200 | monthly revenue targets per store |

### `stores`
`store_id UInt32`, `store_name String`, `city LowCardinality(String)`,
`region LowCardinality(String)`, `open_date Date`,
`format LowCardinality(String)` ∈ {street, mall, outlet}.

### `departments`
`department_id UInt32`, `department_name String`,
`parent_department_id Nullable(UInt32)` (hierarchy).

### `employees`
`employee_id UInt32`, `full_name String` (faker ru_RU),
`department_id UInt32` → departments, `store_id Nullable(UInt32)` → stores
(sales staff assigned; office staff NULL), `position LowCardinality(String)`,
`hire_date Date`, `salary UInt32` (base, RUB).

### `products`
`product_id UInt32`, `product_name String`, `category LowCardinality(String)`
(8–10 categories), `metal LowCardinality(String)`, `price UInt32`,
`cost UInt32` (60–75% of price).

### `sales`
`sale_id UInt64`, `sale_date Date`, `sale_datetime DateTime`,
`store_id UInt32`, `employee_id UInt32`, `product_id UInt32`,
`quantity UInt8` (usually 1–2), `price UInt32` (actual sale price),
`discount_pct UInt8` (0–30). **Revenue = quantity * price * (1 - discount_pct/100).**

### `plans`
`store_id UInt32`, `month Date` (first day of month), `plan_revenue UInt64`.

## Synthetic data patterns (required for the demo)

- **Seasonal peaks**: December (New Year), February–March (Feb 14, Mar 8).
- **Weekly seasonality**: weekends stronger than weekdays.
- **Sales-rep variance**: some reps consistently sell more.
- **Store tiers**: 2–3 leading stores, 2–3 underperforming ones.
- **Idempotent**: rerun does `DROP DATABASE IF EXISTS retail_demo` → `CREATE`.
- **Fixed random seed** for reproducibility.

## Generator design (to be finalized at stage 2)

- Run: `python -m src.data_gen.generate`
- Engine: `MergeTree` fact table ordered by `(sale_date, store_id)`;
  directories small enough for `MergeTree`/`ORDER BY id`.
- Batched inserts for the 1M sales rows (memory-safe).
- Multipliers: month-of-year factor, day-of-week factor, per-store tier factor,
  per-employee skill factor — combined into a daily expected sales count.

## Actuals (stage 2, seed=42) — VERIFIED

Row counts: `stores 50`, `departments 15`, `employees 500`, `products 2,000`,
`sales 994,892`, `plans 1,800`. History window **2024-01-01 … 2026-12-31**
(three full calendar years, `plans` = 50 stores × 36 months). Generation ~3s.

> **Note:** the window extends past "today" (2026-07-07) — Jul–Dec 2026 are
> future-dated sales. This is a deliberate config choice (`DATE_END`), a
> deviation from the spec's "2 years of history"; kept intentionally.

- **Revenue by year**: 2024 ≈ ₽41.7B, 2025 ≈ ₽41.7B, 2026 ≈ ₽41.5B (balanced).
- **Seasonality (revenue by month-of-year, all years)** — peaks clearly visible:
  Dec ₽18.2B (top), Mar ₽15.3B, Feb ₽12.5B, Nov ₽11.2B; trough Jan ₽7.0B,
  soft summer (Jul ₽7.5B). Weekend uplift baked in via `WEEKDAY_FACTOR`.
- **Store tiers**: top store ≈ ₽5.7B vs bottom ≈ ₽0.75B (~8× spread) — 3 leaders
  (factor 2.0–2.6) and 3 laggards (0.30–0.45) plus a log-normal middle.
- **Plan vs actual (2025)**: total actual/plan ≈ 1.02; **20 stores miss, 30 beat**
  their annual plan — a genuine mix (not all-beat / all-miss). Achieved via a
  *persistent per-store ambition factor* (0.90–1.12) plus monthly noise, with
  `avg_sale_revenue` calibrated to the real avg check (₽125.6k).

Revenue formula used everywhere: `sum(quantity * price * (1 - discount_pct/100))`.

## Verification queries (run at end of stage 2)

- Total revenue by year · monthly revenue curve (Dec + Feb–Mar peaks) ·
  top-5 vs bottom-5 stores · row counts per table. All confirmed.

## Open questions / decisions

- **CH client library**: `clickhouse-connect` over the HTTP interface (8123).
  Maintained, pure-Python, efficient bulk insert. Shared helper: `src/db.py`
  (`get_client(database)`; connect with no DB to DROP/CREATE `retail_demo`).
  `src/db.py` is not in the spec §7 tree — added deliberately so `check_env`
  and the generator share one connection factory.
- **History window**: full calendar years **2024–2026** (`DATE_START`/`DATE_END`).
  Extends past today (2026-07-07), so it contains future-dated sales — a
  deliberate deviation from the spec's "2 years". Full years keep year-over-year
  and seasonality clean in the demo.
- **Target rows**: `TARGET_SALES = 995_000` (stochastic rounding lands at
  995,056) — deliberately under the 1M cap (spec §12) while still "~1M".
- **Sales realism model**: per-(store, day) expected count =
  `store_factor × month_factor × weekday_factor × scale`; within a cell,
  employees are drawn weighted by a per-rep log-normal skill factor, products by
  a log-normal popularity factor. `plans.plan_revenue` = expected-sales weights ×
  calibrated `avg_sale_revenue` × a **persistent per-store ambition factor**
  (0.90–1.12) × monthly noise (0.96–1.04), so plan-vs-actual is meaningful
  (20 miss / 30 beat, not all one way).
- **`price` vs `discount_pct`**: `sales.price` is the product's base retail price;
  the realized discount lives in `discount_pct`. Revenue must apply the discount.
