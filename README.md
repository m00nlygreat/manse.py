# manse

manse.py는 규칙 기반(저정밀 태양 황경 근사)으로 사주 4기둥(연/월/일/시)의 간지(천간/지지)를 계산해 JSON으로 출력하는 CLI입니다.

- 연주: 입춘(태양 황경 315deg) 경계
- 월주: 현재 태양 황경을 30deg 구간으로 나눠 결정
- 일주: 로컬(민간) 자정 경계(에폭 상수로 튜닝)
- 시주: 12시진(2시간 단위), 경계 정각은 “이전” 시진에 포함
- 옵션: 경도 기반 LMT(지방평균시) 보정으로 시진 경계 이동

## 사용법

### 간단 입력(권장)

--simple xyyyymmddHHMM 형식으로 --date, --time, --male|--female를 대체합니다.

- x: m|M|f|F (m/M=male, f/F=female)
- 나머지: yyyymmddHHMM

`ash
python manse.py --simple m202512141500 [--tz HOURS] [--lon DEGREES] [--lmt] [--cycle N]
python manse.py --simple f202512141500 [--tz HOURS] [--lon DEGREES] [--lmt] [--cycle N]
`

### 기존 입력(호환)

`ash
python manse.py --date YYYY-MM-DD [--time HH:MM] [--male|--female] [--tz HOURS] [--lon DEGREES] [--lmt] [--cycle N]
`

## Command line parameters

- --simple (선택): xyyyymmddHHMM (x=m/M/f/F). 지정하면 --date/--time/--male/--female는 사용할 수 없습니다.
- --date (선택): 기준 날짜(그레고리력), 형식 YYYY-MM-DD (--simple 미지정 시 필수)
- --time (선택): 기준 시각(로컬 민간시), 형식 HH:MM (기본값: 12:00)
- --male (선택): 남성으로 간주(기본값). 대운 순/역행 결정에 사용 (--simple 미지정 시)
- --female (선택): 여성으로 간주. 대운 순/역행 결정에 사용 (--simple 미지정 시)
- --tz (선택): 시간대 오프셋(시간), 예: KST는 9 (기본값: 9.0)
- --lon (선택): 경도(도), 예: 서울 126.98E (기본값: 126.98)
- --lmt (선택): LMT 보정 적용. 켜면 --lon/--tz로 계산한 분 단위 보정값을 시주 경계에 반영
- --cycle (선택): 대운 출력 개수(기본값: 10)

## 출력

`json
{
  "gregorian": "YYYY-MM-DD HH:MM",
  "ganzhi": {
    "year": "…",
    "month": "…",
    "day": "…",
    "hour": "…"
  },
  "sex": "male",
  "daewoon": {
    "direction": "forward",
    "start_age": 0,
    "cycles": [{"n": 1, "age_start": 0, "pillar": "…"}]
  }
}
`

## 대운(기본 동작)

- 기본 출력에 daewoon이 포함됩니다.
- 성별(sex)과 출생 ganzhi.year의 천간 음양을 기준으로 순행/역행을 선택해 daewoon.direction과 대운 목록을 계산합니다.
- 첫 대운 시작 나이는 “출생 시각 ↔ 해당 방향 절기(절입) 시각”의 차이를 3일=1년으로 환산해 loor 처리합니다.