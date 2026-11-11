# Domi NoSQL lab: running it

Specs: [specs/](specs/README.md).

```
docker compose up -d --build     # ~2 min until all 7 databases are loaded
docker compose logs -f loader    # wait for 7 "loaded in" lines
```

- Gateway: http://localhost:8000 (class code: `domi`, or set `CLASS_CODE`). `GET /health` shows which engines are up.
- Neo4j Browser: http://localhost:7474 (neo4j / `domi-neo4j`, or set `NEO4J_PASSWORD`)
- Qdrant dashboard: http://localhost:6333/dashboard
- Reset one database: `docker compose restart mongo`. The loader refills it within ~20 s.

| Folder | What |
|---|---|
| `loader/domi_data.py` | The dataset: hand-written cast and dishes + seeded generator. `python loader/domi_data.py` dumps it to `data/` |
| `loader/load.py` | Fills each database; reloads any that comes back empty |
| `gateway/app.py` | `POST /<engine>` with the native query as the body; auth + blocked keywords |
| `notebook/domi_lab.ipynb` | The student lab. Upload to Colab; set `GATEWAY` in the setup cell's default to the public URL before class |
