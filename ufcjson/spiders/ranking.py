import scrapy
from ..items import UfcRankingItem


class RankingSpider(scrapy.Spider):
    name = "ranking"
    allowed_domains = ["www.ufc.com"]
    start_urls = ["https://www.ufc.com/rankings"]

    # 添加改标签标识可以通过同步方式进行请求
    # @inline_requests
    def parse(self, response):
        info = response.xpath('//div[@class="view-grouping"]')
        # info=info[0:1]
        for weight, i in enumerate(info):
            rankName = i.xpath('.//div[@class="view-grouping-header"]/text()').extract_first()
            playeras = i.xpath('.//a')
            for index, p in enumerate(playeras):
                player = UfcRankingItem()
                player['rank_name'] = rankName
                player['name'] = p.xpath('./text()').extract_first()
                player['rank'] = index
                player['page'] = 'https://www.ufc.com' + p.xpath('./@href').extract_first()
                print("个人主页:", player['page'])
                yield player
