<div align="center">

# 차대유~
### 대전 주차 정보를 한곳에서 살펴보는 개인 프로젝트

목적지 주변 주차장을 찾고, 요금과 운영시간, 확인 가능한 주차 정보를 지도와 목록으로 살펴볼 수 있습니다.

[서비스 열기](https://daejeon-chadaeu-parking.vercel.app/) · [소스 코드](https://github.com/Dong-DDack/Daejeon-ChaDaeU-Parking)

</div>

---

## 프로젝트 소개

차대유~는 대전광역시 주차장 정보를 더 쉽게 찾아볼 수 있도록 만든 웹 앱입니다. 장소나 주차장 이름으로 검색하고, 주변 주차장의 위치와 제공되는 상세 정보를 확인할 수 있습니다.

주차 정보는 조회 시점과 원천 데이터의 상태에 따라 달라질 수 있습니다. 그래서 이 앱은 마지막으로 정상 확인된 값과 조회 시각을 함께 보여주고, 데이터를 가져오지 못했을 때는 오래된 정보일 수 있음을 표시합니다.

## 주요 기능

- 지도와 목록에서 주변 주차장 탐색
- 장소 및 주차장 이름 검색
- 주차 요금, 운영시간, 위치 등 제공 정보 확인
- 확인 가능한 주차 상태를 기준으로 목록 정렬
- 마지막 정상 조회값과 조회 시각 표시
- 날짜별 기록 저장 및 이전 기록과의 변화 표시
- 데이터 조회 실패 사유와 다시 시도 안내

## 사용 기술

- **화면:** HTML, CSS, JavaScript
- **서버:** Python, FastAPI
- **지도와 장소 검색:** Kakao Maps JavaScript SDK
- **데이터 원천:** 대전광역시 실시간 주차장 정보
- **저장:** SQLite (로컬), PostgreSQL (운영 환경)

## 로컬에서 실행하기

Python 3.11 이상이 필요합니다. Windows PowerShell에서 실행하는 예시입니다.

```powershell
git clone https://github.com/Dong-DDack/Daejeon-ChaDaeU-Parking.git
cd Daejeon-ChaDaeU-Parking
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env`에 사용할 API 설정을 입력한 뒤 서버를 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --reload
```

브라우저에서 [http://127.0.0.1:8000](http://127.0.0.1:8000)을 엽니다. 서버를 종료하려면 `Ctrl+C`를 누릅니다.

## 데이터와 한계

주차장 정보는 [대전광역시 실시간 주차장 정보](https://www.data.go.kr/data/15083717/openapi.do)를 사용합니다. 원천에 등록된 정보만 제공하므로 대전의 모든 주차장이 포함되는 것은 아닙니다.

- 주차장 위치나 요금 정보가 있다고 해서 실시간 빈자리 정보까지 제공되는 것은 아닙니다.
- 원천에서 빈자리 수나 관측 시각을 제공하지 않으면 앱도 임의의 값을 만들어 보여주지 않습니다.
- 외부 데이터 조회가 실패하면 마지막 정상값을 보존하고 정보가 오래되었을 수 있다고 표시합니다.
- 날짜별 변화는 저장된 기록을 바탕으로 계산합니다.
- 개인 위치 정보는 수집하지 않습니다.

## 프로젝트 구조

```text
.
├─ app.py                 # 웹 서버와 데이터 조회
├─ parking.py             # 원천 응답 검증 및 정규화
├─ storage.py             # 주차 정보와 날짜별 기록 저장
├─ readings.py            # 읽기 값 검증 및 비교 계산
├─ public/
│  ├─ index.html          # 주차 정보 화면
│  └─ assets/             # 화면 스타일과 동작
├─ tests/                 # 자동화된 테스트
├─ .env.example           # 환경 설정 예시
└─ requirements.txt       # Python 패키지 목록
```

## 참고

- [대전광역시 실시간 주차장 정보](https://www.data.go.kr/data/15083717/openapi.do)
- [Kakao Maps JavaScript API 안내](https://apis.map.kakao.com/web/guide/)

---

<div align="center">

차대유~ · 대전에서 주차 정보를 찾을 때 편하게 쓰려고 만들고 있는 프로젝트입니다.

</div>
