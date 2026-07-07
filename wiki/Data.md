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

## Verification queries (run at end of stage 2)

- Total revenue by year.
- Monthly revenue curve — Dec + Feb–Mar peaks must be visible.
- Top-5 vs bottom-5 stores by revenue.
- Row counts per table.

## Open questions / decisions

- **CH client library**: `clickhouse-connect` over the HTTP interface (8123).
  Chosen for a maintained, pure-Python API with efficient bulk insert.
- **Actuals** (row counts, revenue numbers) recorded here after stage 2 runs.
