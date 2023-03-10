# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class UfcPassItem(scrapy.Item):
    title = scrapy.Field()                      # 标题
    url = scrapy.Field()                        # 链接
    mainCardTimestamp = scrapy.Field()          # 主卡开始时间戳
    prelimsCardTimestamp = scrapy.Field()       # 副卡开始时间戳
    dataEarlyCardTimestamp = scrapy.Field()     # 早卡开始时间戳
    address = scrapy.Field()                    # 举办地
    fightCards = scrapy.Field()                 # 战卡
    banner = scrapy.Field()                     # 封面
    bannerLocal = scrapy.Field()                # 封面本地地址
    redPlayerCover = scrapy.Field()             # 红方封面地址
    bluePlayerCover = scrapy.Field()            # 蓝方封面地址


class UfcPassCardItem(scrapy.Item):
    weightClass = scrapy.Field()                # 级别
    cardType = scrapy.Field()                   # 战卡级别
    endRound = scrapy.Field()                   # 结束回合
    endTime = scrapy.Field()                    # 结束时间
    endMethod = scrapy.Field()                  # 结束方式

    redPlayerName = scrapy.Field()
    redPlayerPage = scrapy.Field()
    redPlayerOdds = scrapy.Field()
    redPlayerCountry = scrapy.Field()
    redPlayerBack = scrapy.Field()
    redPlayerBackLocal = scrapy.Field()
    redPlayerResult = scrapy.Field()
    redPlayerCountryCode = scrapy.Field()

    bluePlayerName = scrapy.Field()
    bluePlayerPage = scrapy.Field()
    bluePlayerOdds = scrapy.Field()
    bluePlayerCountry = scrapy.Field()
    bluePlayerCountryCode = scrapy.Field()
    bluePlayerBack = scrapy.Field()
    bluePlayerBackLocal = scrapy.Field()
    bluePlayerResult = scrapy.Field()
    redPlayerCountryEmoji=scrapy.Field()
    bluePlayerCountryEmoji=scrapy.Field()


class UfcComingItem(scrapy.Item):
    fightName = scrapy.Field()                      # 战斗名称
    title = scrapy.Field()                          # 标题
    url = scrapy.Field()                            # 链接
    mainCardTimestamp = scrapy.Field()              # 主卡开始时间戳
    prelimsCardTimestamp = scrapy.Field()           # 副卡开始时间戳
    dataEarlyCardTimestamp = scrapy.Field()         # 早卡开始时间戳
    address = scrapy.Field()                        # 举办地
    fightCards = scrapy.Field()                       # 战卡
    banner = scrapy.Field()                         # 封面
    bannerLocal = scrapy.Field()                    # 封面本地地址
    bannerItem = scrapy.Field()
    matchupID = scrapy.Field()


class UfcComingBannerItem(scrapy.Item):
    redPlayerCover = scrapy.Field()
    redPlayerCoverLocal = scrapy.Field()
    bluePlayerCover = scrapy.Field()
    bluePlayerCoverLocal = scrapy.Field()
    fightLable = scrapy.Field()                     # 对战名称


class UfcComingCardItem(scrapy.Item):
    cardType = scrapy.Field()                       # 战卡级别
    weightClass = scrapy.Field()                    # 级别
    matchupStats = scrapy.Field()                   # 扩展信息

    redPlayerName = scrapy.Field()
    redPlayerPage = scrapy.Field()
    redPlayerOdds = scrapy.Field()
    redPlayerCountry = scrapy.Field()
    redPlayerBack = scrapy.Field()
    redPlayerBackLocal = scrapy.Field()
    redPlayerCountryCode = scrapy.Field()
    redPlayerRank = scrapy.Field()

    bluePlayerName = scrapy.Field()
    bluePlayerPage = scrapy.Field()
    bluePlayerOdds = scrapy.Field()
    bluePlayerCountry = scrapy.Field()
    bluePlayerCountryCode = scrapy.Field()
    bluePlayerBack = scrapy.Field()
    bluePlayerBackLocal = scrapy.Field()
    bluePlayerRank = scrapy.Field()
    redPlayerCountryEmoji=scrapy.Field()
    bluePlayerCountryEmoji=scrapy.Field()
    
    fightId = scrapy.Field()


class UfcRankingItem(scrapy.Item):
    rankName = scrapy.Field()
    players = scrapy.Field()

class UfcRankingPlayer(scrapy.Item):
    name=scrapy.Field()
    nickName=scrapy.Field()
    cover=scrapy.Field()
    coverLocal=scrapy.Field()
    weightClass = scrapy.Field()
    playerPage=scrapy.Field()
    historys=scrapy.Field()
    biosInfos=scrapy.Field()
    playerTags=scrapy.Field()
    winsStats=scrapy.Field()
    record=scrapy.Field()
    back=scrapy.Field()
    ranking=scrapy.Field()
    backLocal=scrapy.Field()


