import scrapy
from ..items import UfcPlayerItem
import sqlite3
import os
import json
class AthleteSpider(scrapy.Spider):
    name = "athlete"
    allowed_domains = ["www.ufc.com","dmxg5wxfqgb4u.cloudfront.net"]
    #start_urls = ["https://www.ufc.com/athletes/all?page=254"]
    start_urls = ["https://www.ufc.com/athletes/all"]
    def __init__(self):
        self.page=0
        # 1. 连接到数据库（如果没有数据库文件，会自动创建）
        self.conn = sqlite3.connect('ufc.db')
        # 2. 创建游标对象（用于执行SQL语句）
        self.cursor = self.conn.cursor()

    def close_spider(self, spider):
        if self.conn:
            self.conn.close()

    def parse(self, response):
        items=response.xpath('//div[@class="node node--type-athlete node--view-mode-all-athletes-result ds-1col clearfix"]')
        self.logger.info(f"本页请求地址: {response.url} 本页获取到选手个数: {len(items)}")
        for item in items:
            player=UfcPlayerItem()
            player['name']=item.xpath('.//span[@class="c-listing-athlete__name"]/text()').get(default='').strip()
            player['record']=item.xpath('.//span[@class="c-listing-athlete__record"]/text()').get(default='').strip()
            self.cursor.execute("SELECT * FROM player WHERE name = ? AND record = ?", (player['name'], player['record']))
            results = self.cursor.fetchall()
            if len(results)>0:
                print(f"{player['name']} 已存在数据库，跳过")
                continue
            player['nick_name']=item.xpath('.//span[@class="c-listing-athlete__nickname"]//div[@class="field__item"]/text()').get(default='').strip()
            player['division']=item.xpath('.//span[@class="c-listing-athlete__title"]//div[@class="field__item"]/text()').get(default='').strip()
            if player['nick_name'] is not None and '"' in player['nick_name']:
               player['nick_name']=player['nick_name'].strip('"').strip()
            player['avatar']=item.xpath('.//div[@class="c-listing-athlete__thumbnail"]//img/@src').get(default='').strip()
            player['cover']=item.xpath('.//div[@class="c-listing-athlete-flipcard__back"]//img/@src').get(default='').strip()
            player['page']='https://www.ufc.com'+item.xpath('.//a[@class="e-button--black "]/@href').get(default='').strip()
            self.logger.info(f"准备抓取选手详情: {player['name']} - {player['page']}")
            yield scrapy.Request(url=player['page'], callback=self.parse_detail,meta={'item': player})
        if len(items)>0:
            self.page+=1
            yield scrapy.Request(url=f'https://www.ufc.com/athletes/all?page={self.page}',callback=self.parse)
        else:
            print("停止爬取")
    def parse_detail(self, response):
        player = response.meta['item']
        self.logger.info(f"抓取选手详情页面: {response.url}")
        # 接收结构化数据//field field--name-qna-ufc field--type-text-long field--label-hidden field__item
        #//*[@id="tab-panel-3"]/div/div
        player['history'] = response.xpath('//*[@id="tab-panel-3"]/div/div//p/text()').extract()
        bios_list=response.xpath('//div[@class="c-bio__info-details"]/div/div')
        # biosInfo=[]
        # player['biosInfos']=biosInfo
        for b in bios_list:
            info={}
            info['lable']=b.xpath('.//div/text()').extract()[0].strip()
            if info['lable'] == 'Age':
                info['value'] = b.xpath('.//div/text()').extract()[2].strip()
            else:
                info['value']=b.xpath('.//div/text()').extract()[1].strip()
            #print("数据",str(b))
            self.make_filed(player,info['lable'],info['value'],'Age','age')
            self.make_filed(player, info['lable'], info['value'], 'Status', 'status')
            self.make_filed(player, info['lable'], info['value'], 'Reach', 'reach')
            self.make_filed(player, info['lable'], info['value'], 'Height', 'height')
            self.make_filed(player, info['lable'], info['value'], 'Place of Birth', 'home_town')
            self.make_filed(player, info['lable'], info['value'], 'Trains at', 'team')
            self.make_filed(player, info['lable'], info['value'], 'Fighting style', 'style')
            self.make_filed(player, info['lable'], info['value'], 'Leg reach', 'leg_reach')
            self.make_filed(player, info['lable'], info['value'], 'Octagon Debut', 'debut')
            self.make_filed(player, info['lable'], info['value'], 'Weight', 'weight')
            # biosInfo.append(info)
        player['division']=response.xpath('//p[@class="hero-profile__division-title"]/text()').get(default='').strip()
        player['record']=response.xpath('//p[@class="hero-profile__division-body"]/text()').get(default='').strip()
        player['player_tags']=response.xpath('//div[@class="hero-profile__tags"]/p/text()').extract()
        player['player_tags']=[ i.strip() for i in player['player_tags'] ]
        stats_list=response.xpath('//div[@class="hero-profile__stat"]')
        wins_stats=[]
        player['wins_stats']=wins_stats
        for stat in stats_list:
            s={}
            s['way']=stat.xpath('.//p[@class="hero-profile__stat-text"]/text()').get(default='').strip()
            s['times']=stat.xpath('.//p[@class="hero-profile__stat-numb"]/text()').get(default='').strip()
            wins_stats.append(s)
        player['cover']=response.xpath('//img[@class="hero-profile__image"]/@src').get(default='').strip()
        self.logger.info(f"抓取完成选手: {player['name']}，共 {len(player['history'])} 条历史记录，{len(wins_stats)} 条胜场统计")
        yield player
    def make_filed(self,player,label,value,key,filed):
        if label == key:
            try:
                player[filed] = value
            except Exception as e:
                # 处理其他异常
                print(f"发生异常: {e}")
