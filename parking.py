"""첨부 명세 parkinglotIF XML adapter. 인증키/전화번호는 저장·반환하지 않는다."""
import hashlib
import xml.etree.ElementTree as ET

SOURCE = "https://apis.data.go.kr/6300000/pis/parkinglotIF"
FIELDS = ['name', 'lat', 'lon', 'address', 'totalQty', 'resQty', 'type',
          'baseTime', 'baseRate', 'addTime', 'addRate', 'extraBaseTime',
          'extraAddTime', 'extraAddRate', 'weekdayOpenTime', 'weekdayCloseTime',
          'satOpenTime', 'satCloseTime', 'holidayOpenTime', 'holidayCloseTime', 'operDay']


class SourceError(Exception):
    def __init__(self, code):
        self.code = code


def parse_xml(content):
    try:
        root = ET.fromstring(content)
        code = root.findtext('.//resultCode') or root.findtext('.//returnReasonCode')
        if code not in ('00', '0'):
            if code in ('20', '30', '31', '32'):
                raise SourceError('denied')
            if code in ('22', '23'):
                raise SourceError('rate_limit')
            if code in ('05', '5'):
                raise SourceError('timeout')
            raise SourceError('source_error' if code else 'schema')
        result = []
        for item in root.findall('.//item'):
            raw = {key: (item.findtext(key) or '').strip() for key in FIELDS}
            if not raw['name']:
                raise ValueError('name missing')
            lat, lon = float(raw['lat']), float(raw['lon'])
            # 실제 원천은 totalQty를 빈 태그로 반환하기도 한다.
            # 빈 필드와 삭제/이름 변경은 구분한다. 후자는 schema 오류다.
            if item.find('totalQty') is None or item.find('resQty') is None:
                raise ValueError('count field removed')
            total = int(raw['totalQty']) if raw['totalQty'] else None
            available = int(raw['resQty']) if raw['resQty'] else None
            if not (33 < lat < 39 and 124 < lon < 132):
                raise ValueError('invalid coordinate')
            # total=0 은 명세의 예시에도 존재: 빈자리 0으로 단정하지 않는다.
            if (total is not None and total < 0) or (total and available is not None and available > total):
                raise ValueError('invalid count')
            quality_note = ''
            if available is not None and available < 0:
                available = None
                quality_note = '원천의 주차가능 대수가 음수여서 확인이 필요합니다.'
            identity = '|'.join([raw['name'], raw['address'], str(lat), str(lon)])
            result.append(dict(id=hashlib.sha256(identity.encode()).hexdigest()[:20],
                               name=raw['name'], address=raw['address'], lat=lat, lon=lon,
                               total=total, available=available if total else None,
                               source_time=None, unit='대', quality_note=quality_note, raw=raw))
        count = int(root.findtext('.//totalCount') or len(result))
        if count < 0 or count > 5000:
            raise ValueError('count outside limit')
        return result, count
    except SourceError:
        raise
    except (ET.ParseError, ValueError, TypeError):
        raise SourceError('schema') from None
