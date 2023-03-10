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
from _io import BytesIO
from ufcjson.items import UfcComingItem
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
class UfcjsonPipeline:
    def process_item(self, item, spider):
       if isinstance(item,UfcPassItem):
            pass
       if isinstance(item,UfcComingCardItem):
            pass
       if isinstance(item,UfcRankingItem):
            pass
       return item     

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
                if item['cover']==None or not item['cover'].startswith('http'):
                    item['cover']='https://www.ufc.com/themes/custom/ufc/assets/img/no-profile-image.png'       
           
            if item['back']==None or not item['back'].startswith('http'):
               item['back']='https://dmxg5wxfqgb4u.cloudfront.net/styles/event_fight_card_upper_body_of_standing_athlete/s3/image/fighter_images/SHADOW_Fighter_fullLength_RED.png?VersionId=0NwYm4ow5ym9PWjgcpd05ObDBIC5pBtX&itok=woJQm5ZH'  
       return item     

# 用于将国籍code修改为Emoji表情的管道
class UfcCountryCodePipeline:
    def process_item(self, item, spider):
       if isinstance(item,UfcPassCardItem) or isinstance(item,UfcComingCardItem):
            red_images=item['redPlayerCountryCode'].split('/')
            blue_images=item['bluePlayerCountryCode'].split('/')
            item['redPlayerCountryEmoji']=country.get_country_flag_emoji(red_images[len(red_images)-1].replace('.PNG',''))
            item['bluePlayerCountryEmoji']=country.get_country_flag_emoji(blue_images[len(blue_images)-1].replace('.PNG',''))
       return item   

class UfcRssMakerPipeline:
    def __init__(self):
        self.rssMaker=RssMaker( title="UFC赛程",link='https://www.ufc.com/events#events-list-upcoming',description="新的UFC赛程")
        self.rssList=[]
    def process_item(self, item, spider):
       if isinstance(item,UfcComingCardItem):
            title=item['redPlayerName']+"VS"+item['bluePlayerName']
            self.rssList.append({'title':title,
            'link':"",
            'description':self.rssMaker.get_html_str(title,item['redPlayerBackLocal'],item['bluePlayerBackLocal'])})
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
        images={x['url']:x for ok, x in results if ok}
        if len(images.keys())==0:
            return item
        if isinstance(item,UfcPassItem):
             if item['banner'] in images.keys() :
                  item['bannerLocal']=images[item['banner']]['path']              
        if isinstance(item,UfcPassCardItem):
            if item['redPlayerBack'] in images.keys() :
                  item['redPlayerBackLocal']=images[item['redPlayerBack']]['path']    
            if item['bluePlayerBack'] in images.keys() :
                  item['bluePlayerBackLocal']=images[item['bluePlayerBack']]['path']              
        if isinstance(item,UfcComingItem):
             if item['banner'] in images.keys() :
                  item['bannerLocal']=images[item['banner']]['path']           
        if isinstance(item,UfcComingBannerItem):
            if item['redPlayerCover'] in images.keys() :
                  item['redPlayerCoverLocal']=images[item['redPlayerCover']]['path']    
            if item['bluePlayerCover'] in images.keys() :
                  item['bluePlayerCoverLocal']=images[item['bluePlayerCover']]['path']            
        if isinstance(item,UfcComingCardItem):
            if item['redPlayerBack'] in images.keys() :
                  item['redPlayerBackLocal']=images[item['redPlayerBack']]['path']    
            if item['bluePlayerBack'] in images.keys() :
                  item['bluePlayerBackLocal']=images[item['bluePlayerBack']]['path']  

        if isinstance(item, UfcRankingPlayer) :
            #print("图片下载完毕:",images.keys())
            if item['back'] in images.keys() :
                  item['backLocal']=images[item['back']]['path']      
            if 'cover'in item and item['cover'] in images.keys() :
                  item['coverLocal']=images[item['cover']]['path']                      
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
                "method called without response_body argument.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
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
            self.make_json_file('ufc_coming_data.json',spider)
        if isinstance(spider, EventpassSpider):
            self.make_json_file('ufc_pass_data.json',spider)
        if isinstance(spider, RankingSpider):
            self.make_json_file('ufc_ranking_data.json',spider)
        if isinstance(spider, AthleteSpider):
            self.make_json_file('ufc_athlete_data_temp.json',spider)
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
        if isinstance(item,UfcRankingItem):
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
            shutil.copyfile('ufc_athlete_data_temp.json','ufc_athlete_data.json')
            os.remove('ufc_athlete_data_temp.json')           

class JsonWriterTranslatorPipeline(object):
    # 构造方法（初始化对象时执行的方法）
    def __init__(self):
        pass
    def open_spider(self,spider):    
        #读取所有的翻译
        self.translate_total={}
        self.translate_file_path='./ufc_translat.json'
        if os.path.exists(self.translate_file_path):
            with open(self.translate_file_path,'r', encoding="utf-8") as file:
                self.translate_total = json.load(file)
        if isinstance(spider, UpcomingSpider):
            self.make_json_file('ufc_coming_data_zh.json',spider)
        if isinstance(spider, EventpassSpider):
            self.make_json_file('ufc_pass_data_zh.json',spider)
        if isinstance(spider, RankingSpider):
            self.make_json_file('ufc_ranking_data_zh.json',spider)
        if isinstance(spider, AthleteSpider):
            self.make_json_file('ufc_athlete_data_zh.json',spider)

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
                self.translate(i,'historys')
                self.translate(i,'name')
                self.translate(i,'weightClass')
            self.json_exporter.export_item(item)

        if isinstance(spider, AthleteSpider) and isinstance(item,UfcRankingPlayer):
          self.translate(item,'historys')  
          self.translate(item,'name')
          self.translate(item,'weightClass')
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

    def translate(self,item,key):
        if key in item and item[key] is not None and len(item[key])>0:
            # 判断类型是否是列表类型
            if type(item[key]) is list:
               tr_list=[] 
               for i in item[key]:
                 valueHash=hashlib.sha1(to_bytes(i)).hexdigest()
                 if valueHash in self.translate_total:
                    logging.debug("无需进行翻译:"+i) 
                    tr_list.append(self.translate_total[valueHash])
                 else:
                    #logging.debug("需要进行翻译:",i)
                    if len(i.strip())>0 :
                        translator = Translator(service_urls=['translate.google.com',])
                        tr_result=translator.translate(i, "zh-CN", "en").text
                        tr_list.append(tr_result)
                        self.translate_total[valueHash]=tr_result
               item[key]=tr_list
               return     
            # 是字符串类型   
            valueHash=hashlib.sha1(to_bytes(item[key])).hexdigest()
            #print("计算出来的hash值:",valueHash)
            if valueHash in self.translate_total:
               logging.debug("无需进行翻译:"+item[key]) 
               item[key]=self.translate_total[valueHash]     
               return     
            logging.debug("需要进行翻译:")
            translator = Translator(service_urls=['translate.google.com',])
            item[key]=translator.translate(item[key], "zh-CN", "en").text
            self.translate_total[valueHash]=item[key]
            #print("翻译完毕:",item[key])