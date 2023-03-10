import scrapy
from ..items import UfcRankingPlayer
import os
import json
class AthleteSpider(scrapy.Spider):
    name = "athlete"
    allowed_domains = ["www.ufc.com"]
    #start_urls = ["https://www.ufc.com/athletes/all?page=254"]
    start_urls = ["https://www.ufc.com/athletes/all"]
    def __init__(self):
        self.page=0
        self.old_add={}
        path='./ufc_athlete_data.json'
        if os.path.exists(path):
            print("文件存在")
            with open(path, encoding='utf-8') as a:
                try:
                    data=json.load(a)['data']
                    self.old_add={ i['name']+i['record']: i for i in data }
                except Exception:
                    print("数据读取错误")
                    #os.remove(path)
                    pass     
        else:
            print("文件不存在")

    def parse(self, response):
        items=response.xpath('//div[@class="node node--type-athlete node--view-mode-all-athletes-result ds-1col clearfix"]')
        print("本页请求地址:",response.url)
        print("本页个数:",str(len(items)))
        for item in items:
            player=UfcRankingPlayer()
            player['name']=item.xpath('.//span[@class="c-listing-athlete__name"]/text()').extract_first().strip()
            player['record']=item.xpath('.//span[@class="c-listing-athlete__record"]/text()').extract_first()
            if player['name']+player['record'] in self.old_add.keys():
                print("已存在无需再请求数据")
                old_player=self.old_add[player['name']+player['record']]
                for key in old_player.keys():
                    player[key]=old_player[key]
                yield player
                continue
            player['nickName']=item.xpath('.//span[@class="c-listing-athlete__nickname"]//div[@class="field__item"]/text()').extract_first()
            player['weightClass']=item.xpath('.//span[@class="c-listing-athlete__title"]//div[@class="field__item"]/text()').extract_first()

            player['cover']=item.xpath('.//div[@class="c-listing-athlete__thumbnail"]//img/@src').extract_first()
            player['back']=item.xpath('.//div[@class="c-listing-athlete-flipcard__back"]//img/@src').extract_first()
            player['playerPage']='https://www.ufc.com'+item.xpath('.//a[@class="e-button--black "]/@href').extract_first()
            yield scrapy.Request(url=player['playerPage'], callback=self.parse_detail,meta={'item': player})
        if len(items)>0:
            self.page+=1
            yield scrapy.Request(url=f'https://www.ufc.com/athletes/all?page={self.page}',callback=self.parse)
        else:
            print("停止爬取")
    def parse_detail(self, response):
        print("选手详情:",response.url)
        player = response.meta['item']
        # 接收结构化数据
        player['historys'] = response.xpath('//div[@class="clearfix text-formatted field field--name-qna-ufc field--type-text-long field--label-hidden field__item"]//p/text()').extract()
        bios_list=response.xpath('//div[@class="c-bio__info-details"]/div/div')
        biosInfo=[]
        player['biosInfos']=biosInfo
        for b in bios_list:
            info={}
            info['lable']=b.xpath('.//div/text()').extract()[0].strip()
            info['value']=b.xpath('.//div/text()').extract()[1].strip()
            biosInfo.append(info)
        player['weightClass']=response.xpath('//p[@class="hero-profile__division-title"]/text()').extract_first()    
        player['record']=response.xpath('//p[@class="hero-profile__division-body"]/text()').extract_first()
        player['playerTags']=response.xpath('//div[@class="hero-profile__tags"]/p/text()').extract()
        player['playerTags']=[ i.strip() for i in player['playerTags'] ]
        stats_list=response.xpath('//div[@class="hero-profile__stat"]')
        winsStats=[]
        player['winsStats']=winsStats
        for stat in stats_list:
            s={}
            s['way']=stat.xpath('.//p[@class="hero-profile__stat-text"]/text()').extract_first()
            s['times']=stat.xpath('.//p[@class="hero-profile__stat-numb"]/text()').extract_first()
            winsStats.append(s)
        player['back']=response.xpath('//img[@class="hero-profile__image"]/@src').extract_first()
        yield player              