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

TEN_STEMS = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
TWELVE_BRANCHES = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']

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

# Daewoon (10-year luck cycles) helpers
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

def daewoon_info(JD_birth_utc: float, birth_year: int, gz_month: str, cycles: int = 8):
    """Compute forward/backward daewoon options (no gender input)."""
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

    def start_age(days):
        years = days / 3.0
        return years, int(math.floor(years + 1e-12))

    forward_days = max(0.0, (JD_next - JD_birth_utc))
    backward_days = max(0.0, (JD_birth_utc - JD_prev))
    forward_years, forward_age = start_age(forward_days)
    backward_years, backward_age = start_age(backward_days)

    base = _i60_from_ganzhi(gz_month)

    def cycle_list(direction: int, first_age: int):
        out = []
        for n in range(1, cycles + 1):
            i60 = (base + direction * n) % 60
            age_start = first_age + (n - 1) * 10
            out.append({
                "n": n,
                "age_start": age_start,
                "age_end": age_start + 9,
                "pillar": ganzhi_from_index(i60),
            })
        return out

    return {
        "rule": {
            "term_set": "12-jeol (30deg steps from 315deg)",
            "day_to_year": 3.0,
            "start_age_rounding": "floor",
            "first_cycle_from": "month_pillar_next_or_prev",
        },
        "birth_longitude_deg": lam,
        "current_term": {"name": cur_term[1], "deg": cur_term[0]},
        "forward": {
            "direction": "forward",
            "to_term": {"name": next_name, "deg": next_deg, "jd_utc": JD_next, "utc": jd_iso(JD_next)},
            "days": forward_days,
            "start_age_years": forward_years,
            "start_age": forward_age,
            "cycles": cycle_list(+1, forward_age),
        },
        "backward": {
            "direction": "backward",
            "to_term": {"name": prev_name, "deg": prev_deg, "jd_utc": JD_prev, "utc": jd_iso(JD_prev)},
            "days": backward_days,
            "start_age_years": backward_years,
            "start_age": backward_age,
            "cycles": cycle_list(-1, backward_age),
        },
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
if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)              # YYYY-MM-DD
    p.add_argument("--time", default="12:00")            # HH:MM (local civil)
    p.add_argument("--tz", type=float, default=9.0)      # hours (e.g., 9 for KST)
    p.add_argument("--lon", type=float, default=126.98)  # Seoul ≈ 126.98E
    p.add_argument("--lmt", action="store_true")         # apply LMT boundary shift
    args = p.parse_args()

    y, m, d = map(int, args.date.split("-"))
    hh, mm = map(int, args.time.split(":"))
    gz_year, gz_month, gz_day, gz_hour = manse_calc(y,m,d,hh,mm,args.tz,args.lon,args.lmt)
    JD_utc = gregorian_to_jd(y,m,d, hh - args.tz, mm, 0)
    result = {
        "gregorian": f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}",
        "ganzhi": {
            "year":  gz_year,
            "month": gz_month,
            "day":   gz_day,
            "hour":  gz_hour
        },
        "daewoon": daewoon_info(JD_utc, y, gz_month)
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
