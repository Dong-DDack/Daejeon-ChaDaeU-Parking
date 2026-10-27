'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = value => value == null ? '미제공' : Number(value).toLocaleString('ko-KR');
const time = value => value ? new Intl.DateTimeFormat('ko-KR',{dateStyle:'short',timeStyle:'medium',timeZone:'Asia/Seoul'}).format(new Date(value)) : '미제공';
let data = null, selected = null, map = null, overlays = [], mapCard = null, region = null, locationFilter = null, config = {}, renderVersion = 0;
async function refresh(){
 $('refresh').disabled=true;
 try{
  const response=await fetch('/api/parking',{signal:AbortSignal.timeout(55000),cache:'no-store'});
  if(!response.ok)throw new Error('server');
  const next=await response.json();
  if(!next.items?.length && data?.items?.length){data={...data,state:'stale',error_code:next.error_code,message:next.message,action:next.action};}
  else data=next;
  render();
 }catch(error){
  if(data?.items?.length){data={...data,state:'stale',error_code:'offline',message:'웹사이트 연결 실패 · 마지막 정상값을 유지합니다.',action:'연결을 확인하고 다시 조회하세요.'};render();}
  else{$('status').className='status warn';$('status').textContent='서버 연결 실패 · FastAPI로 실행했는지 확인해 주세요.';}
 }finally{$('refresh').disabled=false;}
}
function filtered(){
 const query=$('query').value.trim().toLowerCase(), district=$('district').value;
 return (data?.items||[]).filter(p=>(!district||p.address.includes(district))&&(!$('available').checked||p.available>0)&&(!query||locationFilter||`${p.name} ${p.address}`.toLowerCase().includes(query))&&(!region||region.contain(new kakao.maps.LatLng(p.lat,p.lon)))&&(!locationFilter||distance(locationFilter.lat,locationFilter.lon,p.lat,p.lon)<=3)).sort((a,b)=>availabilityRank(a)-availabilityRank(b)||a.name.localeCompare(b.name,'ko'));
}
function availabilityRank(p){return p.available>0?0:p.available==null?1:2;}
function distance(a,b,c,d){const r=Math.PI/180;return 6371*2*Math.asin(Math.sqrt(Math.sin((c-a)*r/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin((d-b)*r/2)**2));}
function badge(p){return data?.state==='stale'?'정보 지연':p.available==null?'확인 필요':p.available===0?'만차':`${fmt(p.available)}대`;}
function selectLot(id){selected=id;renderList();renderDetail();const p=data.items.find(x=>x.id===id);if(map&&p){map.panTo(new kakao.maps.LatLng(p.lat,p.lon));showMapCard(p);}}
function renderList(){
 const items=filtered();$('count').innerHTML=`${items.length}<small>곳</small>`;$('coverage').textContent=`원천 제공 전체 ${data?.items.length||0}곳 중`;
 $('list').replaceChildren();
 if(!items.length){$('list').innerHTML='<div class="empty">표시할 주차장이 없습니다. 검색 조건이나 API 연결 상태를 확인하세요.</div>';}
 items.forEach(p=>{const button=document.createElement('button');button.className='lot'+(selected===p.id?' selected':'');button.innerHTML=`<div class="row"><strong>${escapeHTML(p.name)}</strong><span class="pill ${data.state==='stale'||p.available==null?'unknown':p.available===0?'full':''}">${badge(p)}</span></div><div class="address">${escapeHTML(p.address)}</div><span class="muted">${escapeHTML(p.raw.type||'요금 미제공')} · 전체 ${fmt(p.total)}면</span>`;button.onclick=()=>selectLot(p.id);$('list').append(button);});
 if(mapCard){mapCard.setMap(null);mapCard=null;}
 overlays.forEach(o=>o.setMap(null));overlays=[];
 if(map)items.filter(p=>p.available!=null).forEach(p=>{const button=document.createElement('button');button.className='pin '+(data.state==='stale'||p.available==null?'unknown':p.available===0?'full':'');button.textContent=badge(p);button.title=p.name;button.onclick=()=>selectLot(p.id);const overlay=new kakao.maps.CustomOverlay({position:new kakao.maps.LatLng(p.lat,p.lon),content:button,yAnchor:1});overlay.setMap(map);overlays.push(overlay);});
}
function showMapCard(p){
 if(mapCard)mapCard.setMap(null);
 const r=p.raw, card=document.createElement('section');card.className='mapcard';
 const fee=r.type==='무료'?'무료':r.baseTime&&r.baseRate!==''?`${r.baseTime}분 / ${fmt(r.baseRate)}원`:'요금 미제공';
 card.innerHTML=`<button class="mapcard-close" aria-label="지도 상세 닫기">×</button><strong>${escapeHTML(p.name)}</strong><p class="muted">${escapeHTML(p.address)}</p><div class="mapcard-value">${escapeHTML(badge(p))}<small> / 전체 ${fmt(p.total)}면</small></div><p>기본요금 · ${escapeHTML(fee)}</p><p class="muted">평일 ${escapeHTML(r.weekdayOpenTime||'미제공')}–${escapeHTML(r.weekdayCloseTime||'미제공')}<br>조회 ${time(data.fetched_at)}</p>`;
 card.querySelector('button').onclick=()=>{mapCard.setMap(null);mapCard=null;};
 mapCard=new kakao.maps.CustomOverlay({position:new kakao.maps.LatLng(p.lat,p.lon),content:card,yAnchor:0.5,zIndex:10});mapCard.setMap(map);
}
function render(){
 $('status').className='status'+(data.state!=='fresh'?' warn':'');
 $('status').textContent=`${data.message} ${data.action||''} · 마지막 성공 조회 ${time(data.fetched_at)}`;
 if(!data.items.some(p=>p.id===selected))selected=data.items[0]?.id||null;
 renderList();renderDetail();
}
async function renderDetail(){
 const version=++renderVersion,p=data?.items.find(p=>p.id===selected);if(!p){$('detail').innerHTML='<h2>주차장을 선택해 주세요</h2><p class="muted">연결 상태를 확인하거나 목록에서 주차장을 선택하세요.</p>';return;}
 const r=p.raw, row=(label,value)=>`<div><dt>${label}</dt><dd>${escapeHTML(value)}</dd></div>`;
 $('detail').innerHTML=`<p class="eyebrow">PARKING DETAILS</p><div class="detailhead"><div><h2>${escapeHTML(p.name)}</h2><p class="muted">${escapeHTML(p.address)}</p></div><div class="value">${p.available==null?'—':fmt(p.available)}<small> / ${fmt(p.total)}면</small></div></div><div class="detailgrid"><dl>${row('데이터 상태',data.state==='stale'?'오래된 값 · 현재 빈자리 보장 안 됨':p.available==null?(p.quality_note||'총면수·가용 정보 미제공 또는 확인 필요'):'최근 조회 성공')}${row('기본요금',r.type==='무료'?'무료':r.baseRate!==''&&r.baseTime?`${r.baseTime}분 / ${fmt(r.baseRate)}원`:'미제공')}${row('추가요금',r.addTime&&r.addRate!==''?`${r.addTime}분 / ${fmt(r.addRate)}원`:'미제공')}${row('할증정보',r.extraBaseTime?`${r.extraBaseTime}분 기준 / ${r.extraAddTime}분당 ${fmt(r.extraAddRate)}원`:'미제공')}${row('평일 운영',r.weekdayOpenTime&&r.weekdayCloseTime?`${r.weekdayOpenTime}–${r.weekdayCloseTime}`:'미제공')}${row('토요일 운영',r.satOpenTime&&r.satCloseTime?`${r.satOpenTime}–${r.satCloseTime}`:'미제공')}${row('공휴일 운영',r.holidayOpenTime&&r.holidayCloseTime?`${r.holidayOpenTime}–${r.holidayCloseTime}`:'미제공')}${row('운영요일',r.operDay||'미제공')}</dl><dl>${row('단위','주차가능 대수 (대)')}${row('출처','대전광역시 실시간 주차장 정보')}${row('원천 갱신 주기','약 10분 · 제공 주기 안내')}${row('원천 관측 시각',p.source_time?time(p.source_time):'응답에 개별 시각 없음')}${row('조회 시각',time(data.fetched_at))}${row('기준 시간대','Asia/Seoul (KST)')}${row('저장 규칙','KST 날짜별 마지막 성공값 1건')}<p class="muted">10분은 갱신 주기이며, 개별 응답의 정확한 갱신 시각을 뜻하지 않습니다. API 제공 목록은 대전의 모든 주차장을 뜻하지 않습니다.</p></dl></div><h3>일별 기록 <span id="delta" class="muted"></span></h3><div id="history" class="tablewrap">기록을 확인합니다.</div>`;
 try{
  let rows;
  const response=await fetch('/api/history/'+encodeURIComponent(p.id));if(!response.ok)throw new Error('history');rows=(await response.json()).records;
  if(version!==renderVersion)return;
  $('history').innerHTML=rows.length?`<table><thead><tr><th>KST 날짜</th><th>저장값</th><th>원천 시각</th><th>조회 시각</th></tr></thead><tbody>${rows.map(x=>`<tr><td>${escapeHTML(x.day)}</td><td>${fmt(x.available)}대</td><td>${time(x.source_time)}</td><td>${time(x.fetched_at)}</td></tr>`).join('')}</tbody></table>`:'<p class="muted">저장된 실제 기록이 없습니다. 실제 조회 성공 시 날짜별로 저장됩니다.</p>';
  if(rows.length>=2){const a=rows.at(-2),b=rows.at(-1);if(a.available!=null&&b.available!=null){const delta=b.available-a.available;$('delta').textContent=`직전 기록 대비 ${delta>0?'+':''}${delta}대 (${b.available} − ${a.available}) · ${a.day} → ${b.day}`;}}
 }catch{if(version===renderVersion&&$('history'))$('history').textContent='기록을 불러오지 못했습니다. 다시 조회해 주세요.';}
}
async function setupMap(){
 if(!config.kakao_key)return;
 try{await new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='https://dapi.kakao.com/v2/maps/sdk.js?appkey='+encodeURIComponent(config.kakao_key)+'&autoload=false&libraries=services';s.onload=resolve;s.onerror=reject;document.head.append(s);});
 await new Promise(resolve=>kakao.maps.load(resolve));map=new kakao.maps.Map($('map'),{center:new kakao.maps.LatLng(36.3504,127.3845),level:8});renderList();
 }catch{$('map').innerHTML='<div class="mapempty"><h2>지도를 불러오지 못했어요</h2><p>JavaScript 키를 사용했는지 확인하세요. 어드민/REST 키는 지도에 사용할 수 없습니다. 카카오맵 사용 설정·허용 도메인도 확인하세요.</p></div>';}
}
$('search').onsubmit=event=>{event.preventDefault();region=null;locationFilter=null;renderList();const query=$('query').value.trim();if(!query)return;
 if(map){new kakao.maps.services.Places().keywordSearch(query,(places,status)=>{if(status!==kakao.maps.services.Status.OK){$('search-note').textContent='장소 검색 결과 없음 · 주차장 이름/주소로 필터링했습니다.';return;}const place=places.find(x=>x.address_name.startsWith('대전'));if(!place){$('search-note').textContent='대전 내 장소만 검색할 수 있어요.';return;}locationFilter={lat:Number(place.y),lon:Number(place.x)};map.setCenter(new kakao.maps.LatLng(locationFilter.lat,locationFilter.lon));map.setLevel(5);$('search-note').textContent=place.place_name+' 반경 3km · 직선거리 기준';renderList();},{bounds:new kakao.maps.LatLngBounds(new kakao.maps.LatLng(36.18,127.22),new kakao.maps.LatLng(36.51,127.57))});}
 else $('search-note').textContent='지도 미연결 · 주차장 이름·주소 검색만 적용합니다.';
};
$('district').onchange=()=>{locationFilter=null;region=null;renderList();};$('available').onchange=renderList;
$('all-map').onclick=()=>{region=null;locationFilter=null;$('query').value='';$('district').value='';$('search-note').textContent='대전 전체 · 원천 제공 주차장';if(map){map.setCenter(new kakao.maps.LatLng(36.3504,127.3845));map.setLevel(8);}if(data)renderList();};
$('bounds').onclick=()=>{if(!map){$('search-note').textContent='카카오 지도 연결 후 사용할 수 있습니다.';return;}region=map.getBounds();locationFilter=null;$('query').value='';$('search-note').textContent='현재 지도 영역의 주차장';renderList();};
$('refresh').onclick=refresh;
async function boot(){try{const r=await fetch('/api/config');if(!r.ok)throw new Error();config=await r.json();}catch{$('search-note').textContent='서버 설정 연결 실패 · 연결 상태를 확인해 주세요.';}
 await refresh();setupMap();}
boot();
