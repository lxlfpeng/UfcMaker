import os
from scrapy import cmdline
import json
import time
from send_email import EmilTools
import argparse
#通过启动附加参数获取到email的密码
parser = argparse.ArgumentParser(description='manual to this script')
parser.add_argument("--email_pass", type=str,default="", help='input email_pass')
email_pass=parser.parse_args().email_pass

#启动爬虫
os.system("scrapy crawl upcoming")
#os.system("scrapy crawl eventpass")
#os.system("scrapy crawl ranking")

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

#取出所有日志,组成字符串
out_str=''
for file_name in os.listdir('./log'):
    with open('./log/'+file_name,'r', encoding='utf-8') as file:
        out_str+='\n'+file_name+':\n'
        out_str+=json.dumps(json.load(file), indent=2)
#发送爬虫日志邮件
EmilTools().send_email(email_pass,'UFC.Com数据抓取',out_str)