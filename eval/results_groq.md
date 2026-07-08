# Evaluation results

_Generated 2026-07-08 15:35 · backend `external:llama-3.3-70b-versatile` · 30 questions · 138s._

## Metrics

| Metric | Value |
|---|---|
| **Execution accuracy** (SQL runs) | **100%** (30/30) |
| **Result accuracy** (matches reference) | **77%** (23/30) |
| Avg attempts / question | 1.00 |

## By category

| Category | Exec | Result | N |
|---|---|---|---|
| aggregation | 100% | 90% | 10 |
| join | 100% | 100% | 5 |
| plan_vs_actual | 100% | 50% | 2 |
| time_series | 100% | 50% | 4 |
| top_n | 100% | 80% | 5 |
| window | 100% | 50% | 4 |

## Per-question

| # | Category | Exec | Result | Att | Question |
|---|---|:--:|:--:|:--:|---|
| 1 | aggregation | ✅ | ✅ | 1 | Какая общая выручка за 2024 год? |
| 2 | aggregation | ✅ | ✅ | 1 | Сколько всего товаров в каталоге? |
| 3 | aggregation | ✅ | ✅ | 1 | Сколько сотрудников работает в компании? |
| 4 | aggregation | ✅ | ✅ | 1 | Какая средняя цена товара по каждому металлу? |
| 5 | time_series | ✅ | ❌ | 1 | Выручка по кварталам 2025 года. |
| 6 | top_n | ✅ | ✅ | 1 | Три категории товаров с наибольшей выручкой. |
| 7 | top_n | ✅ | ❌ | 1 | Пять лучших сотрудников по выручке за 2025 год. |
| 8 | aggregation | ✅ | ✅ | 1 | Сколько магазинов в каждом федеральном округе? |
| 9 | join | ✅ | ✅ | 1 | Средний чек по городам. |
| 10 | join | ✅ | ✅ | 1 | Сравни выручку по форматам магазинов. |
| 11 | time_series | ✅ | ✅ | 1 | Как менялась выручка по годам? |
| 12 | join | ✅ | ✅ | 1 | Какая доля серебра 925 в общей выручке в процентах? |
| 13 | top_n | ✅ | ✅ | 1 | Какой магазин принёс больше всего выручки? |
| 14 | aggregation | ✅ | ✅ | 1 | Сколько продаж было в выходные дни в 2025 году? |
| 15 | aggregation | ✅ | ❌ | 1 | Какая средняя зарплата у продавцов? |
| 16 | time_series | ✅ | ✅ | 1 | Выручка по месяцам за 2024 год. |
| 17 | top_n | ✅ | ✅ | 1 | Топ-10 самых дорогих товаров. |
| 18 | aggregation | ✅ | ✅ | 1 | Сколько товаров в каждой категории? |
| 19 | plan_vs_actual | ✅ | ❌ | 1 | На сколько процентов выполнен годовой план за 2025 год? |
| 20 | plan_vs_actual | ✅ | ✅ | 1 | Какие магазины перевыполнили годовой план за 2025 год? |
| 21 | join | ✅ | ✅ | 1 | Средний размер скидки по металлам. |
| 22 | window | ✅ | ❌ | 1 | Топ-10 магазинов по выручке с указанием ранга. |
| 23 | window | ✅ | ✅ | 1 | Накопительная выручка по месяцам за 2024 год. |
| 24 | window | ✅ | ✅ | 1 | Прирост выручки год к году. |
| 25 | aggregation | ✅ | ✅ | 1 | Сколько уникальных товаров было продано в 2025 году? |
| 26 | join | ✅ | ✅ | 1 | Какая выручка у магазинов Москвы за 2025 год? |
| 27 | top_n | ✅ | ✅ | 1 | Пять отделов с самой высокой средней зарплатой. |
| 28 | window | ✅ | ❌ | 1 | Доля выручки по федеральным округам в процентах. |
| 29 | time_series | ✅ | ❌ | 1 | В какие часы больше всего продаж? |
| 30 | aggregation | ✅ | ✅ | 1 | Сколько сотрудников не привязано ни к одному магазину? |

## Failures (for analysis)

**Q5. Выручка по кварталам 2025 года.** — executed but result differs (gen 4 vs ref 4 rows)
```sql
SELECT toStartOfQuarter(sale_date) AS quarter, round(sum(quantity * price * (1 - discount_pct / 100))) AS revenue 
FROM sales 
WHERE toYear(sale_date) = 2025 
GROUP BY quarter 
ORDER BY quarter 
LIMIT 1000
```

**Q7. Пять лучших сотрудников по выручке за 2025 год.** — executed but result differs (gen 5 vs ref 5 rows)
```sql
SELECT employee_id, full_name, round(sum(quantity * price * (1 - discount_pct / 100))) AS revenue 
FROM sales 
INNER JOIN employees ON sales.employee_id = employees.employee_id 
WHERE toYear(sale_date) = 2025 
GROUP BY employee_id, full_name 
ORDER BY revenue DESC 
LIMIT 5
```

**Q15. Какая средняя зарплата у продавцов?** — executed but result differs (gen 1 vs ref 1 rows)
```sql
SELECT round(avg(salary)) AS avg_salary FROM employees WHERE position = 'продавец-консультант'
LIMIT 1000
```

**Q19. На сколько процентов выполнен годовой план за 2025 год?** — executed but result differs (gen 1 vs ref 1 rows)
```sql
SELECT round(100 * sum(ac.actual_year) / sum(pl.plan_year), 2) AS plan_completion_pct 
FROM (SELECT store_id, sum(plan_revenue) AS plan_year FROM plans WHERE toYear(month) = 2025 GROUP BY store_id) AS pl 
INNER JOIN (SELECT store_id, round(sum(quantity * price * (1 - discount_pct / 100))) AS actual_year FROM sales WHERE toYear(sale_date) = 2025 GROUP BY store_id) AS ac 
USING (store_id) 
LIMIT 1
```

**Q22. Топ-10 магазинов по выручке с указанием ранга.** — executed but result differs (gen 10 vs ref 10 rows)
```sql
SELECT s.store_name AS store, s.city AS city, round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue, rank() OVER (ORDER BY sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100)) DESC) AS rank FROM sales AS sa INNER JOIN stores AS s ON sa.store_id = s.store_id GROUP BY store, city ORDER BY revenue DESC LIMIT 10
```

**Q28. Доля выручки по федеральным округам в процентах.** — executed but result differs (gen 7 vs ref 7 rows)
```sql
SELECT region, round(revenue, 2) AS revenue, round(100 * revenue / sum(revenue) OVER (), 2) AS share_pct 
FROM (SELECT s.region AS region, round(sum(sa.quantity * sa.price * (1 - sa.discount_pct / 100))) AS revenue 
      FROM sales AS sa INNER JOIN stores AS s ON sa.store_id = s.store_id 
      GROUP BY region) 
ORDER BY revenue DESC LIMIT 1000
```

**Q29. В какие часы больше всего продаж?** — executed but result differs (gen 1 vs ref 12 rows)
```sql
SELECT toHour(sale_datetime) AS hour, count() AS sales 
FROM sales 
GROUP BY hour 
ORDER BY sales DESC 
LIMIT 1
```
