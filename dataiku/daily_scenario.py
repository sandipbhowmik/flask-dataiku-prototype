# Python-script scenario ID: POC_DAILY_BATCH
# Run only one instance of this scenario at a time.
import dataiku
import pandas as pd
from dataiku.scenario import Scenario
from correction_core import LOG_COLUMNS

scenario = Scenario()
# One read captures the committed correction rows visible to this batch.
# UI saves after this read remain in the log for the next batch.
log = dataiku.Dataset('poc_correction_log').get_dataframe(infer_with_pandas=False).fillna('')
snapshot = log.loc[:, list(LOG_COLUMNS)].copy().astype(str)
target = dataiku.Dataset('poc_corrections_snapshot', ignore_flow=True)
target.write_dataframe(snapshot, infer_schema=False)
# Snapshot and raw source are Flow roots. Never rebuild/clear the correction log.
# Force rebuilding the two Python recipes, even when input timestamps appear unchanged.
scenario.build_dataset('poc_final_output', build_mode='RECURSIVE_FORCED_BUILD')
# The apply recipe's second output is poc_correction_results; inspect it for conflicts.
