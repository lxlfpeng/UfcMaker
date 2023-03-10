import scrapy
from ..inline_requests import inline_requests
from ..items import UfcRankingItem
from ..items import UfcRankingPlayer
from copy import deepcopy
import os
import json

class RankingSpider(scrapy.Spider):
    name = "ranking"
    allowed_domains = ["www.ufc.com"]
    start_urls = ["https://www.ufc.com/rankings"]
    def __init__(self):
        self.old={}
        path='./ufc_ranking_data.json'
        if os.path.exists(path):
            with open(path,'r', encoding='utf-8') as a:
                try:
                    data=json.load(a)['data']
                    self.old={i['rankName']+str(item['ranking'])+item['name']:item for i in data  for item in i['players']}
                except Exception:
                    print("未读取到老的数据,需要全量抓取!")
                    pass     
        else:
            print("文件不存在,需要全量抓取!")    
    
    #添加改标签标识可以通过同步方式进行请求
    @inline_requests
    def parse(self, response):
        info = response.xpath('//div[@class="view-grouping"]')
        #info=info[0:1]
        for index,i in enumerate(info):
            item=UfcRankingItem()
            item['rankName']=i.xpath('.//div[@class="view-grouping-header"]/text()').extract_first()
            playeras=i.xpath('.//a')
            players=[]
            item['players']=players
            for index,p in enumerate(playeras):
                player=UfcRankingPlayer()
                players.append(player)
                player['name']=p.xpath('./text()').extract_first()
                player['ranking']=index
                flag_key=item['rankName']+str(player['ranking'])+player['name']
                if flag_key in self.old:
                    for key in self.old[flag_key].keys():
                        player[key]=self.old[flag_key][key]
                    yield player
                    print("数据已存在!")    
                    continue
                player['playerPage']='https://www.ufc.com'+p.xpath('./@href').extract_first()
                print("个人主页:",player['playerPage'])
                try: 
                    next_resp = yield scrapy.Request(url=player['playerPage'],dont_filter=True)
                    self.parse_detail(next_resp,player)
                except Exception:
                    pass
                yield player
            yield item        

    def parse_detail(self, response, player):
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
        return player    
        