import html
from datetime import date


def infer_birth_year(age_text, today=None):
    """由页面的「Age（整数周岁）」推断出生年，返回 'YYYY'；推不出返回空串。

    用途：ufc.com 只有 Age、没有生日。新选手入库时若 birthdate 为空，用它兜一个
    「仅年份」的近似值——App 端 `FighterDetailDisplay.ageOf` 支持 YYYY（按
    `今天年份 − 该年` 展示），误差窗口最多一年（生日未过/已过各占一半）。
    精确值（YYYY-MM-DD）只能靠 Sherdog 回填，回填断点必须是
    `LENGTH(birthdate) < 10`，否则近似值会把精确值挡在门外（DB-NOTES §1.9.7）。

    - Age 只有整数岁 → 出生年有两个候选（今天年 − Age / − 1），取前者；
    - 非数字 / 越界（<=0 或 >=100）一律返回空串，宁可留空，不给脏值。
    """
    raw = (age_text or '').strip()
    if not raw.isdigit():
        return ''
    age = int(raw)
    if not 0 < age < 100:
        return ''
    today = today or date.today()
    return str(today.year - age)


def split_birth_place(birth_place):
    """将出生地 "城市, 国家" 拆分为 (city, country)。

    - 用 rsplit 取最后一段作为国家，兼容 "城市, 州/省, 国家" 三段式数据；
    - 反转义 HTML 实体（如 "Bosnia &amp; Herzegovina" -> "Bosnia & Herzegovina"），
      避免后续 pycountry 匹配和翻译拿到带实体符号的脏数据；
    - 只有国家没有城市时（如 "Japan"），city 返回空字符串。
    """
    birth_place = (birth_place or '').strip()
    if ',' in birth_place:
        city, country = birth_place.rsplit(',', 1)
        city = city.strip()
        country = country.strip()
    else:
        city, country = '', birth_place
    return html.unescape(city), html.unescape(country)
