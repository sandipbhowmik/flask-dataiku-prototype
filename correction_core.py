"""Shared, dependency-free rules: copy into the DSS project's Python library."""
import hashlib
import json
import math
from datetime import datetime, timezone
from uuid import uuid4

FIELDS = ('country', 'segment', 'amount')
LOG_COLUMNS = ('correction_id', 'record_id', 'field_name', 'old_value', 'new_value',
               'source_value', 'source_batch_id', 'edited_by', 'edited_at', 'reason')


def clean(value):
    return '' if value is None else str(value).strip()


def validate(field, value):
    value = clean(value)
    if field == 'country' and value in ('AE', 'IN', 'GB', 'US'):
        return value
    if field == 'segment' and value in ('Retail', 'Corporate'):
        return value
    if field == 'amount':
        try:
            number = float(value)
            if math.isfinite(number) and 0 <= number <= 1000000000:
                return format(number, '.12g')
        except (ValueError, TypeError):
            pass
    raise ValueError('Allowed values: country AE/IN/GB/US; segment Retail/Corporate; amount 0–1,000,000,000.')


def issues(row):
    result = []
    for field in FIELDS:
        try:
            validate(field, row.get(field))
        except ValueError:
            result.append(field)
    return result


def version(row):
    payload = json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def apply_corrections(source, log):
    """Latest saved override wins, but only while its raw source baseline matches."""
    if any(not clean(r.get('record_id')) for r in source):
        raise ValueError('Source record IDs must be nonempty')
    rows = {clean(r['record_id']): {k: clean(v) for k, v in r.items()} for r in source}
    if len(rows) != len(source):
        raise ValueError('Duplicate source record IDs')
    latest = {}
    for event in sorted(log, key=lambda e: (e['edited_at'], e['correction_id'])):
        latest[(event['record_id'], event['field_name'])] = event
    results = []
    for (record_id, field), event in latest.items():
        state = 'APPLIED'
        row = rows.get(record_id)
        if not row:
            state = 'RECORD_MISSING'
        elif field not in FIELDS:
            state = 'FIELD_NOT_ALLOWED'
        elif clean(row.get(field)) != clean(event['source_value']):
            state = 'SOURCE_CHANGED'
        else:
            try:
                row[field] = validate(field, event['new_value'])
            except ValueError:
                state = 'INVALID_VALUE'
        results.append({'correction_id': event['correction_id'], 'record_id': record_id,
                        'field_name': field, 'status': state})
    # Baselines always represent raw inputs, even after corrections.
    for raw in source:
        for field in FIELDS:
            rows[clean(raw['record_id'])]['source_' + field] = clean(raw.get(field))
    return list(rows.values()), results


def calculate(rows, batch_id=None):
    batch_id = batch_id or str(uuid4())
    output = []
    for source in rows:
        row = dict(source)
        invalid = issues(row)
        # Placeholder for business calculations / model scoring, not a real ML model.
        row['calculated_charge'] = None if 'amount' in invalid or 'segment' in invalid else round(
            float(row['amount']) * (0.02 if row['segment'] == 'Retail' else 0.01), 2)
        row['issue_columns'] = ','.join(invalid)
        row['batch_id'] = batch_id
        row['batch_time'] = datetime.now(timezone.utc).isoformat()
        row['row_version'] = version(row)
        output.append(row)
    return output
