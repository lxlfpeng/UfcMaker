import json
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
        """从数据库读取最新的 8 场过往赛事，生成 ufc_pass_data.json"""
        conn = sqlite3.connect('output/db/ufc.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 按 main_time 倒序取最新的 8 场赛事
        cursor.execute('''
            SELECT name, name_cn, title, title_cn, banner, address, address_cn, page as url,
                   main_time, prelims_time, data_early_time
            FROM pass_event
            ORDER BY main_time DESC
            LIMIT 8
        ''')
        events = cursor.fetchall()

        data = []
        for event in events:
            event_dict = dict(event)
            # 查询该赛事的所有战卡
            cursor.execute('''
                SELECT fight_page, card_type, card_division, card_division_cn, end_round, end_time,
                       end_method, end_method_cn, red_page, blue_page, red_result, blue_result,
                       red_odds, blue_odds
                FROM pass_card
                WHERE fight_page = ?
                ORDER BY rowid ASC
            ''', (event_dict['url'],))
            fight_cards = [dict(row) for row in cursor.fetchall()]
            event_dict['fight_cards'] = fight_cards
            data.append(event_dict)

        conn.close()

        # 写入 JSON 文件（保持标准 API 响应格式）
        output = {
            'code': 0,
            'msg': 'success',
            'data': data,
            'timestamp': int(time.time() * 1000),
        }
        with open(file_name, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False)
