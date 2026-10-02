import json
import os

import scrapy

from ..items import UfcCnNewsItem


class UfcCnNewsSpider(scrapy.Spider):
    """UFC 中文站新闻爬虫

    通过 ufc.cn 官方 API（Handler.ashx）抓取新闻列表，
    输出到 RSS 订阅源（与赛程共用 ufc_schedule.xml）。

    列表接口 method=NewsList 的 Details 只是服务端硬截断的 50 字预览
    （实测 920/1000 条以 "..." 结尾，英文人名还会丢空格），因此对未发布过
    的条目再调一次 method=NewsDetails 拿全文正文；图集（Type=1）取
    ImageList，视频（Type=2）取播放地址。

    注意：Scrapy 2.19 + AsyncioSelectorReactor 下，
    纯 start_requests + FormRequest 可能导致调度器不启动，
    因此通过 start_urls 触发一次 GET 后再发起真实 POST 请求。
    """

    name = "ufccn_news"
    allowed_domains = ["www.ufc.cn"]

    # 触发起始请求的占位 URL（真实请求在 parse 中发起 POST）
    start_urls = ["http://www.ufc.cn/Api/Handler.ashx"]

    UFC_CN_BASE = "http://www.ufc.cn"
    API_URL = "http://www.ufc.cn/Api/Handler.ashx"
    PUBLISHED_IDS_PATH = 'output/rss/published_ids.json'

    # 单轮最多补抓多少篇全文。正常情况下每天新增个位数，
    # 这个上限只用于兜住 published_ids.json 缺失时的首次运行。
    MAX_DETAIL_REQUESTS = 60

    def parse(self, response):
        """发起 POST 请求获取新闻列表"""
        yield scrapy.FormRequest(
            url=self.API_URL,
            formdata={"method": "NewsList"},
            callback=self.parse_news,
            dont_filter=True,
        )

    def _published_news_ids(self):
        """读取已发布的新闻 ID，用来判断哪些条目需要补抓全文。

        返回 None 表示文件缺失或损坏，此时无法区分新旧条目，
        调用方应退化为「只处理最新的一批」。
        """
        if not os.path.exists(self.PUBLISHED_IDS_PATH):
            return None
        try:
            with open(self.PUBLISHED_IDS_PATH, 'r', encoding='utf-8') as f:
                keys = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self.logger.warning(f"[新闻] 读取 published_ids.json 失败，退化为只抓最新条目: {e}")
            return None
        return {k for k in keys if isinstance(k, str) and k.startswith('news:')}

    def parse_news(self, response):
        """解析新闻列表，并对新增条目追加详情请求"""
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.error(f"新闻接口返回非 JSON: {response.text[:200]}")
            return

        if data.get("errcode") != 0:
            self.logger.error(f"新闻接口错误: errcode={data.get('errcode')}, errmsg={data.get('errmsg')}")
            return

        result = data.get("result", [])
        self.logger.info(f"抓取到 {len(result)} 条 UFC 中文新闻")

        published = self._published_news_ids()
        budget = self.MAX_DETAIL_REQUESTS
        capped = False

        for item_data in result:
            item = self._build_item(item_data)
            if item is None:
                continue

            is_new = published is None or f"news:{item['id']}" not in published
            if not is_new:
                # 已发布过，管线会按 ID 过滤掉，没必要再发详情请求
                yield item
                continue

            if budget <= 0:
                # 额度用尽就不再产出该条目，管线不会把它记为已发布，
                # 下一轮会自动重试（正常情况下每天新增远低于上限）
                if not capped:
                    self.logger.warning(
                        f"[新闻] 详情请求已达单轮上限 {self.MAX_DETAIL_REQUESTS} 条，"
                        "剩余新增条目顺延到下一轮")
                    capped = True
                continue

            budget -= 1
            yield scrapy.FormRequest(
                url=self.API_URL,
                formdata={"method": "NewsDetails", "ID": str(item["id"])},
                callback=self.parse_detail,
                errback=self.detail_failed,
                dont_filter=True,
                meta={"item": item},
            )

    def _build_item(self, item_data):
        """把列表接口的一条记录组装成 item（详情字段留空待补）"""
        art_id = item_data.get("ID")
        if art_id in (None, ""):
            return None

        item = UfcCnNewsItem()
        item["id"] = art_id
        item["title"] = item_data.get("Title", "")
        item["details"] = item_data.get("Details", "")
        item["type"] = item_data.get("Type", 0)

        # 封面补全为完整 URL
        mp_cover = item_data.get("MpCover", "")
        if mp_cover and not mp_cover.startswith("http"):
            item["cover"] = self.UFC_CN_BASE + mp_cover
        else:
            item["cover"] = mp_cover

        item["time_str"] = item_data.get("Time", "")

        # 拼接详情页 URL（和 Android 端逻辑一致）
        art_type = item_data.get("Type", 0)
        if art_type == 1:
            prefix = "article_atlas.html"
        elif art_type == 2:
            prefix = "article_video.html"
        else:
            prefix = "article.html"
        item["url"] = f"{self.UFC_CN_BASE}/{prefix}?ArtId={art_id}&ArtType={art_type}"

        item["body"] = ""
        item["images"] = []
        item["video_url"] = ""
        item["video_type"] = None
        return item

    def parse_detail(self, response):
        """把详情接口返回的正文/图集/视频补进 item"""
        item = response.meta["item"]

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.warning(f"[新闻] {item['id']} 详情返回非 JSON，退回列表摘要")
            yield item
            return

        detail = data.get("result") or {}
        if data.get("errcode") != 0 or not isinstance(detail, dict):
            self.logger.warning(f"[新闻] {item['id']} 详情接口异常，退回列表摘要")
            yield item
            return

        art_type = item.get("type", 0)
        if art_type == 1:
            # 图集：正文为空，内容全在 ImageList
            item["images"] = detail.get("ImageList") or []
        elif art_type == 2:
            # 视频：详情接口的 Details 就是播放地址，不是 HTML
            item["video_url"] = detail.get("Details") or ""
            item["video_type"] = detail.get("VideoType")
        else:
            item["body"] = detail.get("Details") or ""

        yield item

    def detail_failed(self, failure):
        """详情请求失败时退回列表摘要，不丢条目"""
        item = failure.request.meta.get("item")
        self.logger.warning(f"[新闻] 详情请求失败，退回列表摘要: {failure.value}")
        if item is not None:
            yield item
