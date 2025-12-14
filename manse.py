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

    print(json.dumps({
        "gregorian": f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}",
        "ganzhi": {
            "year":  gz_year,
            "month": gz_month,
            "day":   gz_day,
            "hour":  gz_hour
        }
    }, ensure_ascii=False, indent=2))

