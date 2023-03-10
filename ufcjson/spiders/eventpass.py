import scrapy
from ..items import UfcPassItem
from ..items import UfcPassCardItem
class EventpassSpider(scrapy.Spider):
    name = "eventpass"
    allowed_domains = ["www.ufc.com"]
    start_urls = ["https://www.ufc.com/events#events-list-past"]

    def parse(self, response):
        info = response.xpath('//*[@id="events-list-past"]//li//article[@class="c-card-event--result"]')
        #info==info[0:1]
        for i in info:
            item = UfcPassItem()  
            #title=i.xpath('.//div[@class="fight-card-tickets"]/@data-fight-label').extract_first()
            item['title']=i.xpath('.//h3[@class="c-card-event--result__headline"]/a/text()').extract_first()
            item['url']='https://www.ufc.com'+ i.xpath('.//h3[@class="c-card-event--result__headline"]/a/@href').extract_first()
            item['mainCardTimestamp']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-main-card-timestamp').extract_first()
            item['prelimsCardTimestamp']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-prelims-card-timestamp').extract_first()
            item['dataEarlyCardTimestamp']=i.xpath('.//div[@class="c-card-event--result__date tz-change-data"]/@data-early-card-timestamp').extract_first()
            photo=i.xpath('.//div[@class="field field--name-image field--type-entity-reference field--label-hidden field__item"]//img/@src').extract()
            item['redPlayerCover']=photo[0]
            item['bluePlayerCover']=photo[1]
            address=i.xpath('.//p[@class="address"]/span/text()').extract()
            item['address']=",".join(map(str,address))
            #yield item
            print("title:",item['title'])
            yield scrapy.Request(url=item['url'], callback=self.parse_detail,meta={'item': item})  # 将请求传递给调度器，重新请求
       
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
                itemd['cardType']=card
                itemd['weightClass']=d.xpath('.//div[@class="c-listing-fight__class-text"]/text()').extract_first()
                itemd['endRound']=d.xpath('.//div[@class="c-listing-fight__result-text round"]/text()').extract_first()
                itemd['endTime']=d.xpath('.//div[@class="c-listing-fight__result-text time"]/text()').extract_first()
                itemd['endMethod']=d.xpath('.//div[@class="c-listing-fight__result-text method"]/text()').extract_first()

                itemd['redPlayerPage']=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//a/@href').extract_first()
                redPlayerName=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//span/text()').extract()
                redPlayerName=" ".join(map(str,redPlayerName))
                if len(redPlayerName)==0:
                   redPlayerName=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--red"]//a/text()').extract_first()    
                itemd['redPlayerName']=redPlayerName.replace('\n','').replace(' ','') 
                
                itemd['redPlayerCountry']=d.xpath('.//div[@class="c-listing-fight__country c-listing-fight__country--red"]//div[@class="c-listing-fight__country-text"]/text()').extract_first()
                itemd['redPlayerResult']=d.xpath('.//div[@class="c-listing-fight__corner-body--red"]/div/div/text()').extract_first()
                itemd['redPlayerBack']=d.xpath('.//div[@class="c-listing-fight__corner--red"]//img/@src').extract_first()
                itemd['redPlayerCountryCode']=d.xpath('.//div[@class="c-listing-fight__country c-listing-fight__country--red"]/img/@src').extract_first()

                itemd['bluePlayerPage']=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//a/@href').extract_first()
                bluePlayerName=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//span/text()').extract()
                bluePlayerName=" ".join(map(str,bluePlayerName))
               
                if  len(bluePlayerName)==0:
                    bluePlayerName=d.xpath('.//div[@class="c-listing-fight__corner-name c-listing-fight__corner-name--blue"]//a/text()').extract_first()

                itemd['bluePlayerName']=bluePlayerName.replace('\n','').replace(' ','') 
                itemd['bluePlayerCountry']=d.xpath('.//div[@class="c-listing-fight__country c-listing-fight__country--blue"]//div[@class="c-listing-fight__country-text"]/text()').extract_first()
                itemd['bluePlayerResult']=d.xpath('.//div[@class="c-listing-fight__corner-body--blue"]/div/div/text()').extract_first()
                itemd['bluePlayerBack']=d.xpath('.//div[@class="c-listing-fight__corner--blue"]//img/@src').extract_first()
                itemd['bluePlayerCountryCode']=d.xpath('.//div[@class="c-listing-fight__country c-listing-fight__country--blue"]/img/@src').extract_first()

                odds=d.xpath('.//div[@class="c-listing-fight__odds-wrapper"]//span[@class="c-listing-fight__odds-amount"]/text()').extract()
                if len(odds)==2:
                    itemd['redPlayerOdds']=odds[0]
                    itemd['bluePlayerOdds']=odds[1]
                yield itemd   
        item['fightCards']=all
        yield item

