import datetime
import json
import os
import re
import sqlite3
import xml.etree.ElementTree as ET

from ufcjson.items import UfcComingCardItem, UfcCnNewsItem
from ufcjson.rss import RssMaker, clean_news_text
from ufcjson.spiders.upcoming import UpcomingSpider
from ufcjson.spiders.ufccn_news import UfcCnNewsSpider


# 国家别名映射（复用 country_flag.py 的逻辑）
COUNTRY_ALIASES = {
    'England': 'United Kingdom',
    'Scotland': 'United Kingdom',
    'Wales': 'United Kingdom',
    'Canary Islands': 'Spain',
    'Congo - Kinshasa': 'Congo, the Democratic Republic of the',
    'Democratic Republic of the Congo': 'Congo, the Democratic Republic of the',
    'Bosnia & Herzegovina': 'Bosnia and Herzegovina',
}

# 默认占位图（红/蓝方全身照占位，复用 image.py 中的默认图）
DEFAULT_FIGHTER_IMG = ('https://dmxg5wxfqgb4u.cloudfront.net/styles/'
    'event_fight_card_upper_body_of_standing_athlete/s3/image/fighter_images/'
    'SHADOW_Fighter_fullLength_RED.png?VersionId=0NwYm4ow5ym9PWjgcpd05ObDBIC5pBtX&itok=woJQm5ZH')

RSS_XML_PATH = 'output/rss/ufc_schedule.xml'
PUBLISHED_IDS_PATH = 'output/rss/published_ids.json'
COMING_JSON_PATH = 'output/json/ufc_coming_data.json'
DB_PATH = 'output/db/ufc.db'
TRANSLATE_DB_PATH = 'output/db/ufc_translate.db'

MAX_RSS_ITEMS = 100


def _name_from_url(page_url):
    """从选手主页 URL 推断姓名，例如 /athlete/gabriel-bonfim -> 'Gabriel Bonfim'"""
    if not page_url:
        return ''
    m = re.search(r'/athlete/([^/?#]+)', page_url)
    if not m:
        return ''
    slug = m.group(1).replace('-', ' ')
    return ' '.join(w.capitalize() for w in slug.split())


def _athlete_slug(page_url):
    """取选手主页 URL 的末段并小写，用于绕开 URL 大小写差异（DB 里有 Muhammad-Naimov）。"""
    m = re.search(r'/athlete/([^/?#]+)', page_url or '')
    return m.group(1).lower() if m else ''


def _norm_key(value):
    """归一化查找键：删掉所有空白。

    源站与数据库对同一个值的空格写法不一致，例如举办地在 RSS 里是
    'Las Vegas, NV, United States'，pass_event 里是 'Las Vegas,NV,United States'；
    赛事名 '#UFC Fight Night' 在 spider 里被 replace(' ','') 成了 'UFCFightNight'。
    统一去掉空白后互认，比逐个写别名可靠。
    """
    return re.sub(r'\s+', '', (value or '')).lower()


def _get_flag(country_name):
    """国家名转国旗 emoji（轻量实现，避免在 pipeline 里再依赖 pycountry 的调用开销）。
    先尝试从 player 表自带的 flag 字段取；这里仅作为兜底。"""
    if not country_name:
        return ''
    try:
        import pycountry
        name = COUNTRY_ALIASES.get(country_name, country_name)
        country = pycountry.countries.get(name=name)
        if country is None:
            res = pycountry.countries.search_fuzzy(name)
            if len(res) > 0:
                country = res[0]
        return country.flag
    except Exception:
        return ''


# 每周三由 ranking 爬虫刷新的榜单快照。它和 upcoming 爬虫是两条独立数据源：
# upcoming 抓的是战卡页面上印着的那一次名次（只在该爬虫能抓到页面时才有值），
# 榜单快照则是整张榜单（每级别前 15 + 冠军），不依赖战卡页面。
RANKING_JSON_PATH = 'output/json/ufc_ranking_data.json'

# 战卡级别 -> 榜单名，中英两种写法都收：管道拿到的是英文（'Welterweight Bout'），
# 而就地重渲染只能从旧 title 反解出中文（'次中量级比赛'）。
DIVISION_LIST_ALIASES = {
    'flyweight': 'Flyweight',
    '蝇量级': 'Flyweight',
    'bantamweight': 'Bantamweight',
    '雏量级': 'Bantamweight',
    'featherweight': 'Featherweight',
    '羽量级': 'Featherweight',
    'lightweight': 'Lightweight',
    '轻量级': 'Lightweight',
    'welterweight': 'Welterweight',
    '次中量级': 'Welterweight',
    'middleweight': 'Middleweight',
    '中量级': 'Middleweight',
    'light heavyweight': 'Light Heavyweight',
    '轻重量级': 'Light Heavyweight',
    'heavyweight': 'Heavyweight',
    '重量级': 'Heavyweight',
    "women's strawweight": "Women's Strawweight",
    '女子草量级': "Women's Strawweight",
    "women's flyweight": "Women's Flyweight",
    '女子蝇量级': "Women's Flyweight",
    "women's bantamweight": "Women's Bantamweight",
    '女子雏量级': "Women's Bantamweight",
}


def _compact(text):
    """只留字母数字与汉字，用于级别名的模糊匹配（兜住空格与撇号写法差异）。"""
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', (text or '').lower())


def list_for_division(division):
    """战卡级别 -> 榜单名：'Light Heavyweight Bout' / '轻重量级比赛' -> 'Light Heavyweight'。

    按「别名最长优先」匹配，因为短名是长名的子串：'重量级' 落在 '轻重量级' 里、
    '中量级' 落在 '次中量级' 里，先命中短的就会贴错榜。女子榜再按 '女子' / 'women'
    过滤一遍，否则 "Women's Flyweight" 会被男子蝇量级抢走。
    """
    key = _compact(division)
    if not key:
        return ''
    women = ('女子' in key) or ('women' in key)
    best_key, best_name = '', ''
    for alias, name in DIVISION_LIST_ALIASES.items():
        a = _compact(alias)
        if not a or a not in key:
            continue
        if (('women' in a) or ('女子' in a)) != women:
            continue
        if len(a) > len(best_key):
            best_key, best_name = a, name
    return best_name


def load_rank_index(path=RANKING_JSON_PATH):
    """读榜单快照 -> {'by_slug': {athlete-slug: {榜单名: 名次}}}。

    文件是 API 包装格式 {"code":0,"msg":"success","data":[...]}。文件缺失 / 解析失败
    一律当成「没有榜单」而不是抛错——RSS 少一行排名，远比整条管线挂掉可接受。
    """
    if not os.path.exists(path):
        return {'by_slug': {}}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except (ValueError, IOError):
        return {'by_slug': {}}
    rows = raw.get('data') if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return {'by_slug': {}}
    by_slug = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        slug = _athlete_slug(row.get('page') or '')
        name = (row.get('rank_name') or '').strip()
        rank = row.get('rank')
        if not slug or not name or rank is None:
            continue
        try:
            rank = int(rank)
        except (TypeError, ValueError):
            continue
        # 同一选手可能同时挂在级别榜与 P4P 榜上，两条都留着，取用时按战卡级别挑
        by_slug.setdefault(slug, {})[name] = rank
    return {'by_slug': by_slug}


def rank_for(index, page_url, division):
    """按「选手主页 + 战卡级别对应的榜单」取名次；未上榜 / 跨级别返回 None。

    刻意**不**回落到「该选手在任意榜单上的名次」：实测约翰尼·沃克、布莱恩·奥尔特加
    这类刚换级别的选手，榜单快照还挂在旧级别上，随便挑一条就会贴错榜。宁可不显示。
    """
    name = list_for_division(division)
    slug = _athlete_slug(page_url)
    if not name or not slug:
        return None
    return ((index or {}).get('by_slug') or {}).get(slug, {}).get(name)


# 用于制作Rss订阅文件的管道
class UfcRssMakerPipeline:
    def __init__(self, crawler):
        self.crawler = crawler
        self.rssMaker = RssMaker(
            title="UFC 资讯",
            link='https://www.ufc.com/events#events-list-upcoming',
            description="UFC 赛程战卡与中文新闻资讯"
        )
        self.rssList = []          # 本次爬取的所有战卡/新闻（组装好的RSS dict）
        self.old_fight_ids = set() # 已存在的战卡 key（旧 JSON + 已发布）
        self.player_map = {}       # {page_url: {name, country, flag, cover, ...}}（取值为中文）
        self.player_slug_map = {}  # {athlete-slug: 同上}，URL 大小写不一致时的兜底
        self.zh_map = {}           # {英文原文: 中文}
        self.zh_norm = {}          # {去掉空白的英文: 中文}
        self.rank_index = {'by_slug': {}}  # 每周三的榜单快照，见 load_rank_index
        self.is_first_run = False  # 是否首次运行（无 published_ids 文件）
        self.spider_type = None    # 'upcoming' | 'ufccn_news'
        self.news_ids = set()      # 已发布的新闻 ID（避免重复）

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open_spider(self):
        spider = self.crawler.spider

        # 判断爬虫类型
        if isinstance(spider, UpcomingSpider):
            self.spider_type = 'upcoming'
        elif isinstance(spider, UfcCnNewsSpider):
            self.spider_type = 'ufccn_news'
        else:
            return

        # 1. 从旧的 coming JSON 中提取已存在的战卡 key（仅 upcoming 需要）
        if self.spider_type == 'upcoming':
            if os.path.exists(COMING_JSON_PATH):
                try:
                    with open(COMING_JSON_PATH, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                    events = old_data.get('data', [])
                    for evt in events:
                        evt_name = evt.get('name', '')
                        for card in evt.get('fight_card', []):
                            fid = card.get('fight_id', '')
                            if fid:
                                self.old_fight_ids.add(f'id:{fid}')
                            else:
                                # 无 fight_id 时用组合键
                                key = 'cmp:' + '|'.join([
                                    evt_name,
                                    card.get('red_page', ''),
                                    card.get('blue_page', ''),
                                ])
                                self.old_fight_ids.add(key)
                    spider.logger.info(f"[RSS] 从旧 JSON 加载 {len(self.old_fight_ids)} 个已存在战卡 key")
                except Exception as e:
                    spider.logger.warning(f"[RSS] 读取旧 coming JSON 失败: {e}")

        # 2. 从已发布 ID 文件中加载（防止 RSS 截断后重复发布）
        if os.path.exists(PUBLISHED_IDS_PATH):
            try:
                with open(PUBLISHED_IDS_PATH, 'r', encoding='utf-8') as f:
                    published = json.load(f)
                if self.spider_type == 'upcoming':
                    before = len(self.old_fight_ids)
                    # 只加载战卡类的 key（id: 或 cmp: 开头）
                    fight_keys = [k for k in published if k.startswith('id:') or k.startswith('cmp:')]
                    self.old_fight_ids.update(fight_keys)
                    spider.logger.info(f"[RSS] 从 published_ids 加载 {len(self.old_fight_ids) - before} 个已发布战卡 ID")
                else:
                    # 新闻类 key（news: 开头）
                    news_keys = [k for k in published if k.startswith('news:')]
                    self.news_ids.update(news_keys)
                    spider.logger.info(f"[RSS] 从 published_ids 加载 {len(self.news_ids)} 条已发布新闻 ID")
            except Exception as e:
                spider.logger.warning(f"[RSS] 读取 published_ids.json 失败: {e}")
        else:
            # 首次运行：没有 published_ids 文件
            if self.spider_type == 'upcoming' and self.old_fight_ids:
                spider.logger.info("[RSS] 首次运行，将所有战卡作为初始内容写入 RSS")
                self.old_fight_ids = set()  # 清空，使所有战卡都被视为新增
                self.is_first_run = True

        # 3. 预加载中文字典与选手数据库（仅 upcoming 需要）
        if self.spider_type == 'upcoming':
            self._load_zh_map(spider)
            self._load_players(spider)
            # 4. 榜单快照：给战卡补「排名」行。抓不到新战卡页面时，这是唯一的名次来源
            self.rank_index = load_rank_index()
            spider.logger.info(
                "[RSS] 加载榜单快照 %d 名选手（%s）",
                len(self.rank_index.get('by_slug', {})), RANKING_JSON_PATH)

    def _load_zh_map(self, spider):
        """加载「英文原文 -> 中文」映射，供 RSS 里所有非中文取值查表。

        优先级由低到高：通用翻译表 -> pass_card / pass_event 的 _cn 列
        -> player 的 _cn 列。同键由后写入者覆盖先写入者，所以结构化的 _cn 列
        永远压过通用翻译表，翻译表只负责补 _cn 覆盖不到的部分（如赛事名）。
        """
        def put(en, cn):
            en = (en or '').strip()
            cn = (cn or '').strip()
            if not en or not cn or en == cn:
                return
            # 覆盖语义：后加载的 _cn 列压过先前写入的通用翻译表
            self.zh_map[en] = cn
            self.zh_norm[_norm_key(en)] = cn

        # 1) 通用翻译表（最低优先级，只做补漏）
        if os.path.exists(TRANSLATE_DB_PATH):
            try:
                # 翻译表由独立的翻译脚本持续写入，给足等待时间，读不到就跳过，
                # 不能因为拿不到锁就把整轮 RSS 生成拖垮
                tconn = sqlite3.connect(TRANSLATE_DB_PATH, timeout=10)
                rows = tconn.execute(
                    "SELECT original, translation FROM translate "
                    "WHERE original IS NOT NULL AND translation IS NOT NULL").fetchall()
                tconn.close()
                for original, translation in rows:
                    put(original, translation)
                spider.logger.info(f"[RSS] 加载通用翻译表 {len(rows)} 条")
            except Exception as e:
                spider.logger.warning(f"[RSS] 读取翻译表失败: {e}")
        else:
            spider.logger.warning("[RSS] 翻译表不存在，仅使用数据库 _cn 列")

        if not os.path.exists(DB_PATH):
            spider.logger.warning("[RSS] 数据库不存在，中文映射为空")
            return

        # 2) 数据库里的 _cn 列（权威来源，覆盖翻译表）
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            for row in conn.execute(
                    "SELECT DISTINCT card_division, card_division_cn FROM pass_card "
                    "WHERE card_division <> '' AND card_division_cn <> ''"):
                put(row['card_division'], row['card_division_cn'])
            for row in conn.execute(
                    "SELECT DISTINCT address, address_cn FROM pass_event "
                    "WHERE address <> '' AND address_cn <> ''"):
                put(row['address'], row['address_cn'])
            for row in conn.execute(
                    "SELECT DISTINCT name, name_cn, country, country_cn, style, style_cn "
                    "FROM player"):
                put(row['name'], row['name_cn'])
                put(row['country'], row['country_cn'])
                put(row['style'], row['style_cn'])
        finally:
            conn.close()
        spider.logger.info(f"[RSS] 中文映射就绪，共 {len(self.zh_map)} 条")

    def _load_players(self, spider):
        """预加载选手数据，姓名/国家/风格一律取 _cn 列。"""
        if not os.path.exists(DB_PATH):
            spider.logger.warning("[RSS] 选手数据库不存在，选手信息将使用降级数据")
            return
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT page, name, name_cn, country, country_cn, style, style_cn, "
                "flag, cover, record, age, height, weight, reach, leg_reach FROM player")
            count = 0
            for row in cursor.fetchall():
                info = {
                    'name': row['name_cn'] or row['name'] or '',
                    'name_en': row['name'] or '',
                    'country': row['country_cn'] or row['country'] or '',
                    'country_en': row['country'] or '',
                    'flag': row['flag'] or '',
                    'cover': row['cover'] or '',
                    'record': row['record'] or '',
                    'age': row['age'] or '',
                    'style': row['style_cn'] or row['style'] or '',
                    'height': row['height'] or '',
                    'weight': row['weight'] or '',
                    'reach': row['reach'] or '',
                    'leg_reach': row['leg_reach'] or '',
                }
                self.player_map[row['page']] = info
                slug = _athlete_slug(row['page'])
                if slug:
                    self.player_slug_map.setdefault(slug, info)
                count += 1
            conn.close()
            spider.logger.info(f"[RSS] 预加载选手数据 {count} 条（姓名/国家/风格取中文列）")
        except Exception as e:
            spider.logger.warning(f"[RSS] 加载选手数据库失败: {e}")

    def _zh(self, value, default=None):
        """英文取值 -> 中文。查不到返回 default（默认原值），保证不会输出空白。"""
        s = (value or '').strip()
        if not s:
            return '' if default is None else default
        cn = self.zh_map.get(s) or self.zh_norm.get(_norm_key(s))
        if cn:
            return cn
        return s if default is None else default

    def _zh_fight_name(self, raw):
        """赛事名转中文。

        源站 h1 取下来时被 spider 去掉了空格（'Crypto.com UFC 331' -> 'Crypto.comUFC331'），
        所以先按去空白归一化查表，命中就返回；没命中时对「UFC + 编号」补回空格，
        UFC 数字赛的中文写法本来就带空格（'UFC 332'），顺带修掉粘连。
        """
        s = (raw or '').strip()
        if not s:
            return ''
        cn = self.zh_map.get(s) or self.zh_norm.get(_norm_key(s))
        if cn:
            return cn
        fixed = re.sub(r'ufc\s*(\d{2,4})', lambda m: 'UFC ' + m.group(1), s, flags=re.I)
        fixed = re.sub(r'(?<=\.com)(?=UFC)', ' ', fixed)
        fixed = re.sub(r'(?<=[a-z])(?=UFC\b)', ' ', fixed)
        return fixed.strip()

    def _zh_address(self, raw):
        """举办地转中文。

        pass_event 的 address_cn 是「国家+州+城市」的中文写法，整串命中就用它；
        未来新赛事出现库里没有的城市时，退回逐段查（城市 / 州 / 国家分开翻），
        至少保证国家和城市是中文，而不是整串英文原样输出。
        """
        s = (raw or '').strip()
        if not s:
            return ''
        cn = self.zh_map.get(s) or self.zh_norm.get(_norm_key(s))
        if cn:
            return cn
        parts = [p.strip() for p in s.split(',') if p.strip()]
        if len(parts) <= 1:
            return s
        return ', '.join(self._zh(p, p) for p in parts)

    def _get_player_info(self, page_url):
        """根据选手主页 URL 获取选手信息，查不到则降级。返回的姓名/国家/风格均为中文。"""
        p = self.player_map.get(page_url) or self.player_slug_map.get(_athlete_slug(page_url))
        if p:
            return {
                'name': p['name'],
                'name_en': p['name_en'],
                'country': p['country'],
                # 国旗只按英文国名查表（pycountry 认英文），DB 自带的 flag 优先
                'flag': p['flag'] or (_get_flag(p['country_en']) if p['country_en'] else ''),
                'cover': p['cover'] or DEFAULT_FIGHTER_IMG,
                'record': p['record'],
                'age': p['age'],
                'style': p['style'],
                'height': p['height'],
                'weight': p['weight'],
                'reach': p['reach'],
                'leg_reach': p['leg_reach'],
            }
        # 降级
        return {
            'name': '未知选手',
            'name_en': _name_from_url(page_url),
            'country': '',
            'flag': '',
            'cover': DEFAULT_FIGHTER_IMG,
            'record': '',
            'age': '',
            'style': '',
            'height': '',
            'weight': '',
            'reach': '',
            'leg_reach': '',
        }

    def _card_key(self, card_dict):
        """生成战卡的唯一标识键。优先用 fight_id，否则用组合键。"""
        fid = card_dict.get('fight_id', '')
        if fid:
            return f'id:{fid}'
        # 无 fight_id 时用 赛事名+红方URL+蓝方URL 组合
        return 'cmp:' + '|'.join([
            card_dict.get('fight_name', ''),
            card_dict.get('red_page', ''),
            card_dict.get('blue_page', ''),
        ])

    def _news_key(self, news_dict):
        """生成新闻的唯一标识键。"""
        return f'news:{news_dict.get("news_id", "")}'

    def process_item(self, item):
        if isinstance(item, UfcComingCardItem):
            return self._process_fight_card(item)
        if isinstance(item, UfcCnNewsItem):
            return self._process_news_item(item)
        return item

    def _resolve_rank(self, live_value, page_url, card_division):
        """名次有两个来源，时效性不同，页面值优先。

        - `item['red_rank']`：`upcoming` 爬虫从战卡页面抄下来的，是抓取那一刻的名次。
        - 榜单快照：整张榜单，每周三刷新，最多可能落后一周。

        页面值只要非空就采信；为空（爬虫抓不到新战卡时的常态）才回落到快照。
        """
        if str(live_value or '').strip():
            return live_value
        return rank_for(self.rank_index, page_url, card_division)

    def _process_fight_card(self, item):

        red = self._get_player_info(item.get('red_page', ''))
        blue = self._get_player_info(item.get('blue_page', ''))

        # 主卡时间戳 → datetime
        main_ts = item.get('main_time', '')
        try:
            fight_dt = datetime.datetime.fromtimestamp(int(main_ts))
        except (ValueError, TypeError):
            fight_dt = datetime.datetime.now()

        # 组装 title —— 赛事名 / 级别 / 举办地一律转中文
        title = "{date} {fight_name} ({red_name} VS {blue_name}) 级别：{division} 举办地:{address}".format(
            date=fight_dt.strftime("%m-%d"),
            fight_name=self._zh_fight_name(item.get('fight_name', '')),
            red_name=red['name'],
            blue_name=blue['name'],
            division=self._zh(item.get('card_division', '')),
            address=self._zh_address(item.get('address', '')),
        )

        # RSS link：用红方选手主页作为兜底（UFC官网战卡详情页URL不固定，选手主页稳定可达）
        link = item.get('red_page', '')

        # 名次：优先用战卡页面上印着的那一次，取不到再回落到每周三的榜单快照
        card_division = item.get('card_division', '')
        red_rank = self._resolve_rank(item.get('red_rank', ''),
                                      item.get('red_page', ''), card_division)
        blue_rank = self._resolve_rank(item.get('blue_rank', ''),
                                       item.get('blue_page', ''), card_division)

        # description 的 HTML 模板数据（传给 RssMaker.get_html_str）
        desc_data = {
            'fight_name': self._zh_fight_name(item.get('fight_name', '')),
            'card_division': self._zh(item.get('card_division', '')),
            'address': self._zh_address(item.get('address', '')),
            'redPlayerName': red['name'],
            'redPlayerCountry': red['country'] or '—',
            'redPlayerCountryEmoji': red['flag'] or '🏳',
            'redPlayerRank': red_rank,
            'redPlayerOdds': item.get('red_odds', '') or '—',
            'redPlayerBack': red['cover'],
            'redRecord': red['record'] or '—',
            'redAge': red['age'] or '—',
            'redStyle': red['style'] or '—',
            'redHeight': red['height'] or '—',
            'redWeight': red['weight'] or '—',
            'redReach': red['reach'] or '—',
            'redLegReach': red['leg_reach'] or '—',
            'bluePlayerName': blue['name'],
            'bluePlayerCountry': blue['country'] or '—',
            'bluePlayerCountryEmoji': blue['flag'] or '🏳',
            'bluePlayerRank': blue_rank,
            'bluePlayerOdds': item.get('blue_odds', '') or '—',
            'bluePlayerBack': blue['cover'],
            'blueRecord': blue['record'] or '—',
            'blueAge': blue['age'] or '—',
            'blueStyle': blue['style'] or '—',
            'blueHeight': blue['height'] or '—',
            'blueWeight': blue['weight'] or '—',
            'blueReach': blue['reach'] or '—',
            'blueLegReach': blue['leg_reach'] or '—',
        }

        self.rssList.append({
            'fight_id': item.get('fight_id', ''),
            'fight_name': item.get('fight_name', ''),
            'red_page': item.get('red_page', ''),
            'blue_page': item.get('blue_page', ''),
            'title': title,
            'link': link,
            'time': fight_dt,           # 比赛时间（暂存，新增战卡的 pubDate 会被覆盖为发现时间）
            'description': self.rssMaker.get_html_str(desc_data),
        })

        return item

    def _process_news_item(self, item):
        """处理 UFC 中文新闻条目，组装成 RSS item dict。"""
        news_id = item.get('id', '')
        title = clean_news_text(item.get('title', ''))
        link = item.get('url', '')
        time_str = item.get('time_str', '')

        # 解析发布时间（列表接口的 Time 是 "2026/09/15 06:00:00"；
        # 详情接口是 "2026.09.15  06:00"，所以这里只能用列表那一份）
        try:
            pub_dt = datetime.datetime.strptime(time_str, "%Y/%m/%d %H:%M:%S")
        except (ValueError, TypeError):
            pub_dt = datetime.datetime.now()

        # description 的 HTML 由 RssMaker 统一生成：
        # 实体还原、标签白名单、文本转义、去站内稿源前缀都在那边做
        desc_html = self.rssMaker.get_news_html_str({
            'title': title,
            'type': item.get('type', 0),
            'cover': item.get('cover', ''),
            'body': item.get('body', ''),
            'details': item.get('details', ''),
            'images': item.get('images', []),
            'video_url': item.get('video_url', ''),
            'link': link,
        })

        self.rssList.append({
            'news_id': news_id,
            'title': f'[新闻] {title}',
            'link': link,
            'time': pub_dt,
            'description': desc_html,
        })

        return item

    def close_spider(self):
        spider = self.crawler.spider

        if self.spider_type == 'upcoming':
            self._close_upcoming(spider)
        elif self.spider_type == 'ufccn_news':
            self._close_ufccn_news(spider)

    def _close_upcoming(self, spider):
        # 过滤：只保留新出现的战卡（用 card_key 做唯一标识）
        new_cards = [c for c in self.rssList if self._card_key(c) not in self.old_fight_ids]

        spider.logger.info(f"[RSS] 本次爬取 {len(self.rssList)} 张战卡，新增 {len(new_cards)} 张")

        if not new_cards:
            spider.logger.info("[RSS] 无新增战卡，跳过 RSS 生成")
            return

        # 新战卡的 pubDate 设为发现时间（当前时间）
        now = datetime.datetime.now()
        for c in new_cards:
            c['time'] = now

        # 读取旧 RSS 的 items（如果有）
        old_items = []
        if os.path.exists(RSS_XML_PATH):
            try:
                old_items = self._parse_rss_items(RSS_XML_PATH)
            except Exception as e:
                spider.logger.warning(f"[RSS] 解析旧 RSS 失败，将覆盖: {e}")

        # 合并：新的在前，按时间倒序，截断
        merged = new_cards + old_items
        # 按 pubDate 降序
        merged.sort(key=lambda x: x['time'], reverse=True)
        # 去重（按 title 简单去重，防止无 fight_id 的战卡重复）
        seen_titles = set()
        unique = []
        for it in merged:
            if it['title'] in seen_titles:
                continue
            seen_titles.add(it['title'])
            unique.append(it)
        merged = unique[:MAX_RSS_ITEMS]

        # 确保输出目录存在
        os.makedirs(os.path.dirname(RSS_XML_PATH), exist_ok=True)

        # 写回 RSS
        self.rssMaker.makeRss(merged, RSS_XML_PATH)
        spider.logger.info(f"[RSS] 生成 RSS 完成，共 {len(merged)} 条（新增 {len(new_cards)} 条）")

        # 更新已发布 ID
        new_keys = [self._card_key(c) for c in new_cards]
        if new_keys:
            # 合并已有 ID 后写回（保持文件是全量的，方便后续直接读）
            all_published = set(self.old_fight_ids)
            all_published.update(new_keys)
            try:
                with open(PUBLISHED_IDS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(sorted(all_published), f, ensure_ascii=False, indent=2)
                spider.logger.info(f"[RSS] 已更新 published_ids.json，共 {len(all_published)} 个 ID")
            except Exception as e:
                spider.logger.error(f"[RSS] 写入 published_ids.json 失败: {e}")

    def _close_ufccn_news(self, spider):
        """UFC 中文新闻的 close 逻辑：去重后追加到 RSS 文件。"""
        # 过滤：只保留未发布过的新闻
        new_news = [n for n in self.rssList if self._news_key(n) not in self.news_ids]

        spider.logger.info(f"[RSS-新闻] 本次爬取 {len(self.rssList)} 条新闻，新增 {len(new_news)} 条")

        if not new_news:
            spider.logger.info("[RSS-新闻] 无新增新闻，跳过 RSS 更新")
            return

        # 读取旧 RSS 的 items
        old_items = []
        if os.path.exists(RSS_XML_PATH):
            try:
                old_items = self._parse_rss_items(RSS_XML_PATH)
            except Exception as e:
                spider.logger.warning(f"[RSS-新闻] 解析旧 RSS 失败，将覆盖: {e}")

        # 合并：新的在前，按时间倒序，截断
        merged = new_news + old_items
        merged.sort(key=lambda x: x['time'], reverse=True)
        # 按 title 去重
        seen_titles = set()
        unique = []
        for it in merged:
            if it['title'] in seen_titles:
                continue
            seen_titles.add(it['title'])
            unique.append(it)
        merged = unique[:MAX_RSS_ITEMS]

        # 确保输出目录存在
        os.makedirs(os.path.dirname(RSS_XML_PATH), exist_ok=True)

        # 写回 RSS
        self.rssMaker.makeRss(merged, RSS_XML_PATH)
        spider.logger.info(f"[RSS-新闻] RSS 更新完成，共 {len(merged)} 条（新增新闻 {len(new_news)} 条）")

        # 更新已发布 ID（新闻类）
        new_keys = [self._news_key(n) for n in new_news]
        if new_keys:
            all_published = set()
            # 读取已有全部 key（战卡 + 新闻）
            if os.path.exists(PUBLISHED_IDS_PATH):
                try:
                    with open(PUBLISHED_IDS_PATH, 'r', encoding='utf-8') as f:
                        all_published = set(json.load(f))
                except Exception:
                    pass
            all_published.update(self.news_ids)  # 旧新闻 ID
            all_published.update(new_keys)       # 新新闻 ID
            try:
                with open(PUBLISHED_IDS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(sorted(all_published), f, ensure_ascii=False, indent=2)
                spider.logger.info(f"[RSS-新闻] 已更新 published_ids.json，共 {len(all_published)} 个 ID")
            except Exception as e:
                spider.logger.error(f"[RSS-新闻] 写入 published_ids.json 失败: {e}")

    def _parse_rss_items(self, path):
        """解析现有 RSS XML，提取 items 列表，格式和 makeRss 输入一致。"""
        tree = ET.parse(path)
        root = tree.getroot()
        channel = root.find('channel')
        if channel is None:
            return []
        items = []
        for item_elem in channel.findall('item'):
            title = item_elem.findtext('title', '')
            link = item_elem.findtext('link', '')
            description = item_elem.findtext('description', '')
            pub_date_str = item_elem.findtext('pubDate', '')
            pub_dt = None
            if pub_date_str:
                # PyRSS2Gen 默认用 RFC 2822 格式，尝试解析
                try:
                    from email.utils import parsedate_to_datetime
                    pub_dt = parsedate_to_datetime(pub_date_str)
                    # 转为 naive datetime（和 makeRss 里的 datetime.datetime.now() 一致）
                    if pub_dt.tzinfo is not None:
                        pub_dt = pub_dt.replace(tzinfo=None)
                except Exception:
                    pass
            if pub_dt is None:
                pub_dt = datetime.datetime.fromtimestamp(0)
            items.append({
                'title': title,
                'link': link,
                'description': description,
                'time': pub_dt,
            })
        return items
