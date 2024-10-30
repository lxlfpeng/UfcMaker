# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
from ufcjson.items import UfcPassItem
from ufcjson.items import UfcPassCardItem
from scrapy import Request
from scrapy.pipelines.images import ImagesPipeline
import hashlib
from scrapy.utils.python import get_func_args, to_bytes
from scrapy.exporters import JsonItemExporter
from scrapy.exporters import JsonLinesItemExporter

import json
from io import BytesIO

from .spiders.upcoming import UpcomingSpider
from .spiders.eventpass import EventpassSpider
from .spiders.ranking import RankingSpider
from .spiders.athlete import AthleteSpider

from ufcjson.items import UfcComingBannerItem
from ufcjson.items import UfcComingCardItem
from ufcjson.items import UfcComingItem
from . import country
from ufcjson.rss import RssMaker

from ufcjson.items import UfcRankingItem
from ufcjson.items import UfcRankingPlayer

from .export import JsonObjectItemExporter
from .export import JsonObjectLinesItemExporter
import shutil
import os
from googletrans import Translator
import logging
import datetime
import sqlite3
import pycountry
import warnings

# 用于设置头像和背景默认的管道
class UfcDefaultPhotoPipeline:
    def process_item(self, item, spider):
       if isinstance(item,UfcComingBannerItem):
          if not item['redPlayerCover'].startswith('http') :
            item['redPlayerCover']='https://www.ufc.com'+item['redPlayerCover']
          if not item['bluePlayerCover'].startswith('http') :
            item['bluePlayerCover']='https://www.ufc.com'+item['bluePlayerCover']

       if isinstance(item,UfcComingCardItem):
            if 'themes/custom/ufc/assets/img/silhouette-headshot-female.png' in item['redPlayerBack']:
                item['redPlayerBack']="https://dmxg5wxfqgb4u.cloudfront.net/styles/event_fight_card_upper_body_of_standing_athlete/s3/image/2022-02/womens-silhouette-RED-corner.png?itok=bYCcdQLM"
            if 'themes/custom/ufc/assets/img/standing-stance-right-silhouette.png' in item['redPlayerBack']:
                item['redPlayerBack']="https://dmxg5wxfqgb4u.cloudfront.net/styles/event_fight_card_upper_body_of_standing_athlete/s3/image/fighter_images/SHADOW_Fighter_fullLength_RED.png?VersionId=0NwYm4ow5ym9PWjgcpd05ObDBIC5pBtX&itok=woJQm5ZH"
            if 'themes/custom/ufc/assets/img/silhouette-headshot-female.png' in item['bluePlayerBack']:
                item['bluePlayerBack']="https://dmxg5wxfqgb4u.cloudfront.net/styles/event_fight_card_upper_body_of_standing_athlete/s3/image/2022-02/womens-silhouette-BLUE-corner.png?itok=bYCcdQLM"
            if '/themes/custom/ufc/assets/img/standing-stance-left-silhouette.png' in item['bluePlayerBack']:
                item['bluePlayerBack']="https://dmxg5wxfqgb4u.cloudfront.net/styles/event_fight_card_upper_body_of_standing_athlete/s3/image/fighter_images/SHADOW_Fighter_fullLength_BLUE.png?VersionId=1Jeml9w1QwZqmMUJDg8qTrTk7fFhqUra&itok=fiyOmUkc"

       if isinstance(item,UfcRankingPlayer):
            if 'cover' in item:
                if item['cover'] is None or not item['cover'].startswith('http'):
                    item['cover']='https://www.ufc.com/themes/custom/ufc/assets/img/no-profile-image.png'

            if item['back'] is None or not item['back'].startswith('http'):
               item['back']='https://dmxg5wxfqgb4u.cloudfront.net/styles/event_fight_card_upper_body_of_standing_athlete/s3/image/fighter_images/SHADOW_Fighter_fullLength_RED.png?VersionId=0NwYm4ow5ym9PWjgcpd05ObDBIC5pBtX&itok=woJQm5ZH'
       return item

# 用于将国籍code修改为Emoji表情的管道
class UfcCountryCodePipeline:
    def process_item(self, item, spider):
       if isinstance(item,UfcPassCardItem) or isinstance(item,UfcComingCardItem):
            try:
                red_images=item['redPlayerCountryCode'].split('/')
                item['redPlayerCountryEmoji']=country.get_country_flag_emoji(red_images[len(red_images)-1].replace('.PNG',''))
            except :
                item['redPlayerCountryEmoji']='🏳'
            try:
                blue_images=item['bluePlayerCountryCode'].split('/')
                item['bluePlayerCountryEmoji']=country.get_country_flag_emoji(blue_images[len(blue_images)-1].replace('.PNG',''))
            except :
                item['bluePlayerCountryEmoji']='🏳'

       if isinstance(item, UfcRankingPlayer):
          country=item.get('home_town','')
          if ',' in country:
              country = country.split(",")[1]
          item['flag']=self.get_country_flag(country.strip())

       return item

    def get_country_flag(self,country_name):
        if not country_name:
            return '🏳'
        try:
            country = pycountry.countries.get(name=country_name)
            if country is None:
                country = pycountry.countries.search_fuzzy(country_name)
                if len(country)>0:
                    country=country[0]
            return country.flag
        except Exception as e:
            return '🏳'

class UfcRssMakerPipeline:
    def __init__(self):
        self.rssMaker=RssMaker( title="UFC赛程",link='https://www.ufc.com/events#events-list-upcoming',description="新的UFC赛程")
        self.rssList=[]
    def process_item(self, item, spider):
       if isinstance(item,UfcComingCardItem):
            # 将时间戳转换为datetime对象
            dt_object = datetime.datetime.fromtimestamp(int(item['mainCardTimestamp']))
            # 格式化为字符串
            formatted_time = dt_object.strftime("%m-%d")
            title=formatted_time+" "+item['fightName']+" ("+item['redPlayerName']+" VS "+item['bluePlayerName'] +") 级别："+item['weightClass']+" 举办地:"+item['address']
            self.rssList.append({'title':title,
            'link':"",
            'time':dt_object,
            'description':self.rssMaker.get_html_str(item)})
       return item
    def close_spider(self, spider):
        if isinstance(spider, UpcomingSpider):
            self.rssMaker.makeRss(self.rssList,'./rss/ufc_schedule.xml')

# 继承ImagesPipeline用于下载图片的管道
class ImagesDownloadPipeline(ImagesPipeline):
    def get_media_requests(self, item, info):
        # 根据不同的Item取出图片进行下载     
        if isinstance(item,UfcPassItem) or isinstance(item, UfcComingItem):
            if 'banner' in item and item['banner'] is not None:
                yield Request(item['banner'])
        if isinstance(item,UfcPassCardItem) or isinstance(item, UfcComingCardItem):
            if 'redPlayerBack' in item and item['redPlayerBack'] is not None:
                yield Request(item['redPlayerBack'])
            if 'bluePlayerBack' in item and item['bluePlayerBack'] is not None:
                yield Request(item['bluePlayerBack'])
        if isinstance(item, UfcComingBannerItem):
            if 'redPlayerCover' in item and item['redPlayerCover'] is not None:
                yield Request(item['redPlayerCover'])
            if 'bluePlayerCover' in item and item['bluePlayerCover'] is not None:
                yield Request(item['bluePlayerCover'])
        if isinstance(item, UfcRankingPlayer):
            if 'back' in item and item['back'] is not None:
                yield Request(item['back'])
            if 'cover' in item and item['cover'] is not None:
                yield Request(item['cover'])

    def file_path(self, request, response=None, info=None, *, item=None):
        # 自定义下载图片名称  
        image_guid = hashlib.sha1(to_bytes(request.url)).hexdigest()
        return f"full/{image_guid}.webp"

    def item_completed(self, results, item, info):
        images = {x['url']: x for ok, x in results if ok}
        #logging.warning("下载图片内容成功")
        #logging.warning(images)
        if len(images.keys()) == 0:
            return item
        if isinstance(item, UfcPassItem):
            if item['banner'] in images.keys():
                item['bannerLocal'] = images[item['banner']]['path']
        if isinstance(item, UfcPassCardItem):
            if item['redPlayerBack'] in images.keys():
                item['redPlayerBackLocal'] = images[item['redPlayerBack']]['path']
            if item['bluePlayerBack'] in images.keys():
                item['bluePlayerBackLocal'] = images[item['bluePlayerBack']]['path']
        if isinstance(item, UfcComingItem):
            if item['banner'] in images.keys():
                item['bannerLocal'] = images[item['banner']]['path']
        if isinstance(item, UfcComingBannerItem):
            if item['redPlayerCover'] in images.keys():
                item['redPlayerCoverLocal'] = images[item['redPlayerCover']]['path']
            if item['bluePlayerCover'] in images.keys():
                item['bluePlayerCoverLocal'] = images[item['bluePlayerCover']]['path']
        if isinstance(item, UfcComingCardItem):
            if item['redPlayerBack'] in images.keys():
                item['redPlayerBackLocal'] = images[item['redPlayerBack']]['path']
            if item['bluePlayerBack'] in images.keys():
                item['bluePlayerBackLocal'] = images[item['bluePlayerBack']]['path']

        if isinstance(item, UfcRankingPlayer):
            #print("图片下载完毕:",images.keys())
            if item['back'] in images.keys():
                item['backLocal'] = images[item['back']]['path']
            if 'cover' in item and item['cover'] in images.keys():
                item['coverLocal'] = images[item['cover']]['path']
        #logging.warning(item)
        # image_paths = [x['path'] for ok, x in results if ok]
        # if len(image_paths)>0:
        #     if isinstance(item,UfcPassItem):
        #         item['bannerLocal']=image_paths[0]
        #     if isinstance(item,UfcPassCardItem):
        #         item['redPlayerBackLocal'] =image_paths[0]
        #         item['bluePlayerBackLocal']=image_paths[1]  
        #     if isinstance(item,UfcComingItem):
        #         item['bannerLocal']=image_paths[0]
        #     if isinstance(item,UfcComingBannerItem):
        #         item['redPlayerCoverLocal'] =image_paths[0]
        #         item['bluePlayerCoverLocal']=image_paths[1] 
        #     if isinstance(item,UfcComingCardItem):
        #         item['redPlayerBackLocal'] =image_paths[0]
        #         item['bluePlayerBackLocal']=image_paths[1] 
        #     if isinstance(item, UfcRankingPlayer):
        #         item['backLocal']=image_paths[0]
        #         item['coverLocal']=image_paths[1]

        return item

    # 由于ImagesPipeline默认返回jpg图片,如果要返回其他格式图片则需要重写该父类方法 
    def convert_image(self, image, size=None, response_body=None):
        if response_body is None:
            warnings.warn(
                f"{self.__class__.__name__}.convert_image() method called in a deprecated way, "
                "method called without response_body argument."
            )

        if size:
            image = image.copy()
            try:
                # Image.Resampling.LANCZOS was added in Pillow 9.1.0
                # remove this try except block,
                # when updating the minimum requirements for Pillow.
                resampling_filter = self._Image.Resampling.LANCZOS
            except AttributeError:
                resampling_filter = self._Image.ANTIALIAS
            image.thumbnail(size, resampling_filter)
        elif response_body is not None and image.format == "JPEG":
            return image, response_body

        buf = BytesIO()
        image.convert("RGBA")
        image.save(buf, "WEBP")
        return image, buf

class JsonWriterPipeline(object):
    # 构造方法（初始化对象时执行的方法）
    def __init__(self):
        pass
    def open_spider(self,spider):
        if isinstance(spider, UpcomingSpider):
            self.make_json_file('./json/ufc_coming_data.json',spider)
        if isinstance(spider, EventpassSpider):
            self.make_json_file('./json/ufc_pass_data.json',spider)
        if isinstance(spider, RankingSpider):
            self.make_json_file('./json/ufc_ranking_data.json',spider)
        if isinstance(spider, AthleteSpider):
            self.make_json_file('./json/ufc_athlete_data_temp.json',spider)
        # else:
        #    self.make_json_file('未命名.json')

    def make_json_file(self,file_name,spider):
        # 使用 'wb' （二进制写模式）模式打开文件
        self.json_file = open(file_name, 'wb')
        # 构建 JsonItemExporter 对象，设定不使用 ASCII 编码，并指定编码格式为 'UTF-8'
        self.json_exporter = JsonObjectItemExporter(self.json_file, ensure_ascii=False, encoding='UTF-8')
        if isinstance(spider, AthleteSpider):
            self.json_exporter =JsonObjectLinesItemExporter(self.json_file, ensure_ascii=False, encoding='UTF-8')
        if isinstance(spider, UpcomingSpider):
            self.json_exporter =JsonObjectLinesItemExporter(self.json_file, ensure_ascii=False, encoding='UTF-8')
        # 声明 exporting 过程 开始，这一句也可以放在 open_spider() 方法中执行。
        self.json_exporter.start_exporting()

    # 爬虫 pipeline 接收到 Scrapy 引擎发来的 item 数据时，执行的方法
    def process_item(self, item, spider):
        # 将 item 存储到内存中
        if isinstance(item,UfcPassItem):
          self.json_exporter.export_item(item)
        if isinstance(item,UfcComingItem):
          self.json_exporter.export_item(item)
        if isinstance(spider, RankingSpider) and isinstance(item,UfcRankingPlayer):
          self.json_exporter.export_item(item)
        if isinstance(spider, AthleteSpider) and isinstance(item,UfcRankingPlayer):
          self.json_exporter.export_item(item)
        return item

    def close_spider(self, spider):
        if isinstance(spider, UpcomingSpider) or isinstance(spider, EventpassSpider) or isinstance(spider, RankingSpider)or isinstance(spider, AthleteSpider):
            # 声明 exporting 过程 结束，结束后，JsonItemExporter 会将收集存放在内存中的所有数据统一写入文件中
            self.json_exporter.finish_exporting()
            # 关闭文件
            self.json_file.close()
        if isinstance(spider, AthleteSpider):
            shutil.copyfile('./json/ufc_athlete_data_temp.json','./json/ufc_athlete_data.json')
            os.remove('./json/ufc_athlete_data_temp.json')

class JsonWriterTranslatorPipeline(object):
    # 构造方法（初始化对象时执行的方法）
    def __init__(self):
        pass
    def open_spider(self,spider):
        #读取所有的翻译
        self.translate_total={}
        self.translate_file_path='./json/ufc_translat.json'
        if os.path.exists(self.translate_file_path):
            with open(self.translate_file_path,'r', encoding="utf-8") as file:
                self.translate_total = json.load(file)
        if isinstance(spider, UpcomingSpider):
            self.make_json_file('./json/zh/ufc_coming_data.json',spider)
        if isinstance(spider, EventpassSpider):
            self.make_json_file('./json/zh/ufc_pass_data.json',spider)
        if isinstance(spider, RankingSpider):
            self.make_json_file('./json/zh/ufc_ranking_data.json',spider)
        if isinstance(spider, AthleteSpider):
            self.make_json_file('./json/zh/ufc_athlete_data.json',spider)
            # 1. 连接到数据库（如果没有数据库文件，会自动创建）
            self.conn = sqlite3.connect('example3.db')
            # 2. 创建游标对象（用于执行SQL语句）
            self.cursor = self.conn.cursor()
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS player (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,     -- 用户名
                    name_cn TEXT,           -- 用户名(中文)
                    nick_name TEXT,         -- 昵称
                    nick_name_cn TEXT,      -- 昵称(中文)
                    page TEXT,              -- 个人主页
                    division TEXT,          -- 级别
                    avatar TEXT,            -- 头像
                    avatar_local TEXT,      -- 头像(本地)
                    cover TEXT,             -- 封面
                    cover_local TEXT,       -- 封面(本地)
                    record TEXT,            -- 战绩
                    age TEXT,               -- 年龄          
                    status TEXT,            -- 状态
                    home_town TEXT,         -- 国籍
                    team TEXT,              -- 团队
                    style TEXT,             -- 风格                          
                    height TEXT,            -- 身高                          
                    weight TEXT,            -- 体重                         
                    reach TEXT,             -- 臂展                          
                    leg_reach TEXT,         -- 腿长
                    debut TEXT,             -- 首次亮像                           
                    history TEXT,          -- 历史
                    wins_stats TEXT,        -- 获胜方式
                    flag TEXT,              -- 国旗
                    history_cn TEXT,         -- 历史(中文)
                    home_town_cn TEXT        -- 国家(中文)
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP                                
                )
            ''')
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS translate (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original TEXT NOT NULL,     -- 原文
                    translation TEXT            -- 译文
                )
            ''')

    def make_json_file(self,file_name,spider):
        self.json_file = open(file_name, 'wb')
        self.json_exporter = JsonObjectItemExporter(self.json_file, ensure_ascii=False, encoding='UTF-8')
        if isinstance(spider, AthleteSpider):
            self.json_exporter =JsonObjectLinesItemExporter(self.json_file, ensure_ascii=False, encoding='UTF-8')
        self.json_exporter.start_exporting()

    def process_item(self, item, spider):

        if isinstance(item,UfcPassItem):
            self.translate(item,'address')
            for i in item['fightCards']:
                self.translate(i,'bluePlayerCountry')
                self.translate(i,'redPlayerCountry')
                self.translate(i,'bluePlayerName')
                self.translate(i,'redPlayerName')
                self.translate(i,'weightClass')
                self.translate(i,'cardType')
            self.json_exporter.export_item(item)

        if isinstance(item,UfcComingItem):
            self.translate(item,'address')
            self.translate(item,'fightName')
            for i in item['fightCards']:
                self.translate(i,'bluePlayerCountry')
                self.translate(i,'redPlayerCountry')
                self.translate(i,'bluePlayerName')
                self.translate(i,'redPlayerName')
                self.translate(i,'weightClass')
                self.translate(i,'cardType')
            self.json_exporter.export_item(item)

        if isinstance(item,UfcRankingItem):
            self.translate(item,'rankName')
            for i in item['players']:
                self.translate(i,'history')
                self.translate(i,'name')
                self.translate(i,'weightClass')
            self.json_exporter.export_item(item)

        if isinstance(item,UfcRankingPlayer):
          self.translate(item,'name')
          self.translate(item, 'nick_name')
          self.translate(item, 'history')
          self.translate(item, 'home_town')
          self.cursor.execute(
              '''
              INSERT OR IGNORE INTO player (name, page,division,avatar,avatar_local,cover,cover_local,record,age,status,
              home_town,team,style,height,weight,reach,leg_reach,debut,nick_name,wins_stats,history,name_cn,flag,nick_name_cn,
              history_cn,home_town_cn) 
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ''', (item['name'], item['playerPage'], item['weightClass'], item['cover'], item.get('coverLocal', ''),
                    item['back'], item.get('backLocal', ''), item.get('record',''),item.get('age',''),item.get('status',''),item.get('home_town',''),
                    item.get('team',''),item.get('style',''),item.get('height',''),item.get('weight',''),item.get('reach',''),item.get('leg_reach','')
                                  ,item.get('debut',''),item.get('nick_name',''),str(json.dumps(item.get('winsStats'))),
                    str(json.dumps(item.get('history'))),item.get('name_cn',''),item.get('flag',''),item.get('nick_name_cn',''),
                    str(json.dumps(item.get('history_cn',[]))),item.get('home_town_cn',''))
          )
          self.json_exporter.export_item(item)
        return item

    def close_spider(self, spider):
        if isinstance(spider, UpcomingSpider) or isinstance(spider, EventpassSpider) or isinstance(spider, RankingSpider)or isinstance(spider, AthleteSpider):
            # 声明 exporting 过程 结束，结束后，JsonItemExporter 会将收集存放在内存中的所有数据统一写入文件中
            self.json_exporter.finish_exporting()
            # 关闭文件
            self.json_file.close()
            with open(self.translate_file_path, "w", encoding='utf-8') as file:
                file.write(str(json.dumps(self.translate_total)))
        if isinstance(spider, AthleteSpider):
            # # 5. 提交更改
            self.conn.commit()
            # 7. 关闭连接
            self.conn.close()

    def translate_real(self,value):
        print("翻译原文:",value)
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM translate WHERE original = ?", (value,))
        result = cursor.fetchone()
        if result is not None:
            print("已存在不需要翻译:", result[1])
            return result[2]
        else:
            tr_result=""
            translator = Translator(service_urls=['translate.google.com', ])
            try:
                tr_result=translator.translate(value, "zh-CN", "en").text
                print("翻译译文:" + tr_result)
            except Exception as e:
                print(f"翻译发生异常: {e}")
            if len(tr_result)>0:
                self.cursor.execute(
                    '''
                    INSERT OR IGNORE INTO translate (original,translation) 
                    VALUES (?,?)
                    ''', (value, tr_result)
                )
            return tr_result

    def translate(self,item,key):
        tr_key=key+"_cn"
        value=item.get(key,None)
        if key in item and value is not None and len(value)>0:
            if type(value) is list:
               # 判断类型是否是列表类型
               tr_list=[]
               for i in item[key]:
                 if i.strip():
                    tr_list.append(self.translate_real(i))
               item[tr_key]=tr_list
            else:
                # 是字符串类型
               item[tr_key]=self.translate_real(value)

