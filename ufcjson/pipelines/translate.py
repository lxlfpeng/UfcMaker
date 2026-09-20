import sqlite3

from ufcjson.items import (
    UfcPassItem,
    UfcPassCardItem,
    UfcComingItem,
    UfcComingCardItem,
    UfcRankingItem,
    UfcPlayerItem,
)
from ufcjson.translate_cache import ensure_cache_table


# 用于翻译的管道（只查缓存，不发起网络请求；未命中的翻译由 run.py 的 translate_db_fields 统一处理）
class TranslatorPipeline(object):
    # 构造方法（初始化对象时执行的方法）
    def __init__(self):
        pass

    def open_spider(self):
        # 1. 连接到数据库（如果没有数据库文件，会自动创建）
        self.conn = sqlite3.connect('output/db/ufc_translate.db')
        # 2. 创建游标对象（用于执行SQL语句）
        self.cursor = self.conn.cursor()
        # 3. 建翻译表（含 original 唯一索引；老库会顺手去一次重）
        ensure_cache_table(self.conn)

    def process_item(self, item):
        if isinstance(item, UfcPassItem):
            self.translate(item, 'address')
            self.translate(item, 'name')
            self.translate(item, 'title')
        if isinstance(item, UfcPassCardItem):
            self.translate(item, 'end_method')
            self.translate(item, 'card_division')
        if isinstance(item, UfcComingItem):
            self.translate(item, 'address')
        if isinstance(item, UfcComingCardItem):
            pass
        if isinstance(item, UfcRankingItem):
            pass
        if isinstance(item, UfcPlayerItem):
            self.translate(item, 'name')
            self.translate(item, 'nick_name')
            self.translate(item, 'country')
            self.translate(item, 'city')
            self.translate(item, 'division')
            self.translate(item, 'status')
            self.translate(item, 'team')
            self.translate(item, 'style')
            # history / wins_stats 是 JSON 列，暂不在管线翻译（后续用大模型处理）
        return item

    def close_spider(self):
        # 7. 关闭连接
        self.conn.close()

    def translate_real(self, value):
        """仅查询翻译缓存；未命中返回空字符串，翻译统一由 run.py 的 translate_db_fields 处理。"""
        self.cursor.execute("SELECT * FROM translate WHERE original = ?", (value,))
        result = self.cursor.fetchone()
        if result is not None:
            return result[2]
        return ""

    def translate(self, item, key):
        tr_key = key + "_cn"
        value = item.get(key, None)
        if key in item and value is not None and len(value) > 0:
            if type(value) is list:
                # 列表类型：任一元素未命中缓存则整体不落库，交给 run.py 补翻
                tr_list = []
                for i in item[key]:
                    if i.strip():
                        tr_list.append(self.translate_real(i))
                if tr_list and all(tr_list):
                    item[tr_key] = tr_list
            else:
                # 字符串类型
                tr = self.translate_real(value)
                if tr:
                    item[tr_key] = tr
