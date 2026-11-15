import csv
import json
import os
import sqlite3
from pathlib import Path
from correction_core import apply_corrections, calculate, LOG_COLUMNS

ROOT = Path(__file__).resolve().parent


class LocalStore:
    def __init__(self, path=None):
        self.path = path or ROOT / 'prototype.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS corrections (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS output (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        if not self.read_output():
            self.run()

    def connect(self):
        return sqlite3.connect(self.path)

    def read_output(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM output ORDER BY id')]

    def schema(self):
        rows = self.read_output()
        return [{'name': k, 'type': 'double' if k == 'calculated_charge' else 'string'} for k in rows[0]]

    def read_log(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM corrections')]

    def append(self, event):
        with self.connect() as db:
            db.execute('INSERT INTO corrections VALUES (?, ?)', (event['correction_id'], json.dumps(event)))

    def run(self):
        with (ROOT / 'sample_data/poc_raw_source.csv').open() as file:
            raw = list(csv.DictReader(file))
        corrected, report = apply_corrections(raw, self.read_log())
        output = calculate(corrected)
        with self.connect() as db:
            db.execute('DELETE FROM output')
            db.executemany('INSERT INTO output VALUES (?, ?)', [(r['record_id'], json.dumps(r)) for r in output])
        return {'message': 'Local batch completed', 'correction_results': report}

    def status(self):
        return {'running': False, 'mode': 'local'}


class DSSStore:
    def __init__(self):
        import dataiku
        self.dataiku = dataiku
        # Demo-only bypass must be explicitly enabled; verification is the default.
        verify_ssl = os.getenv('DSS_VERIFY_SSL', 'true').lower() not in ('false', '0', 'no')
        dataiku.set_remote_dss(os.environ['DSS_URL'], os.environ['DSS_API_KEY'],
                              no_check_certificate=not verify_ssl)
        self.project = dataiku.api_client().get_project(os.environ['DSS_PROJECT_KEY'])
        self.output_name = os.getenv('DSS_OUTPUT_DATASET', 'poc_final_output')
        self.log_name = os.getenv('DSS_CORRECTIONS_DATASET', 'poc_correction_log')
        self.scenario = self.project.get_scenario(os.getenv('DSS_SCENARIO_ID', 'POC_DAILY_BATCH'))

    def core(self, name):
        return self.dataiku.Dataset(name, project_key=os.environ['DSS_PROJECT_KEY'], ignore_flow=True)

    def read_output(self):
        # All rows for the tiny prototype. Production needs server-side paging/filtering.
        return [dict(row.items()) for row in self.core(self.output_name).iter_rows()]

    def schema(self):
        return self.project.get_dataset(self.output_name).get_schema()['columns']

    def read_log(self):
        return [{key: ('' if value is None else value) for key, value in row.items()}
                for row in self.core(self.log_name).iter_rows()]

    def append(self, event):
        dataset = self.core(self.log_name)
        dataset.spec_item['appendMode'] = True
        # Schema is fixed at setup. Never write_with_schema in a UI request.
        with dataset.get_writer() as writer:
            writer.write_row_dict({column: event[column] for column in LOG_COLUMNS})

    def run(self):
        if self.scenario.get_status().running:
            return {'message': 'Scenario is already running; no additional run requested.'}
        self.scenario.run()
        return {'message': 'Scenario run requested. Check status; the output is not updated immediately.'}

    def status(self):
        current = self.scenario.get_current_run()
        previous = self.scenario.get_last_finished_run()
        return {'running': bool(current), 'last_outcome': previous.outcome if previous else None,
                'last_run_id': previous.id if previous else None, 'mode': 'dss'}
