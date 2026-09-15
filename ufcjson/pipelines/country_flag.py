import pycountry

from ufcjson.items import UfcPlayerItem

# 出生地拆分出的国家写法与 pycountry 标准名不一致时的映射，避免查不到国旗
# 统一映射到 pycountry 可精确命中的标准名
COUNTRY_ALIASES = {
    'England': 'United Kingdom',
    'Scotland': 'United Kingdom',
    'Wales': 'United Kingdom',
    'Canary Islands': 'Spain',
    'Congo - Kinshasa': 'Congo, the Democratic Republic of the',
    'Democratic Republic of the Congo': 'Congo, the Democratic Republic of the',
    'Bosnia & Herzegovina': 'Bosnia and Herzegovina',
}


# 用于将国家转换为Emoji表情的管道
class UfcCountryCodePipeline:
    def process_item(self, item):
        if isinstance(item, UfcPlayerItem):
            # country 由出生地在爬虫里拆好，直接用于国旗匹配，不再解析 home_town
            country = item.get('country', '')
            item['flag'] = self.get_country_flag(country.strip())
        return item

    def get_country_flag(self, country_name):
        if not country_name:
            return '🏳'
        country_name = COUNTRY_ALIASES.get(country_name, country_name)
        try:
            country = pycountry.countries.get(name=country_name)
            if country is None:
                country = pycountry.countries.search_fuzzy(country_name)
                if len(country) > 0:
                    country = country[0]
            return country.flag
        except Exception as e:
            return '🏳'
