import scrapy
from ..items import UfcComingItem
from ..items import UfcComingCardItem

class UpcomingSpider(scrapy.Spider):
    name = "upcoming"
    allowed_domains = ["www.ufc.com","dmxg5wxfqgb4u.cloudfront.net","ufc.com"]
    start_urls = ["https://www.ufc.com/events#events-list-upcoming"]

    def parse(self, response):
        info = response.xpath('//*[@id="events-list-upcoming"]//div[@class="l-listing__item views-row"]')
        self.logger.info(f"抓取到 {len(info)} 个即将发生的比赛事件")
        #print('dapeng',len(info))
        #截取第一个战卡
        #info=info[0:1]
        for i in info:
            # print("info",i)
            item =UfcComingItem()
            item['title']=i.xpath('.//h3[@class="c-card-event--result__headline"]/a/text()').get(default='').strip()
            self.logger.info(f"抓取到比赛标题: "+item['title'])
            item['page']='https://www.ufc.com'+ i.xpath('.//h3[@class="c-card-event--result__headline"]/a/@href').get(default='').strip()
            item['main_time']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-main-card-timestamp').get(default='').strip()
            item['prelims_time']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-prelims-card-timestamp').get(default='').strip()
            item['data_early_time']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-early-card-timestamp').get(default='').strip()
            address_list = i.xpath('.//p[@class="address"]/span/text()').getall()
            item['address'] = ", ".join(filter(None, map(str.strip, address_list)))
            # 将请求传递给调度器，重新请求
            self.logger.info(f"准备抓取比赛详情: {item['title']} - {item['address']} - {item['page']}")
            yield scrapy.Request(url=item['page'], callback=self.parse_detail,meta={'item': item})
            
    def parse_detail(self, response):
        # 接收结构化数据
        item = response.meta['item']
        item['banner']=response.xpath('//*[@class="c-hero__image"]//img/@src').get(default='').strip()
        if item['banner'] is not None and not item['banner'].startswith("http"):
            item['banner']=None
        item['name']=response.xpath('//*[@class="c-hero__headline-prefix"]//h1/text()').get(default='').strip().replace('\n','').replace(' ','')
        info =response.xpath('//*[@class="l-listing__group--bordered"]')
        fight_cards=[]
        item['fight_card']=fight_cards
        for index,i in enumerate(info) :
            cardType="Main"
            if index==1:
               cardType="Prelims"
            if index==2:
                cardType="EarlyPrelims"
            card_elements=i.xpath('./li')
            for index,d in enumerate(card_elements):
                card_item = UfcComingCardItem()
                fight_cards.append(card_item)
                card_item['card_type']=cardType
                card_item['main_time']=item['main_time']
                card_item['address']=item['address']
                card_item['fight_name']=item['name']
                card_item['card_division']=d.xpath('.//div[@class="c-listing-fight__class-text"]/text()').get(default='').strip()
                card_item['red_page']=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//a/@href').get(default='').strip()
                card_item['blue_page']=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//a/@href').get(default='').strip()
                odds = d.xpath('.//div[@class="c-listing-fight__odds-wrapper"]//span[@class="c-listing-fight__odds-amount"]/text()').getall()
                card_item['red_odds'], card_item['blue_odds'] = (odds + ["", ""])[:2]
                rank=d.xpath('.//div[@class="c-listing-fight__ranks-row"]/div')
                if len(rank)==2:
                    card_item['red_rank']=rank[0].xpath('./span/text()').get(default='').strip()
                    card_item['blue_rank']=rank[1].xpath('./span/text()').get(default='').strip()

                card_item['fight_id']=d.xpath('.//div[@class="c-listing-fight"]/@data-fmid').get(default='').strip()
                self.logger.info(f"抓取到的战卡: {card_item['fight_name']} {card_item['red_page']} VS {card_item['blue_page']} - {card_item['card_type']} - {card_item['card_division']}")
                yield card_item
        self.logger.info(f"完成抓取比赛: {item['name']}，共 {len(fight_cards)} 个战卡分组")
        yield item
