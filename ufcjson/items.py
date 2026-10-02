# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy

class UfcPassItem(scrapy.Item):
    # 标题
    title = scrapy.Field()
    # 标题(中文)
    title_cn = scrapy.Field()
    # 名称
    name = scrapy.Field()
    # 名称(中文)
    name_cn = scrapy.Field()
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
    # 举办城市（从 address 拆出，如 Las Vegas）
    city = scrapy.Field()
    # 举办国家（从 address 拆出，如 United States）
    country = scrapy.Field()
    # 举办城市(中文)，如 拉斯维加斯
    city_cn = scrapy.Field()
    # 举办国家(中文)，如 美国
    country_cn = scrapy.Field()
    # 封面
    banner = scrapy.Field()
    # 封面本地地址
    banner_local = scrapy.Field()
    # 战卡
    fight_cards = scrapy.Field()


class UfcPassCardItem(scrapy.Item):
    # 级别
    card_division = scrapy.Field()
    # 级别(中文)
    card_division_cn = scrapy.Field()
    # 战卡类型
    card_type = scrapy.Field()
    # 结束回合
    end_round = scrapy.Field()
    # 结束时间
    end_time = scrapy.Field()
    # 结束方式
    end_method = scrapy.Field()
    # 结束方式(中文)
    end_method_cn = scrapy.Field()
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
    # 举办城市（从 address 拆出，如 Las Vegas）
    city = scrapy.Field()
    # 举办国家（从 address 拆出，如 United States）
    country = scrapy.Field()
    # 举办城市(中文)，如 拉斯维加斯
    city_cn = scrapy.Field()
    # 举办国家(中文)，如 美国
    country_cn = scrapy.Field()
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
    # 体重级别(中文)
    division_cn = scrapy.Field()
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
    # 状态(中文)
    status_cn = scrapy.Field()
    # 出生日期(YYYY-MM-DD 精确 / YYYY 只知年份)
    birthdate = scrapy.Field()
    # 出生地(城市, 国家)
    home_town = scrapy.Field()
    # 城市
    city = scrapy.Field()
    # 城市(中文)
    city_cn = scrapy.Field()
    # 国家
    country = scrapy.Field()
    # 国家(中文)
    country_cn = scrapy.Field()
    # 团队
    team = scrapy.Field()
    # 团队(中文)
    team_cn = scrapy.Field()
    # 风格
    style = scrapy.Field()
    # 风格(中文)
    style_cn = scrapy.Field()
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
    # 获胜方式(中文)
    wins_stats_cn = scrapy.Field()
    # 用户名(中文)
    name_cn = scrapy.Field()
    # 国旗
    flag = scrapy.Field()
    # 中文昵称
    nick_name_cn = scrapy.Field()

    # ranking = scrapy.Field()
    # rankName = scrapy.Field()


class UfcCnNewsItem(scrapy.Item):
    """UFC 中文站新闻条目（用于 RSS 输出）"""
    # 新闻ID
    id = scrapy.Field()
    # 标题
    title = scrapy.Field()
    # 列表接口的摘要（50 字截断预览，仅作正文抓取失败时的兜底）
    details = scrapy.Field()
    # 详情接口的富文本正文（<p>/<br>/<strong>/<a>，原始值，渲染时清洗）
    body = scrapy.Field()
    # 图集图片列表 [{Image, Title}, ...]（Type=1）
    images = scrapy.Field()
    # 视频地址（Type=2 时详情接口的 Details 就是播放地址）
    video_url = scrapy.Field()
    # 视频类型 1=直链 2=iframe
    video_type = scrapy.Field()
    # 类型 0=图文 1=图集 2=视频
    type = scrapy.Field()
    # 移动端封面(完整 URL)
    cover = scrapy.Field()
    # 发布时间字符串
    time_str = scrapy.Field()
    # 详情页URL
    url = scrapy.Field()