"""공식 fixture만 사용하는, 실제 기록과 분리한 결정론 replay."""
import copy
import hashlib
import json
from pathlib import Path

from readings import comparison, daily_row, validate

PACKAGE = Path(__file__).parent / 'public/assets/t04'
ERRORS = {'timeout', 'auth', 'rate_limit', 'offline', 'schema_error'}
MANIFEST = json.loads((PACKAGE / 'asset-manifest.json').read_text(encoding='utf-8'))
FIXTURES = {f['fixture_id']: f for f in [json.loads(p.read_text(encoding='utf-8')) for p in (PACKAGE / 'fixtures').glob('*.json')]}


def verify_package():
    files = []
    for entry in MANIFEST['files']:
        content = (PACKAGE / entry['path']).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        files.append(dict(path=entry['path'], expected=entry['sha256'], actual=digest,
                          bytes=len(content), verified=digest == entry['sha256'] and len(content) == entry['bytes']))
    return dict(package_id=MANIFEST['package_id'], hash_algorithm='sha256', verified=all(f['verified'] for f in files),
                files=files, fixture_ids=list(FIXTURES), contract_version='2.0.0', fixture_version='1.1.0')


def reset():
    return dict(schema_version='aleph-t04-evaluation-state-v1', daily_readings=[], current_reading=None,
                status=None, last_delta=None, last_comparison=dict(state='insufficient', direction=None, magnitude=None, unit=None), last_run=None, sequence=0)


def success(state, reading, meta):
    validate(reading)
    existing = next((r for r in state['daily_readings'] if r['signal_id'] == reading['signal_id'] and r['record_date'] == reading['record_date']), None)
    row = daily_row(reading, existing)
    # 공식 참조 adapter와 동일한 결정론 ID를 사용한다.
    if not existing:
        row['record_id'] = f"demo-{reading['signal_id']}-{reading['record_date']}"
    state['daily_readings'] = [r for r in state['daily_readings'] if r is not existing] + [row]
    state['daily_readings'].sort(key=lambda r: r['record_date'])
    state['current_reading'] = copy.deepcopy(reading)
    state['status'] = dict(freshness='fresh', error_code='none')
    state['last_comparison'] = comparison(state['daily_readings'], row)
    state['last_delta'] = state['last_comparison']['magnitude']
    state['sequence'] += 1
    state['last_run'] = dict(meta, outcome='success', error_code='none', retry_after_seconds=None)
    return state


def run(state, fixture_id):
    if fixture_id not in FIXTURES:
        raise ValueError('unknown official fixture')
    state = copy.deepcopy(state)
    # 합성 상태만 처리하며 실제 DB와 snapshot에는 접근하지 않는다.
    if not isinstance(state, dict) or state.get('schema_version') != 'aleph-t04-evaluation-state-v1' or len(state.get('daily_readings', [])) > 10:
        raise ValueError('invalid replay state')
    for row in state['daily_readings']:
        validate(row['reading'])
        if row['signal_id'] != 'aleph-demo-index':
            raise ValueError('synthetic signal only')
    fixture = FIXTURES[fixture_id]
    t = fixture['transport']
    retry = t['headers'].get('retry-after')
    meta = dict(fixture_id=fixture_id, virtual_now=fixture['virtual_now'], retry_after_seconds=int(retry) if retry else None)
    if t['mode'] == 'timeout':
        code = 'timeout'
    elif t['mode'] == 'offline':
        code = 'offline'
    elif t['status'] in (401, 403):
        code = 'auth'
    elif t['status'] == 429:
        code = 'rate_limit'
    elif t['status'] is not None and 200 <= t['status'] < 300:
        try:
            validate(fixture['payload'])
        except (ValueError, TypeError, KeyError, AttributeError):
            code = 'schema_error'
        else:
            return success(state, fixture['payload'], meta)
    else:
        code = 'schema_error'
    state['status'] = dict(freshness='stale', error_code=code)
    state['sequence'] += 1
    state['last_run'] = dict(meta, outcome='error', error_code=code)
    return state
