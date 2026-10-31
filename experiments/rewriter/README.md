# E6d: a rewrite layer over the PostgreSQL catalog

`ckrewrite.py` reads unique indexes (with predicates, NULLS NOT DISTINCT) and CHECK constraints
of the form NOT (P) OR (k IS NOT NULL AND ...) from `pg_index` / `pg_constraint`, translates
predicates into conditions (exactly for catalog predicates, over-approximated for query
predicates), and rewrites SELECT DISTINCT, GROUP BY with count(*), and left joins into the scope,
deciding by implication (Algorithm 1 with the reductions when b <= 10, else SAT).

`run_e6d.py` declares the mined keys of the E6b tables as their enforcement artefacts, feeds all
E6b queries as SQL text through the layer, checks every decision against E6b and the emitted SQL
of a sample against the original's result, and records catalog-read and rewrite times
(`results_e6d.json`). UniProt is excluded: some of its keys over long text values exceed
PostgreSQL's 8 kB index-row limit and cannot be declared as unique indexes.

Requires `sqlglot` (25.34.1) and `psycopg`.
