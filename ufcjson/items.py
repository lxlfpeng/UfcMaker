# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class UfcPassItem(scrapy.Item):
    # 标题
    title = scrapy.Field()
    # 名称
    name = scrapy.Field()
    # 链接
    url = scrapy.Field()
    # 主卡开始时间戳
    main_time = scrapy.Field()
    # 副卡开始时间戳
    prelims_time = scrapy.Field()
    # 早卡开始时间戳
    data_early_time = scrapy.Field()
    # 举办地
    address = scrapy.Field()
    # 封面
    banner = scrapy.Field()
    # 封面本地地址
    banner_local = scrapy.Field()
    # 战卡
    fightCards = scrapy.Field()
    # 红方封面地址
    redPlayerCover = scrapy.Field()
    # 蓝方封面地址
    bluePlayerCover = scrapy.Field()


class UfcPassCardItem(scrapy.Item):
    # 级别
    weightClass = scrapy.Field()
    # 战卡类型
    cardType = scrapy.Field()
    # 结束回合
    endRound = scrapy.Field()
    # 结束时间
    endTime = scrapy.Field()
    # 结束方式
    endMethod = scrapy.Field()
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
    redPlayerCountryEmoji = scrapy.Field()
    bluePlayerCountryEmoji = scrapy.Field()
    fight_page = scrapy.Field()


class UfcComingItem(scrapy.Item):
    # 战斗名称
    name = scrapy.Field()
    # 标题
    title = scrapy.Field()
    # 链接
    page = scrapy.Field()
    # 主卡开始时间戳
    main_time = scrapy.Field()
    # 副卡开始时间戳
    prelims_time = scrapy.Field()
    # 早卡开始时间戳
    data_early_time = scrapy.Field()
    # 举办地
    address = scrapy.Field()
    # 举办地(CN)
    address_cn = scrapy.Field()
    # 封面
    banner = scrapy.Field()
    # 封面本地地址
    banner_local = scrapy.Field()
    # 战卡
    fight_card = scrapy.Field()
    # 封面战卡
    bannerItem = scrapy.Field()


class UfcComingCardItem(scrapy.Item):
    # 战卡级别
    card_type = scrapy.Field()
    # 级别
    card_division = scrapy.Field()
    # # 扩展信息
    # matchupStats = scrapy.Field()
    # 主卡开始时间戳
    main_time = scrapy.Field()
    # 举办地
    address = scrapy.Field()
    # 名称
    fight_name = scrapy.Field()
    # 红方主页
    red_page = scrapy.Field()
    #蓝方主页
    blue_page = scrapy.Field()
    #红方赔率
    red_odds = scrapy.Field()
    #蓝方赔率
    blue_odds = scrapy.Field()
    #红方排名
    red_rank = scrapy.Field()
    #蓝方排名
    blue_rank = scrapy.Field()

    fightId = scrapy.Field()


class UfcRankingItem(scrapy.Item):
    #名字
    name = scrapy.Field()
    #主页
    page = scrapy.Field()
    #榜单名称
    rank_name = scrapy.Field()
    #排名
    rank = scrapy.Field()
    # 排名(中文)
    rank_name_cn = scrapy.Field()

class UfcPlayerItem(scrapy.Item):
    # 名字
    name = scrapy.Field()
    # 昵称
    nick_name = scrapy.Field()
    # 封面
    cover = scrapy.Field()
    # 本地封面
    coverLocal = scrapy.Field()
    # 体重级别
    weightClass = scrapy.Field()
    # 个人主页
    playerPage = scrapy.Field()

    biosInfos = scrapy.Field()
    playerTags = scrapy.Field()
    winsStats = scrapy.Field()
    # 战绩
    record = scrapy.Field()
    # 背景图片
    back = scrapy.Field()
    ranking = scrapy.Field()
    # 背景图片(本地)
    backLocal = scrapy.Field()
    rankName = scrapy.Field()
    # 历史
    history = scrapy.Field()
    # 历史中文
    history_cn = scrapy.Field()
    # 体重
    weight = scrapy.Field()
    # 状态
    status = scrapy.Field()
    # 年龄
    age = scrapy.Field()
    # 国籍
    home_town = scrapy.Field()
    # 国籍(中文)
    home_town_cn = scrapy.Field()
    # 团队
    team = scrapy.Field()
    # 风格
    style = scrapy.Field()
    # 身高
    height = scrapy.Field()
    # 臂展
    reach = scrapy.Field()
    # 腿长
    leg_reach = scrapy.Field()
    # 首次亮像
    debut = scrapy.Field()
    # 获胜方式
    wins_stats = scrapy.Field()
    # 用户名(中文)
    name_cn = scrapy.Field()
    # 国旗
    flag = scrapy.Field()
    # 中文昵称
    nick_name_cn = scrapy.Field()
