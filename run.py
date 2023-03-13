import os
from scrapy import cmdline
import json
import time
# os.system("scrapy crawl eventpass")
# os.system("scrapy crawl upcoming")
# os.system("scrapy crawl ranking")

# should=True
# path='./ufc_athlete_data.json'
# if os.path.exists(path):
#     with open(path, 'r',encoding='utf-8') as file:
#         try:
#             diff=stamp=int(round(time.time() * 1000))-json.load(file)['timeStamp']
#             if diff<30*24*60*60*1000:
#                 should=False
#         except Exception:
#             pass
# if should:
#    os.system("scrapy crawl athlete") 


#cmdline.execute("scrapy crawl ranking".split())


cmdline.execute("scrapy crawl upcoming".split())