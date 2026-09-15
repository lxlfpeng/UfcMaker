import scrapy
from w3lib.url import url_query_parameter
from ..items import UfcPlayerItem
from ..birth_place import split_birth_place
import sqlite3
import os
import json
import re

LABEL_FIELD_MAP = {
    'Age': 'age',
    'Status': 'status',
    'Reach': 'reach',
    'Height': 'height',
    'Place of Birth': 'home_town',
    'Trains at': 'team',
    'Fighting style': 'style',
    'Leg reach': 'leg_reach',
    'Octagon Debut': 'debut',
    'Weight': 'weight',
}

class AthleteSpider(scrapy.Spider):
    name = "athlete"
    allowed_domains = ["www.ufc.com","dmxg5wxfqgb4u.cloudfront.net"]
    #start_urls = ["https://www.ufc.com/athletes/all?page=254"]
    start_urls = ["https://www.ufc.com/athletes/all"]
    def __init__(self, pagination=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pagination = pagination
        # 1. 连接到数据库（如果没有数据库文件，会自动创建）
        self.conn = sqlite3.connect('output/db/ufc.db')
        # 2. 创建游标对象（用于执行SQL语句）
        self.cursor = self.conn.cursor()
        # 收集未匹配的 bio label，用于感知页面结构变化
        self.unmatched_bio_labels = set()

    def closed(self, reason):
        if self.unmatched_bio_labels:
            self.logger.warning(f"发现 {len(self.unmatched_bio_labels)} 个未匹配的 bio label: {sorted(self.unmatched_bio_labels)}")
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
            if len(results) > 0:
                self.logger.info(f"{player['name']} 已存在数据库，跳过")
                continue
            player['nick_name'] = item.xpath('.//span[@class="c-listing-athlete__nickname"]//div[@class="field__item"]/text()').get(default='').strip()
            player['division'] = item.xpath('.//span[@class="c-listing-athlete__title"]//div[@class="field__item"]/text()').get(default='').strip()
            # 剥离首尾各类引号（英文双引号、中文双引号、英文单引号、中文单引号）
            player['nick_name'] = re.sub(r'^[\'\"""]+|[\'\"""]+$', '', player['nick_name']).strip()
            player['avatar']=item.xpath('.//div[@class="c-listing-athlete__thumbnail"]//img/@src').get(default='').strip()
            player['cover']=item.xpath('.//div[@class="c-listing-athlete-flipcard__back"]//img/@src').get(default='').strip()
            player['page']='https://www.ufc.com'+item.xpath('.//a[@class="e-button--black "]/@href').get(default='').strip()
            self.logger.info(f"准备抓取选手详情: {player['name']} - {player['page']}")
            yield scrapy.Request(url=player['page'], callback=self.parse_detail,meta={'item': player})
        if self.pagination and len(items) > 0:
            # 从当前 URL 解析页码，避免并发下 self.page 竞态
            current_page = int(url_query_parameter(response.url, 'page', default='0'))
            next_page = current_page + 1
            self.logger.info(f"继续翻页，下一页: page={next_page}")
            yield scrapy.Request(url=f'https://www.ufc.com/athletes/all?page={next_page}', callback=self.parse)
        elif not self.pagination:
            self.logger.info("未开启分页抓取，仅抓取第一页")
        else:
            self.logger.info("已无更多数据，停止爬取")
    def parse_detail(self, response):
        player = response.meta.get('item')
        if not player:
            self.logger.error(f"详情页缺少 item meta，跳过: {response.url}")
            return
        self.logger.info(f"抓取选手详情页面: {response.url}")
        # 接收结构化数据//field field--name-qna-ufc field--type-text-long field--label-hidden field__item
        #//*[@id="tab-panel-3"]/div/div
        # 取所有文本节点，避免 <li>、<strong> 等标签内容丢失
        player['history'] = [t.strip() for t in response.xpath('//*[@id="tab-panel-3"]/div/div//text()').getall() if t.strip()]
        bios_list = response.xpath('//div[@class="c-bio__info-details"]/div/div')
        for b in bios_list:
            text_nodes = [t.strip() for t in b.xpath('.//div/text()').getall() if t.strip()]
            if len(text_nodes) < 2:
                self.logger.warning(f"bio 项文本节点不足，跳过: {text_nodes}")
                continue
            label = text_nodes[0]
            # Age 项的 value 在第 3 个文本节点（中间是生日）
            if label == 'Age' and len(text_nodes) >= 3:
                value = text_nodes[2]
            else:
                value = text_nodes[1]
            field = LABEL_FIELD_MAP.get(label)
            if field:
                player[field] = value
            else:
                self.unmatched_bio_labels.add(label)
        # 详情页值非空时才覆盖列表页的值，避免空字符串覆盖有效数据
        detail_division = response.xpath('//p[@class="hero-profile__division-title"]/text()').get(default='').strip()
        if detail_division:
            player['division'] = detail_division
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
