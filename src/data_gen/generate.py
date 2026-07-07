"""Synthetic data generator for the ``retail_demo`` ClickHouse database.

Run: ``python -m src.data_gen.generate``

Domain: a jewelry retail chain. Builds all six tables (stores, departments,
employees, products, sales, plans) with realistic patterns required for the
demo (see [[Data]]):

- seasonal peaks: December (New Year), February–March (Feb 14 / Feb 23 / Mar 8);
- weekly seasonality: weekends stronger than weekdays;
- per-employee performance variance;
- 2–3 leading stores and 2–3 underperforming ones.

Idempotent: drops and recreates ``retail_demo`` from scratch. Uses a fixed
random seed for reproducibility.

Design note: directory rows are modelled as dataclasses for clarity; the ~1M
``sales`` rows are streamed as plain tuples in batches for memory/speed.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
from dataclasses import astuple, dataclass

from clickhouse_connect.driver.client import Client
from faker import Faker

from src.config import configure_logging, get_settings
from src.db import get_client

logger = logging.getLogger("data_gen")

# --- Reproducibility ---------------------------------------------------------
SEED = 42

# --- Sizing (spec §3) --------------------------------------------------------
N_STORES = 50
N_DEPARTMENTS = 15
N_PRODUCTS = 2_000
SALES_STAFF_PER_STORE = 8          # 1 manager + 2 senior + 5 associates -> 400
N_OFFICE_EMPLOYEES = 100           # store_id = NULL -> total ~500 employees
TARGET_SALES = 995_000             # ~1M, kept safely under the 1M cap
INSERT_BATCH = 100_000

# History window: full calendar years 2024–2026 (includes the current year;
# note it extends past "today", i.e. contains some future-dated sales).
DATE_START = dt.date(2024, 1, 1)
DATE_END = dt.date(2026, 12, 31)

# --- Seasonality factors -----------------------------------------------------
# Month-of-year multiplier: Dec peak (New Year), Feb–Mar peak (14 Feb / 8 Mar),
# post-holiday January dip, softer summer.
MONTH_FACTOR: dict[int, float] = {
    1: 0.75, 2: 1.45, 3: 1.60, 4: 1.00, 5: 0.95, 6: 0.85,
    7: 0.80, 8: 0.85, 9: 1.00, 10: 1.05, 11: 1.20, 12: 1.95,
}
# Day-of-week multiplier (0=Mon … 6=Sun): weekends stronger.
WEEKDAY_FACTOR: list[float] = [0.85, 0.85, 0.90, 0.95, 1.15, 1.55, 1.35]

# --- Reference / domain data -------------------------------------------------
CITIES: list[tuple[str, str]] = [
    ("Москва", "Центральный ФО"),
    ("Санкт-Петербург", "Северо-Западный ФО"),
    ("Новосибирск", "Сибирский ФО"),
    ("Екатеринбург", "Уральский ФО"),
    ("Казань", "Приволжский ФО"),
    ("Нижний Новгород", "Приволжский ФО"),
    ("Челябинск", "Уральский ФО"),
    ("Самара", "Приволжский ФО"),
    ("Омск", "Сибирский ФО"),
    ("Ростов-на-Дону", "Южный ФО"),
    ("Уфа", "Приволжский ФО"),
    ("Красноярск", "Сибирский ФО"),
    ("Воронеж", "Центральный ФО"),
    ("Волгоград", "Южный ФО"),
    ("Краснодар", "Южный ФО"),
    ("Пермь", "Приволжский ФО"),
    ("Калининград", "Северо-Западный ФО"),
    ("Владивосток", "Дальневосточный ФО"),
]
STORE_FORMATS = ["street", "mall", "outlet"]

DEPARTMENTS_SEED: list[tuple[str, str | None]] = [
    ("Розничная сеть", None),        # 1 (top-level, parent of store ops)
    ("Продажи", "Розничная сеть"),   # 2 — sales staff belong here
    ("Маркетинг", None),
    ("Логистика", None),
    ("Финансы", None),
    ("Персонал (HR)", None),
    ("ИТ", None),
    ("Закупки", None),
    ("Юридический отдел", None),
    ("Клиентский сервис", "Розничная сеть"),
    ("Мерчандайзинг", "Маркетинг"),
    ("Электронная коммерция", None),
    ("Аналитика", "Финансы"),
    ("Служба безопасности", None),
    ("Администрация", None),
]

PRODUCT_CATEGORIES = [
    "Кольца", "Серьги", "Цепи", "Браслеты", "Подвески",
    "Колье", "Броши", "Запонки", "Комплекты", "Пирсинг",
]
METALS = ["золото 585", "серебро 925", "платина"]
# Retail price range (RUB) per metal.
METAL_PRICE_RANGE: dict[str, tuple[int, int]] = {
    "золото 585": (15_000, 300_000),
    "серебро 925": (2_000, 30_000),
    "платина": (80_000, 500_000),
}
GEMSTONES = [
    "с бриллиантом", "с фианитом", "с сапфиром", "с изумрудом", "с рубином",
    "с жемчугом", "с топазом", "с аметистом", "без вставки", "с эмалью",
]
# --- Dataclasses for directory rows -----------------------------------------
@dataclass
class Store:
    store_id: int
    store_name: str
    city: str
    region: str
    open_date: dt.date
    format: str


@dataclass
class Department:
    department_id: int
    department_name: str
    parent_department_id: int | None


@dataclass
class Employee:
    employee_id: int
    full_name: str
    department_id: int
    store_id: int | None
    position: str
    hire_date: dt.date
    salary: int


@dataclass
class Product:
    product_id: int
    product_name: str
    category: str
    metal: str
    price: int
    cost: int


@dataclass
class Plan:
    store_id: int
    month: dt.date
    plan_revenue: int


# --- DDL ---------------------------------------------------------------------
DDL_STATEMENTS: list[str] = [
    """
    CREATE TABLE retail_demo.stores (
        store_id UInt32,
        store_name String,
        city LowCardinality(String),
        region LowCardinality(String),
        open_date Date,
        format LowCardinality(String)
    ) ENGINE = MergeTree ORDER BY store_id
    """,
    """
    CREATE TABLE retail_demo.departments (
        department_id UInt32,
        department_name String,
        parent_department_id Nullable(UInt32)
    ) ENGINE = MergeTree ORDER BY department_id
    """,
    """
    CREATE TABLE retail_demo.employees (
        employee_id UInt32,
        full_name String,
        department_id UInt32,
        store_id Nullable(UInt32),
        position LowCardinality(String),
        hire_date Date,
        salary UInt32
    ) ENGINE = MergeTree ORDER BY employee_id
    """,
    """
    CREATE TABLE retail_demo.products (
        product_id UInt32,
        product_name String,
        category LowCardinality(String),
        metal LowCardinality(String),
        price UInt32,
        cost UInt32
    ) ENGINE = MergeTree ORDER BY product_id
    """,
    """
    CREATE TABLE retail_demo.sales (
        sale_id UInt64,
        sale_date Date,
        sale_datetime DateTime,
        store_id UInt32,
        employee_id UInt32,
        product_id UInt32,
        quantity UInt8,
        price UInt32,
        discount_pct UInt8
    ) ENGINE = MergeTree
    PARTITION BY toYYYYMM(sale_date)
    ORDER BY (sale_date, store_id)
    """,
    """
    CREATE TABLE retail_demo.plans (
        store_id UInt32,
        month Date,
        plan_revenue UInt64
    ) ENGINE = MergeTree ORDER BY (store_id, month)
    """,
]


def recreate_database(client: Client) -> None:
    """Drop and recreate ``retail_demo`` (idempotent), then create all tables."""
    logger.info("Dropping and recreating database retail_demo ...")
    client.command("DROP DATABASE IF EXISTS retail_demo")
    client.command("CREATE DATABASE retail_demo")
    for ddl in DDL_STATEMENTS:
        client.command(ddl)
    logger.info("Created %d tables.", len(DDL_STATEMENTS))


# --- Directory generation ----------------------------------------------------
def gen_departments() -> list[Department]:
    name_to_id = {name: i + 1 for i, (name, _) in enumerate(DEPARTMENTS_SEED)}
    rows: list[Department] = []
    for i, (name, parent) in enumerate(DEPARTMENTS_SEED, start=1):
        parent_id = name_to_id[parent] if parent else None
        rows.append(Department(i, name, parent_id))
    return rows


def gen_stores(faker: Faker, rng: random.Random) -> list[Store]:
    rows: list[Store] = []
    for sid in range(1, N_STORES + 1):
        city, region = rng.choice(CITIES)
        fmt = rng.choices(STORE_FORMATS, weights=[0.5, 0.4, 0.1])[0]
        if fmt == "mall":
            name = f"ТЦ «{faker.word().capitalize()}», {city}"
        elif fmt == "outlet":
            name = f"Аутлет «{faker.word().capitalize()}», {city}"
        else:
            # street_name() already includes a type prefix (ул./бул./пер./…).
            name = f"Магазин на {faker.street_name()}, {city}"
        open_date = faker.date_between(start_date="-10y", end_date="-1y")
        rows.append(Store(sid, name, city, region, open_date, fmt))
    return rows


def gen_products(rng: random.Random) -> list[Product]:
    rows: list[Product] = []
    for pid in range(1, N_PRODUCTS + 1):
        category = rng.choice(PRODUCT_CATEGORIES)
        metal = rng.choices(METALS, weights=[0.45, 0.45, 0.10])[0]
        gem = rng.choice(GEMSTONES)
        low, high = METAL_PRICE_RANGE[metal]
        # Log-uniform price so cheaper items dominate but a long tail exists.
        price = int(round(rng.uniform(low, high) / 100) * 100)
        cost = int(price * rng.uniform(0.60, 0.75))
        # Singular category word for a natural name.
        singular = {
            "Кольца": "Кольцо", "Серьги": "Серьги", "Цепи": "Цепь",
            "Браслеты": "Браслет", "Подвески": "Подвеска", "Колье": "Колье",
            "Броши": "Брошь", "Запонки": "Запонки", "Комплекты": "Комплект",
            "Пирсинг": "Пирсинг",
        }[category]
        name = f"{singular} {metal} {gem}".strip()
        rows.append(Product(pid, name, category, metal, price, cost))
    return rows


def gen_employees(
    faker: Faker,
    rng: random.Random,
    stores: list[Store],
    departments: list[Department],
) -> tuple[list[Employee], dict[int, list[tuple[int, float]]]]:
    """Generate employees and the per-store sales roster with skill weights.

    Returns the employee list and a mapping ``store_id -> [(employee_id, skill)]``
    used to attribute sales with realistic per-rep performance variance.
    """
    dept_by_name = {d.department_name: d.department_id for d in departments}
    sales_dept = dept_by_name["Продажи"]
    office_dept_ids = [
        d.department_id for d in departments
        if d.department_name not in ("Продажи", "Розничная сеть")
    ]

    salary_by_position = {
        "продавец-консультант": (45_000, 70_000),
        "старший продавец": (70_000, 100_000),
        "директор магазина": (110_000, 180_000),
    }

    employees: list[Employee] = []
    roster: dict[int, list[tuple[int, float]]] = {}
    next_id = 1

    for store in stores:
        roster[store.store_id] = []
        # Composition per store: 1 director, 2 senior, rest associates.
        positions = (
            ["директор магазина"]
            + ["старший продавец"] * 2
            + ["продавец-консультант"] * (SALES_STAFF_PER_STORE - 3)
        )
        for position in positions:
            name = faker.name()
            lo, hi = salary_by_position[position]
            salary = int(rng.uniform(lo, hi) / 1000) * 1000
            hire = faker.date_between(start_date=store.open_date, end_date="today")
            employees.append(
                Employee(next_id, name, sales_dept, store.store_id, position, hire, salary)
            )
            # Skill factor (log-normal-ish): most ~1.0, a few strong performers.
            skill = round(rng.lognormvariate(0.0, 0.35), 3)
            roster[store.store_id].append((next_id, skill))
            next_id += 1

    # Office staff — no store (store_id NULL).
    office_positions = [
        "специалист", "старший специалист", "менеджер",
        "руководитель отдела", "аналитик", "бухгалтер",
    ]
    for _ in range(N_OFFICE_EMPLOYEES):
        name = faker.name()
        dept = rng.choice(office_dept_ids)
        position = rng.choice(office_positions)
        salary = int(rng.uniform(60_000, 200_000) / 1000) * 1000
        hire = faker.date_between(start_date="-8y", end_date="today")
        employees.append(Employee(next_id, name, dept, None, position, hire, salary))
        next_id += 1

    return employees, roster


def assign_store_factors(rng: random.Random, stores: list[Store]) -> dict[int, float]:
    """Store performance tiers: 3 leaders, 3 laggards, the rest ~log-normal."""
    ids = [s.store_id for s in stores]
    rng.shuffle(ids)
    factors: dict[int, float] = {}
    leaders, laggards = ids[:3], ids[3:6]
    for sid in leaders:
        factors[sid] = round(rng.uniform(2.0, 2.6), 3)
    for sid in laggards:
        factors[sid] = round(rng.uniform(0.30, 0.45), 3)
    for sid in ids[6:]:
        factors[sid] = round(rng.lognormvariate(0.0, 0.30), 3)
    return factors


# --- Sales & plans -----------------------------------------------------------
def _iter_days() -> list[tuple[dt.date, float]]:
    """Return each day in the window with its combined seasonality weight."""
    days: list[tuple[dt.date, float]] = []
    d = DATE_START
    one = dt.timedelta(days=1)
    while d <= DATE_END:
        w = MONTH_FACTOR[d.month] * WEEKDAY_FACTOR[d.weekday()]
        days.append((d, w))
        d += one
    return days


def _stochastic_round(x: float, rng: random.Random) -> int:
    base = int(x)
    return base + (1 if rng.random() < (x - base) else 0)


def gen_plans(
    rng: random.Random,
    stores: list[Store],
    store_factors: dict[int, float],
    days: list[tuple[dt.date, float]],
    scale: float,
    avg_sale_revenue: float,
) -> list[Plan]:
    """Monthly revenue targets, loosely aligned with expected actuals.

    Plan multiplier varies per store/month so plan-vs-actual is meaningful
    (some stores beat plan, some miss).
    """
    # Expected sales count per (store, month) from the same weights as sales.
    monthly: dict[tuple[int, tuple[int, int]], float] = {}
    for d, w in days:
        key_month = (d.year, d.month)
        for store in stores:
            k = (store.store_id, key_month)
            monthly[k] = monthly.get(k, 0.0) + store_factors[store.store_id] * w * scale

    # Persistent per-store ambition: some stores get consistently ambitious
    # (>1) plans they tend to miss, others lax (<1) plans they tend to beat.
    # Combined with small monthly noise this yields a real plan-vs-actual mix.
    ambition = {s.store_id: rng.uniform(0.90, 1.12) for s in stores}

    plans: list[Plan] = []
    for (store_id, (year, month)), exp_sales in monthly.items():
        month_noise = rng.uniform(0.96, 1.04)
        plan_revenue = int(exp_sales * avg_sale_revenue * ambition[store_id] * month_noise)
        plans.append(Plan(store_id, dt.date(year, month, 1), plan_revenue))
    return plans


def gen_and_insert_sales(
    client: Client,
    rng: random.Random,
    stores: list[Store],
    products: list[Product],
    roster: dict[int, list[tuple[int, float]]],
    store_factors: dict[int, float],
    days: list[tuple[dt.date, float]],
    scale: float,
) -> int:
    """Generate ~TARGET_SALES rows and bulk-insert them in batches."""
    price_by_product = {p.product_id: p.price for p in products}
    product_ids = [p.product_id for p in products]
    # Product popularity (log-normal); cheaper/common items sell more often.
    product_weights = [rng.lognormvariate(0.0, 0.6) for _ in products]

    # Business hours 10:00–21:00, afternoon/evening heavier.
    hours = list(range(10, 22))
    hour_weights = [1, 1, 1.5, 1.8, 2, 1.6, 1.6, 2, 2.2, 2.4, 2.0, 1.2]

    columns = [
        "sale_id", "sale_date", "sale_datetime", "store_id", "employee_id",
        "product_id", "quantity", "price", "discount_pct",
    ]

    batch: list[tuple] = []
    total = 0
    sale_id = 0

    def flush() -> None:
        nonlocal batch
        if batch:
            client.insert("retail_demo.sales", batch, column_names=columns)
            logger.info("  inserted batch, running total = %d", total)
            batch = []

    for store in stores:
        emp_ids = [e for e, _ in roster[store.store_id]]
        emp_weights = [s for _, s in roster[store.store_id]]
        sfactor = store_factors[store.store_id]

        for d, w in days:
            expected = sfactor * w * scale
            count = _stochastic_round(expected, rng)
            if count <= 0:
                continue

            # Bulk-sample the components for this (store, day) cell.
            emps = rng.choices(emp_ids, weights=emp_weights, k=count)
            prods = rng.choices(product_ids, weights=product_weights, k=count)
            qtys = rng.choices([1, 2, 3], weights=[0.80, 0.17, 0.03], k=count)
            discounts = rng.choices(
                [0, 5, 10, 15, 20, 25, 30],
                weights=[0.50, 0.14, 0.13, 0.10, 0.07, 0.04, 0.02],
                k=count,
            )
            hrs = rng.choices(hours, weights=hour_weights, k=count)

            for i in range(count):
                sale_id += 1
                total += 1
                pid = prods[i]
                sale_dt = dt.datetime(
                    d.year, d.month, d.day, hrs[i],
                    rng.randint(0, 59), rng.randint(0, 59),
                )
                batch.append((
                    sale_id, d, sale_dt, store.store_id, emps[i], pid,
                    qtys[i], price_by_product[pid], discounts[i],
                ))
                if len(batch) >= INSERT_BATCH:
                    flush()
    flush()
    return total


def insert_directories(
    client: Client,
    departments: list[Department],
    stores: list[Store],
    employees: list[Employee],
    products: list[Product],
    plans: list[Plan],
) -> None:
    client.insert(
        "retail_demo.departments",
        [astuple(d) for d in departments],
        column_names=["department_id", "department_name", "parent_department_id"],
    )
    client.insert(
        "retail_demo.stores",
        [astuple(s) for s in stores],
        column_names=["store_id", "store_name", "city", "region", "open_date", "format"],
    )
    client.insert(
        "retail_demo.employees",
        [astuple(e) for e in employees],
        column_names=[
            "employee_id", "full_name", "department_id", "store_id",
            "position", "hire_date", "salary",
        ],
    )
    client.insert(
        "retail_demo.products",
        [astuple(p) for p in products],
        column_names=["product_id", "product_name", "category", "metal", "price", "cost"],
    )
    client.insert(
        "retail_demo.plans",
        [astuple(p) for p in plans],
        column_names=["store_id", "month", "plan_revenue"],
    )


def log_summary(client: Client) -> None:
    """Log row counts per table as a quick post-generation sanity check."""
    logger.info("Row counts:")
    for table in ("stores", "departments", "employees", "products", "sales", "plans"):
        n = client.query(f"SELECT count() FROM retail_demo.{table}").result_rows[0][0]
        logger.info("  %-12s %s", table, f"{n:,}")


def main() -> None:
    configure_logging()
    get_settings()  # fail fast if config/.env is broken
    rng = random.Random(SEED)
    faker = Faker("ru_RU")
    faker.seed_instance(SEED)

    client = get_client()
    try:
        recreate_database(client)

        logger.info("Generating directories ...")
        departments = gen_departments()
        stores = gen_stores(faker, rng)
        products = gen_products(rng)
        employees, roster = gen_employees(faker, rng, stores, departments)
        store_factors = assign_store_factors(rng, stores)

        # Shared weight scale so expected sales sum to ~TARGET_SALES.
        days = _iter_days()
        total_weight = sum(
            store_factors[s.store_id] * w for s in stores for _, w in days
        )
        scale = TARGET_SALES / total_weight

        # Expected revenue per sale ≈ mean catalog price × mean quantity (~1.23)
        # × (1 − mean discount ~0.065). Calibrated so total plan ≈ total actual.
        avg_sale_revenue = (
            sum(p.price for p in products) / len(products) * 1.23 * 0.935
        )
        plans = gen_plans(rng, stores, store_factors, days, scale, avg_sale_revenue)

        logger.info("Inserting directories ...")
        insert_directories(client, departments, stores, employees, products, plans)

        logger.info("Generating and inserting ~%d sales ...", TARGET_SALES)
        total = gen_and_insert_sales(
            client, rng, stores, products, roster, store_factors, days, scale
        )
        logger.info("Inserted %d sales rows.", total)

        log_summary(client)
        logger.info("Done. retail_demo is ready.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
