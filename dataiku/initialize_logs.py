# Run ONCE in a DSS Python notebook in the intended prototype project.
# Choose a managed-write-enabled dataset/database connection available in your DSS.
import dataiku
import pandas as pd
from correction_core import LOG_COLUMNS

CONNECTION = 'REPLACE_WITH_MANAGED_WRITE_ENABLED_DATASET_CONNECTION'
project = dataiku.api_client().get_project(dataiku.default_project_key())
names = ('poc_correction_log', 'poc_corrections_snapshot')
existing = {item['name'] for item in project.list_datasets()}
if existing.intersection(names):
    raise RuntimeError('Setup stopped: a log/snapshot dataset already exists. Do not reinitialize saved edits.')
for name in names:
    builder = project.new_managed_dataset(name)
    builder.with_store_into(CONNECTION)
    builder.create()
    dataset = dataiku.Dataset(name, ignore_flow=True)
    dataset.write_schema([{'name': column, 'type': 'string'} for column in LOG_COLUMNS])
    dataset.write_dataframe(pd.DataFrame({column: pd.Series(dtype='str') for column in LOG_COLUMNS}), infer_schema=False)
print('Created two empty datasets. Never rerun this initializer to clear corrections.')
