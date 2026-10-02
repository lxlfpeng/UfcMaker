import json
import os
import sqlite3
import time

from ufcjson.export import JsonObjectItemExporter, JsonObjectLinesItemExporter
from ufcjson.items import UfcPassItem, UfcComingItem
from ufcjson.spiders.upcoming import UpcomingSpider
from ufcjson.spiders.eventpass import EventpassSpider
from ufcjson.spiders.ranking import RankingSpider


# 用于写入Json文件的管道
class JsonWriterPipeline(object):
    # 构造方法（初始化对象时执行的方法）
    def __init__(self, crawler):
        self.crawler = crawler
        self.json_file = None
        self.json_exporter = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open_spider(self):
        spider = self.crawler.spider
        if isinstance(spider, UpcomingSpider):
            self.make_json_file('output/json/ufc_coming_data.json', spider)
        if isinstance(spider, RankingSpider):
            self.make_json_file('output/json/ufc_ranking_data.json', spider)
        # EventpassSpider 不在此处打开文件，改为在 close_spider 时从数据库读取生成

    def make_json_file(self, file_name, spider):
        # 使用 'wb' （二进制写模式）模式打开文件
        self.json_file = open(file_name, 'wb')
        # 构建 JsonItemExporter 对象，设定不使用 ASCII 编码，并指定编码格式为 'UTF-8'
        self.json_exporter = JsonObjectItemExporter(self.json_file, ensure_ascii=False, encoding='UTF-8')
        if isinstance(spider, RankingSpider):
            self.json_exporter = JsonObjectLinesItemExporter(self.json_file, ensure_ascii=False, encoding='UTF-8')
        # 声明 exporting 过程 开始，这一句也可以放在 open_spider() 方法中执行。
        self.json_exporter.start_exporting()

    # 爬虫 pipeline 接收到 Scrapy 引擎发来的 item 数据时，执行的方法
    def process_item(self, item):
        # 将 item 存储到内存中
        spider = self.crawler.spider
        if isinstance(item, UfcComingItem):
            self.json_exporter.export_item(item)
        if isinstance(spider, RankingSpider):
            self.json_exporter.export_item(item)
        # UfcPassItem 不在这里写入，改为 close_spider 时从数据库统一生成
        return item

    def close_spider(self):
        spider = self.crawler.spider
        if isinstance(spider, EventpassSpider):
            # eventpass 的 JSON 从数据库读取最新的 8 场赛事生成
            self._generate_pass_json_from_db('output/json/ufc_pass_data.json')
        elif self.json_exporter is not None:
            # 声明 exporting 过程 结束，结束后，JsonItemExporter 会将收集存放在内存中的所有数据统一写入文件中
            self.json_exporter.finish_exporting()
            # 关闭文件
            self.json_file.close()

    def _generate_pass_json_from_db(self, file_name):
        """从数据库读取最新的 8 场过往赛事，生成 ufc_pass_data.json

        ⚠️ 排序必须按数值而不是字符串：`main_time` 是 TEXT 列，存的是 Unix 时间戳；
        库里 1970 ~ 2001-09-09 的赛事只有 9 位数字、之后都是 10 位，而 SQLite 对 TEXT
        是逐字符比较（'9…' > '1…'）⇒ 直接 `ORDER BY main_time DESC` 会让
        1999–2001 那批排到最前，LIMIT 8 取到的全是二十多年前的比赛。
        """
        events = []
        cards_by_page = {}
        conn = sqlite3.connect('output/db/ufc.db')
        conn.row_factory = sqlite3.Row
        try:
            events = conn.execute('''
                SELECT name, name_cn, title, title_cn, banner, banner_local,
                       address, address_cn, page as url,
                       main_time, prelims_time, data_early_time
                FROM pass_event
                ORDER BY CAST(main_time AS INTEGER) DESC
                LIMIT 8
            ''').fetchall()

            # 战卡一次性取回再按赛事分组，避免每场赛事发一条子查询
            if events:
                pages = [event['url'] for event in events]
                placeholders = ','.join('?' * len(pages))
                for row in conn.execute(f'''
                        SELECT fight_page, card_type, card_division, card_division_cn,
                               end_round, end_time, end_method, end_method_cn,
                               red_page, blue_page, red_result, blue_result,
                               red_odds, blue_odds
                        FROM pass_card
                        WHERE fight_page IN ({placeholders})
                        ORDER BY rowid ASC
                        ''', pages):
                    card = dict(row)
                    cards_by_page.setdefault(card['fight_page'], []).append(card)
        finally:
            conn.close()

        data = []
        for event in events:
            event_dict = dict(event)
            event_dict['fight_cards'] = cards_by_page.get(event_dict['url'], [])
            data.append(event_dict)

        # 写入 JSON 文件（保持标准 API 响应格式）
        output = {
            'code': 0,
            'msg': 'success',
            'data': data,
            'timestamp': int(time.time() * 1000),
        }
        # 先写临时文件再原子替换：客户端随时会来拉这个文件，
        # 直接覆盖原文件时若进程中途挂掉，会留下半截 JSON。
        tmp_path = f'{file_name}.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False)
        os.replace(tmp_path, file_name)
