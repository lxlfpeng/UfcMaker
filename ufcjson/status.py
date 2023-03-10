from scrapy.statscollectors import StatsCollector
from scrapy.utils.serialize import ScrapyJSONEncoder

from .spiders.upcoming import UpcomingSpider
from .spiders.eventpass import EventpassSpider
from .spiders.ranking import RankingSpider
from .spiders.athlete import AthleteSpider

# 状态收集器


class SaveStatsCollector(StatsCollector):

    def _persist_stats(self, stats, spider):
        path = ""
        if isinstance(spider, UpcomingSpider):
            path = './log/upcoming_status.json'
            print("UpcomingSpider统计数据:")
        if isinstance(spider, EventpassSpider):
            path = './log/eventpass_status.json'
            print("Eventpass统计数据:")
        if isinstance(spider, RankingSpider):
            path = './log/ranking_status.json'
            print("RankingSpider统计数据:")
        if isinstance(spider, AthleteSpider):
            path = './log/athlete_status.json'
            print("AthleteSpiderSpider统计数据:")
        encoder = ScrapyJSONEncoder()
        with open(path, "wb") as file:
            data = encoder.encode(stats)
            file.write(data.encode())
