# Input: poc_corrected_source. Output: poc_final_output
import dataiku
import pandas as pd
from correction_core import calculate

rows = dataiku.Dataset('poc_corrected_source').get_dataframe(infer_with_pandas=False).fillna('').to_dict('records')
output = pd.DataFrame(calculate(rows))
output['calculated_charge'] = pd.to_numeric(output['calculated_charge'], errors='coerce').astype('float64')
dataiku.Dataset('poc_final_output').write_with_schema(output)
