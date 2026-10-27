import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).parent / '.env')
import storage
from parking import SOURCE, SourceError, parse_xml

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
