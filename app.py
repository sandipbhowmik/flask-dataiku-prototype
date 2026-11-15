import hmac
import os
import secrets
import threading
from datetime import datetime, timezone
from functools import wraps
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from correction_core import FIELDS, clean, validate
from store import LocalStore, DSSStore

load_dotenv()


def create_app(store=None):
    app = Flask(__name__)
    for name in ('APP_USER', 'APP_PASSWORD', 'SECRET_KEY'):
        if not os.getenv(name):
            raise RuntimeError('Set ' + name + ' in .env before starting')
    app.secret_key = os.environ['SECRET_KEY']
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict', MAX_CONTENT_LENGTH=16384)
    app.store = store or (DSSStore() if os.getenv('BACKEND', 'local') == 'dss' else LocalStore())
    lock = threading.Lock()  # Prototype: exactly one application process.

    def protected(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth = request.authorization
            if not auth or not hmac.compare_digest(auth.username or '', os.environ['APP_USER']) or not hmac.compare_digest(auth.password or '', os.environ['APP_PASSWORD']):
                return 'Sign in to the prototype', 401, {'WWW-Authenticate': 'Basic realm="Correction prototype"'}
            if request.method == 'POST':
                expected = session.get('csrf', '')
                if not expected or not hmac.compare_digest(expected, request.headers.get('X-CSRF-Token', '')):
                    return jsonify(error='Reload the page before submitting.'), 403
            return fn(*args, **kwargs)
        return wrapper

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/')
    @protected
    def home():
        session.setdefault('csrf', secrets.token_urlsafe(32))
        rows = app.store.read_output()
        return render_template('index.html', rows=rows, schema=app.store.schema(),
                               fields=FIELDS, csrf=session['csrf'], log=app.store.read_log(),
                               mode='Dataiku DSS' if isinstance(app.store, DSSStore) else 'Local demo')

    @app.get('/api/schema')
    @protected
    def schema():
        return jsonify(columns=app.store.schema(), editable_columns=FIELDS)

    @app.get('/api/records')
    @protected
    def records():
        return jsonify(records=app.store.read_output())

    @app.get('/api/corrections')
    @protected
    def corrections():
        return jsonify(corrections=app.store.read_log())

    @app.post('/api/corrections')
    @protected
    def save():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error='A JSON object is required.'), 400
        required = ('correction_id', 'record_id', 'field_name', 'new_value', 'row_version', 'reason')
        if any(not isinstance(body.get(k), str) for k in required):
            return jsonify(error='Required fields must be strings.'), 400
        try:
            UUID(body['correction_id'])
            value = validate(body['field_name'], body['new_value'])
            if not 1 <= len(body['reason'].strip()) <= 500:
                raise ValueError('Provide a reason of 1–500 characters.')
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        with lock:
            log = app.store.read_log()
            existing = next((e for e in log if e['correction_id'] == body['correction_id']), None)
            if existing:
                same = (existing['record_id'] == body['record_id'] and existing['field_name'] == body['field_name']
                        and existing['new_value'] == value and existing['reason'] == body['reason'].strip()
                        and existing['edited_by'] == request.authorization.username)
                return (jsonify(message='Already saved', correction=existing), 200) if same else (jsonify(error='Correction ID already used.'), 409)
            row = next((r for r in app.store.read_output() if r['record_id'] == body['record_id']), None)
            if not row:
                return jsonify(error='Record no longer exists.'), 404
            if row['row_version'] != body['row_version']:
                return jsonify(error='Output changed. Reload and review again.'), 409
            if any(e['record_id'] == body['record_id'] and e['field_name'] == body['field_name']
                   and e['source_batch_id'] == row['batch_id'] for e in log):
                return jsonify(error='A correction for this field is pending. Run the batch and reload before editing again.'), 409
            if clean(row[body['field_name']]) == value:
                return jsonify(error='The new value is unchanged.'), 400
            event = {'correction_id': body['correction_id'], 'record_id': body['record_id'],
                     'field_name': body['field_name'], 'old_value': clean(row[body['field_name']]),
                     'new_value': value, 'source_value': clean(row['source_' + body['field_name']]),
                     'source_batch_id': row['batch_id'], 'edited_by': request.authorization.username,
                     'edited_at': datetime.now(timezone.utc).isoformat(), 'reason': body['reason'].strip()}
            app.store.append(event)
            return jsonify(message='Saved. The next batch will apply this correction.', correction=event), 201

    @app.post('/api/batch/run')
    @protected
    def run_batch():
        with lock:
            return jsonify(app.store.run()), 202

    @app.get('/api/batch/status')
    @protected
    def status():
        return jsonify(app.store.status())

    @app.errorhandler(Exception)
    def failure(error):
        from werkzeug.exceptions import HTTPException
        if isinstance(error, HTTPException):
            return error
        app.logger.exception('Prototype operation failed')
        return jsonify(error='Operation failed. Check the server log; reload the correction history before retrying a save.'), 502

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5000, debug=False)
