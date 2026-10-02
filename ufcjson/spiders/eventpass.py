import scrapy
from w3lib.url import url_query_parameter
from ..items import UfcPassItem
from ..items import UfcPassCardItem
from ..athlete_url import load_alias_map, load_player_pages, load_probe_map
from ..athlete_url import normalize_url as normalize_athlete_page_url
import re
import sqlite3
from ..items import UfcPlayerItem
from urllib.parse import urlparse
from ..birth_place import split_birth_place
from ..textutil import is_blank_text
class EventpassSpider(scrapy.Spider):
    name = "eventpass"
    allowed_domains = ["www.ufc.com","dmxg5wxfqgb4u.cloudfront.net","ufc.com"]
    start_urls = ["https://www.ufc.com/events#events-list-past"]
    # 分页请求 URL：ufc.com 的 Events 列表走普通 URL 分页（页面上的翻页控件就是
    # <a href="?page=N" rel="next">）。实测 past 区块每页 8 条、连续无重叠，
    # page=99 是最后一页，page>=100 起 past 区块取到 0 条 ⇒ 天然的结束信号。
    # 2026-09 之前这里用的是 /views/ajax + 硬编码 view_dom_id/ajax_page_state，
    # 那套 token 是某一次页面快照，站点一部署就失效（现已对任何参数都返回排行榜视图）。
    PAGE_URL_TEMPLATE = "https://www.ufc.com/events?page={page}"

    # 翻页上限，纯粹防御站点异常（正常只需 100 页左右）
    MAX_PAGES = 300

    def __init__(self, pagination=False, normalize_urls="true", *args, **kwargs):
        super().__init__(*args, **kwargs)
        # pagination 参数为 True 时开启全量分页爬取
        # ⚠️ 命令行 -a 传进来的永远是字符串，字符串 "false" 也是 truthy，必须显式转换
        self.pagination = str(pagination).lower() not in ("", "0", "false", "no", "none")
        # 角标主页 URL 归一：把 ufc.com 的别名 slug 换成规范 slug（见 ufcjson/athlete_url.py）
        self.normalize_urls = str(normalize_urls).lower() not in ("0", "false", "no")
        self._url_cache = {}
        self._url_pages = None
        self._url_alias = None
        self._url_probe = None
        # 地点中文字典缓存（懒加载，见 place_cn_dicts）
        self._place_cn_cache = None
        # 统计信息
        self.total_new = 0
        self.total_skipped = 0
        self.total_pages = 0
        # 收集选手页未匹配的 bio label，用于感知页面结构变化（同 AthleteSpider）
        self.unmatched_bio_labels = set()
        # 1. 连接到数据库（如果没有数据库文件，会自动创建）
        self.conn = sqlite3.connect('output/db/ufc.db')
        # 2. 创建游标对象（用于执行SQL语句）
        self.cursor = self.conn.cursor()

    def normalize_athlete_url(self, url):
        """把赛事页角标 href 归一到规范 slug。

        player.page 由 athlete.py 从 /athletes/all 取（规范 slug），而赛事页角标给的是
        站点当下的写法，可能是别名 slug（实测 guram-kutateladze-1 就是张名扬的资料页）。
        两侧不等时 App 的 queryPlayer(page) 精确匹配查不到 → 战卡那格空白。
        归一失败时原样返回，绝不猜。
        """
        if not url or not self.normalize_urls:
            return url
        if url in self._url_cache:
            return self._url_cache[url]
        if self._url_pages is None:
            self._url_pages = load_player_pages(self.conn)
            self._url_alias = load_alias_map(self.conn)
            self._url_probe = load_probe_map(self.conn)
        resolved = normalize_athlete_page_url(
            self.conn, url, online=True, player_pages=self._url_pages,
            alias_map=self._url_alias, probe_cache=self._url_probe
        )
        result = resolved or url
        self._url_cache[url] = result
        return result

    def extract_avatar(self, response):
        """从选手详情页取「本人」的头像 URL；取不到返回空串，并打 warning。

        为什么要判别式：`event_results_athlete_headshot` 这个 class 在页面上同时挂着
        「本人」和「历史对手」的头像（实测 Joshua Van 页 8 张 = Van×4 + Pantoja×2
        + Taira×2），而且红/蓝角不代表本人（Van 在自己页是红角，Taira 在 Van 页是
        蓝角），所以不能直接取第一张。

        主判据用 href 而不是姓名：实测每个头像的最近 <a href> 都是
        `https://www.ufc.com/athlete/<slug>`（绝对、无尾斜杠、无 query）；而按姓名匹配
        不牢靠——库里有 13 个名字带 `Jr.`/`III`（h1 与 alt 逐字不一致就 0 命中）、
        另有 10 组完全同名（会静默取到错人的图）。
        ⚠️ 刻意写成「href 以 /athlete/<slug> 结尾」而不是 contains —— 库里有 20 对
        slug 互为前缀（`lance-gibson`/`lance-gibson-jr`、`joey-gomez`/`joey-gomez-0`…），
        contains 会命中别人的页。

        取不到时**必须留痕**：空值会被 `UfcDefaultPhotoPipeline` 换成
        `no-profile-image.png` 剪影占位图，事后无法区分「这人确实没头像」和
        「选择器被站点改版打挂了」。
        """
        slug = urlparse(response.url).path.rstrip('/').rsplit('/', 1)[-1]
        avatar = response.xpath(
            '//a[substring(@href, string-length(@href) - string-length($s) + 1) = $s]'
            '//img[contains(@class, "athlete-headshot")]/@src',
            s=f'/athlete/{slug}').get(default='')
        if not avatar:                        # 兜底：按 h1 姓名匹配 alt
            name = response.xpath(
                '//h1[@class="hero-profile__name"]/text()').get(default='').strip()
            if name:
                avatar = response.xpath(
                    '//img[@class="image-style-event-results-athlete-headshot"]'
                    '[@alt=$n]/@src', n=name).get(default='')
        if not avatar:
            self.logger.warning(f"[avatar] 未取到头像: {response.url}")
        return avatar

    def closed(self, reason):
        # 未匹配的 bio label 是选手页结构变化的唯一信号，收集了必须打出来，否则没人看
        if self.unmatched_bio_labels:
            self.logger.warning(
                f"发现 {len(self.unmatched_bio_labels)} 个未匹配的 bio label: "
                f"{sorted(self.unmatched_bio_labels)}"
            )
        if self.conn:
            self.conn.close()
        self.logger.info(
            f"爬取结束，共翻页 {self.total_pages} 次，新增赛事 {self.total_new} 场，跳过 {self.total_skipped} 场"
        )

    def parse(self, response):
        """解析赛事列表页（普通页面 URL，靠 ?page=N 翻页）"""
        self.logger.info(f"请求地址: {response.url}")
        # 只认 past 区块，不做整页兜底：?page=N 翻的是 upcoming+past 合并视图，
        # 整页取 l-listing__item 会把未来赛事当成已打完的赛事混进来。
        info = response.xpath('//*[@id="events-list-past"]/div/div/div[2]/div/div/div')
        current_page = int(url_query_parameter(response.url, 'page', default='0'))
        self.logger.info(f"获取到 {len(info)} 个比赛事件")

        if len(info) == 0:
            if current_page == 0:
                self.logger.error(
                    "第一页就没取到赛事：ufc.com 的 events-list-past 区块结构可能变了，请检查选择器"
                )
            else:
                self.logger.info("已到达最后一页，停止分页爬取")
            return

        new_count = 0
        skip_count = 0
        for i in info:
            item = UfcPassItem()
            item['title']=i.xpath('.//h3[@class="c-card-event--result__headline"]/a/text()').get(default='').strip()
            item['name']=i.xpath('.//h3[@class="c-card-event--result__headline"]/a/@href').get(default='').strip().strip('/').split('/')[-1]
            item['url']='https://www.ufc.com'+ i.xpath('.//h3[@class="c-card-event--result__headline"]/a/@href').get(default='').strip()
            self.cursor.execute("SELECT * FROM pass_event WHERE page = ?", (item['url'],))
            results = self.cursor.fetchall()
            if len(results)>0:
                self.logger.info(f"{item['title']} 已存在数据库，跳过")
                skip_count += 1
                continue
            item['main_time']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-main-card-timestamp').get(default='').strip()
            item['prelims_time']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-prelims-card-timestamp').get(default='').strip()
            item['data_early_time']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-early-card-timestamp').get(default='').strip()
            address=i.xpath('.//p[@class="address"]/span/text()').extract()
            item['address']=",".join(map(str,address))
            item['city'], item['country'] = self.parse_address(item['address'])
            self.logger.info(f"准备抓取详情: {item['title']} - {item['url']}")
            new_count += 1
            yield scrapy.Request(url=item['url'], callback=self.parse_detail, meta={'item': item})

        # 每页汇总
        self.total_new += new_count
        self.total_skipped += skip_count
        if self.pagination:
            self.logger.info(
                f"第 {current_page} 页完成: 新增 {new_count} 场, 跳过 {skip_count} 场"
            )

        # 开启分页模式时继续请求下一页
        if self.pagination:
            next_page = current_page + 1
            self.total_pages = next_page
            if next_page > self.MAX_PAGES:
                self.logger.warning(f"翻页已达上限 {self.MAX_PAGES} 页，强制停止（正常只需 100 页左右）")
                return
            self.logger.info(f"请求第 {next_page} 页数据")
            yield scrapy.Request(
                url=self.PAGE_URL_TEMPLATE.format(page=next_page),
                callback=self.parse,
            )

    @staticmethod
    def parse_address(address):
        """把 ufc.com 的地点串拆成 (city, country)。
        形态：City,Country / City,State,Country / 场馆,City,State,Country（巴西页）
             / 'Macao' / 'Macao SAR China' / 只有国家（如 'Brazil'）。"""
        a = (address or '').strip()
        if not a:
            return '', ''
        if a == 'Macao':
            return 'Macao', 'Macao'
        if a == 'Macao SAR China':
            return 'Macao', 'Macao SAR China'
        segs = [s.strip() for s in a.split(',') if s.strip()]
        if len(segs) == 1:
            return '', segs[0]
        if len(segs) == 2:
            return segs[0], segs[1]
        if len(segs) == 3:
            return segs[0], segs[2]
        if len(segs) == 4:
            return segs[1], segs[3]
        return segs[0], segs[-1]

    def parse_detail(self, response):
        # 接收结构化数据
        item = response.meta['item']
        self.logger.info(f"抓取比赛详情: {item['name']} - {response.url}")
        item['banner']=response.xpath('//*[@class="c-hero__image"]//img/@src').get(default='').strip()
        info =response.xpath('//*[@class="l-listing__group--bordered"]')
        fight_cards=[]
        for index,i in enumerate(info) :
            card="Main"
            if index==1:
               card="Prelims"
            if index==2:
                card="EarlyPrelims"
            card_elements=i.xpath('./li')
            for d in card_elements:
                # 空壳战卡过滤：ufc.com 渲染缺陷——个别卡的两个角指向同一个链接
                # （实测是 /node/1037xx，且名字 span 为空、图为剪影占位，结果/回合/时间也全空）。
                # 这类卡不是真实比赛，直接跳过不入库。
                # 判据"两侧 href 相同"全库实测零误伤（恰好命中 6 行，见 2026-09-17 备忘）。
                red_href = d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//a/@href').get(default='').strip()
                blue_href = d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//a/@href').get(default='').strip()
                if red_href and red_href == blue_href:
                    self.logger.info(f"跳过空壳战卡（两侧同一链接）: {red_href}")
                    continue
 
                card_item = UfcPassCardItem()
                fight_cards.append(card_item)
                card_item['fight_page']=response.url
                card_item['card_type']=card
                card_item['card_division']=d.xpath('.//div[@class="c-listing-fight__class-text"]/text()').get(default='').strip()
                card_item['end_round']=d.xpath('.//div[@class="c-listing-fight__result-text round"]/text()').get(default='').strip()
                card_item['end_time']=d.xpath('.//div[@class="c-listing-fight__result-text time"]/text()').get(default='').strip()
                card_item['end_method']=d.xpath('.//div[@class="c-listing-fight__result-text method"]/text()').get(default='').strip()

                card_item['red_page']=red_href
                card_item['red_page']=self.normalize_athlete_url(card_item['red_page'])
                card_item['red_result'] = d.xpath('.//div[@class="c-listing-fight__corner-body--red"]/div/div/text()').get(default='').strip()
                card_item['red_result'] = card_item['red_result'].replace(" ", "").replace('\n', '')

                card_item['blue_page'] = blue_href
                card_item['blue_page'] = self.normalize_athlete_url(card_item['blue_page'])
                card_item['blue_result'] = d.xpath('.//div[@class="c-listing-fight__corner-body--blue"]/div/div/text()').get(default='').strip()
                card_item['blue_result'] = card_item['blue_result'].replace(" ", "").replace('\n', '')
                odds = d.xpath('.//div[@class="c-listing-fight__odds-wrapper"]//span[@class="c-listing-fight__odds-amount"]/text()').getall()
                card_item['red_odds'], card_item['blue_odds'] = (odds + ["", ""])[:2]
                yield card_item
                # 空串/None 不能直接交给 scrapy.Request（抛 ValueError: Missing scheme）：
                # 上面那句空壳过滤只挡「两侧 href 相等」，漏掉「只有一侧没有 <a>」的卡。
                # 更麻烦的是生成器会整体中断 ⇒ item 不 yield ⇒ pass_event 写不进去
                # ⇒ 下次把这场当新赛事重抓、再崩，单场赛事永久卡死。
                # 这里只决定「要不要抓选手详情」，卡本身照常入库。
                for page in (card_item['red_page'], card_item['blue_page']):
                    if page:
                        yield scrapy.Request(url=page, callback=self.parse_fighter)
        item['fight_cards']=fight_cards
        yield item

    def parse_fighter(self, response):
        player=UfcPlayerItem()
        self.logger.info(f"抓取选手详情页面: {response.url}")
        # 选手名取自详情页 h1（与 extract_avatar 兜底分支用的是同一个 class）
        player['name'] = response.xpath(
            '//h1[@class="hero-profile__name"]/text()').get(default='').strip()
        # 昵称：页面上是 <p class="hero-profile__nickname">"The Fearless"</p>，原文自带引号
        nick = response.xpath(
            '//p[@class="hero-profile__nickname"]/text()').get(default='').strip()
        # 剥离首尾各类引号（英文双引号、中文双引号、英文单引号、中文单引号）
        player['nick_name'] = re.sub(r'^[\'\"""]+|[\'\"""]+$', '', nick).strip()
        player['avatar'] = self.extract_avatar(response)
        # 接收结构化数据//field field--name-qna-ufc field--type-text-long field--label-hidden field__item
        #//*[@id="tab-panel-3"]/div/div
        player['page']=response.url
        # 取所有文本节点，避免 <li>、<strong> 等标签内容丢失
        player['history'] = [t.strip() for t in response.xpath('//*[@id="tab-panel-3"]/div/div//text()').getall() if not is_blank_text(t)]
        bios_list = response.xpath('//div[@class="c-bio__info-details"]/div/div')
        for b in bios_list:
            text_nodes = [t.strip() for t in b.xpath('.//div/text()').getall() if t.strip()]
            if len(text_nodes) < 2:
                self.logger.warning(f"bio 项文本节点不足，跳过: {text_nodes}")
                continue
            label = text_nodes[0]
            # age 字段已废弃：页面上的 Age 是抓取当天的快照，实测 61% 的行与真实年龄
            if label == 'Age':
                continue
            value = text_nodes[1]
            field = {
                    'Status': 'status',
                    'Reach': 'reach',
                    'Height': 'height',
                    'Place of Birth': 'home_town',
                    'Trains at': 'team',
                    'Fighting style': 'style',
                    'Leg reach': 'leg_reach',
                    'Octagon Debut': 'debut',
                    'Weight': 'weight',
                }.get(label)
            if field:
                player[field] = value
            else:
                self.unmatched_bio_labels.add(label)
        # 无条件赋值：本入口没有「列表页的值」可保护，而 SqliteDbPipeline 的 INSERT 分支
        # 用的是硬下标 item['division']，不赋值就会 KeyError（只在新选手分支炸）。
        # 「空值不覆盖老值」的逻辑在管道的 UPDATE 分支里（if new:），不在这里。
        player['division'] = response.xpath(
            '//p[@class="hero-profile__division-title"]/text()').get(default='').strip()
        detail_record = response.xpath('//p[@class="hero-profile__division-body"]/text()').get(default='').strip()
        if detail_record:
            player['record'] = detail_record
        player['player_tags']=response.xpath('//div[@class="hero-profile__tags"]/p/text()').extract()
        player['player_tags']=[ i.strip() for i in player['player_tags'] ]
        stats_list = response.xpath('//div[@class="hero-profile__stat"]')
        player['wins_stats'] = []
        for stat in stats_list:
            player['wins_stats'].append({
                'way': stat.xpath('.//p[@class="hero-profile__stat-text"]/text()').get(default='').strip(),
                'times': stat.xpath('.//p[@class="hero-profile__stat-numb"]/text()').get(default='').strip(),
            })
        player['cover']=response.xpath('//img[@class="hero-profile__image"]/@src').get(default='').strip()
        # 将出生地拆分为 城市/国家，供筛选、国旗和中文翻译使用（home_town 保留原始值）
        player['city'], player['country'] = split_birth_place(player.get('home_town'))
        self.logger.info(f"抓取完成选手: {player['name']}，共 {len(player['history'])} 条历史记录，{len(player['wins_stats'])} 条胜场统计")
        yield player

   