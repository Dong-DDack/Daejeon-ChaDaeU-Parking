"""공식 정규화 의미와 실제/합성 공통 일별 행 생성."""
import math
import re
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
KEYS = {'signal_id', 'normalized_value', 'unit', 'source_name', 'source_url',
        'source_time', 'fetched_at', 'record_timezone', 'record_date'}


def timestamp(value):
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('timezone required')
    return date


def validate(reading):
    if not isinstance(reading, dict) or set(reading) != KEYS:
        raise ValueError('normalized keys mismatch')
    if not isinstance(reading['signal_id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,99}', reading['signal_id']):
        raise ValueError('signal_id invalid')
    value = reading['normalized_value']
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('value invalid')
    for key, size in [('unit', 24), ('source_name', 120)]:
        if not isinstance(reading[key], str) or not reading[key].strip() or len(reading[key]) > size:
            raise ValueError('text invalid')
    if not isinstance(reading['source_url'], str) or not reading['source_url'].startswith('https://'):
        raise ValueError('HTTPS source required')
    if reading['source_time'] is not None:
        timestamp(reading['source_time'])
    date = timestamp(reading['fetched_at'])
    if reading['record_timezone'] != 'Asia/Seoul' or reading['record_date'] != date.astimezone(KST).date().isoformat():
        raise ValueError('KST date mismatch')
    return reading


def daily_row(reading, existing=None):
    validate(reading)
    return {'record_id': (existing or {}).get('record_id', f"reading-{reading['signal_id']}-{reading['record_date']}"),
            'signal_id': reading['signal_id'], 'record_date': reading['record_date'],
            'normalized_value': reading['normalized_value'], 'unit': reading['unit'],
            'first_fetched_at': (existing or {}).get('first_fetched_at', reading['fetched_at']),
            'last_fetched_at': reading['fetched_at'], 'reading': dict(reading)}


def live_reading(item, fetched_at, source_url):
    if item.get('available') is None:
        return None
    return validate({'signal_id': 'parking-' + item['id'], 'normalized_value': item['available'],
                     'unit': item.get('unit', '대'), 'source_name': '대전광역시 실시간 주차장 정보',
                     'source_url': source_url, 'source_time': item.get('source_time'),
                     'fetched_at': fetched_at, 'record_timezone': 'Asia/Seoul',
                     'record_date': timestamp(fetched_at).astimezone(KST).date().isoformat()})


def comparison(rows, current):
    previous = sorted([r for r in rows if r['signal_id'] == current['signal_id'] and r['record_date'] < current['record_date']], key=lambda r: r['record_date'])
    if not previous:
        return {'state': 'insufficient', 'direction': None, 'magnitude': None, 'unit': None}
    before = previous[-1]
    if before['unit'] != current['unit']:
        return {'state': 'unit_mismatch', 'direction': None, 'magnitude': None, 'unit': None}
    value = current['normalized_value'] - before['normalized_value']
    return {'state': 'comparable', 'direction': 'increase' if value > 0 else 'decrease' if value < 0 else 'unchanged', 'magnitude': abs(value), 'unit': current['unit']}
