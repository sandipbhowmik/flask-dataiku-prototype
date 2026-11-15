# Flask + Dataiku correction prototype — step-by-step guide

This prototype implements an external, organization level Flask UI. Its Dataiku adapter reads the batch output and schema, appends manually validated edits to a separate SQL-backed Dataiku dataset, and requests an existing DSS scenario. No Dataiku Application or Visual Edit plugin is used.

Two modes are provided:

- **Local:** a working demonstration using SQLite and five sample records. No DSS account is needed.
- **DSS:** the same UI uses Dataiku's Python APIs over the DSS connection. The daily scenario captures saved corrections, applies them to source records, then recalculates the output.

The local path is tested. DSS files are ready to configure but have not been run against your instance. Check your installed DSS version and available connections before use. The name `accenture-ask-flask` is treated as a display name: obtain its actual project key from DSS. All `poc_` names below are proposed prototype assets, not verified existing assets.

## Connect this demonstration to your existing DSS Flow

Your DSS base URL is `https://20.203.127.11` and the project key observed in your job logs is `ACCENTURETEAMASKPROJECT`.

1. Activate `.venv` and install the Dataiku client from your DSS instance, as described in section 7.
2. Use `.env.dss.example` as the template for `.env`. Keep your existing private `.env` if one is already configured. Fill in your API key, choose `APP_PASSWORD`, and generate a `SECRET_KEY` if absent. Never put the API key in the HTML or commit it.
3. For this approved self-signed demonstration only, `.env` sets `DSS_VERIFY_SSL=false`. The client installer command is `pip install --trusted-host 20.203.127.11 dataiku-api-client https://20.203.127.11/public/packages/dataiku-internal-client.tar.gz`. Use `DSS_VERIFY_SSL=true` with a trusted certificate outside this demonstration.
4. Run `python check_dss_connection.py`. It reads datasets and scenario status; it does not save edits or start processing.
5. Run `python app.py` and open `http://127.0.0.1:5000`. The page must show **Data source: Dataiku DSS**.
6. Since record 1002 may already have been fixed in your notebook test, select 1003 and correct country from UK to GB. Save, reload to see history, and show that the current batch output still says UK.
7. Click **Request batch run**, then **Check batch status** until the run completes with SUCCESS. Click **Reload data**. Record 1003 should now show GB and its country issue should disappear.
8. Inspect the correction log, snapshot and application results in DSS if the audience wants to see the complete data path.

Use a single Flask process for the prototype's filesystem correction store. The computer running Flask must be able to reach the DSS address. The `raw_source` name you used in DSS does not require a change in Flask: Flask reads only the final output and correction log.

The remainder of this guide describes the original build from scratch. PostgreSQL is its optional SQL storage choice; your already-created managed filesystem datasets work for this single-user prototype.

## 1. Understand the prototype Flow

```text
Flask UI ── DSS API append ──> poc_correction_log (SQL table; persistent)
                                      |
                         daily/manual scenario takes snapshot
                                      v
poc_raw_source ───────────────> apply_corrections <── poc_corrections_snapshot
                                      |
                       +--------------+----------------+
                       v                               v
             poc_corrected_source           poc_correction_results
                       |
                 demo_calculations
                       |
                       v
               poc_final_output ── DSS API read ──> Flask UI
```

The snapshot and raw source are Flow roots. The snapshot is populated by the scenario, not by a recipe linked back from the output. This avoids a circular Flow. `poc_correction_log` is persistent input state: never clear or rebuild it in the daily scenario.

The business calculation is deliberately a placeholder: charge = amount × 2% for Retail, or amount × 1% for Corporate. This is not a trained ML model. Replace the calculation recipe with real calculations/scoring later.

## 2. Run the UI locally first

Prerequisite: Python 3.9 or newer for the local demo. Use a Python version supported by your DSS client when connecting to DSS.

From this prototype directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: keep `BACKEND=local`, choose an `APP_PASSWORD`, and set a random `SECRET_KEY`. For example, generate a secret with:

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Start the app:

```sh
python app.py
```

Open <http://127.0.0.1:5000> and sign in using `APP_USER` and `APP_PASSWORD`. On first launch, the local store creates the initial batch output from `sample_data/raw_source.csv`.

Four rows are highlighted. Select a record, choose its incorrect field, supply the corrected value and reason, then click **Save correction**. The old value remains in the displayed batch output until you run the batch. Reload to see saved correction history. **Request batch run** runs the local calculation immediately; this button requests asynchronous scenario execution in DSS mode.

Local data persists in `prototype.sqlite3`. Restarting the app preserves edits. There is no reset endpoint.

## 3. Prepare the sample source dataset in DSS

Use a dedicated prototype Flow zone in `accenture-ask-flask`, or a separate sandbox project. Preserve the existing production Flow and scenario.

1. Get the project **key** from DSS, not only its display name.
2. Upload `sample_data/raw_source.csv` and name the dataset `poc_raw_source`.
3. In its schema, explicitly set **all five columns to string**, including `record_id` and `amount`. This keeps the raw values, invalid values and source baselines consistent. Treat `record_id` as unique and nonempty.
4. Verify that the dataset has five rows and the following errors.

| Record | Field | Initial value | Example correction |
|---|---|---|---|
| 1002 | country | empty | AE |
| 1003 | country | UK | GB |
| 1004 | amount | -50 | 50 |
| 1005 | segment | Unknown | Corporate |

The uploaded file substitutes for Hive/HDFS in this first demonstration. Later replace this root with the actual Hive/HDFS dataset, or a recipe selecting and renaming its columns. Preserve stable record IDs and explicit source-to-editable-field mappings.

The country/segment lists and amount bounds are invented demo rules in `correction_core.py`. Agree the real rules with the business team.

## 4. Create the separate writable correction datasets

Choose an existing DSS PostgreSQL connection with permission to create managed tables, read rows and append rows. PostgreSQL stores edits; it does not replace Hive/HDFS as the incoming source. Using SQL here avoids attempting interactive row updates on HDFS files.

1. Open the DSS project's Python library editor.
2. Add the supplied `correction_core.py` at the library's Python root so `from correction_core import ...` works in recipes, notebooks and scenarios.
3. Create a Python code environment with `pandas` and make it available to the prototype notebook, recipes and scenario. Use a version compatible with your DSS installation; the built-in Dataiku packages are supplied by DSS.
4. Open a Python notebook in the project.
5. Paste `dataiku/initialize_logs.py`.
6. Set `CONNECTION` to your actual managed-write-enabled PostgreSQL connection name and run **once**.

It creates empty SQL-backed `poc_correction_log` and `poc_corrections_snapshot` datasets. The script refuses to run if either already exists. Do not rerun it to reset the demo.

Both datasets use these columns, all with DSS storage type **string**:

| Column | Purpose |
|---|---|
| correction_id | UUID generated in the browser and reused if the same submission is retried |
| record_id | Stable source business key |
| field_name | Editable source field: country, segment or amount |
| old_value | Value displayed to the reviewer |
| new_value | Validated replacement value |
| source_value | Raw source value when the reviewer saw that batch |
| source_batch_id | Batch reviewed by the user |
| edited_by | User authenticated by Flask |
| edited_at | Server-generated UTC timestamp |
| reason | Business explanation |

The log records **corrections**, not a second full copy of the final output. The Flow separately materializes a complete `poc_corrected_source` dataset for downstream processing.

## 5. Add the correction and calculation recipes

Create a **Python recipe** with:

- Inputs: `poc_raw_source`, `poc_corrections_snapshot`.
- Outputs: new managed datasets `poc_corrected_source`, `poc_correction_results`.
- Code: paste `dataiku/apply_recipe.py`.

Use your approved prototype storage connection for the outputs. Run the recipe once with the empty snapshot. The results dataset has columns `correction_id`, `record_id`, `field_name`, `status`.

Create a second **Python recipe** with:

- Input: `poc_corrected_source`.
- Output: new managed dataset `poc_final_output`.
- Code: paste `dataiku/calculate_recipe.py`.

Run it once. Verify five output rows and the same four invalid fields. The output also contains `source_country`, `source_segment`, `source_amount`, `batch_id`, `batch_time`, `row_version`, `issue_columns` and `calculated_charge`. These support source-change checks, review and demonstration.

The app permits edits only to the three configured source fields. Calculated charge, IDs and batch metadata cannot be edited. A prediction override would need a separate override stage after scoring.

## 6. Create the daily scenario

1. Create a **Python-script scenario** with ID `POC_DAILY_BATCH`.
2. Paste `dataiku/daily_scenario.py` as its script.
3. Select a Python environment with `pandas` and access to the project library.
4. Configure the scenario to avoid overlapping runs. For the prototype, use only this scenario to build these outputs; avoid independent manual builds during review.
5. Add a time-based trigger for **02:00 every day, Asia/Dubai**. Verify the timezone explicitly; do not assume DSS server time is Dubai time.
6. Enable the scenario's automatic triggers. Availability depends on the DSS installation/license.
7. Run it manually once and check the successful run and resulting datasets.

Each run reads the committed correction log once into a snapshot, overwrites the snapshot dataset, and forces the downstream recipes to rebuild. The scenario never overwrites the correction log. Edits committed after the snapshot read are picked up by the next run. Use a transactional SQL connection and keep the snapshot read consistent.

Correction rules:

- The latest event per record and field wins, ordered by server save time with UUID as a deterministic tie-breaker.
- Its replacement is applied only if the current raw source value equals the saved raw baseline.
- An unchanged source continues to receive the saved override on subsequent batches.
- `SOURCE_CHANGED` means the source value changed: the old override is skipped and must be reviewed again.
- `RECORD_MISSING`, `FIELD_NOT_ALLOWED` and `INVALID_VALUE` also skip the affected correction.
- The result dataset reports the latest effective event per field, not every historical event. Full submission history remains in the log.

The comparison uses trimmed source strings. Formatting changes can therefore require re-review. Replaying the same log is safe: it does not create new correction events.

For an actual source-refresh recipe, add a source-refresh build step at the appropriate point and ensure it operates on a stable input batch. The supplied sample scenario reads the existing uploaded source; it does not fetch a third-party feed.

## 7. Connect the external Flask backend to DSS

Create/use a DSS API key for an authorized user with access to this project, read access to output and correction datasets, write access to the correction dataset, and permission to execute the scenario. Validate the exact permissions with your administrator. API calls run with that DSS identity; `edited_by` separately records the Flask identity.

On the Flask machine, activate the virtual environment and install the Dataiku packages compatible with your DSS version:

```sh
pip install dataiku-api-client
pip install 'https://YOUR-DSS-HOST/public/packages/dataiku-internal-client.tar.gz'
```

Use the actual DSS base URL, including any deployment path. The `dataiku` package comes from your DSS instance; do not install an unrelated package of the same name from PyPI. Keep TLS certificate verification enabled and configure your organization's CA if needed.

Update `.env`:

```dotenv
BACKEND=dss
APP_USER=reviewer
APP_PASSWORD=your-demo-password
SECRET_KEY=your-generated-secret
DSS_URL=https://YOUR-DSS-HOST
DSS_API_KEY=your-key
DSS_PROJECT_KEY=YOUR_ACTUAL_PROJECT_KEY
DSS_OUTPUT_DATASET=poc_final_output
DSS_CORRECTIONS_DATASET=poc_correction_log
DSS_SCENARIO_ID=POC_DAILY_BATCH
```

Keep `.env` private. DSS credentials stay on the server. Restart Flask. Initially keep it bound to localhost. For a controlled shared demonstration behind your organization's HTTPS endpoint, use exactly **one application worker**:

```sh
gunicorn --workers 1 --threads 4 --bind 127.0.0.1:5000 'app:create_app()'
```

This prototype uses one demo Basic Auth account, session-based CSRF protection and a process-local save lock. The SQL append is closed before a success response. A repeated correction UUID returns the prior saved event instead of adding a second copy. Attempts to edit the same field twice against the same output batch are rejected; run and reload before editing it again.

**Save correction does not trigger processing.** It appends the event and makes it available for the next scenario snapshot. **Request batch run** optionally requests the existing scenario immediately. Check batch status and reload after SUCCESS. The daily trigger still works if nobody presses the button.

## 8. Demonstrate the complete cycle

1. Open Flask and confirm the four highlighted records.
2. Correct 1002 country to AE and provide a reason.
3. Reload: output still has the old blank country; the correction is visible in history.
4. Request a batch run, or wait for the daily schedule.
5. Check status until the run completes successfully, then reload.
6. Verify 1002 country is AE, its country issue is gone, and `poc_correction_results` contains APPLIED.
7. Save the other three sample corrections and run again.
8. Verify zero invalid fields. Record 1004 charge is 1.00; record 1005 charge is 120.00.
9. Run another batch without saving anything: corrections persist and log row count stays unchanged.
10. Change raw source 1002 country to IN and refresh that source dataset. Run again. The output should now use IN and the old correction should report SOURCE_CHANGED. A new review establishes a new source baseline.

| Acceptance check | Expected result |
|---|---|
| Missing country corrected | Saved immediately to log; applied after batch |
| UK submitted as a corrected country | HTTP 400: allowed code is GB |
| Negative / NaN / infinite amount | HTTP 400 |
| Browser retry of identical submission ID | Existing event returned; one log event |
| Another batch ran since page load | HTTP 409: reload required |
| Second pending correction to same field/batch | HTTP 409 |
| Source changed since reviewed batch | Correction skipped; SOURCE_CHANGED |
| Scenario run failed | Status shows failure; inspect DSS logs before retrying |

## 9. API routes and integration points

| Method / route | Purpose |
|---|---|
| GET / | Review UI and CSRF session initialization |
| GET /api/schema | Output schema and editable-field allowlist |
| GET /api/records | Output rows |
| GET /api/corrections | Saved audit history |
| POST /api/corrections | Validate and append one field correction |
| POST /api/batch/run | Request scenario execution |
| GET /api/batch/status | Running status and last completed outcome |

All routes require authentication. POST requests require the session cookie and `X-CSRF-Token` from the UI. Do not bypass these to call the app from another service; add service authentication deliberately if required.

`store.py` isolates the platform adapter. The business UI can keep its own organization-wide identity and routing layer while selecting a Dataiku adapter for this project. The prototype deliberately fixes one project and dataset rather than accepting arbitrary DSS object names from the browser.

## 10. Tests and production boundaries

Run:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The tests cover the local end-to-end save/batch/replay cycle, all four fixes and recalculation, stale submissions, pending-edit conflicts, retry deduplication, invalid numbers, duplicate source IDs, source-change protection, authentication and CSRF. Live DSS API access, SQL permissions, scenario scheduling and Hive connectivity require validation on your instance.

Before organization-wide deployment, replace the shared demo login with corporate SSO and per-user authorization. Use a transactional correction service/table with a unique correction-ID constraint and atomic conflict checks if you need multiple Flask workers or instances. The process-local lock here is not a distributed lock. Use database ordering/commit timestamps rather than application clocks across multiple servers.

This small-data app reads entire datasets and logs on each request. Add server-side filtering/pagination and a durable batch ledger for real volumes. Publish output versions atomically so a reviewer never reads a partially rebuilt table; the prototype should be reviewed after the scenario completes. Keep snapshots/results by run ID if historical application evidence is required. Preserve separate raw baselines, distinguish explicit null overrides from absent edits, define correction expiry/withdrawal, and define what happens when IDs change.

This prototype feeds a corrected dataset into the next Dataiku calculation. It does **not** update a third-party Hive/HDFS table. If physical source write-back is required, add an explicit validated export/merge stage and use the source owner's permitted mechanism.

## Official references

- [Public DSS API](https://doc.dataiku.com/dss/latest/publicapi/index.html)
- [Install and connect the Python clients](https://developer.dataiku.com/latest/tutorials/devtools/python-client/index.html)
- [Dataset append versus overwrite](https://developer.dataiku.com/latest/concepts-and-examples/datasets/datasets-data.html)
- [Dataset API and fixed-schema writers](https://developer.dataiku.com/latest/api-reference/python/datasets.html)
- [Run and monitor scenarios externally](https://developer.dataiku.com/latest/api-reference/python/scenarios.html)
- [Build datasets inside a scenario](https://developer.dataiku.com/latest/api-reference/python/scenarios-inside.html)
