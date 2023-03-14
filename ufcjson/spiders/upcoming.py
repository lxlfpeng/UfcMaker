import scrapy
from ..items import UfcComingItem
from ..items import UfcComingCardItem
from ..items import UfcComingBannerItem
import json
class UpcomingSpider(scrapy.Spider):
    name = "upcoming"
    allowed_domains = ["www.ufc.com"]
    start_urls = ["https://www.ufc.com/events#events-list-upcoming"]

    def parse(self, response):
        info = response.xpath('//*[@id="events-list-upcoming"]//li[@class="l-listing__item"]')
        #info=info[0:1]
        for i in info:
            item =UfcComingItem()
            item['title']=i.xpath('.//h3[@class="c-card-event--result__headline"]/a/text()').extract_first()
            item['url']='https://www.ufc.com'+ i.xpath('.//h3[@class="c-card-event--result__headline"]/a/@href').extract_first()
            item['mainCardTimestamp']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-main-card-timestamp').extract_first()
            item['prelimsCardTimestamp']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-prelims-card-timestamp').extract_first()
            item['dataEarlyCardTimestamp']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-early-card-timestamp').extract_first()
            address=i.xpath('.//p[@class="address"]/span/text()').extract()
            item['address']=",".join(map(str,address))
            covers=i.xpath('.//div[@class="c-carousel__item"]')
            gameScheduleBanner=[]
            item['bannerItem']=gameScheduleBanner
            for cover in covers:
                bannerItem=UfcComingBannerItem()
                gameScheduleBanner.append(bannerItem)
                bannerItem['fightLable']=cover.xpath('.//div[@class="fight-card-tickets"]/@data-fight-label').extract_first()
                bannerItem['redPlayerCover']=cover.xpath('.//img/@src').extract()[0]
                bannerItem['bluePlayerCover']=cover.xpath('.//img/@src').extract()[1]
                yield bannerItem 
            
            yield scrapy.Request(url=item['url'], callback=self.parse_detail,meta={'item': item})  # 将请求传递给调度器，重新请求
            
    def parse_detail(self, response):
        # 接收结构化数据
        item = response.meta['item']
        item['banner']=response.xpath('//*[@class="c-hero__image"]//img/@src').extract_first()
        item['fightName']=response.xpath('//*[@class="c-hero__headline-prefix"]//h1/text()').extract_first().replace('\n','').replace(' ','')
        item['matchupID']=response.xpath('.//div[@class="c-listing-ticker--footer"]/@data-fmid').extract_first()
        #print('matchupID==>',item['matchupID'])
        info =response.xpath('//*[@class="l-listing__group--bordered"]')
        all=[]
        item['fightCards']=all
        for index,i in enumerate(info) : 
            cardType="Main"
            if index==1:
               cardType="Prelims" 
            if index==2:
                cardType="EarlyPrelims"
            infoD=i.xpath('./li')
            for index,d in enumerate(infoD):
                itemd = UfcComingCardItem()
                all.append(itemd)
                itemd['cardType']=cardType
                itemd['weightClass']=d.xpath('.//div[@class="c-listing-fight__class-text"]/text()').extract_first()
                itemd['redPlayerPage']=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//a/@href').extract_first()
                redPlayerName=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//a/text()').extract_first().replace('\n','').replace(' ','')
                if len(redPlayerName)==0:
                    redPlayerName=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//span/text()').extract()
                    redPlayerName=" ".join(map(str,redPlayerName))
                itemd['redPlayerName']=redPlayerName
                itemd['redPlayerCountry']=d.xpath('.//div[@class="c-listing-fight__country c-listing-fight__country--red"]//div[@class="c-listing-fight__country-text"]/text()').extract_first()
                itemd['redPlayerBack']=d.xpath('.//div[@class="c-listing-fight__corner--red"]//img/@src').extract_first()
                itemd['redPlayerCountryCode']=d.xpath('.//div[@class="c-listing-fight__country c-listing-fight__country--red"]/img/@src').extract_first()

                itemd['bluePlayerPage']=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//a/@href').extract_first()
                bluePlayerName=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//a/text()').extract_first().replace('\n','').replace(' ','')
                if len(bluePlayerName)==0:
                    bluePlayerName=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//span/text()').extract()
                    bluePlayerName=" ".join(map(str,bluePlayerName))
                itemd['bluePlayerName']=bluePlayerName
                itemd['bluePlayerCountry']=d.xpath('.//div[@class="c-listing-fight__country c-listing-fight__country--blue"]//div[@class="c-listing-fight__country-text"]/text()').extract_first()
                itemd['bluePlayerBack']=d.xpath('.//div[@class="c-listing-fight__corner--blue"]//img/@src').extract_first()
                itemd['bluePlayerCountryCode']=d.xpath('.//div[@class="c-listing-fight__country c-listing-fight__country--blue"]/img/@src').extract_first()

                odds=d.xpath('.//div[@class="c-listing-fight__odds-wrapper"]//span[@class="c-listing-fight__odds-amount"]/text()').extract()
                if len(odds)==2:
                    itemd['redPlayerOdds']=odds[0]
                    itemd['bluePlayerOdds']=odds[1]
                rank=d.xpath('.//div[@class="c-listing-fight__ranks-row"]/div')
                if len(rank)==2:
                    itemd['redPlayerRank']=rank[0].xpath('./span/text()').extract_first() 
                    itemd['bluePlayerRank']=rank[1].xpath('./span/text()').extract_first()

                itemd['fightId']=d.xpath('.//div[@class="c-listing-fight"]/@data-fmid').extract_first()
                print('fightId:',itemd['fightId'])               
                yield itemd    
        matchup_url='https://d29dxerjsp82wz.cloudfront.net/api/v3/event/live/'+item['matchupID']+'.json'
        yield scrapy.Request(url=matchup_url, callback=self.parse_matchup,errback=lambda failure, item=item: self.on_error(failure, item),meta={'item': item},dont_filter=True)

    def parse_matchup(self, response):
        item = response.meta['item']
        rs =  json.loads(response.text)
        cards={str(i['FightId']): i for i in rs['LiveEventDetail']['FightCard']}
        for i in item['fightCards']:
            print('fightId:',i['fightId'])
            if i['fightId'] is not None and i['fightId'] in cards:
                i['matchupStats']=cards[i['fightId']]
        yield item

    def on_error(self, failure, item):
        yield item           
