import scrapy
from ..items import UfcRankingItem


class RankingSpider(scrapy.Spider):
    name = "ranking"
    allowed_domains = ["www.ufc.com"]
    start_urls = ["https://www.ufc.com/rankings"]

    def parse(self, response):
        # 全局按级别去重：页面上可能有多套排名（如不同 view），只取第一套
        seen_ranks = set()

        groups = response.xpath('//div[@class="view-grouping"]')
        for group in groups:
            rank_name = group.xpath('.//div[@class="view-grouping-header"]/text()').get(default='').strip()
            if not rank_name:
                continue

            # 已处理过该级别，跳过（避免多套排名重复）
            if rank_name in seen_ranks:
                continue
            seen_ranks.add(rank_name)

            is_pound_for_pound = 'pound-for-pound' in rank_name.lower()
            seen_players = set()

            # ---- 1. 抓取冠军（表格上方的冠军展示区，rank=0）----
            # UFC 排名页中，冠军（金腰带持有者）显示在排名表格的上方
            # Pound-for-Pound 没有冠军，跳过
            if not is_pound_for_pound:
                champ_name, champ_href = self._find_champion(group)
                if champ_name and champ_href:
                    seen_players.add(champ_name)
                    player = UfcRankingItem()
                    player['rank_name'] = rank_name
                    player['name'] = champ_name
                    player['rank'] = 0
                    player['page'] = response.urljoin(champ_href)
                    self.logger.info("排名选手: [%s] #冠军 %s", rank_name, champ_name)
                    yield player

            # ---- 2. 抓取第一个排名表格（挑战者 1-15 名）----
            # 同一级别内可能有多个 table（不同视图），只取第一个
            table = group.xpath('(.//table)[1]')
            rows = table.xpath('.//tbody//tr')
            if not rows:
                rows = table.xpath('.//tr[td]')

            for row in rows:
                # 第一列：排名数字
                rank_text = row.xpath('./td[1]//text()').get(default='').strip()
                # 选手名字链接（优先第二列，否则找行内第一个 athlete 链接）
                name_link = row.xpath('./td[2]//a[contains(@href,"/athlete/")]')
                if not name_link:
                    name_link = row.xpath('.//a[contains(@href, "/athlete/")]')
                if not name_link:
                    continue

                name = name_link.xpath('./text()').get(default='').strip()
                href = name_link.xpath('./@href').get(default='').strip()
                if not name or not href:
                    continue

                # 同级别内同名去重（冠军已抓过的不再抓）
                if name in seen_players:
                    continue
                seen_players.add(name)

                # 解析排名数字
                try:
                    rank = int(rank_text)
                except ValueError:
                    # 非数字跳过（如 "C"、"NR"、空等）
                    continue

                player = UfcRankingItem()
                player['rank_name'] = rank_name
                player['name'] = name
                player['rank'] = rank
                player['page'] = response.urljoin(href)
                self.logger.info("排名选手: [%s] #%d %s", rank_name, rank, name)
                yield player

    def _find_champion(self, group):
        """从分组中查找冠军选手的名字和链接，返回 (name, href) 或 (None, None)"""
        # 尝试1：冠军标题区
        link = group.xpath('.//*[contains(@class,"rankings--title")]//a[contains(@href,"/athlete/")]')
        # 尝试2：champion 类容器
        if not link:
            link = group.xpath('.//div[contains(@class,"champion")]//a[contains(@href,"/athlete/")]')
        # 尝试3：表格之前的第一个 athlete 链接（在本分组内）
        if not link:
            # 用第一个 table 之前、且在 view-grouping-content 内的链接
            link = group.xpath(
                './/div[contains(@class,"view-grouping-content")]'
                '/table[1]/preceding-sibling::*//a[contains(@href,"/athlete/")][last()]'
            )
        if not link:
            return None, None

        name = link.xpath('./text()').get(default='').strip()
        href = link.xpath('./@href').get(default='').strip()
        return name if name else None, href if href else None
