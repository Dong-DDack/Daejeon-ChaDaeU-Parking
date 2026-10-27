import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent / '.env')
import storage
from parking import SOURCE, SourceError, parse_xml
import review
from readings import daily_row, live_reading

app = FastAPI(title='차대유~', docs_url=None, redoc_url=None)
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).parent
MESSAGES = {
    'timeout': ('원천 응답이 지연되고 있어요.', '잠시 후 다시 조회해 주세요.'),
    'denied': ('원천에서 접근을 거절했어요.', '운영자는 키와 활용 승인 상태를 확인해 주세요.'),
    'rate_limit': ('원천 호출 한도에 도달했어요.', '잠시 기다린 뒤 다시 조회해 주세요.'),
    'offline': ('원천 서버에 연결할 수 없어요.', '연결 상태를 확인한 뒤 다시 조회해 주세요.'),
    'schema': ('원천 응답 형식을 확인할 수 없어요.', '운영자가 명세를 확인해야 해요. 나중에 다시 시도해 주세요.'),
    'source_error': ('원천 서비스에 오류가 있어요.', '잠시 후 다시 조회해 주세요.'),
    'configuration': ('대전 API 키가 아직 설정되지 않았어요.', '배포 환경변수를 입력한 뒤 다시 배포해 주세요.'),
    'storage': ('기록 저장소를 사용할 수 없어요.', 'DATABASE_URL과 DB 연결 상태를 확인해 주세요.'),
}


def envelope(snapshot, error='none'):
    message, action = MESSAGES.get(error, ('최근 정상 조회값입니다.', ''))
    old = bool(snapshot and (datetime.now(KST) - datetime.fromisoformat(snapshot['fetched_at'])).total_seconds() > 180)
    return dict(items=snapshot['items'] if snapshot else [],
                fetched_at=snapshot['fetched_at'] if snapshot else None,
                state=('stale' if snapshot else 'error') if error != 'none' else ('stale' if old else 'fresh'),
                error_code=error, message=message if not old or error != 'none' else '마지막 조회 후 3분 이상 지났어요.',
                action=action, source_url=SOURCE, source_time=None, timezone='Asia/Seoul',
                source_time_note='원천 관측 시각 미제공 · 조회 시각과 다릅니다.', mode='live')


@app.get('/')
def home():
    return FileResponse(ROOT / 'public/index.html')


@app.get('/review')
def review_page():
    return FileResponse(ROOT / 'public/review.html')


@app.get('/api/review/package')
def review_package():
    return review.verify_package()


class ReplayRequest(BaseModel):
    fixture_ids: list[str] = Field(default_factory=list, max_length=100)


@app.post('/api/review/replay')
def review_replay(request: ReplayRequest):
    # 공식 fixture ID 순서로 매번 재구성. 임의 payload와 실제 기록은 받지 않는다.
    if not review.verify_package()['verified']:
        raise HTTPException(409, 'official package hash mismatch')
    state = review.reset()
    checks = []
    fixture_record_ids = {}
    try:
        for fixture_id in request.fixture_ids:
            previous_good = state['current_reading']
            state = review.run(state, fixture_id)
            expected = review.FIXTURES[fixture_id]['expected']
            current = state['current_reading']
            actual = dict(freshness=state['status']['freshness'], error_code=state['status']['error_code'],
                          row_count=len(state['daily_readings']), stored_value=current['normalized_value'] if current else None,
                          delta=state['last_delta'], preserve_last_good=current is not None and (state['status']['error_code'] == 'none' or current == previous_good))
            current_row = next((r for r in state['daily_readings'] if current and r['signal_id'] == current['signal_id'] and r['record_date'] == current['record_date']), None)
            if 'same_record_id_as' in expected:
                reference = expected['same_record_id_as']
                actual['same_record_id_as'] = reference if current_row and fixture_record_ids.get(reference) == current_row['record_id'] else None
            if current_row:
                fixture_record_ids[fixture_id] = current_row['record_id']
            if 'record_date' in expected:
                actual['record_date'] = current['record_date'] if current else None
            checks.append(dict(fixture_id=fixture_id, expected=expected, actual=actual,
                               passed=all(actual.get(k) == v for k, v in expected.items())))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(400, 'invalid official fixture sequence') from None
    return dict(state=state, checks=checks, mode='synthetic', persisted_to_live=False)


@app.get('/api/review/live/{parking_id}')
def review_live(parking_id: str):
    if len(parking_id) != 20 or not all(c in '0123456789abcdef' for c in parking_id):
        raise HTTPException(400, 'invalid id')
    try:
        records = storage.history(parking_id)
        rows = []
        for record in records:
            reading = live_reading(record, record['fetched_at'], record.get('source_url', SOURCE))
            if reading:
                normalized = record.get('normalized_record') or daily_row(reading)
                rows.append(dict(day=record['day'], source_fields=record.get('raw', {}),
                                 stored=normalized, displayed_value=record['available'],
                                 legacy_normalized_view='normalized_record' not in record,
                                 receipt_payload_candidate=dict(source_url=reading['source_url'],
                                                                source_observed_at=reading['source_time'],
                                                                normalized_value=reading['normalized_value'], unit=reading['unit'])))
        return dict(records=rows, mode='live', platform_receipts_issued=False,
                    source_time_note='원천 관측 시각 미제공. C07 판단은 담당자 확인 필요.')
    except Exception:
        return JSONResponse(status_code=503, content={'records': [], 'error': '기록 저장소 연결 실패'})


@app.get('/api/config')
def config():
    return {'kakao_key': os.getenv('KAKAO_JAVASCRIPT_KEY', ''),
            'parking_configured': bool(os.getenv('DAEJEON_PARKING_API_KEY')),
            'storage': 'postgres' if os.getenv('DATABASE_URL') else ('missing' if os.getenv('VERCEL') else 'local-sqlite')}


async def fetch_page(client, page):
    response = await client.get(SOURCE, params={'serviceKey': os.environ['DAEJEON_PARKING_API_KEY'], 'pageNo': page, 'numOfRows': 50})
    if response.status_code in (401, 403):
        raise SourceError('denied')
    if response.status_code == 429:
        raise SourceError('rate_limit')
    if response.status_code != 200:
        raise SourceError('source_error')
    return parse_xml(response.content)


@app.get('/api/parking')
async def parking():
    # DB의 snapshot을 공유 캐시로도 사용. 방문자마다 전체 원천을 다시 부르지 않는다.
    try:
        previous = storage.latest()
    except Exception:
        return envelope(None, 'storage')
    if not os.getenv('DAEJEON_PARKING_API_KEY'):
        return envelope(previous, 'configuration')
    if previous and (datetime.now(KST) - datetime.fromisoformat(previous['fetched_at'])).total_seconds() < 60:
        return envelope(previous)
    try:
        async with asyncio.timeout(40):
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                items, count = await fetch_page(client, 1)
                for page in range(2, (count + 49) // 50 + 1):
                    batch, expected = await fetch_page(client, page)
                    if expected != count:
                        raise SourceError('schema')
                    items.extend(batch)
        if len(items) != count or count == 0 or len({i['id'] for i in items}) != count:
            raise SourceError('schema')
        now = datetime.now(KST)
        snapshot = dict(items=items, fetched_at=now.isoformat(), day=now.date().isoformat(), source_url=SOURCE)
        try:
            storage.save(snapshot)
        except Exception:
            return envelope(previous, 'storage')
        return envelope(snapshot)
    except (httpx.TimeoutException, TimeoutError):
        return envelope(previous, 'timeout')
    except httpx.RequestError:
        return envelope(previous, 'offline')
    except SourceError as error:
        return envelope(previous, error.code)


@app.get('/api/history/{parking_id}')
def history(parking_id: str):
    if len(parking_id) != 20 or not all(c in '0123456789abcdef' for c in parking_id):
        raise HTTPException(400, 'invalid id')
    try:
        return {'records': storage.history(parking_id)}
    except Exception:
        return JSONResponse(status_code=503, content={'records': [], 'error': '기록 저장소 연결 실패'})


# Vercel은 public/을 CDN에서 제공. 로컬 uvicorn에서는 같은 경로로 제공한다.
if not os.getenv('VERCEL'):
    app.mount('/assets', StaticFiles(directory=ROOT / 'public/assets'), name='assets')
