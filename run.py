import os
from datetime import datetime
import argparse

# 通过启动附加参数获取到email的密码
parser = argparse.ArgumentParser(description='manual to this script')
parser.add_argument("--email_pass", type=str, default="", help='input email_pass')
os.environ['email_pwd'] = parser.parse_args().email_pass


# # 周三爬取排行榜和选手数据
# if datetime.now().weekday() == 2:
#     os.system("scrapy crawl ranking")
#     os.system("scrapy crawl athlete")
#
# # 周三爬取已进行比赛的数据
# if datetime.now().weekday() == 6:
#     os.system("scrapy crawl eventpass")
#
# # 每日爬取赛程
# os.system("scrapy crawl upcoming")

# os.system("scrapy crawl upcoming")
# os.system("scrapy crawl eventpass")
# os.system("scrapy crawl ranking")
os.system("scrapy crawl athlete")
# # os.system("scrapy crawl eventpass -a category=全量")

# 取出所有日志,组成字符串
# out_str=''
# for file_name in os.listdir('./log'):
#     with open('./log/'+file_name,'r', encoding='utf-8') as file:
#         out_str+='\n'+file_name+':\n'
#         out_str+=json.dumps(json.load(file), indent=2)
# #发送爬虫日志邮件
# EmilTools().send_email(email_pass,'UFC.Com数据抓取',out_str)
