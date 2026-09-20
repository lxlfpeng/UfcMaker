# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals
from scripts.send_email import EmailTools
# useful for handling different item types with a single interface
from itemadapter import is_item, ItemAdapter
import os

class UfcjsonSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    def __init__(self):
        self.crawler = None

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        s.crawler = crawler
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    async def process_spider_output_async(self, response, result):
        # 异步版本，供 Scrapy 2.16+ 的异步引擎使用
        async for i in result:
            yield i

    def process_spider_exception(self, response, exception):
        import traceback
        email_pwd = os.environ.get('email_pwd')
        spider = self.crawler.spider if self.crawler else None
        err_msg = (
            f"Spider异常: spider={spider}, url={response.url}, "
            f"status={response.status}, exception={exception}\n"
            f"{traceback.format_exc()}"
        )
        if spider:
            spider.logger.error(err_msg)
        else:
            print(err_msg)
        if email_pwd:
            EmailTools().send_email(email_pwd, 'UFC.Com数据抓取', err_msg)
        return []

    async def process_start(self, start):
        # 供 Scrapy 2.13+ 使用，替代 process_start_requests
        async for r in start:
            yield r

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class UfcjsonDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)
