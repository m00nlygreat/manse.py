# AGENTS.md

## Project Overview

**manse** is a command-line tool for calculating the Four Pillars (사주팔자) of Korean/Chinese astrology based on birth date and time. The tool uses rule-based calculations with low-precision solar longitude approximations to determine the heavenly stems (천간) and earthly branches (지지) for year, month, day, and hour pillars.

## Core Components

### 1. Main Calculator (`manse.py`)

**Purpose**: Core calculation engine for Four Pillars astrology

**Key Functions**:
- `manse_calc()`: Main calculation function that returns all four pillars
- `year_pillar()`: Calculates year pillar based on Lichun (solar longitude 315°) boundary
- `month_pillar_from_longitude()`: Determines month pillar from current solar longitude
- `day_pillar_local_midnight()`: Calculates day pillar using local midnight boundary
- `hour_pillar()`: Computes hour pillar using 12 double-hours system

**Calculation Rules**:
- **Year Pillar**: Boundary at Lichun (solar longitude 315°)
- **Month Pillar**: Current solar longitude divided into 30° segments
- **Day Pillar**: Local civil midnight boundary (epoch tuned)
- **Hour Pillar**: 12 double-hours (2-hour units), exact boundaries belong to previous branch
- **Optional**: LMT (Local Mean Time) correction for hour boundaries based on longitude

### 2. Astronomical Calculations

**Solar Longitude Module**:
- `sun_ecliptic_longitude_deg()`: Low-precision solar ecliptic longitude calculation
- Uses Meeus-like algorithms for astronomical computations
- Supports solar term calculations for accurate pillar boundaries

**Calendar Conversions**:
- `gregorian_to_jd()`: Gregorian to Julian Date conversion
- `jd_to_gregorian()`: Julian Date to Gregorian conversion
- `gregorian_to_lunar()`: Gregorian to lunar calendar conversion (1900-2100 range)

### 3. Luck Cycles System

**Purpose**: Calculate 10-year luck cycles (대운)

**Key Functions**:
- `luck_cycles_info()`: Computes luck cycles with detailed metadata
- `luck_cycles_direction()`: Determines forward/backward direction based on gender and year stem
- Uses solar term boundaries and 3-days=1-year conversion rule

**Direction Rules**:
- Male: Forward if year stem is yang, backward if yin
- Female: Forward if year stem is yin, backward if yang

### 4. CLI Interface

**Input Methods**:
1. **Compact Format (Recommended)**: `xyyyymmddHHMM` where x = m/M/f/F
2. **Traditional Format**: Separate `--date`, `--time`, `--male/--female` flags

**Output Formats**:
- **Simple**: Korean and Hanja representations with basic luck cycles
- **Verbose**: Complete JSON with astronomical data, lunar dates, and detailed calculations

## Data Structures

### Input Parameters
- Birth date/time (Gregorian)
- Gender (male/female)
- Timezone offset (hours)
- Longitude (degrees)
- LMT correction flag
- Number of luck cycles

### Output Structure
```json
{
  "date": "YYYY-MM-DD HH:MM",
  "korean": "Korean pillar representation",
  "hanja": "Chinese character representation", 
  "cycles": [{"start_age": float, "start_date": "YYYY-MM-DD HH:MM", "ganzhi": "XX", "ganzhi_kor": "XX"}],
  "verbose": {
    "gregorian": "ISO datetime",
    "lunar": "ISO lunar datetime",
    "yoon": boolean,
    "ganzhi": {"year": "XX", "month": "XX", "day": "XX", "hour": "XX"},
    "sex": "male|female",
    "luck_cycles": {...detailed calculation data...}
  }
}
```

## Constants and Tables

### Astronomical Constants
- `_TROPICAL_YEAR_DAYS = 365.242196`
- `_DAY_EPOCH_CONST = 50` (tuned for 1988-01-27 KST → 辛巳)

### Solar Terms (`_TERMS12`)
12 solar terms with 30° intervals starting from 315° (Lichun)

### Lunar Calendar Data
- `_LUNAR_INFO_1900`: Bit-encoded lunar calendar data for 1900-2100
- Supports leap months and variable month lengths

### Stem/Branch Mappings
- `TEN_STEMS`: 甲乙丙丁戊己庚辛壬癸
- `TWELVE_BRANCHES`: 子丑寅卯辰巳午未申酉戌亥
- Korean pronunciation mappings for both stems and branches

## Algorithm Flow

1. **Parse Input**: Convert command-line arguments to datetime components
2. **Calculate JD**: Convert local datetime to UTC Julian Date
3. **Solar Longitude**: Compute solar ecliptic longitude for given JD
4. **Year Pillar**: Use Lichun boundary to determine year pillar
5. **Month Pillar**: Use solar longitude to determine month pillar
6. **Day Pillar**: Use local midnight boundary with epoch tuning
7. **Hour Pillar**: Use 12 double-hours system with optional LMT correction
8. **Luck Cycles**: Calculate 10-year cycles based on gender and year stem
9. **Format Output**: Generate both simple and verbose JSON representations

## Error Handling

- Input validation for date/time ranges
- Boundary condition handling for exact hour transitions
- Lunar calendar range limitations (1900-2100)
- Graceful fallback for unsupported dates

## Dependencies

- **Standard Library Only**: `math`, `argparse`, `json`, `sys`, `datetime`, `typing`
- **No External Dependencies**: Fully self-contained calculation engine
- **Python 3.6+ Compatible**: Uses type hints and modern Python features

## Performance Characteristics

- **Fast**: Rule-based calculations without database lookups
- **Accurate**: Low-precision astronomical calculations suitable for astrology
- **Lightweight**: Minimal memory footprint and CPU usage
- **Portable**: Works across platforms without external data files