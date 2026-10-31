"""Generate TPC-DS with DuckDB's dsdgen and load it into PostgreSQL with the keys of the TPC-DS
specification: primary keys (surrogate keys; composite for the fact tables) and NOT NULL on
key and business-key columns (the specification's NOT NULL declarations). DuckDB declares no
constraints, so they are added here. Usage: python load_tpcds.py SF WORKDIR DSN"""
import os, sys, time
import duckdb, psycopg

PK = {
    'call_center': ['cc_call_center_sk'], 'catalog_page': ['cp_catalog_page_sk'],
    'catalog_returns': ['cr_item_sk', 'cr_order_number'], 'catalog_sales': ['cs_item_sk', 'cs_order_number'],
    'customer': ['c_customer_sk'], 'customer_address': ['ca_address_sk'],
    'customer_demographics': ['cd_demo_sk'], 'date_dim': ['d_date_sk'],
    'household_demographics': ['hd_demo_sk'], 'income_band': ['ib_income_band_sk'],
    'inventory': ['inv_date_sk', 'inv_item_sk', 'inv_warehouse_sk'], 'item': ['i_item_sk'],
    'promotion': ['p_promo_sk'], 'reason': ['r_reason_sk'], 'ship_mode': ['sm_ship_mode_sk'],
    'store': ['s_store_sk'], 'store_returns': ['sr_item_sk', 'sr_ticket_number'],
    'store_sales': ['ss_item_sk', 'ss_ticket_number'], 'time_dim': ['t_time_sk'],
    'warehouse': ['w_warehouse_sk'], 'web_page': ['wp_web_page_sk'],
    'web_returns': ['wr_item_sk', 'wr_order_number'], 'web_sales': ['ws_item_sk', 'ws_order_number'],
    'web_site': ['web_site_sk'],
}
# business keys declared NOT NULL by the specification
BUSINESS = {'call_center': 'cc_call_center_id', 'catalog_page': 'cp_catalog_page_id', 'customer': 'c_customer_id',
            'customer_address': 'ca_address_id', 'date_dim': 'd_date_id', 'item': 'i_item_id',
            'promotion': 'p_promo_id', 'reason': 'r_reason_id', 'ship_mode': 'sm_ship_mode_id',
            'store': 's_store_id', 'time_dim': 't_time_id', 'warehouse': 'w_warehouse_id',
            'web_page': 'wp_web_page_id', 'web_site': 'web_site_id'}


def main():
    sf, work, dsn = float(sys.argv[1]), sys.argv[2], sys.argv[3]
    os.makedirs(work, exist_ok=True)
    db = os.path.join(work, f'tpcds_sf{sf:g}.duckdb')
    con = duckdb.connect(db)
    con.execute('INSTALL tpcds; LOAD tpcds;')
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'store_sales'").fetchone()[0]:
        con.execute(f'CALL dsdgen(sf={sf:g})')
    pg = psycopg.connect(dsn, autocommit=True)
    for t in PK:
        cols = con.execute("select column_name, data_type from duckdb_columns() where table_name = ? order by column_index", [t]).fetchall()
        nn = set(PK[t]) | ({BUSINESS[t]} if t in BUSINESS else set())
        ddl = ', '.join(f'{c} {ty}' + (' NOT NULL' if c in nn else '') for c, ty in cols)
        path = os.path.join(work, f'{t}.csv')
        con.execute(f"COPY {t} TO '{path}' (HEADER false, DELIMITER '|', NULL '')")
        t0 = time.time()
        with pg.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS {t} CASCADE')
            cur.execute(f'CREATE TABLE {t} ({ddl})')
            with open(path, 'rb') as fh, cur.copy(f"COPY {t} FROM STDIN (FORMAT csv, DELIMITER '|', NULL '')") as cp:
                while chunk := fh.read(1 << 20): cp.write(chunk)
            cur.execute(f'ALTER TABLE {t} ADD PRIMARY KEY ({", ".join(PK[t])})')
            cur.execute(f'ANALYZE {t}')
            cur.execute(f'SELECT count(*) FROM {t}'); n = cur.fetchone()[0]
        os.remove(path)
        print(f'{t}: {n} rows, {time.time() - t0:.1f}s', flush=True)


if __name__ == '__main__':
    main()
