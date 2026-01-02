# manse.py
# -*- coding: utf-8 -*-
"""
Rules-based Manse (만세력) pillars without DB.
- Year pillar: boundary at Lichun (solar longitude 315°)
- Month pillar: determined directly from current solar longitude
  (寅月: [315°,345°), then every +30°)
- Day pillar: local civil midnight boundary (epoch tuned)
- Hour pillar: 12 double-hours; EXACT BOUNDARY (정각) belongs to the *previous* branch.
  (e.g., 15:00 => 未시, 15:00:00.001 => 申시)
- Optional LMT shift for hour boundaries
"""
import math
import argparse
import json
import sys
import datetime
from typing import Optional

TEN_STEMS = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
TWELVE_BRANCHES = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']

KOREAN_STEMS = {
    '甲': '갑',
    '乙': '을',
    '丙': '병',
    '丁': '정',
    '戊': '무',
    '己': '기',
    '庚': '경',
    '辛': '신',
    '壬': '임',
    '癸': '계',
}
KOREAN_BRANCHES = {
    '子': '자',
    '丑': '축',
    '寅': '인',
    '卯': '묘',
    '辰': '진',
    '巳': '사',
    '午': '오',
    '未': '미',
    '申': '신',
    '酉': '유',
    '戌': '술',
    '亥': '해',
}

def ganzhi_to_korean(gz: str) -> str:
    if not isinstance(gz, str) or len(gz) != 2:
        raise ValueError(f"Invalid ganzhi: {gz!r}")
    try:
        return KOREAN_STEMS[gz[0]] + KOREAN_BRANCHES[gz[1]]
    except KeyError as e:
        raise ValueError(f"Invalid ganzhi char: {gz!r}") from e

def ganzhi_from_index(i60:int) -> str:
    return TEN_STEMS[i60 % 10] + TWELVE_BRANCHES[i60 % 12]

# ── Gregorian ↔ JD ───────────────────────────────────────────────────────────
def gregorian_to_jd(y:int,m:int,d:int,h:float=12,mi:float=0,se:float=0) -> float:
    if m <= 2:
        y -= 1; m += 12
    A = y // 100
    B = 2 - A + (A // 4)
    frac = (h + mi/60 + se/3600) / 24.0
    return int(365.25*(y+4716)) + int(30.6001*(m+1)) + d + B - 1524.5 + frac

# ── Solar ecliptic longitude (low precision, Meeus-like) ────────────────────
def sun_ecliptic_longitude_deg(JD:float) -> float:
    T = (JD - 2451545.0) / 36525.0
    M  = 357.52911 + 35999.05029*T - 0.0001537*(T**2)
    L0 = 280.46646 + 36000.76983*T + 0.0003032*(T**2)
    Mr = math.radians(M % 360.0)
    C = (1.914602 - 0.004817*T - 0.000014*(T**2))*math.sin(Mr) \
      + (0.019993 - 0.000101*T)*math.sin(2*Mr) \
      + 0.000289*math.sin(3*Mr)
    true_long = L0 + C
    omega = 125.04 - 1934.136*T
    lam = true_long - 0.00569 - 0.00478*math.sin(math.radians(omega))
    return lam % 360.0

def _find_term_time_near(year:int, target_deg:float, guess_month:int) -> float:
    """Find UT JD when sun longitude hits target_deg, near guess_month."""
    JD0 = gregorian_to_jd(year, guess_month, 15, 0, 0, 0)
    lo, hi = JD0 - 40, JD0 + 40
    def f(jd):
        return ((sun_ecliptic_longitude_deg(jd) - target_deg + 540) % 360) - 180
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0: hi = mid
        else: lo = mid
    return (lo + hi) / 2

# ── Year pillar (立春 boundary) ──────────────────────────────────────────────
def year_pillar(JD_utc:float, civil_year:int) -> str:
    lichun = _find_term_time_near(civil_year, 315.0, 2)
    y = civil_year if JD_utc >= lichun else civil_year - 1
    # 1984 = 甲子年 baseline
    return ganzhi_from_index((y - 1984) % 60)

# ── Month pillar from instantaneous solar longitude ─────────────────────────
# 寅月: [315°,345°), 卯月: [345°,15°), …, 丑月: [285°,315°)
_STEM_START_FROM_YEAR_STEM = {
    '甲':'丙','己':'丙',
    '乙':'戊','庚':'戊',
    '丙':'庚','辛':'庚',
    '丁':'壬','壬':'壬',
    '戊':'甲','癸':'甲',
}
def month_pillar_from_longitude(solar_long_deg:float, year_gz:str) -> str:
    offset = (solar_long_deg - 315.0) % 360.0
    m_idx = int(offset // 30.0)  # 0..11 (0=寅, 11=丑)
    branch = TWELVE_BRANCHES[(2 + m_idx) % 12]  # 寅 index=2
    y_stem = year_gz[0]
    stem_start = _STEM_START_FROM_YEAR_STEM[y_stem]
    s0 = TEN_STEMS.index(stem_start)
    stem = TEN_STEMS[(s0 + m_idx) % 10]
    return stem + branch

# ── Day pillar (local midnight boundary; epoch tuned) ───────────────────────
# Epoch constant chosen so 1988-01-27 (KST) -> 辛巳.
_DAY_EPOCH_CONST = 50
def day_pillar_local_midnight(y:int,m:int,d:int, tz_hours:float) -> str:
    jd0 = gregorian_to_jd(y,m,d, -tz_hours, 0, 0)  # local 00:00 -> UTC JD
    idx = (int(jd0 + 0.5) + _DAY_EPOCH_CONST) % 60
    return ganzhi_from_index(idx)

# ── Hour pillar (12 double-hours; exact boundary → previous bin) ────────────
def _lmt_shift_minutes(lon_deg:float, tz_hours:float) -> float:
    return lon_deg*4.0 - tz_hours*60.0  # LMT - civil minutes

def hour_pillar(day_gz:str, hour:int, minute:int, use_lmt:bool, lon_deg:float, tz_hours:float) -> str:
    minutes = hour*60 + minute + (_lmt_shift_minutes(lon_deg, tz_hours) if use_lmt else 0.0)
    minutes %= 1440.0
    # Offset from 23:00 (子시 origin)
    offset = (minutes - 23*60) % 1440.0  # in [0,1440)
    # Put EXACT boundaries (0,120,240,...) into the PREVIOUS bin
    eps = 1e-7
    offset_adj = (offset - eps) % 1440.0
    bin_idx = int(offset_adj // 120.0)  # 0..11 => 子..亥
    branch = TWELVE_BRANCHES[bin_idx]
    start_for_zi = {
        '甲':'甲','己':'甲',
        '乙':'丙','庚':'丙',
        '丙':'戊','辛':'戊',
        '丁':'庚','壬':'庚',
        '戊':'壬','癸':'壬',
    }[day_gz[0]]
    s0 = TEN_STEMS.index(start_for_zi)
    stem = TEN_STEMS[(s0 + bin_idx) % 10]
    return stem + branch

# ── Main ────────────────────────────────────────────────────────────────────

# luck_cycles (10-year luck cycles) helpers
_TROPICAL_YEAR_DAYS = 365.242196
_TERMS12 = [
    (315.0, "입춘", 2),
    (345.0, "경칩", 3),
    (15.0,  "청명", 4),
    (45.0,  "입하", 5),
    (75.0,  "망종", 6),
    (105.0, "소서", 7),
    (135.0, "입추", 8),
    (165.0, "백로", 9),
    (195.0, "한로", 10),
    (225.0, "입동", 11),
    (255.0, "대설", 12),
    (285.0, "소한", 1),
]
def _i60_from_ganzhi(gz: str) -> int:
    stem = gz[0]
    branch = gz[1]
    s = TEN_STEMS.index(stem)
    b = TWELVE_BRANCHES.index(branch)
    for i in range(60):
        if i % 10 == s and i % 12 == b:
            return i
    raise ValueError(f"Invalid ganzhi pair: {gz!r}")

def jd_to_gregorian(jd: float):
    """Convert JD (UT) to Gregorian calendar date/time."""
    jd = jd + 0.5
    Z = int(jd)
    F = jd - Z
    if Z < 2299161:
        A = Z
    else:
        alpha = int((Z - 1867216.25) / 36524.25)
        A = Z + 1 + alpha - int(alpha / 4)
    B = A + 1524
    C = int((B - 122.1) / 365.25)
    D = int(365.25 * C)
    E = int((B - D) / 30.6001)
    day = B - D - int(30.6001 * E) + F

    month = E - 1 if E < 14 else E - 13
    year = C - 4716 if month > 2 else C - 4715

    d_int = int(day)
    frac = day - d_int
    hour = int(frac * 24)
    frac = frac * 24 - hour
    minute = int(frac * 60)
    frac = frac * 60 - minute
    second = int(round(frac * 60))

    if second == 60:
        second = 59
    return year, month, d_int, hour, minute, second


# ── Gregorian → Lunar (Chinese/Korean lunisolar; table-based) ─────────────────
# Supported range: 1900-01-31 .. 2100-12-31 (common published table)
_LUNAR_INFO_1900 = [
    0x04BD8, 0x04AE0, 0x0A570, 0x054D5, 0x0D260, 0x0D950, 0x16554, 0x056A0,
    0x09AD0, 0x055D2, 0x04AE0, 0x0A5B6, 0x0A4D0, 0x0D250, 0x1D255, 0x0B540,
    0x0D6A0, 0x0ADA2, 0x095B0, 0x14977, 0x04970, 0x0A4B0, 0x0B4B5, 0x06A50,
    0x06D40, 0x1AB54, 0x02B60, 0x09570, 0x052F2, 0x04970, 0x06566, 0x0D4A0,
    0x0EA50, 0x06E95, 0x05AD0, 0x02B60, 0x186E3, 0x092E0, 0x1C8D7, 0x0C950,
    0x0D4A0, 0x1D8A6, 0x0B550, 0x056A0, 0x1A5B4, 0x025D0, 0x092D0, 0x0D2B2,
    0x0A950, 0x0B557, 0x06CA0, 0x0B550, 0x15355, 0x04DA0, 0x0A5B0, 0x14573,
    0x052B0, 0x0A9A8, 0x0E950, 0x06AA0, 0x0AEA6, 0x0AB50, 0x04B60, 0x0AAE4,
    0x0A570, 0x05260, 0x0F263, 0x0D950, 0x05B57, 0x056A0, 0x096D0, 0x04DD5,
    0x04AD0, 0x0A4D0, 0x0D4D4, 0x0D250, 0x0D558, 0x0B540, 0x0B5A0, 0x195A6,
    0x095B0, 0x049B0, 0x0A974, 0x0A4B0, 0x0B27A, 0x06A50, 0x06D40, 0x0AF46,
    0x0AB60, 0x09570, 0x04AF5, 0x04970, 0x064B0, 0x074A3, 0x0EA50, 0x06B58,
    0x05AC0, 0x0AB60, 0x096D5, 0x092E0, 0x0C960, 0x0D954, 0x0D4A0, 0x0DA50,
    0x07552, 0x056A0, 0x0ABB7, 0x025D0, 0x092D0, 0x0CAB5, 0x0A950, 0x0B4A0,
    0x0BAA4, 0x0AD50, 0x055D9, 0x04BA0, 0x0A5B0, 0x15176, 0x052B0, 0x0A930,
    0x07954, 0x06AA0, 0x0AD50, 0x05B52, 0x04B60, 0x0A6E6, 0x0A4E0, 0x0D260,
    0x0EA65, 0x0D530, 0x05AA0, 0x076A3, 0x096D0, 0x04BD7, 0x04AD0, 0x0A4D0,
    0x1D0B6, 0x0D250, 0x0D520, 0x0DD45, 0x0B5A0, 0x056D0, 0x055B2, 0x049B0,
    0x0A577, 0x0A4B0, 0x0AA50, 0x1B255, 0x06D20, 0x0ADA0, 0x14B63, 0x09370,
    0x049F8, 0x04970, 0x064B0, 0x168A6, 0x0EA50, 0x06B20, 0x1A6C4, 0x0AAE0,
    0x092E0, 0x0D2E3, 0x0C960, 0x0D557, 0x0D4A0, 0x0DA50, 0x05D55, 0x056A0,
    0x0A6D0, 0x055D4, 0x052D0, 0x0A9B8, 0x0A950, 0x0B4A0, 0x0B6A6, 0x0AD50,
    0x055A0, 0x0ABA4, 0x0A5B0, 0x052B0, 0x0B273, 0x06930, 0x07337, 0x06AA0,
    0x0AD50, 0x14B55, 0x04B60, 0x0A570, 0x054E4, 0x0D160, 0x0E968, 0x0D520,
    0x0DAA0, 0x16AA6, 0x056D0, 0x04AE0, 0x0A9D4, 0x0A2D0, 0x0D150, 0x0F252,
    0x0D520,
]


def _lunar_leap_month(year: int) -> int:
    return _LUNAR_INFO_1900[year - 1900] & 0xF


def _lunar_leap_days(year: int) -> int:
    if _lunar_leap_month(year) == 0:
        return 0
    return 30 if (_LUNAR_INFO_1900[year - 1900] & 0x10000) else 29


def _lunar_month_days(year: int, month: int) -> int:
    info = _LUNAR_INFO_1900[year - 1900]
    return 30 if (info & (0x10000 >> month)) else 29


def _lunar_year_days(year: int) -> int:
    days = 29 * 12
    info = _LUNAR_INFO_1900[year - 1900]
    for month in range(1, 13):
        if info & (0x10000 >> month):
            days += 1
    return days + _lunar_leap_days(year)


def gregorian_to_lunar(y: int, m: int, d: int):
    """Convert Gregorian local date to lunar date (year, month, day, is_leap_month).

    Returns None if date is outside supported range.
    """
    base = datetime.date(1900, 1, 31)  # lunar 1900-01-01
    try:
        target = datetime.date(y, m, d)
    except ValueError:
        return None

    min_supported = base
    max_supported = datetime.date(2100, 12, 31)
    if target < min_supported or target > max_supported:
        return None

    offset = (target - base).days
    lunar_year = 1900
    while lunar_year < 2101:
        year_days = _lunar_year_days(lunar_year)
        if offset < year_days:
            break
        offset -= year_days
        lunar_year += 1

    leap_month = _lunar_leap_month(lunar_year)
    lunar_month = 1
    is_leap = False
    while lunar_month <= 12:
        month_days = _lunar_leap_days(lunar_year) if is_leap else _lunar_month_days(lunar_year, lunar_month)
        if offset < month_days:
            lunar_day = offset + 1
            return lunar_year, lunar_month, lunar_day, is_leap
        offset -= month_days

        if leap_month and lunar_month == leap_month and not is_leap:
            is_leap = True
        else:
            if is_leap:
                is_leap = False
            lunar_month += 1

    return None

def _term_index_from_longitude(solar_long_deg: float) -> int:
    offset = (solar_long_deg - 315.0) % 360.0
    return int(offset // 30.0)  # 0..11

def _term_time_candidates_near(birth_year: int, deg: float, guess_month: int):
    years = [birth_year - 1, birth_year, birth_year + 1]
    out = []
    for y in years:
        out.append(_find_term_time_near(y, deg, guess_month))
    return out

def _next_prev_term_times(JD_birth_utc: float, birth_year: int, next_term, prev_term):
    next_deg, next_name, next_guess_m = next_term
    prev_deg, prev_name, prev_guess_m = prev_term

    eps = 1e-9

    next_candidates = _term_time_candidates_near(birth_year, next_deg, next_guess_m)
    next_after = [jd for jd in next_candidates if jd > JD_birth_utc + eps]
    if not next_after:
        next_after = next_candidates
    JD_next = min(next_after, key=lambda jd: jd - JD_birth_utc)

    prev_candidates = _term_time_candidates_near(birth_year, prev_deg, prev_guess_m)
    prev_before = [jd for jd in prev_candidates if jd < JD_birth_utc - eps]
    if not prev_before:
        prev_before = prev_candidates
    JD_prev = max(prev_before, key=lambda jd: jd - JD_birth_utc)

    return (JD_next, next_name, next_deg), (JD_prev, prev_name, prev_deg)


def _is_yang_stem(stem: str) -> bool:
    return (TEN_STEMS.index(stem) % 2) == 0


def _add_years_clamped(dt: datetime.datetime, years: int) -> datetime.datetime:
    """Add years, clamping day for Feb 29 etc."""
    if years == 0:
        return dt
    target_year = dt.year + years
    try:
        return dt.replace(year=target_year)
    except ValueError:
        if dt.month == 2 and dt.day == 29:
            return dt.replace(year=target_year, day=28)
        # Clamp to last day of the target month.
        last_day = (datetime.datetime(target_year, dt.month, 1) + datetime.timedelta(days=31)).replace(day=1) - datetime.timedelta(days=1)
        return dt.replace(year=target_year, day=last_day.day)


def luck_cycles_direction(gz_year: str, is_female: bool) -> int:
    """Return +1 for forward, -1 for backward."""
    yang_year = _is_yang_stem(gz_year[0])
    if is_female:
        return +1 if not yang_year else -1
    return +1 if yang_year else -1


def luck_cycles_info(
    JD_birth_utc: float,
    birth_year: int,
    birth_local_dt: datetime.datetime,
    gz_month: str,
    direction: int,
    cycles: int = 10,
):
    """Compute 10-year luck cycles for selected direction (+1 forward, -1 backward)."""
    if direction not in (+1, -1):
        raise ValueError('direction must be +1 (forward) or -1 (backward)')

    lam = sun_ecliptic_longitude_deg(JD_birth_utc)
    idx = _term_index_from_longitude(lam)

    cur_term = _TERMS12[idx]
    next_term = _TERMS12[(idx + 1) % 12]
    prev_term = _TERMS12[idx]

    (JD_next, next_name, next_deg), (JD_prev, prev_name, prev_deg) = _next_prev_term_times(
        JD_birth_utc, birth_year, next_term, prev_term
    )

    def jd_iso(jd):
        y, m, d, hh, mm, ss = jd_to_gregorian(jd)
        return f"{y:04d}-{m:02d}-{d:02d}T{hh:02d}:{mm:02d}:{ss:02d}Z"

    def dt_iso_local(dt: datetime.datetime) -> str:
        return dt.isoformat(timespec='seconds')

    def start_age_years(days: float) -> float:
        return days / 3.0

    if direction == +1:
        JD_target, term_name, term_deg = JD_next, next_name, next_deg
        days = max(0.0, (JD_target - JD_birth_utc))
        dir_name = 'forward'
    else:
        JD_target, term_name, term_deg = JD_prev, prev_name, prev_deg
        days = max(0.0, (JD_birth_utc - JD_target))
        dir_name = 'backward'

    start_years = start_age_years(days)
    start_dt = birth_local_dt + datetime.timedelta(days=start_years * _TROPICAL_YEAR_DAYS)

    base = _i60_from_ganzhi(gz_month)

    out_cycles = []
    for n in range(1, cycles + 1):
        i60 = (base + direction * n) % 60
        age_start = start_years + (n - 1) * 10.0
        age_end = start_years + n * 10.0
        cycle_start_dt = start_dt + datetime.timedelta(days=(n - 1) * 10.0 * _TROPICAL_YEAR_DAYS)
        cycle_end_dt = (start_dt + datetime.timedelta(days=n * 10.0 * _TROPICAL_YEAR_DAYS)) - datetime.timedelta(seconds=1)
        out_cycles.append({
            'n': n,
            'age_start': age_start,
            'age_end': age_end,
            'date_start': dt_iso_local(cycle_start_dt),
            'date_end': dt_iso_local(cycle_end_dt),
            'pillar': ganzhi_from_index(i60),
        })

    luck_cycles_start_date = dt_iso_local(start_dt)
    luck_cycles_end_date = dt_iso_local((start_dt + datetime.timedelta(days=cycles * 10.0 * _TROPICAL_YEAR_DAYS)) - datetime.timedelta(seconds=1))

    return {
        'rule': {
            'term_set': '12-jeol (30deg steps from 315deg)',
            'day_to_year': 3.0,
            'tropical_year_days': _TROPICAL_YEAR_DAYS,
            'start_age_rounding': 'exact',
            'first_cycle_from': 'month_pillar_next_or_prev',
            'direction_rule': 'male/female + year-stem yin-yang',
        },
        'direction': dir_name,
        'birth_longitude_deg': lam,
        'current_term': {'name': cur_term[1], 'deg': cur_term[0]},
        'to_term': {'name': term_name, 'deg': term_deg, 'jd_utc': JD_target, 'utc': jd_iso(JD_target)},
        'days': days,
        'start_age_years': start_years,
        'start_age': start_years,
        'date_start': luck_cycles_start_date,
        'date_end': luck_cycles_end_date,
        'cycles': out_cycles,
    }


def manse_calc(y:int,m:int,d:int, hh:int, mm:int, tz:float, lon:float, use_lmt:bool=False):
    JD_utc = gregorian_to_jd(y,m,d, hh - tz, mm, 0)
    gz_year = year_pillar(JD_utc, y)
    lam = sun_ecliptic_longitude_deg(JD_utc)
    gz_month = month_pillar_from_longitude(lam, gz_year)
    gz_day = day_pillar_local_midnight(y,m,d, tz_hours=tz)
    gz_hour = hour_pillar(gz_day, hh, mm, use_lmt=use_lmt, lon_deg=lon, tz_hours=tz)
    return gz_year, gz_month, gz_day, gz_hour

# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_compact_datetime(stamp: str):
    """Parse xyyyymmddHHMM where x in {m,M,f,F}."""
    if not isinstance(stamp, str):
        raise ValueError('stamp must be a string')
    stamp = stamp.strip()
    if len(stamp) != 13:
        raise ValueError('stamp must be 13 chars: xyyyymmddHHMM')

    sex_char = stamp[0]
    if sex_char in ('m', 'M'):
        is_female = False
    elif sex_char in ('f', 'F'):
        is_female = True
    else:
        raise ValueError('stamp[0] must be m/M/f/F')

    digits = stamp[1:]
    if not digits.isdigit():
        raise ValueError('stamp[1:] must be digits (yyyymmddHHMM)')

    y = int(digits[0:4])
    m = int(digits[4:6])
    d = int(digits[6:8])
    hh = int(digits[8:10])
    mm = int(digits[10:12])

    if not (1 <= m <= 12):
        raise ValueError('month out of range')
    if not (1 <= d <= 31):
        raise ValueError('day out of range')
    if not (0 <= hh <= 23):
        raise ValueError('hour out of range')
    if not (0 <= mm <= 59):
        raise ValueError('minute out of range')

    return is_female, y, m, d, hh, mm

def _format_ymdhm(y: int, m: int, d: int, hh: int, mm: int) -> str:
    return f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}"

def _iso_to_ymdhm(stamp: Optional[str]) -> Optional[str]:
    if stamp is None:
        return None
    if not isinstance(stamp, str):
        raise ValueError("stamp must be a string or None")
    # Accept both "YYYY-MM-DDTHH:MM:SS" and "YYYY-MM-DD HH:MM:SS" forms.
    stamp = stamp.replace("T", " ").strip()
    return stamp[:16]

def _normalize_age_years(age_years: float):
    if isinstance(age_years, bool) or not isinstance(age_years, (int, float)):
        return age_years
    nearest = round(float(age_years))
    if abs(float(age_years) - nearest) < 1e-9:
        return int(nearest)
    return float(age_years)

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument("--male", action="store_true")
    g.add_argument("--female", action="store_true")
    p.add_argument("stamp", nargs="?", help="xyyyymmddHHMM (x=m/M/f/F)")
    p.add_argument("--simple", help="DEPRECATED: use positional stamp (xyyyymmddHHMM)")
    p.add_argument("--date")              # YYYY-MM-DD
    p.add_argument("--time", default="12:00")            # HH:MM (local civil)
    p.add_argument("--tz", type=float, default=9.0)      # hours (e.g., 9 for KST)
    p.add_argument("--lon", type=float, default=126.98)  # Seoul ≈ 126.98E
    p.add_argument("--lmt", action="store_true", default=True)  # apply LMT boundary shift
    p.add_argument("--no-lmt", action="store_false", dest="lmt")  # disable LMT boundary shift
    p.add_argument("--cycle", type=int, default=10)     # luck cycle count
    args = p.parse_args()

    if args.stamp and args.simple:
        p.error("use either positional stamp or --simple, not both")

    compact = args.stamp or args.simple
    if compact:
        if args.date is not None or args.time != "12:00" or args.male or args.female:
            p.error("stamp replaces --date/--time/--male/--female")
        try:
            is_female, y, m, d, hh, mm = parse_compact_datetime(compact)
        except ValueError as e:
            p.error(str(e))
    else:
        if not args.date:
            p.error("positional stamp or --date is required")
        y, m, d = map(int, args.date.split("-"))
        hh, mm = map(int, args.time.split(":"))
        is_female = bool(args.female)
    gz_year, gz_month, gz_day, gz_hour = manse_calc(y,m,d,hh,mm,args.tz,args.lon,args.lmt)
    JD_utc = gregorian_to_jd(y,m,d, hh - args.tz, mm, 0)

    lunar_r = gregorian_to_lunar(y, m, d)
    lunar_str = None
    yoon = None
    if lunar_r is not None:
        lunar_str = datetime.datetime(lunar_r[0], lunar_r[1], lunar_r[2], hh, mm).isoformat(timespec='seconds')
        yoon = bool(lunar_r[3])

    verbose_result = {
        "gregorian": datetime.datetime(y, m, d, hh, mm).isoformat(timespec='seconds'),
        "lunar": lunar_str,
        "yoon": yoon,
        "ganzhi": {
            "year":  gz_year,
            "month": gz_month,
            "day":   gz_day,
            "hour":  gz_hour
        },
        "sex": ("female" if is_female else "male"),
        "luck_cycles": luck_cycles_info(
            JD_utc,
            y,
            datetime.datetime(y, m, d, hh, mm),
            gz_month,
            luck_cycles_direction(gz_year, is_female=is_female),
            cycles=args.cycle,
        )
    }

    cycles = [
        {
            "start_age": _normalize_age_years(cycle["age_start"]),
            "start_date": _iso_to_ymdhm(cycle["date_start"]),
            "ganzhi": cycle["pillar"],
            "ganzhi_kor": ganzhi_to_korean(cycle["pillar"]),
        }
        for cycle in (verbose_result.get("luck_cycles") or {}).get("cycles") or []
    ]

    result = {
        "date": _format_ymdhm(y, m, d, hh, mm),
        "korean": (
            f"{ganzhi_to_korean(gz_year)}년 "
            f"{ganzhi_to_korean(gz_month)}월 "
            f"{ganzhi_to_korean(gz_day)}일 "
            f"{ganzhi_to_korean(gz_hour)}시"
        ),
        "hanja": f"{gz_year}년 {gz_month}월 {gz_day}일 {gz_hour}시",
        "cycles": cycles,
        "verbose": verbose_result,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
