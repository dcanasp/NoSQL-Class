# Instructor demo queries (visualizers)

Every query below was run against the default dataset. Numbers in *italics* are the results you should see.
These are for the projector. The notebook covers the same engines through the gateway, so these focus on what
only a UI can show: the graph, the chart, the document tree, the vector map.

---

## Redis: RedisInsight, http://localhost:5540

Open the `domi` connection, then **Workbench** (paste commands) or **Browser** (click through keys).

```redis
HGETALL user:U-0001
ZREVRANGE ranking:restaurants:rating 0 -1 WITHSCORES      // the whole leaderboard, already sorted
ZRANGEBYSCORE ranking:restaurants:rating 4.6 +inf WITHSCORES   // 4 restaurants: R-003, R-007, R-006, R-001
ZINCRBY ranking:restaurants:rating 0.5 R-009              // Pollo Brasa jumps from last to first. Re-run line 2
ZINCRBY ranking:restaurants:rating -0.5 R-009             // put it back
ZREVRANK ranking:restaurants:rating R-001                 // position = O(log n), no sorting at read time
OBJECT ENCODING user:U-0001                               // "listpack": tiny hashes are stored packed
MEMORY USAGE user:U-0001                                  // ~112 bytes for a whole user
SCAN 0 MATCH user:* COUNT 100                             // never KEYS * in production
```

Worth showing live: the **Profiler** tab (bottom bar). Start it while students run the Redis section and every
command they send through the gateway scrolls by, in real time.

---

## MongoDB: Mongo Express, http://localhost:8081

Database `domi`. Click a collection and switch the search box to **Advanced**. It has Query, Projection and Sort fields.

| Show | Collection | Query | Projection / Sort |
|---|---|---|---|
| A restaurant **with its menu embedded** (open it, expand `menu`) | restaurants | `{_id: "R-001"}` | |
| The golden order: items live inside the order | orders | `{_id: "O-000042"}` | |
| Valentina's orders, newest first (*10*) | orders | `{user_id: "U-0001"}` | sort `{placed_at: -1}` |
| Query **inside an array of subdocuments** | orders | `{"items.name": "Ajiaco santafereño"}` | proj. `{items: 1, total_cop: 1}` |
| Big orders (*46*) | orders | `{total_cop: {$gte: 100000}}` | sort `{total_cop: -1}` |
| Restaurants with a vegetarian dish (*6*) | restaurants | `{"menu.tags": "vegetarian"}` | proj. `{name: 1}` |
| Restaurants that sell soup (*4*) | restaurants | `{"menu.tags": "soup"}` | proj. `{name: 1, "menu.name": 1}` |

Point to make: the restaurant document *is* the menu page. One read, no join. Then ask: "what happens to the
order when the restaurant changes a price?" (Nothing. The order keeps its `unit_price_cop`. That's the point.)

Mongo Express has no aggregation box. For `$group`/`$lookup`, use the notebook.

---

## Neo4j: Neo4j Browser, http://localhost:7474 (neo4j / domi-neo4j)

These return **paths**, so the Browser draws them as a graph. That view is what students remember.

```cypher
// 0. The data model, drawn from the data itself
CALL db.schema.visualization()
```

```cypher
// 1. The golden order: everything that touched O-000042
MATCH p = (:User)-[:PLACED]->(o:Order {order_id: 'O-000042'})-[:CONTAINS]->(:Dish)<-[:SERVES]-(:Restaurant)
MATCH q = (:Courier)-[:DELIVERED]->(o)
RETURN p, q
```

```cypher
// 2. Valentina's food world: her orders, the dishes, and where they came from
MATCH p = (:User {user_id: 'U-0001'})-[:PLACED]->(:Order)-[:CONTAINS]->(:Dish)<-[:SERVES]-(:Restaurant)
RETURN p
```

```cypher
// 3. The referral forest. Variable-length path; Valentina → Andrés → Camila → Santiago is the 3-hop chain
MATCH p = (:User)-[:REFERRED*]->(:User)
RETURN p
```

```cypher
// 4. Who brought the most people in? (Camila Herrera, 4)
MATCH (u:User)-[:REFERRED]->(x)
RETURN u.name AS user, count(x) AS referrals ORDER BY referrals DESC LIMIT 5
```

```cypher
// 5. Dishes bought together. A self-join in SQL, one pattern here
//    (Ajiaco + Tamal tolimense: 12 orders; Pollo asado + Maduro con queso: 12)
MATCH (d1:Dish)<-[:CONTAINS]-(o:Order)-[:CONTAINS]->(d2:Dish)
WHERE d1.dish_id < d2.dish_id
RETURN d1.name, d2.name, count(o) AS together ORDER BY together DESC LIMIT 5
```

```cypher
// 6. Courier workload (Jhon Fredy: 256 of 479 orders)
MATCH (c:Courier)-[:DELIVERED]->(o:Order)
RETURN c.name AS courier, count(o) AS deliveries ORDER BY deliveries DESC
```

```cypher
// 7. Restaurants that pull customers from other localidades (El Ajiaco: 43 people)
MATCH (r:Restaurant)-[:SERVES]->(:Dish)<-[:CONTAINS]-(:Order)<-[:PLACED]-(u:User)
WHERE u.localidad <> r.localidad
RETURN r.name AS restaurant, count(DISTINCT u) AS fans_from_elsewhere ORDER BY fans_from_elsewhere DESC LIMIT 5
```

Tip: in the graph view, double-click a node to expand its neighbours. Start from query 1 and double-click the
restaurant to "walk" the graph live.

---

## InfluxDB: InfluxDB 3 Explorer, http://localhost:8888

**Data Explorer**, database `domi`, SQL. Switch the result to a **line/bar chart**. Times are UTC, so the
queries subtract 5 hours to show Bogotá time.

```sql
-- 1. The rain story in one number: orders per localidad-hour, by weather
--    (rain ≥ 2mm: 1.05 · drizzle: 0.37 · dry: 0.13). Rain means 8× the orders
SELECT sky, count(*) AS localidad_hours, sum(n) AS orders, round(avg(n), 2) AS orders_per_hour
FROM (
  SELECT w.localidad, w.time,
         CASE WHEN w.rain_mm >= 2 THEN 'rain >= 2mm' WHEN w.rain_mm > 0 THEN 'drizzle' ELSE 'dry' END AS sky,
         count(o.total_cop) AS n
  FROM weather w
  LEFT JOIN orders o ON o.localidad = w.localidad AND date_bin(INTERVAL '1 hour', o.time) = w.time
  GROUP BY 1, 2, 3)
GROUP BY sky ORDER BY orders_per_hour DESC
```

```sql
-- 2. Friday night in Chapinero, rain per hour (chart it: the spike is 19:00–21:00, the golden order)
SELECT time - INTERVAL '5 hours' AS bogota_time, rain_mm, temp_c
FROM weather
WHERE localidad = 'Chapinero' AND time >= '2026-10-30T11:00:00Z' AND time < '2026-10-31T05:00:00Z'
ORDER BY time
```

```sql
-- 3. Orders per day, Bogotá time (chart as bars)
SELECT date_bin(INTERVAL '1 day', time - INTERVAL '5 hours') AS day, count(*) AS orders
FROM orders GROUP BY 1 ORDER BY 1
```

```sql
-- 4. Orders by hour of day: lunch and dinner peaks
SELECT extract(hour FROM time - INTERVAL '5 hours') AS hour, count(*) AS orders
FROM orders GROUP BY 1 ORDER BY 1
```

```sql
-- 5. Revenue by localidad (Chapinero: 167 orders, 8.4M COP)
SELECT localidad, count(*) AS orders, sum(total_cop) AS revenue_cop
FROM orders GROUP BY localidad ORDER BY revenue_cop DESC
```

```sql
-- 6. The wettest hours of the two weeks (all Friday night, Chapinero 11.2 mm at 20:00)
SELECT time - INTERVAL '5 hours' AS bogota_time, localidad, rain_mm
FROM weather ORDER BY rain_mm DESC LIMIT 5
```

---

## Qdrant: dashboard, http://localhost:6333/dashboard

### Visualize (the best visual of the day)
Collections → `dishes` → **Visualize**. Paste and run:

```json
{ "limit": 50, "color_by": "restaurant_name" }
```

50 dishes projected to 2D. Soups, breakfasts and fried food cluster by *meaning*. Hover a dot to see the dish.

### Console (no embedding needed: query by point id)
Point ids follow dish order: `1` = Ajiaco, `2` = Chocolate santafereño, `31` = Changua, `37` = Caldo de costilla.

```http
// "More like the ajiaco" → Chocolate santafereño, Changua, ... (no keyword in common with "ajiaco")
POST collections/dishes/points/query
{ "query": 1, "limit": 5, "with_payload": ["name", "restaurant_name"] }
```

```http
// Same, but from other restaurants (a vector search plus a payload filter)
POST collections/dishes/points/query
{ "query": 1, "limit": 5, "with_payload": ["name", "restaurant_name"],
  "filter": { "must_not": [ { "key": "restaurant_name", "match": { "value": "El Ajiaco de la Abuela" } } ] } }
```

```http
// Recommend: like the ajiaco, but NOT like the hot chocolate → savoury dishes (Empanadas, Bandeja paisa...)
POST collections/dishes/points/query
{ "query": { "recommend": { "positive": [1], "negative": [2] } }, "limit": 5,
  "with_payload": ["name", "restaurant_name"] }
```

```http
// Look at one point: payload + the 384 numbers
POST collections/dishes/points
{ "ids": [1], "with_vector": true, "with_payload": true }
```

---

## Scylla and Elasticsearch

No UI in the stack. Run them from the notebook (or `docker compose exec scylla cqlsh` for Scylla).
