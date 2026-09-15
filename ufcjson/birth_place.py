import html


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
