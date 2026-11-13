# Domi NoSQL lab: running it

Specs: [specs/](specs/README.md).

```
docker compose up -d --build     # ~2 min until all 7 databases are loaded
docker compose logs -f loader    # wait for 7 "loaded in" lines
```

- Gateway: http://localhost (class code: `domi`, or set `CLASS_CODE`). `GET /health` shows which engines are up.

Visualizers (instructor screen):

| Engine | UI | URL |
|---|---|---|
| Redis | RedisInsight | http://localhost:5540 (`domi` connection preloaded) |
| MongoDB | Mongo Express | http://localhost:8081 |
| Neo4j | Neo4j Browser | http://localhost:7474 (neo4j / `domi-neo4j`, or set `NEO4J_PASSWORD`) |
| InfluxDB | InfluxDB 3 Explorer | http://localhost:8888 (`domi` server preloaded; else add `http://influx:8181`) |
| Qdrant | Qdrant dashboard | http://localhost:6333/dashboard |
| Scylla, Elasticsearch | none (use the gateway) | |

- Reset one database: `docker compose restart mongo`. The loader refills it within ~20 s.

| Folder | What |
|---|---|
| `loader/domi_data.py` | The dataset: hand-written cast and dishes + seeded generator. `python loader/domi_data.py` dumps it to `data/` |
| `loader/load.py` | Fills each database; reloads any that comes back empty |
| `gateway/app.py` | `POST /<engine>` with the native query as the body; auth + blocked keywords |
| `notebook/domi_lab.ipynb` | The student lab. Upload to Colab; set `GATEWAY` in the setup cell's default to the public URL before class |
