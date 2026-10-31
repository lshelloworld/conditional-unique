"""Query-optimisation cases: the top conditional keys of discovery/report.md.

Each case is a conditional key C:K(K) with its scope as a SQL predicate. Constants are the
pseudonymised (hashed) values of the exports; they are looked up in discovery/results by
column and frequency rank, so the predicate is exactly the discovered condition."""
import json, os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')

def const(ds, table, label):
    D = json.load(open(os.path.join(ROOT, 'discovery', 'results', f'{ds}.json')))
    for t in D['tables']:
        if t['table'] != table: continue
        for r in t['conditional']:
            if label in r['constants']: return int(r['constants'][label])
    raise KeyError((ds, table, label))

def cases():
    nhl = const('hockey', 'Hockey.SeriesPost', 'lgIDWinner=v1')
    hof = const('hockey', 'Hockey.HOF', 'category=v2')
    ch1 = const('voc', 'voc.invoices', 'chamber=v1')
    return [
        # id, dataset, table, class, key, predicate (scope), list
        dict(id='SP',   ds='hockey', table='SeriesPost', cls='cand', K=['year', 'tmIDLoser'],
             P=f'"lgIDWinner" = {nhl}', list='QO'),
        dict(id='GO',   ds='hockey', table='Goalies', cls='cand', K=['playerID', 'year', 'tmID'],
             P=f'"lgID" = {nhl}', list='QO'),
        dict(id='CO',   ds='hockey', table='Coaches', cls='cand', K=['coachID', 'year'],
             P='"postg" IS NOT NULL', list='QO'),
        dict(id='GO2',  ds='hockey', table='Goalies', cls='cand', K=['playerID', 'year'],
             P='"PostGP" IS NOT NULL', list='QO'),
        dict(id='HOF',  ds='hockey', table='HOF', cls='cand', K=['name'],
             P=f'"category" = {hof}', list='QO'),
        dict(id='SO',   ds='voc', table='soldiers', cls='cand', K=['number'],
             P='"onboard_at_arrival" IS NOT NULL', list='QO'),
        dict(id='SE',   ds='voc', table='seafarers', cls='cand', K=['number'],
             P='"onboard_at_arrival" IS NOT NULL', list='QO'),
        dict(id='VO1',  ds='voc', table='voyages', cls='cert', K=['number', 'arrival_date'],
             P='"type_of_boat" IS NULL', list='QO'),
        dict(id='VO2',  ds='voc', table='voyages', cls='cand', K=['number', 'departure_date'],
             P='"type_of_boat" IS NULL', list='QO'),
        dict(id='VO3',  ds='voc', table='voyages', cls='dom', K=['boatname', 'departure_date'],
             P='"master" IS NOT NULL', list='QO'),
        dict(id='IN',   ds='voc', table='invoices', cls='cand', K=['number', 'invoice'],
             P=f'"chamber" = {ch1}', list='QO'),
        dict(id='TR1',  ds='voc', table='voyages', cls='pos', K=['master', 'departure_date'],
             P='"yard" IS NOT NULL', list='GROUP-BY-trap'),
        dict(id='TR2',  ds='voc', table='voyages', cls='pos', K=['master', 'departure_date'],
             P='"cape_arrival" IS NOT NULL', list='GROUP-BY-trap'),
    ] + csv_cases()

# plaintext datasets, real scale (NCVoter: all 1,023,993 records; UniProt: 24,173 records)
CSV_COLS = {
    'ncvoter': ['ncid', 'last_name', 'first_name', 'middle_name', 'birth_age', 'birth_state',
                'res_street_address', 'status_cd', 'drivers_lic'],
    'uniprot': ['accession', 'cross_reference_geneid', 'sequence_checksum', 'feature_chain',
                'cross_reference_oma', 'feature_modified_residue'],
}

def csv_cases():
    act = '"status_cd" = \'A\' AND "drivers_lic" = \'Y\''
    ina = '"status_cd" = \'I\' AND "drivers_lic" = \'Y\''
    return [
        dict(id='NV1', ds='ncvoter', table='voters', cls='cert',
             K=['last_name', 'first_name', 'middle_name', 'birth_age', 'res_street_address'], P=act, list='QO'),
        dict(id='NV2', ds='ncvoter', table='voters', cls='cand',
             K=['last_name', 'first_name', 'birth_age', 'res_street_address'], P=ina, list='QO'),
        dict(id='NV3', ds='ncvoter', table='voters', cls='dom',
             K=['first_name', 'middle_name', 'birth_age', 'birth_state', 'res_street_address'], P=act, list='QO'),
        dict(id='NVT', ds='ncvoter', table='voters', cls='pos',
             K=['first_name', 'middle_name', 'birth_age', 'res_street_address'], P=act, list='GROUP-BY-trap'),
        dict(id='UP1', ds='uniprot', table='proteins', cls='cert',
             K=['cross_reference_geneid', 'sequence_checksum'], P='"cross_reference_oma" IS NOT NULL', list='QO'),
        dict(id='UP2', ds='uniprot', table='proteins', cls='cert',
             K=['sequence_checksum', 'feature_chain'], P='"feature_modified_residue" IS NULL', list='QO'),
    ]
