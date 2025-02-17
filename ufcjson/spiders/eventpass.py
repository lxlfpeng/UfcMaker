import json

import scrapy
from ..items import UfcPassItem
from ..items import UfcPassCardItem
from scrapy.http import HtmlResponse
import sqlite3

class EventpassSpider(scrapy.Spider):
    name = "eventpass"
    allowed_domains = ["www.ufc.com","dmxg5wxfqgb4u.cloudfront.net"]
    start_urls = ["https://www.ufc.com/views/ajax?view_name=events_upcoming_past&view_display_id=past&view_args=&view_path=%2Fevents&view_base_path=&view_dom_id=b02e3f39797a47a6c0fc51ed4c374e76674ea6419ce0018d933c1aec5146d291&pager_element=0&page=0&ajax_page_state%5Btheme%5D=ufc&ajax_page_state%5Btheme_token%5D=&ajax_page_state%5Blibraries%5D=eJx1kQFyhCAMRS8Ey0V6ByZCVLZZ4pDg1p6-FHS6005nHP3_RfEngRiVIR8OTnGbC2c1E4R3r9yuzb1of5d_S4ofauKObk8R2cwJKfqlcN0cEj4w623lkj7b8UBeYRKzMC-EHjLQoSmI-w0MwcFVfUwSeMdyOM4YmMzGRC6WugHdvrWllN_FyCGKjxZL0NQ5uKmqcpauA5RoQ_t7S2JnZsXyw3Fv9LJcBambOVF7zTaLYZQX4gnIBpFXex9uxcJD8NMq2ydoWF_O_ottH1AvpmwhaOLcXe_HxsJb5OdAbYTVPiANt8EyepQ27gmKnVMRPYnia4fdrwjx9H32TfgeQdx4vKXxuZ_TsuoGIg6q9pXBFcsTB6ATuILLxY-2fCcIJay-hTF7wqe4fr89OFbCgTzc4cMvqO4SJ095Trnl9BLK9247tRe1g34BunMJCA"]
    def __init__(self, category=None):
        self.page=0
        self.category=category
        # 1. 连接到数据库（如果没有数据库文件，会自动创建）
        self.conn = sqlite3.connect('ufc.db')
        # 2. 创建游标对象（用于执行SQL语句）
        self.cursor = self.conn.cursor()

    # def start_requests(self):
    #     if self.category is None:
    #         yield scrapy.Request( "https://www.ufc.com/events#events-list-past", self.parse)
    def close_spider(self, spider):
        if self.conn:
            self.conn.close()
    def parse(self, response):
        print("请求地址:",response.url)
        #response.body 是 JSON 格式的数据
        json_data = json.loads(response.xpath('//textarea/text()').get())  # 将 response.body 转换为字典
        # 获取 data 字段
        data_field = json_data[2].get('data',None)
        if len(data_field)==0:
            data_field = json_data[1].get('data')
        #创建 HtmlResponse 对象
        response = HtmlResponse(url=response.url, body=data_field.encode('utf-8'), encoding='utf-8')
        info = response.xpath('//article[@class="c-card-event--result"]')
        print("获取到的数据个数", len(info))
        for i in info:
            item = UfcPassItem()
            item['title']=i.xpath('.//h3[@class="c-card-event--result__headline"]/a/text()').extract_first()
            item['name']=i.xpath('.//h3[@class="c-card-event--result__headline"]/a/@href').extract_first().strip('/').split('/')[-1]
            item['url']='https://www.ufc.com'+ i.xpath('.//h3[@class="c-card-event--result__headline"]/a/@href').extract_first()
            self.cursor.execute("SELECT * FROM pass_event WHERE page = ?", (item['url'],))
            results = self.cursor.fetchall()
            if len(results)>0:
                print("已存在无需再请求数据")
                continue
            item['main_time']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-main-card-timestamp').extract_first()
            item['prelims_time']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-prelims-card-timestamp').extract_first()
            item['data_early_time']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-early-card-timestamp').extract_first()
            address=i.xpath('.//p[@class="address"]/span/text()').extract()
            item['address']=",".join(map(str,address))
            yield scrapy.Request(url=item['url'], callback=self.parse_detail,meta={'item': item})  # 将请求传递给调度器，重新请求
        if self.category is not None and len(info)>0:
            print("开始全量分页爬取")
            self.page+=1
            yield scrapy.Request(url=f'https://www.ufc.com/views/ajax?view_name=events_upcoming_past&view_display_id=past&view_args=&view_path=%2Fevents&view_base_path=&view_dom_id=b02e3f39797a47a6c0fc51ed4c374e76674ea6419ce0018d933c1aec5146d291&pager_element=0&page={self.page}&ajax_page_state%5Btheme%5D=ufc&ajax_page_state%5Btheme_token%5D=&ajax_page_state%5Blibraries%5D=eJx1kQFyhCAMRS8Ey0V6ByZCVLZZ4pDg1p6-FHS6005nHP3_RfEngRiVIR8OTnGbC2c1E4R3r9yuzb1of5d_S4ofauKObk8R2cwJKfqlcN0cEj4w623lkj7b8UBeYRKzMC-EHjLQoSmI-w0MwcFVfUwSeMdyOM4YmMzGRC6WugHdvrWllN_FyCGKjxZL0NQ5uKmqcpauA5RoQ_t7S2JnZsXyw3Fv9LJcBambOVF7zTaLYZQX4gnIBpFXex9uxcJD8NMq2ydoWF_O_ottH1AvpmwhaOLcXe_HxsJb5OdAbYTVPiANt8EyepQ27gmKnVMRPYnia4fdrwjx9H32TfgeQdx4vKXxuZ_TsuoGIg6q9pXBFcsTB6ATuILLxY-2fCcIJay-hTF7wqe4fr89OFbCgTzc4cMvqO4SJ095Trnl9BLK9247tRe1g34BunMJCA',callback=self.parse)
        else:
            print("停止爬取")

    def parse_detail(self, response):
        print("url:",response.url)
        # 接收结构化数据
        item = response.meta['item']
        item['banner']=response.xpath('//*[@class="c-hero__image"]//img/@src').extract_first()
        info =response.xpath('//*[@class="l-listing__group--bordered"]')
        all=[]
        for index,i in enumerate(info) :
            card="Main"
            if index==1:
               card="Prelims"
            if index==2:
                card="EarlyPrelims"
            infoD=i.xpath('./li')
            for d in infoD:
                itemd = UfcPassCardItem()
                all.append(itemd)
                itemd['fight_page']=response.url
                itemd['card_type']=card
                itemd['card_division']=d.xpath('.//div[@class="c-listing-fight__class-text"]/text()').extract_first()
                itemd['end_round']=d.xpath('.//div[@class="c-listing-fight__result-text round"]/text()').extract_first()
                itemd['end_time']=d.xpath('.//div[@class="c-listing-fight__result-text time"]/text()').extract_first()
                itemd['end_method']=d.xpath('.//div[@class="c-listing-fight__result-text method"]/text()').extract_first()

                itemd['red_page']=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//a/@href').extract_first()
                itemd['red_result']=d.xpath('.//div[@class="c-listing-fight__corner-body--red"]/div/div/text()').extract_first()
                if itemd['red_result'] is not None:
                    itemd['red_result'] = itemd['red_result'].replace(" ", "").replace('\n', '')

                itemd['blue_page']=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//a/@href').extract_first()
                itemd['blue_result']=d.xpath('.//div[@class="c-listing-fight__corner-body--blue"]/div/div/text()').extract_first()
                if itemd['blue_result'] is not None:
                    itemd['blue_result']=itemd['blue_result'].replace(" ", "").replace('\n', '')

                odds=d.xpath('.//div[@class="c-listing-fight__odds-wrapper"]//span[@class="c-listing-fight__odds-amount"]/text()').extract()
                if len(odds)==2:
                    itemd['red_odds']=odds[0]
                    itemd['blue_odds']=odds[1]
                yield itemd
        item['fight_cards']=all
        yield item

