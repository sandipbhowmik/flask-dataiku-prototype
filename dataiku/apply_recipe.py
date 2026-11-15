# Inputs: poc_raw_source, poc_corrections_snapshot
# Outputs: poc_corrected_source, poc_correction_results
import dataiku
import pandas as pd
from correction_core import apply_corrections

raw = dataiku.Dataset('poc_raw_source').get_dataframe(infer_with_pandas=False).fillna('').to_dict('records')
log = dataiku.Dataset('poc_corrections_snapshot').get_dataframe(infer_with_pandas=False).fillna('').to_dict('records')
corrected, results = apply_corrections(raw, log)
dataiku.Dataset('poc_corrected_source').write_with_schema(pd.DataFrame(corrected))
report = pd.DataFrame(results, columns=['correction_id', 'record_id', 'field_name', 'status'])
# Explicit string schema also works when no corrections exist.
report = report.astype(str)
dataiku.Dataset('poc_correction_results').write_with_schema(report)
