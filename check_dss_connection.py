"""Read-only checks; does not save corrections or trigger a scenario."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / '.env')


def main():
    required = ('DSS_URL', 'DSS_API_KEY', 'DSS_PROJECT_KEY')
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit('Fill these settings in .env: ' + ', '.join(missing))
    if os.getenv('BACKEND') != 'dss':
        raise SystemExit('Set BACKEND=dss in .env to connect the actual Dataiku instance.')
    try:
        import dataiku
        if not hasattr(dataiku, 'set_remote_dss'):
            raise ImportError('Dataiku client is not installed')
    except ImportError:
        raise SystemExit('Install the Dataiku client package from your DSS instance into this virtual environment.')
    if os.getenv('DSS_VERIFY_SSL', 'true').lower() in ('false', '0', 'no'):
        print('Demo setting: DSS certificate verification is disabled.')
    from store import DSSStore
    try:
        store = DSSStore()
        columns = {column['name'] for column in store.schema()}
        needed = {'record_id', 'customer_name', 'country', 'segment', 'amount', 'row_version',
                  'batch_id', 'issue_columns', 'calculated_charge', 'source_country', 'source_segment', 'source_amount'}
        if needed - columns:
            raise SystemExit('Final output is missing required columns: ' + ', '.join(sorted(needed - columns)))
        rows = store.read_output()
        log = store.read_log()
        status = store.status()
    except Exception as exc:
        print('Connection check failed (' + type(exc).__name__ + ').')
        print('Check the DSS URL/network, API key, project/dataset/scenario IDs, and user permissions.')
        print('No corrections were saved and no batch run was requested.')
        raise SystemExit(1)
    print('Connected to DSS project: ' + os.environ['DSS_PROJECT_KEY'])
    print('Output records: ' + str(len(rows)))
    print('Saved corrections: ' + str(len(log)))
    print('Scenario running: ' + str(status['running']))
    print('Last completed outcome: ' + str(status['last_outcome']))
    if not rows:
        print('Run the Dataiku batch to produce output records before opening the review screen.')
    print('Read-only checks passed. Start the app with: python app.py')


if __name__ == '__main__':
    main()
