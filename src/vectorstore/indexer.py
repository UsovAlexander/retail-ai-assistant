"""Build the Qdrant collections used for the two RAG layers.

Run: ``python -m src.vectorstore.indexer``

- ``retail_schema``   — one document per table (name + columns + Russian
  description + a few real sample values), for schema RAG.
- ``retail_few_shot`` — manually written ``question → reference SQL`` pairs,
  for dynamic few-shot RAG.

Idempotent: recreates both collections from scratch. See [[Qdrant_Collections]].
"""

from __future__ import annotations

import logging

from qdrant_client.models import PointStruct

from src.config import configure_logging, get_settings
from src.db import get_client
from src.vectorstore import client as vs

logger = logging.getLogger("indexer")

REV_EXPR = "sum(quantity * price * (1 - discount_pct / 100))"


# --- Schema documents --------------------------------------------------------
# Each entry: table name, Russian purpose, and (column, type, ru-description).
# Sample values for "key" columns are pulled live from ClickHouse at build time.
TABLES: list[dict] = [
    {
        "table": "stores",
        "purpose": "Справочник магазинов розничной сети (ювелирные магазины).",
        "columns": [
            ("store_id", "UInt32", "идентификатор магазина"),
            ("store_name", "String", "название магазина"),
            ("city", "LowCardinality(String)", "город"),
            ("region", "LowCardinality(String)", "федеральный округ"),
            ("open_date", "Date", "дата открытия"),
            ("format", "LowCardinality(String)", "формат: street/mall/outlet"),
        ],
        "sample_columns": ["city", "region", "format"],
    },
    {
        "table": "departments",
        "purpose": "Справочник отделов компании с иерархией.",
        "columns": [
            ("department_id", "UInt32", "идентификатор отдела"),
            ("department_name", "String", "название отдела"),
            ("parent_department_id", "Nullable(UInt32)", "родительский отдел (иерархия)"),
        ],
        "sample_columns": ["department_name"],
    },
    {
        "table": "employees",
        "purpose": "Справочник сотрудников. Продавцы привязаны к магазину (store_id), офисные сотрудники — store_id = NULL.",
        "columns": [
            ("employee_id", "UInt32", "идентификатор сотрудника"),
            ("full_name", "String", "ФИО"),
            ("department_id", "UInt32", "отдел (FK на departments)"),
            ("store_id", "Nullable(UInt32)", "магазин (FK на stores), NULL для офиса"),
            ("position", "LowCardinality(String)", "должность"),
            ("hire_date", "Date", "дата найма"),
            ("salary", "UInt32", "оклад, руб."),
        ],
        "sample_columns": ["position"],
    },
    {
        "table": "products",
        "purpose": "Каталог ювелирных изделий.",
        "columns": [
            ("product_id", "UInt32", "идентификатор товара"),
            ("product_name", "String", "название товара"),
            ("category", "LowCardinality(String)", "категория (кольца, серьги, ...)"),
            ("metal", "LowCardinality(String)", "металл (золото 585, серебро 925, платина)"),
            ("price", "UInt32", "розничная цена, руб."),
            ("cost", "UInt32", "себестоимость, руб. (60-75% от цены)"),
        ],
        "sample_columns": ["category", "metal"],
    },
    {
        "table": "sales",
        "purpose": "Факт продаж (~1 млн строк, 3 года). Выручка строки = quantity * price * (1 - discount_pct/100).",
        "columns": [
            ("sale_id", "UInt64", "идентификатор продажи"),
            ("sale_date", "Date", "дата продажи"),
            ("sale_datetime", "DateTime", "точное время продажи"),
            ("store_id", "UInt32", "магазин (FK на stores)"),
            ("employee_id", "UInt32", "продавец (FK на employees)"),
            ("product_id", "UInt32", "товар (FK на products)"),
            ("quantity", "UInt8", "количество единиц"),
            ("price", "UInt32", "фактическая цена продажи, руб."),
            ("discount_pct", "UInt8", "скидка, % (0-30)"),
        ],
        "sample_columns": [],
    },
    {
        "table": "plans",
        "purpose": "План выручки по магазинам на каждый месяц (план vs факт).",
        "columns": [
            ("store_id", "UInt32", "магазин (FK на stores)"),
            ("month", "Date", "первый день месяца"),
            ("plan_revenue", "UInt64", "плановая выручка, руб."),
        ],
        "sample_columns": [],
    },
]


# --- Few-shot examples (manually written against the real schema) ------------
# Coverage: aggregations, joins with directories, top-N, time series,
# window functions, and plan-vs-actual.
FEW_SHOT: list[dict] = [
    {
        "question": "Сколько всего продаж за 2025 год?",
        "sql": "SELECT count() AS sales FROM sales WHERE toYear(sale_date) = 2025",
        "tags": ["aggregation"],
    },
    {
        "question": "Какая общая выручка за всё время?",
        "sql": f"SELECT round({REV_EXPR}) AS revenue FROM sales",
        "tags": ["aggregation"],
    },
    {
        "question": "Покажи выручку по месяцам за 2025 год.",
        "sql": (
            f"SELECT toStartOfMonth(sale_date) AS month, round({REV_EXPR}) AS revenue "
            "FROM sales WHERE toYear(sale_date) = 2025 GROUP BY month ORDER BY month"
        ),
        "tags": ["time_series"],
    },
    {
        "question": "Динамика выручки по годам.",
        "sql": (
            f"SELECT toYear(sale_date) AS year, round({REV_EXPR}) AS revenue "
            "FROM sales GROUP BY year ORDER BY year"
        ),
        "tags": ["time_series"],
    },
    {
        "question": "Выручка по городам.",
        "sql": (
            "SELECT s.city AS city, round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue "
            "FROM sales AS sa INNER JOIN stores AS s ON sa.store_id = s.store_id "
            "GROUP BY city ORDER BY revenue DESC"
        ),
        "tags": ["join", "directory"],
    },
    {
        "question": "Выручка по федеральным округам.",
        "sql": (
            "SELECT s.region AS region, round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue "
            "FROM sales AS sa INNER JOIN stores AS s ON sa.store_id = s.store_id "
            "GROUP BY region ORDER BY revenue DESC"
        ),
        "tags": ["join", "directory"],
    },
    {
        "question": "Топ-10 товаров по выручке.",
        "sql": (
            "SELECT p.product_name AS product, round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue "
            "FROM sales AS sa INNER JOIN products AS p ON sa.product_id = p.product_id "
            "GROUP BY product ORDER BY revenue DESC LIMIT 10"
        ),
        "tags": ["join", "top_n"],
    },
    {
        "question": "Топ-5 магазинов по выручке.",
        "sql": (
            "SELECT s.store_name AS store, s.city AS city, round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue "
            "FROM sales AS sa INNER JOIN stores AS s ON sa.store_id = s.store_id "
            "GROUP BY store, city ORDER BY revenue DESC LIMIT 5"
        ),
        "tags": ["join", "top_n"],
    },
    {
        "question": "Топ-10 продавцов по выручке.",
        "sql": (
            "SELECT e.full_name AS employee, round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue "
            "FROM sales AS sa INNER JOIN employees AS e ON sa.employee_id = e.employee_id "
            "GROUP BY employee ORDER BY revenue DESC LIMIT 10"
        ),
        "tags": ["join", "top_n"],
    },
    {
        "question": "Выручка по категориям товаров.",
        "sql": (
            "SELECT p.category AS category, round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue "
            "FROM sales AS sa INNER JOIN products AS p ON sa.product_id = p.product_id "
            "GROUP BY category ORDER BY revenue DESC"
        ),
        "tags": ["join", "directory"],
    },
    {
        "question": "Выручка по металлам (золото, серебро, платина).",
        "sql": (
            "SELECT p.metal AS metal, round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue "
            "FROM sales AS sa INNER JOIN products AS p ON sa.product_id = p.product_id "
            "GROUP BY metal ORDER BY revenue DESC"
        ),
        "tags": ["join", "directory"],
    },
    {
        "question": "Какой средний чек по продаже?",
        "sql": f"SELECT round(avg(quantity * price * (1 - discount_pct / 100))) AS avg_check FROM sales",
        "tags": ["aggregation"],
    },
    {
        "question": "Сколько сотрудников в каждом отделе?",
        "sql": (
            "SELECT d.department_name AS department, count() AS headcount "
            "FROM employees AS e INNER JOIN departments AS d ON e.department_id = d.department_id "
            "GROUP BY department ORDER BY headcount DESC"
        ),
        "tags": ["join", "directory"],
    },
    {
        "question": "Средняя зарплата по отделам.",
        "sql": (
            "SELECT d.department_name AS department, round(avg(e.salary)) AS avg_salary "
            "FROM employees AS e INNER JOIN departments AS d ON e.department_id = d.department_id "
            "GROUP BY department ORDER BY avg_salary DESC"
        ),
        "tags": ["join", "aggregation"],
    },
    {
        "question": "Сколько магазинов каждого формата?",
        "sql": "SELECT format, count() AS stores FROM stores GROUP BY format ORDER BY stores DESC",
        "tags": ["aggregation"],
    },
    {
        "question": "Выручка по дням недели.",
        "sql": (
            f"SELECT toDayOfWeek(sale_date) AS weekday, round({REV_EXPR}) AS revenue "
            "FROM sales GROUP BY weekday ORDER BY weekday"
        ),
        "tags": ["time_series"],
    },
    {
        "question": "Средний размер скидки по категориям.",
        "sql": (
            "SELECT p.category AS category, round(avg(sa.discount_pct), 1) AS avg_discount "
            "FROM sales AS sa INNER JOIN products AS p ON sa.product_id = p.product_id "
            "GROUP BY category ORDER BY avg_discount DESC"
        ),
        "tags": ["join", "aggregation"],
    },
    {
        "question": "Выполнение плана по магазинам за декабрь 2025 (план и факт).",
        "sql": (
            "SELECT s.store_name AS store, p.plan_revenue AS plan, "
            "round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS actual, "
            "round(100 * sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100)) / p.plan_revenue, 1) AS pct "
            "FROM plans AS p "
            "INNER JOIN sales AS sa ON sa.store_id = p.store_id AND toStartOfMonth(sa.sale_date) = p.month "
            "INNER JOIN stores AS s ON s.store_id = p.store_id "
            "WHERE p.month = '2025-12-01' "
            "GROUP BY store, plan ORDER BY pct DESC"
        ),
        "tags": ["plan_vs_actual", "join"],
    },
    {
        "question": "Какие магазины не выполнили годовой план за 2025 год?",
        # Aggregate plans and sales separately, then join — joining the fact
        # table to plans before summing would multiply plan_revenue by the
        # number of matching sales rows (fan-out).
        "sql": (
            "SELECT s.store_name AS store, pl.plan_year AS plan_year, ac.actual_year AS actual_year "
            "FROM (SELECT store_id, sum(plan_revenue) AS plan_year FROM plans "
            "WHERE toYear(month) = 2025 GROUP BY store_id) AS pl "
            "INNER JOIN (SELECT store_id, round(sum(quantity * price * (1 - discount_pct / 100))) AS actual_year "
            "FROM sales WHERE toYear(sale_date) = 2025 GROUP BY store_id) AS ac USING (store_id) "
            "INNER JOIN stores AS s USING (store_id) "
            "WHERE actual_year < plan_year ORDER BY actual_year / plan_year ASC"
        ),
        "tags": ["plan_vs_actual", "join"],
    },
    {
        "question": "Ранжируй магазины по выручке внутри каждого федерального округа.",
        "sql": (
            "SELECT region, store_name, revenue, "
            "rank() OVER (PARTITION BY region ORDER BY revenue DESC) AS rank_in_region "
            "FROM (SELECT s.region AS region, s.store_name AS store_name, "
            "round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue "
            "FROM sales AS sa INNER JOIN stores AS s ON sa.store_id = s.store_id "
            "GROUP BY region, store_name) ORDER BY region, rank_in_region"
        ),
        "tags": ["window", "join"],
    },
    {
        "question": "Накопительная выручка по месяцам за 2025 год.",
        "sql": (
            "SELECT month, revenue, sum(revenue) OVER (ORDER BY month) AS cumulative "
            "FROM (SELECT toStartOfMonth(sale_date) AS month, "
            "round(sum(quantity * price * (1 - discount_pct / 100))) AS revenue "
            "FROM sales WHERE toYear(sale_date) = 2025 GROUP BY month) ORDER BY month"
        ),
        "tags": ["window", "time_series"],
    },
    {
        "question": "Прирост выручки месяц к месяцу за 2025 год.",
        "sql": (
            "SELECT month, revenue, revenue - lagInFrame(revenue, 1, 0) OVER (ORDER BY month) AS mom_change "
            "FROM (SELECT toStartOfMonth(sale_date) AS month, "
            "round(sum(quantity * price * (1 - discount_pct / 100))) AS revenue "
            "FROM sales WHERE toYear(sale_date) = 2025 GROUP BY month) ORDER BY month"
        ),
        "tags": ["window", "time_series"],
    },
    {
        "question": "Доля каждого металла в общей выручке в процентах.",
        "sql": (
            "SELECT metal, revenue, round(100 * revenue / sum(revenue) OVER (), 1) AS share_pct "
            "FROM (SELECT p.metal AS metal, "
            "sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100)) AS revenue "
            "FROM sales AS sa INNER JOIN products AS p ON sa.product_id = p.product_id "
            "GROUP BY metal) ORDER BY revenue DESC"
        ),
        "tags": ["window", "join"],
    },
    {
        "question": "Топ-3 самых дорогих товара в каждой категории.",
        "sql": (
            "SELECT category, product_name, price FROM ("
            "SELECT category, product_name, price, "
            "row_number() OVER (PARTITION BY category ORDER BY price DESC) AS rn "
            "FROM products) WHERE rn <= 3 ORDER BY category, price DESC"
        ),
        "tags": ["window"],
    },
    {
        "question": "Сколько продавцов работает в каждом магазине?",
        "sql": (
            "SELECT s.store_name AS store, count() AS employees "
            "FROM employees AS e INNER JOIN stores AS s ON e.store_id = s.store_id "
            "GROUP BY store ORDER BY employees DESC"
        ),
        "tags": ["join", "directory"],
    },
    {
        "question": "Выручка по месяцам для магазинов Москвы.",
        "sql": (
            "SELECT toStartOfMonth(sa.sale_date) AS month, "
            "round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue "
            "FROM sales AS sa INNER JOIN stores AS s ON sa.store_id = s.store_id "
            "WHERE s.city = 'Москва' GROUP BY month ORDER BY month"
        ),
        "tags": ["join", "time_series"],
    },
    {
        # The dataset contains future-dated sales, so relative periods must be
        # bounded on BOTH sides (see sql_system.txt).
        "question": "Продажи и выручка по дням за последнюю неделю.",
        "sql": (
            "SELECT sale_date, count() AS sales, "
            "round(sum(quantity * price * (1 - discount_pct / 100))) AS revenue "
            "FROM sales WHERE sale_date BETWEEN today() - 7 AND today() "
            "GROUP BY sale_date ORDER BY sale_date"
        ),
        "tags": ["time_series", "relative_dates"],
    },
    {
        "question": "Сколько продаж было вчера?",
        "sql": "SELECT count() AS sales FROM sales WHERE sale_date = yesterday()",
        "tags": ["aggregation", "relative_dates"],
    },
]


def fetch_samples(table: str, column: str, limit: int = 3) -> list[str]:
    """Fetch up to ``limit`` distinct values of a column (for schema docs)."""
    ch = get_client(database="retail_demo")
    try:
        rows = ch.query(
            f"SELECT DISTINCT {column} FROM {table} "
            f"WHERE {column} != '' ORDER BY rand() LIMIT {limit}"
        ).result_rows
        return [str(r[0]) for r in rows]
    finally:
        ch.close()


def build_schema_document(spec: dict) -> str:
    """Render one table into the text that gets embedded and retrieved."""
    lines = [f"Таблица: {spec['table']}", spec["purpose"], "Колонки:"]
    for col, ctype, desc in spec["columns"]:
        lines.append(f"  - {col} ({ctype}): {desc}")
    for column in spec["sample_columns"]:
        values = fetch_samples(spec["table"], column)
        if values:
            lines.append(f"Примеры значений {column}: {', '.join(values)}")
    return "\n".join(lines)


def index_schema() -> int:
    name = get_settings().qdrant_schema_collection
    vs.recreate_collection(name)
    documents = [build_schema_document(spec) for spec in TABLES]
    vectors = vs.embed(documents)
    points = [
        PointStruct(
            id=i,
            vector=vectors[i],
            payload={"table": TABLES[i]["table"], "document": documents[i]},
        )
        for i in range(len(TABLES))
    ]
    vs.upsert(name, points)
    return len(points)


def index_few_shot() -> int:
    name = get_settings().qdrant_few_shot_collection
    vs.recreate_collection(name)
    questions = [ex["question"] for ex in FEW_SHOT]
    vectors = vs.embed(questions)
    points = [
        PointStruct(
            id=i,
            vector=vectors[i],
            payload={
                "question": FEW_SHOT[i]["question"],
                "sql": FEW_SHOT[i]["sql"],
                "tags": FEW_SHOT[i].get("tags", []),
            },
        )
        for i in range(len(FEW_SHOT))
    ]
    vs.upsert(name, points)
    return len(points)


def main() -> None:
    configure_logging()
    logger.info("Indexing schema collection ...")
    n_schema = index_schema()
    logger.info("Indexed %d table documents.", n_schema)

    logger.info("Indexing few-shot collection ...")
    n_few = index_few_shot()
    logger.info("Indexed %d few-shot examples.", n_few)

    logger.info("Done. Collections ready.")


if __name__ == "__main__":
    main()
