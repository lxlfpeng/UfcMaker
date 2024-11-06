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
    # 举办地(CN)
    address_cn = scrapy.Field()
    # 封面
    banner = scrapy.Field()
    # 封面本地地址
    banner_local = scrapy.Field()
    # 战卡
    fight_cards = scrapy.Field()


class UfcPassCardItem(scrapy.Item):
    # 级别
    card_division = scrapy.Field()
    # 战卡类型
    card_type = scrapy.Field()
    # 结束回合
    end_round = scrapy.Field()
    # 结束时间
    end_time = scrapy.Field()
    # 结束方式
    end_method = scrapy.Field()
    # 红方主页
    red_page = scrapy.Field()
    # 蓝方主页
    blue_page = scrapy.Field()
    # 红方结果
    red_result = scrapy.Field()
    # 蓝方结果
    blue_result = scrapy.Field()
    # 红方odds
    red_odds = scrapy.Field()
    # 蓝方odds
    blue_odds = scrapy.Field()
    # 主页
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
    # 主卡开始时间戳
    main_time = scrapy.Field()
    # 举办地
    address = scrapy.Field()
    # 名称
    fight_name = scrapy.Field()
    # 红方主页
    red_page = scrapy.Field()
    # 蓝方主页
    blue_page = scrapy.Field()
    # 红方赔率
    red_odds = scrapy.Field()
    # 蓝方赔率
    blue_odds = scrapy.Field()
    # 红方排名
    red_rank = scrapy.Field()
    # 蓝方排名
    blue_rank = scrapy.Field()
    #id
    fight_id = scrapy.Field()


class UfcRankingItem(scrapy.Item):
    # 名字
    name = scrapy.Field()
    # 主页
    page = scrapy.Field()
    # 榜单名称
    rank_name = scrapy.Field()
    # 排名
    rank = scrapy.Field()
    # 排名(中文)
    rank_name_cn = scrapy.Field()


class UfcPlayerItem(scrapy.Item):
    # 名字
    name = scrapy.Field()
    # 昵称
    nick_name = scrapy.Field()
    # 头像
    avatar = scrapy.Field()
    # 本地头像
    avatar_local = scrapy.Field()
    # 标签
    player_tags = scrapy.Field()
    # 体重级别
    division = scrapy.Field()
    # 个人主页
    page = scrapy.Field()
    #获胜方式
    wins_stats = scrapy.Field()
    # 战绩
    record = scrapy.Field()
    # 封面
    cover = scrapy.Field()
    # 本地封面
    cover_local = scrapy.Field()

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

    # ranking = scrapy.Field()
    # rankName = scrapy.Field()