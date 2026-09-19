import json
import sqlite3

from ufcjson.items import (
    UfcPassItem,
    UfcPassCardItem,
    UfcPlayerItem,
)
from ufcjson.spiders.eventpass import EventpassSpider
from ufcjson.spiders.athlete import AthleteSpider


def dump_cn_field(value):
    """中文 JSON 列（history_cn / wins_stats_cn）的落库口径。

    没有译文时写空串，**不要**写 '[]'。translator._collect_pending 只把
    「NULL 或空串」当作待翻译；写成 '[]' 会被当成「已翻译」而永远跳过。
    空列表 / None / '' 一律落成 ''。"""
    if not value:
        return ''
    return str(json.dumps(value))


# 用于写入sqlite3数据库的管道
class SqliteDbPipeline(object):
    # 构造方法（初始化对象时执行的方法）
    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open_spider(self):
        spider = self.crawler.spider
        # 1. 连接到数据库（如果没有数据库文件，会自动创建）
        self.conn = sqlite3.connect('output/db/ufc.db')
        # 2. 创建游标对象（用于执行SQL语句）
        self.cursor = self.conn.cursor()
        if isinstance(spider, EventpassSpider):
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pass_event (
             id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主键
             name TEXT,                             -- 名称
             name_cn TEXT,                          -- 名称(中文)
             title TEXT,                            -- 头条主赛
             title_cn TEXT,                         -- 头条主赛(中文)
             banner TEXT,                           -- 横幅
             banner_local TEXT,                     -- 横幅(本地)
             address TEXT,                          -- 地点
             address_cn TEXT,                       -- 地点(cn)
             page TEXT UNIQUE,                      -- 主页
             main_time TEXT,                        -- 主卡时间
             prelims_time TEXT,                     -- 副卡时间
             data_early_time TEXT                   -- 早卡时间
            )
            ''')
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pass_card (
             id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主键
             fight_page TEXT,                       -- 主页
             blue_page TEXT,                        -- 蓝方主页
             red_page TEXT,                         -- 红方主页
             blue_result TEXT,                      -- 蓝方结果
             red_result TEXT,                       -- 红方结果
             blue_odds TEXT,                        -- 蓝方odds
             red_odds TEXT,                         -- 红方odds
             end_method TEXT,                       -- 结束方式
             end_method_cn TEXT,                    -- 结束方式(中文)
             end_round TEXT,                        -- 结束回合
             end_time TEXT,                         -- 结束时间
             card_type TEXT,                        -- 类型(主赛复赛)
             card_division  TEXT,                   -- 级别
             card_division_cn TEXT                  -- 级别(中文)
            )
            ''')
        if isinstance(spider, AthleteSpider):
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS player (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,     -- 用户名
                    name_cn TEXT,           -- 用户名(中文)
                    nick_name TEXT,         -- 昵称
                    nick_name_cn TEXT,      -- 昵称(中文)
                    page TEXT UNIQUE,       -- 个人主页
                    division TEXT,          -- 级别
                    division_cn TEXT,       -- 级别(中文)
                    avatar TEXT,            -- 头像
                    avatar_local TEXT,      -- 头像(本地)
                    cover TEXT,             -- 封面
                    cover_local TEXT,       -- 封面(本地)
                    record TEXT,            -- 战绩
                    age TEXT,               -- 年龄
                    status TEXT,            -- 状态
                    status_cn TEXT,         -- 状态(中文)
                    home_town TEXT,         -- 出生地(城市, 国家)
                    city TEXT,              -- 城市
                    city_cn TEXT,           -- 城市(中文)
                    country TEXT,           -- 国家
                    country_cn TEXT,        -- 国家(中文)
                    team TEXT,              -- 团队
                    team_cn TEXT,           -- 团队(中文)
                    style TEXT,             -- 风格
                    style_cn TEXT,          -- 风格(中文)
                    height TEXT,            -- 身高
                    weight TEXT,            -- 体重
                    reach TEXT,             -- 臂展
                    leg_reach TEXT,         -- 腿长
                    debut TEXT,             -- 首次亮像
                    history TEXT,          -- 历史
                    wins_stats TEXT,        -- 获胜方式
                    wins_stats_cn TEXT,     -- 获胜方式(中文)
                    flag TEXT,              -- 国旗
                    history_cn TEXT         -- 历史(中文)
                )
            ''')

    def process_item(self, item):
        if isinstance(item, UfcPassItem):
            self.cursor.execute('''
                     INSERT INTO pass_event (name,name_cn,title,title_cn,banner,banner_local,address,address_cn,page,main_time,prelims_time,data_early_time)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ''', (item.get('name', ''), item.get('name_cn', ''), item.get('title', ''), item.get('title_cn', ''),
                         item.get('banner', ''),
                         item.get('banner_local', ''),
                         item.get('address', ''), item.get('address_cn', ''), item.get('url', ''),
                         item.get('main_time', ''),
                         item.get('prelims_time', ''), item.get('data_early_time', '')
                         ))
            # # 5. 提交更改
            self.conn.commit()
        if isinstance(item, UfcPassCardItem):
            # 一场对局（赛事 + 双方主页）在表里只应有一行。
            # 爬虫的判重只做在 pass_event 上、且发生在列表页解析时，真正写库在详情页抓回之后，
            # 中间隔着一次网络请求 —— 同一赛事被派发两次时两次都会通过检查，整张战卡被写两遍。
            # 这里按 (fight_page, blue_page, red_page) 兜底：命中则更新，未命中才插入。
            fight_key = (item.get('fight_page', ''), item.get('blue_page', ''), item.get('red_page', ''))
            row = self.cursor.execute(
                'SELECT id FROM pass_card WHERE fight_page = ? AND blue_page = ? AND red_page = ? LIMIT 1',
                fight_key).fetchone()
            update_fields = ('blue_result', 'red_result', 'blue_odds', 'red_odds',
                             'end_method', 'end_method_cn', 'end_round', 'end_time',
                             'card_type', 'card_division', 'card_division_cn')
            if row:
                # 已有该对局：只覆盖新抓到的非空值，避免"赛前写入的空结果"把"赛后的结果"覆盖掉
                set_clause = ', '.join(f"{f} = CASE WHEN ? <> '' THEN ? ELSE {f} END" for f in update_fields)
                args = []
                for f in update_fields:
                    value = item.get(f, '')
                    args += [value, value]
                args.append(row[0])
                self.cursor.execute(f'UPDATE pass_card SET {set_clause} WHERE id = ?', args)
            else:
                self.cursor.execute('''
                       INSERT INTO pass_card (fight_page,blue_page,red_page,blue_result,red_result,blue_odds,red_odds,
                       end_method,end_method_cn,end_round,end_time,card_type,card_division,card_division_cn)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                     ''', (fight_key[0], fight_key[1], fight_key[2],
                           item.get('blue_result', ''), item.get('red_result', ''), item.get('blue_odds', ''),
                           item.get('red_odds', ''), item.get('end_method', ''), item.get('end_method_cn', ''),
                           item.get('end_round', ''),
                           item.get('end_time', '')
                           , item.get('card_type', ''), item.get('card_division', ''), item.get('card_division_cn', '')
                           ))
            # # 5. 提交更改
            self.conn.commit()
        if isinstance(item, UfcPlayerItem):
            self.cursor.execute(
                '''
                INSERT OR REPLACE INTO player (name, page,division,division_cn,avatar,avatar_local,cover,cover_local,record,age,status,status_cn,
                home_town,city,city_cn,country,country_cn,team,team_cn,style,style_cn,height,weight,reach,leg_reach,debut,nick_name,wins_stats,wins_stats_cn,
                history,name_cn,flag,nick_name_cn,history_cn)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (item['name'], item['page'], item['division'], item.get('division_cn', ''), item['avatar'],
                      item.get('avatar_local', ''),
                      item['cover'], item.get('cover_local', ''), item.get('record', ''), item.get('age', ''),
                      item.get('status', ''), item.get('status_cn', ''), item.get('home_town', ''),
                      item.get('city', ''), item.get('city_cn', ''), item.get('country', ''), item.get('country_cn', ''),
                      item.get('team', ''), item.get('team_cn', ''), item.get('style', ''), item.get('style_cn', ''),
                      item.get('height', ''), item.get('weight', ''),
                      item.get('reach', ''), item.get('leg_reach', '')
                      , item.get('debut', ''), item.get('nick_name', ''), str(json.dumps(item.get('wins_stats'))),
                      dump_cn_field(item.get('wins_stats_cn')),
                      str(json.dumps(item.get('history'))), item.get('name_cn', ''), item.get('flag', ''),
                      item.get('nick_name_cn', ''),
                      dump_cn_field(item.get('history_cn')))
            )
            # # 5. 提交更改
            self.conn.commit()
        return item

    def close_spider(self):
        # 7. 关闭连接
        self.conn.close()
