import json

import scrapy
from w3lib.url import url_query_parameter
from ..items import UfcPassItem
from ..items import UfcPassCardItem
from scrapy.http import HtmlResponse
import sqlite3

class EventpassSpider(scrapy.Spider):
    name = "eventpass"
    allowed_domains = ["www.ufc.com","dmxg5wxfqgb4u.cloudfront.net"]
    start_urls = ["https://www.ufc.com/events#events-list-past"]

    # AJAX 分页请求 URL 模板
    AJAX_URL_TEMPLATE = (
        "https://www.ufc.com/views/ajax?"
        "view_name=events_upcoming_past"
        "&view_display_id=past"
        "&view_args="
        "&view_path=%2Fevents"
        "&view_base_path="
        "&view_dom_id=b02e3f39797a47a6c0fc51ed4c374e76674ea6419ce0018d933c1aec5146d291"
        "&pager_element=0"
        "&page={page}"
        "&ajax_page_state%5Btheme%5D=ufc"
        "&ajax_page_state%5Btheme_token%5D="
        "&ajax_page_state%5Blibraries%5D=eJx1kQFyhCAMRS8Ey0V6ByZCVLZZ4pDg1p6-FHS6005nHP3_RfEngRiVIR8OTnGbC2c1E4R3r9yuzb1of5d_S4ofauKObk8R2cwJKfqlcN0cEj4w623lkj7b8UBeYRKzMC-EHjLQoSmI-w0MwcFVfUwSeMdyOM4YmMzGRC6WugHdvrWllN_FyCGKjxZL0NQ5uKmqcpauA5RoQ_t7S2JnZsXyw3Fv9LJcBambOVF7zTaLYZQX4gnIBpFXex9uxcJD8NMq2ydoWF_O_ottH1AvpmwhaOLcXe_HxsJb5OdAbYTVPiANt8EyepQ27gmKnVMRPYnia4fdrwjx9H32TfgeQdx4vKXxuZ_TsuoGIg6q9pXBFcsTB6ATuILLxY-2fCcIJay-hTF7wqe4fr89OFbCgTzc4cMvqO4SJ095Trnl9BLK9247tRe1g34BunMJCA"
    )

    def __init__(self, pagination=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # pagination 参数为 True 时开启全量分页爬取
        self.pagination = pagination
        # 统计信息
        self.total_new = 0
        self.total_skipped = 0
        self.total_pages = 0
        # 1. 连接到数据库（如果没有数据库文件，会自动创建）
        self.conn = sqlite3.connect('output/db/ufc.db')
        # 2. 创建游标对象（用于执行SQL语句）
        self.cursor = self.conn.cursor()

    def closed(self, reason):
        if self.conn:
            self.conn.close()
        self.logger.info(
            f"爬取结束，共翻页 {self.total_pages} 次，新增赛事 {self.total_new} 场，跳过 {self.total_skipped} 场"
        )

    def parse(self, response):
        """解析赛事列表页面（首页或AJAX返回的HTML片段）"""
        self.logger.info(f"请求地址: {response.url}")
        info = response.xpath('//*[@id="events-list-past"]/div/div/div[2]/div/div/div')
        if len(info) == 0:
            # AJAX 返回的 HTML 片段没有 events-list-past 包裹层，直接取 item
            info = response.xpath('//div[contains(@class, "l-listing__item") and contains(@class, "views-row")]')
        self.logger.info(f"获取到 {len(info)} 个比赛事件")

        if len(info) == 0:
            # 没有数据了，到达最后一页
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
        current_page = int(url_query_parameter(response.url, 'page', default='0'))
        if self.pagination:
            self.logger.info(
                f"第 {current_page} 页完成: 新增 {new_count} 场, 跳过 {skip_count} 场"
            )

        # 开启分页模式时继续请求下一页
        if self.pagination and len(info) > 0:
            next_page = current_page + 1
            self.total_pages = next_page
            self.logger.info(f"请求第 {next_page} 页数据")
            ajax_url = self.AJAX_URL_TEMPLATE.format(page=next_page)
            yield scrapy.Request(
                url=ajax_url,
                callback=self.parse_ajax_page,
                headers={
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'X-Requested-With': 'XMLHttpRequest',
                },
            )

    def parse_ajax_page(self, response):
        """解析 AJAX 分页返回的 JSON 数据，提取 HTML 后复用 parse 逻辑"""
        try:
            data = json.loads(response.text)
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"解析 AJAX 响应失败 ({e}): {response.url}")
            return

        # Drupal Views AJAX 返回的是一个数组，找到包含 HTML 内容的项
        html_content = None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get('command') == 'insert':
                    html_content = item.get('data', '')
                    break
                elif isinstance(item, dict) and 'data' in item and isinstance(item['data'], str):
                    html_content = item['data']
                    break

        if html_content is None:
            self.logger.warning(f"未从 AJAX 响应中找到 HTML 内容，可能已到达最后一页: {response.url}")
            return

        # 构造一个 HtmlResponse 复用 parse 逻辑
        ajax_response = HtmlResponse(
            url=response.url,
            body=html_content,
            encoding='utf-8',
            request=response.request,
        )
        yield from self.parse(ajax_response)

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
                card_item = UfcPassCardItem()
                fight_cards.append(card_item)
                card_item['fight_page']=response.url
                card_item['card_type']=card
                card_item['card_division']=d.xpath('.//div[@class="c-listing-fight__class-text"]/text()').get(default='').strip()
                card_item['end_round']=d.xpath('.//div[@class="c-listing-fight__result-text round"]/text()').get(default='').strip()
                card_item['end_time']=d.xpath('.//div[@class="c-listing-fight__result-text time"]/text()').get(default='').strip()
                card_item['end_method']=d.xpath('.//div[@class="c-listing-fight__result-text method"]/text()').get(default='').strip()

                card_item['red_page']=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//a/@href').get(default='').strip()
                card_item['red_result'] = d.xpath('.//div[@class="c-listing-fight__corner-body--red"]/div/div/text()').get(default='').strip()
                card_item['red_result'] = card_item['red_result'].replace(" ", "").replace('\n', '')

                card_item['blue_page'] = d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//a/@href').get(default='').strip()
                card_item['blue_result'] = d.xpath('.//div[@class="c-listing-fight__corner-body--blue"]/div/div/text()').get(default='').strip()
                card_item['blue_result'] = card_item['blue_result'].replace(" ", "").replace('\n', '')
                odds = d.xpath('.//div[@class="c-listing-fight__odds-wrapper"]//span[@class="c-listing-fight__odds-amount"]/text()').getall()
                card_item['red_odds'], card_item['blue_odds'] = (odds + ["", ""])[:2]
                yield card_item
        item['fight_cards']=fight_cards
        yield item

