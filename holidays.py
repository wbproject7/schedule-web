"""
한국 공휴일 데이터 (2024-2028)
==============================
외부 API 의존 없이 하드코딩. 유지비용: 0원.
음력 공휴일(설날, 추석)은 연도별 양력 변환 포함.
대체공휴일 포함.
"""

# 고정 공휴일 (매년 동일)
FIXED_HOLIDAYS = {
    (1, 1): '신정',
    (3, 1): '삼일절',
    (5, 5): '어린이날',
    (6, 6): '현충일',
    (8, 15): '광복절',
    (10, 3): '개천절',
    (10, 9): '한글날',
    (12, 25): '크리스마스',
}

# 음력 기반 공휴일 (양력 변환, 연도별)
# 설날: 음력 1/1 전날, 당일, 다음날
# 추석: 음력 8/15 전날, 당일, 다음날
# 부처님오신날: 음력 4/8
LUNAR_HOLIDAYS = {
    2024: {
        'seollal': [(2, 9), (2, 10), (2, 11)],      # 설날 연휴
        'seollal_sub': [(2, 12,)],                    # 대체공휴일
        'chuseok': [(9, 16), (9, 17), (9, 18)],      # 추석 연휴
        'buddha': [(5, 15)],                           # 부처님오신날
    },
    2025: {
        'seollal': [(1, 28), (1, 29), (1, 30)],
        'chuseok': [(10, 5), (10, 6), (10, 7)],
        'chuseok_sub': [(10, 8,)],
        'buddha': [(5, 5)],                            # 어린이날과 겹침
        'buddha_sub': [(5, 6,)],
    },
    2026: {
        'seollal': [(2, 16), (2, 17), (2, 18)],
        'chuseok': [(9, 24), (9, 25), (9, 26)],
        'buddha': [(5, 24)],
    },
    2027: {
        'seollal': [(2, 5), (2, 6), (2, 7)],
        'seollal_sub': [(2, 8,)],
        'chuseok': [(9, 14), (9, 15), (9, 16)],
        'buddha': [(5, 13)],
    },
    2028: {
        'seollal': [(1, 25), (1, 26), (1, 27)],
        'chuseok': [(10, 2), (10, 3), (10, 4)],
        'buddha': [(5, 2)],
    },
}

# 선거일 등 특별 공휴일
SPECIAL_HOLIDAYS = {
    2024: {(4, 10): '제22대 국회의원 선거일'},
    2025: {},
    2026: {(6, 3): '제9회 전국동시지방선거일'},
    2027: {},
    2028: {(4, 12): '제21대 대통령 선거일'},
}


def get_holidays(year, month):
    """
    특정 연월의 공휴일 목록 반환.
    Returns: list of {'day': int, 'name': str}
    """
    result = []

    # 고정 공휴일
    for (m, d), name in FIXED_HOLIDAYS.items():
        if m == month:
            result.append({'day': d, 'name': name})

    # 음력 기반 공휴일
    lunar = LUNAR_HOLIDAYS.get(year, {})
    for key, dates in lunar.items():
        for date_tuple in dates:
            m, d = date_tuple[0], date_tuple[1]
            if m == month:
                if 'seollal' in key:
                    name = '설날 연휴' if 'sub' not in key else '설날 대체공휴일'
                elif 'chuseok' in key:
                    name = '추석 연휴' if 'sub' not in key else '추석 대체공휴일'
                elif 'buddha' in key:
                    name = '부처님오신날' if 'sub' not in key else '부처님오신날 대체공휴일'
                else:
                    name = '공휴일'
                result.append({'day': d, 'name': name})

    # 특별 공휴일
    specials = SPECIAL_HOLIDAYS.get(year, {})
    for (m, d), name in specials.items():
        if m == month:
            result.append({'day': d, 'name': name})

    result.sort(key=lambda x: x['day'])
    return result


def get_holiday_days(year, month):
    """공휴일 날짜(일)만 리스트로 반환"""
    return [h['day'] for h in get_holidays(year, month)]
