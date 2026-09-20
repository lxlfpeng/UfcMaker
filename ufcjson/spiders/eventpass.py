import scrapy
from w3lib.url import url_query_parameter
from ..items import UfcPassItem
from ..items import UfcPassCardItem
from ..athlete_url import load_alias_map, load_player_pages, load_probe_map
from ..athlete_url import normalize_url as normalize_athlete_page_url
import sqlite3

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
        # 统计信息
        self.total_new = 0
        self.total_skipped = 0
        self.total_pages = 0
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

    def closed(self, reason):
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
        item['fight_cards']=fight_cards
        yield item

