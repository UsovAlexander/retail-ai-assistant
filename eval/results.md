# Evaluation results

_Generated 2026-07-08 15:18 · model `qwen2.5-coder:14b` · 30 questions · 128s._

## Metrics

| Metric | Value |
|---|---|
| **Execution accuracy** (SQL runs) | **97%** (29/30) |
| **Result accuracy** (matches reference) | **70%** (21/30) |
| Avg attempts / question | 1.10 |

## By category

| Category | Exec | Result | N |
|---|---|---|---|
| aggregation | 100% | 80% | 10 |
| join | 100% | 60% | 5 |
| plan_vs_actual | 100% | 50% | 2 |
| time_series | 100% | 50% | 4 |
| top_n | 100% | 100% | 5 |
| window | 75% | 50% | 4 |

## Per-question

| # | Category | Exec | Result | Att | Question |
|---|---|:--:|:--:|:--:|---|
| 1 | aggregation | ✅ | ✅ | 1 | Какая общая выручка за 2024 год? |
| 2 | aggregation | ✅ | ✅ | 1 | Сколько всего товаров в каталоге? |
| 3 | aggregation | ✅ | ✅ | 1 | Сколько сотрудников работает в компании? |
| 4 | aggregation | ✅ | ✅ | 1 | Какая средняя цена товара по каждому металлу? |
| 5 | time_series | ✅ | ❌ | 1 | Выручка по кварталам 2025 года. |
| 6 | top_n | ✅ | ✅ | 1 | Три категории товаров с наибольшей выручкой. |
| 7 | top_n | ✅ | ✅ | 1 | Пять лучших сотрудников по выручке за 2025 год. |
| 8 | aggregation | ✅ | ✅ | 1 | Сколько магазинов в каждом федеральном округе? |
| 9 | join | ✅ | ✅ | 1 | Средний чек по городам. |
| 10 | join | ✅ | ❌ | 2 | Сравни выручку по форматам магазинов. |
| 11 | time_series | ✅ | ✅ | 1 | Как менялась выручка по годам? |
| 12 | join | ✅ | ❌ | 1 | Какая доля серебра 925 в общей выручке в процентах? |
| 13 | top_n | ✅ | ✅ | 1 | Какой магазин принёс больше всего выручки? |
| 14 | aggregation | ✅ | ❌ | 1 | Сколько продаж было в выходные дни в 2025 году? |
| 15 | aggregation | ✅ | ❌ | 1 | Какая средняя зарплата у продавцов? |
| 16 | time_series | ✅ | ✅ | 1 | Выручка по месяцам за 2024 год. |
| 17 | top_n | ✅ | ✅ | 1 | Топ-10 самых дорогих товаров. |
| 18 | aggregation | ✅ | ✅ | 1 | Сколько товаров в каждой категории? |
| 19 | plan_vs_actual | ✅ | ❌ | 1 | На сколько процентов выполнен годовой план за 2025 год? |
| 20 | plan_vs_actual | ✅ | ✅ | 1 | Какие магазины перевыполнили годовой план за 2025 год? |
| 21 | join | ✅ | ✅ | 1 | Средний размер скидки по металлам. |
| 22 | window | ✅ | ❌ | 1 | Топ-10 магазинов по выручке с указанием ранга. |
| 23 | window | ✅ | ✅ | 1 | Накопительная выручка по месяцам за 2024 год. |
| 24 | window | ❌ | ❌ | 3 | Прирост выручки год к году. |
| 25 | aggregation | ✅ | ✅ | 1 | Сколько уникальных товаров было продано в 2025 году? |
| 26 | join | ✅ | ✅ | 1 | Какая выручка у магазинов Москвы за 2025 год? |
| 27 | top_n | ✅ | ✅ | 1 | Пять отделов с самой высокой средней зарплатой. |
| 28 | window | ✅ | ✅ | 1 | Доля выручки по федеральным округам в процентах. |
| 29 | time_series | ✅ | ❌ | 1 | В какие часы больше всего продаж? |
| 30 | aggregation | ✅ | ✅ | 1 | Сколько сотрудников не привязано ни к одному магазину? |

## Failures (for analysis)

**Q5. Выручка по кварталам 2025 года.** — executed but result differs (gen 12 vs ref 4 rows)
```sql
SELECT 
    toYYYYMM(toStartOfMonth(sale_date)) AS quarter, 
    round(sum(quantity * price * (1 - discount_pct / 100))) AS revenue 
FROM 
    sales 
WHERE 
    toYear(sale_date) = 2025 
GROUP BY 
    quarter 
ORDER BY 
    quarter
LIMIT 1000
```

**Q10. Сравни выручку по форматам магазинов.** — executed but result differs (gen 1000 vs ref 3 rows)
```sql
SELECT 
    s.format AS store_format,
    round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS actual_revenue,
    round(p.plan_revenue) AS planned_revenue
FROM 
    sales AS sa
INNER JOIN 
    stores AS s ON sa.store_id = s.store_id
LEFT JOIN 
    plans AS p ON sa.store_id = p.store_id AND toYYYYMM(sa.sale_date) = toYYYYMM(p.month)
GROUP BY 
    store_format, planned_revenue
ORDER BY 
    actual_revenue DESC
LIMIT 1000
```

**Q12. Какая доля серебра 925 в общей выручке в процентах?** — executed but result differs (gen 1 vs ref 1 rows)
```sql
SELECT 
    metal, 
    revenue, 
    round(100 * revenue / sum(revenue) OVER (), 1) AS share_pct 
FROM 
(
    SELECT 
        p.metal AS metal, 
        sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100)) AS revenue 
    FROM 
        sales AS sa 
    INNER JOIN 
        products AS p ON sa.product_id = p.product_id 
    WHERE 
        p.metal = 'серебро 925' 
    GROUP BY 
        metal
) 
ORDER BY 
    revenue DESC
LIMIT 1000
```

**Q14. Сколько продаж было в выходные дни в 2025 году?** — executed but result differs (gen 1 vs ref 1 rows)
```sql
SELECT count() AS weekend_sales 
FROM sales 
WHERE toYear(sale_date) = 2025 AND toDayOfWeek(sale_date) IN (7, 1)
LIMIT 1000
```

**Q15. Какая средняя зарплата у продавцов?** — executed but result differs (gen 1 vs ref 1 rows)
```sql
SELECT round(avg(salary)) AS avg_salary 
FROM employees 
WHERE position = 'продавец-консультант'
LIMIT 1000
```

**Q19. На сколько процентов выполнен годовой план за 2025 год?** — executed but result differs (gen 50 vs ref 1 rows)
```sql
SELECT 
    round((actual_year / plan_year) * 100, 2) AS execution_percentage
FROM 
    (SELECT store_id, sum(plan_revenue) AS plan_year FROM plans WHERE toYear(month) = 2025 GROUP BY store_id) AS pl
INNER JOIN 
    (SELECT store_id, round(sum(quantity * price * (1 - discount_pct / 100))) AS actual_year FROM sales WHERE toYear(sale_date) = 2025 GROUP BY store_id) AS ac
USING (store_id)
LIMIT 1000
```

**Q22. Топ-10 магазинов по выручке с указанием ранга.** — executed but result differs (gen 10 vs ref 10 rows)
```sql
SELECT 
    s.store_name AS store, 
    s.city AS city, 
    round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue,
    rank() OVER (ORDER BY sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100)) DESC) AS revenue_rank
FROM 
    sales AS sa 
INNER JOIN 
    stores AS s ON sa.store_id = s.store_id 
GROUP BY 
    store, city 
ORDER BY 
    revenue DESC 
LIMIT 10
```

**Q24. Прирост выручки год к году.** — Received ClickHouse exception, code: 215, server response: Code: 215. DB::Exception: Column 'year' is not under aggregate function and not in GROUP BY keys. In query SELECT year, revenue, round((revenue - lagInFrame(revenue, 1, 0)) / lagInFrame(revenue, 1, 1), 2) * 100 AS yoy_change FROM (SELECT toYear(sale_date) AS year, round(sum((quantity * price) * (1 - (discount_pct / 100)))) AS revenue FROM sales GROUP BY year) ORDER BY year ASC LIMIT 1000. (NOT_AN_AGGREGATE) (for url http://localhost:8123)
```sql
SELECT year, revenue, round((revenue - lagInFrame(revenue, 1, 0)) / lagInFrame(revenue, 1, 1), 2) * 100 AS yoy_change 
FROM (
    SELECT toYear(sale_date) AS year, round(sum(quantity * price * (1 - discount_pct / 100))) AS revenue 
    FROM sales 
    GROUP BY year
) 
ORDER BY year
LIMIT 1000
```

**Q29. В какие часы больше всего продаж?** — executed but result differs (gen 1 vs ref 12 rows)
```sql
SELECT toHour(sale_datetime) AS hour, count() AS sales_count 
FROM sales 
GROUP BY hour 
ORDER BY sales_count DESC 
LIMIT 1
```
