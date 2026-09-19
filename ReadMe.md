# UfcMaker — UFC 赛事数据爬虫

基于 Scrapy 的 UFC（终极格斗冠军赛）官方网站数据爬虫，抓取赛程、战卡、选手排名、运动员档案等结构化数据，支持 JSON 导出、SQLite 持久化、图片下载、自动翻译、RSS 生成等功能。

## 功能特性

- **赛程抓取** — 即将举行的 UFC 赛事（主卡/副卡/早卡时间、举办地、战卡对阵、赔率等）
- **历史战报** — 已结束赛事的完整战卡数据（结束回合、结束方式、对阵结果等），支持全量分页爬取
- **官方排名** — 各体重级别男子/女子排名及 P4P 榜单
- **运动员档案** — 选手基本信息（身高、臂展、体重、年龄、国籍、团队、风格、战绩、历史对战等），支持全量分页爬取
- **图片本地化** — 赛事封面、选手头像自动下载到本地
- **自动翻译** — 爬虫管线只查翻译缓存，跑完后统一由大模型把英文姓名、国籍、级别、战队、历史战绩等字段翻译为中文
- **选手归一化** — 选手主页 URL（slug）变更后自动合并 `player` 表里的多行，并把 `pass_card` 的旧 URL 改写为新 URL
- **多格式导出** — JSON 文件 + SQLite 数据库双写
- **RSS 订阅** — 可生成赛事 RSS Feed（在 `settings.py` 的 `ITEM_PIPELINES` 中开关）
- **定时调度** — 内置按星期自动执行不同爬虫的调度逻辑

## 项目结构

```
UfcMaker/
├── run.py                    # 调度入口（按星期执行不同爬虫）
├── scrapy.cfg                # Scrapy 项目配置
├── requirements.txt          # Python 依赖
├── ufcjson/                  # Scrapy 项目主目录
│   ├── items.py              # 数据结构定义（6 种 Item）
│   ├── settings.py           # 全局配置
│   ├── middlewares.py        # 中间件
│   ├── rss.py                # RSS 生成工具
│   ├── export.py             # 导出工具
│   ├── normalize.py          # 导出层归一化（合并同一选手的多行 + 改写旧 URL）
│   ├── translator.py         # 翻译调度（扫描待翻译字段、回填译文）
│   ├── llm_translator.py     # 大模型翻译后端（OpenAI 兼容接口）
│   ├── inline_requests/      # 内联请求工具
│   ├── spiders/              # 爬虫（共 5 个）
│   │   ├── upcoming.py       # 即将到来的赛事
│   │   ├── eventpass.py      # 历史赛事战报
│   │   ├── ranking.py        # 官方排名
│   │   ├── athlete.py        # 运动员档案
│   │   └── ufccn_news.py     # UFC 中文新闻（供 RSS）
│   └── pipelines/            # 数据管道
│       ├── country_flag.py   # 国旗/国家代码处理
│       ├── image.py          # 图片下载
│       ├── translate.py      # 中文翻译
│       ├── export_json.py    # JSON 导出
│       ├── export_db.py      # SQLite 导出
│       └── rss_export.py     # RSS 导出
├── scripts/                  # 辅助脚本
│   ├── image_maintenance.py  # 图片维护（下载缺失 / 清理未引用）
│   ├── translate.py          # 翻译工具
│   ├── send_email.py         # 邮件通知
│   ├── country.py            # 国家代码映射
│   └── db.py                 # 数据库操作
├── output/                   # 输出目录
│   ├── db/                   # SQLite 数据库
│   ├── json/                 # JSON 导出文件
│   ├── images/full/          # 下载的图片（webp 格式）
│   └── log/                  # 运行日志
└── log/                      # Scrapy 日志（运行时自动创建）
```

## 数据结构

| Item 类 | 说明 | 主要字段 |
|--------|------|---------|
| `UfcComingItem` | 即将到来的赛事 | 标题、链接、主/副/早卡时间戳、举办地、封面、战卡列表 |
| `UfcComingCardItem` | 即将到来的战卡 | 级别、对阵双方主页、赔率、排名 |
| `UfcPassItem` | 已结束赛事 | 同上 + 战卡结果 |
| `UfcPassCardItem` | 已结束战卡 | 结束回合、结束时间、结束方式、红/蓝方结果 |
| `UfcRankingItem` | 排名条目 | 选手名、级别、排名、主页 |
| `UfcPlayerItem` | 运动员档案 | 姓名、昵称、身高、臂展、体重、年龄、国籍、团队、风格、战绩、历史对战 |

## 快速开始

### 环境要求

- Python 3.8+
- Scrapy 2.19+

### 安装依赖

```bash
pip install -r requirements.txt
```

### 单独运行某个爬虫

```bash
# 抓取即将到来的赛事
scrapy crawl upcoming

# 抓取历史赛事（首页）
scrapy crawl eventpass

# 抓取历史赛事（全量分页）
scrapy crawl eventpass -a pagination=true

# 抓取官方排名
scrapy crawl ranking

# 抓取运动员（首页）
scrapy crawl athlete

# 抓取运动员（全量分页）
scrapy crawl athlete -a pagination=true
```

### 使用调度入口运行

`run.py` 会根据当前星期自动选择要执行的爬虫：

| 星期 | 执行的爬虫 | 说明 |
|-----|-----------|------|
| 周三 | `ranking` + `athlete` (全量) | 周中更新排名和选手库 |
| 周日 | `eventpass` | 周末更新比赛结果 |
| 每天 | `upcoming` + `ufccn_news` | 每日更新赛程与 UFC 中文新闻 |

```bash
python run.py

# 带邮箱密码参数（用于日志邮件通知）
python run.py --email_pwd your_password
```

> **爬虫跑完后固定执行三步收尾**（顺序不可调换）：
> 1. `normalize_db()` — 合并被 slug 变更拆开的选手行、改写 `pass_card` 里的旧 URL（见「选手主页 URL 变更与多行归一化」）；
> 2. `translate_db_fields()` — 统一翻译未翻译字段（见「中文翻译」）；
> 3. 图片维护 — 补下载缺失图片、清理未引用图片（见「图片维护」）。
>
> 三步都排在 `generate_meta_json()` 之前，保证 `meta.json` 里的 `db_md5` 是**最终库**的指纹，客户端才能据此判断出需要下载新库。
> 任一步骤抛异常只会打印警告，不中断整个流程。

## 配置说明

核心配置在 `ufcjson/settings.py` 中：

```python
# 管道执行顺序（数字越小优先级越高）
ITEM_PIPELINES = {
   'ufcjson.pipelines.UfcCountryCodePipeline': 1,    # 国家代码处理
   'ufcjson.pipelines.UfcDefaultPhotoPipeline': 2,   # 默认图片填充
   'ufcjson.pipelines.ImagesDownloadPipeline': 3,    # 图片下载
   'ufcjson.pipelines.TranslatorPipeline': 4,        # 中文翻译
   'ufcjson.pipelines.JsonWriterPipeline': 300,      # JSON 导出
   'ufcjson.pipelines.SqliteDbPipeline': 300,        # SQLite 导出
   # 'ufcjson.pipelines.UfcRssMakerPipeline': 300     # RSS 导出（按需开启）
}

# 图片保存目录
IMAGES_STORE = './output/images'
# 图片过期天数（过期会被自动重新下载，默认 20000 天即永不过期）
IMAGES_EXPIRES = 20000

# 日志
LOG_LEVEL = 'INFO'
LOG_FILE = './log/scrapy_log.log'
```

## 输出产物

所有数据文件输出到 `output/` 目录下：

```
output/
├── db/
│   ├── ufc.db                 # 主数据库（赛事、战卡、运动员）
│   └── ufc_translate.db       # 翻译缓存库
├── json/
│   ├── ufc_coming_data.json   # 即将到来的赛事
│   ├── ufc_pass_data.json     # 历史赛事战报（最新 8 场）
│   ├── ufc_ranking_data.json  # 官方排名
│   ├── meta.json              # 数据版本元信息
│   └── app_version.json       # App 版本 & 升级配置
└── images/
    └── full/                  # 下载的图片（webp 格式，文件名 = URL 的 SHA1）
```

### ufc.db — 主数据库

包含 4 张表：

#### pass_event — 历史赛事

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键，自增 |
| `name` | TEXT | 赛事名称 |
| `name_cn` | TEXT | 赛事名称（中文） |
| `title` | TEXT | 头条主赛标题 |
| `title_cn` | TEXT | 头条主赛标题（中文） |
| `banner` | TEXT | 赛事横幅图片 URL |
| `banner_local` | TEXT | 赛事横幅本地路径 |
| `address` | TEXT | 举办地 |
| `address_cn` | TEXT | 举办地（中文） |
| `page` | TEXT | 赛事详情页 URL（唯一） |
| `main_time` | TEXT | 主卡开始时间戳 |
| `prelims_time` | TEXT | 副卡开始时间戳 |
| `data_early_time` | TEXT | 早卡开始时间戳 |

#### pass_card — 历史战卡对阵

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键，自增 |
| `fight_page` | TEXT | 所属赛事详情页 URL |
| `blue_page` | TEXT | 蓝方选手主页 URL |
| `red_page` | TEXT | 红方选手主页 URL |
| `blue_result` | TEXT | 蓝方结果 |
| `red_result` | TEXT | 红方结果 |
| `blue_odds` | TEXT | 蓝方赔率 |
| `red_odds` | TEXT | 红方赔率 |
| `end_method` | TEXT | 结束方式 |
| `end_method_cn` | TEXT | 结束方式（中文） |
| `end_round` | TEXT | 结束回合 |
| `end_time` | TEXT | 结束时间 |
| `card_type` | TEXT | 战卡类型（主赛/副赛等） |
| `card_division` | TEXT | 体重级别 |
| `card_division_cn` | TEXT | 体重级别（中文） |

#### player — 运动员档案

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键，自增 |
| `name` | TEXT | 姓名 |
| `name_cn` | TEXT | 姓名（中文） |
| `nick_name` | TEXT | 昵称 |
| `nick_name_cn` | TEXT | 昵称（中文） |
| `page` | TEXT | 选手主页 URL（唯一） |
| `division` | TEXT | 体重级别 |
| `division_cn` | TEXT | 体重级别（中文） |
| `avatar` | TEXT | 头像 URL |
| `avatar_local` | TEXT | 头像本地路径 |
| `cover` | TEXT | 封面图 URL |
| `cover_local` | TEXT | 封面图本地路径 |
| `record` | TEXT | 战绩（如 `20-3-0`） |
| `age` | TEXT | 年龄 |
| `status` | TEXT | 状态 |
| `status_cn` | TEXT | 状态（中文） |
| `home_town` | TEXT | 出生地原始值（如 `Huntington Beach, United States`） |
| `city` | TEXT | 城市（拆分自 home_town，仅国家时为空） |
| `city_cn` | TEXT | 城市（中文） |
| `country` | TEXT | 国家（拆分自 home_town 最后一段） |
| `country_cn` | TEXT | 国家（中文） |
| `team` | TEXT | 所属团队 |
| `team_cn` | TEXT | 所属团队（中文） |
| `style` | TEXT | 格斗风格 |
| `style_cn` | TEXT | 格斗风格（中文） |
| `height` | TEXT | 身高 |
| `weight` | TEXT | 体重 |
| `reach` | TEXT | 臂展 |
| `leg_reach` | TEXT | 腿长 |
| `debut` | TEXT | UFC 首秀日期 |
| `history` | TEXT | 历史对战记录（JSON 字符串） |
| `history_cn` | TEXT | 历史对战记录（中文，JSON 字符串） |
| `wins_stats` | TEXT | 获胜方式统计（JSON 字符串） |
| `wins_stats_cn` | TEXT | 获胜方式统计（中文，JSON 字符串） |
| `flag` | TEXT | 国旗代码 |

#### player_url_alias — 选手旧 URL 对照表

由 `ufcjson/normalize.py` 在导出层维护，记录「改版前的选手主页 URL → 合并后保留的 URL」。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键，自增 |
| `old_page` | TEXT | 改版前的选手主页 URL（唯一） |
| `new_page` | TEXT | 合并后保留的选手主页 URL |

> App 端不声明这张表：Room 只校验 `@Database` 里声明过的实体，库中多出的表不影响启动。

### ufc_translate.db — 翻译缓存库

翻译流程使用的缓存库，避免重复翻译相同文本：

- 爬虫管线（`TranslatorPipeline`）**只查缓存**：命中则带上译文，未命中留空，不发起网络请求；
- 真正的翻译在爬虫落库后由 `run.py` 统一执行（`ufcjson/translator.py` 的 `translate_db_fields`），
  通过大模型批量翻译，译文按原文写回本库。

完整流程与配置见下方「[中文翻译](#中文翻译)」章节。

#### translate — 翻译对照表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键，自增 |
| `original` | TEXT | 原文 |
| `translation` | TEXT | 译文 |

### ufc_coming_data.json — 即将到来的赛事

外层结构：
```json
{
  "timeStamp": 1757759400000,
  "data": [ ... ]
}
```

`data` 为赛事数组，每场赛事包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 赛事名称 |
| `title` | string | 头条主赛标题 |
| `page` | string | 赛事详情页 URL |
| `main_time` | string | 主卡开始时间戳 |
| `prelims_time` | string | 副卡开始时间戳 |
| `data_early_time` | string | 早卡开始时间戳 |
| `address` | string | 举办地 |
| `address_cn` | string | 举办地（中文） |
| `banner` | string | 赛事横幅图片 URL |
| `fight_card` | array | 战卡对阵列表 |

### ufc_pass_data.json — 历史赛事战报

从数据库读取最新的 8 场已结束赛事生成，结构同 `ufc_coming_data.json`，区别在于：
- 使用 `url` 字段而非 `page` 表示赛事链接
- `fight_cards` 数组中包含比赛结果（结束回合、结束方式、红/蓝方结果、赔率等）

### ufc_ranking_data.json — 官方排名

外层结构同上，`data` 为排名条目数组：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 选手姓名 |
| `page` | string | 选手主页 URL |
| `rank_name` | string | 榜单名称（如 `Flyweight`、`Pound-for-Pound`） |
| `rank` | string | 排名位次 |
| `rank_name_cn` | string | 榜单名称（中文） |

### meta.json — 数据版本元信息

每次通过 `run.py` 跑完爬虫后自动生成，用于判断数据是否有更新。

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | int | 数据结构版本号，字段/表结构发生不兼容变更时 +1 |
| `last_updated` | string | 内容最后变更时间（ISO 8601，东八区） |
| `last_updated_ts` | int | 内容最后变更时间戳（Unix 秒） |
| `generator` | string | 生成方标识，固定为 `UfcMaker` |
| `spiders_run` | array | 本次执行了哪些爬虫 |
| `athlete_count` | int | 运动员数量（来自数据库 player 表） |
| `pass_event_count` | int | 历史赛事数量（来自数据库 pass_event 表） |
| `upcoming_event_count` | int | 即将到来的赛事数量（来自 ufc_coming_data.json） |
| `ranking_count` | int | 排名条目数量（来自 ufc_ranking_data.json） |

> **判断是否有更新**：对比本地保存的 `last_updated_ts` 和远端的 `last_updated_ts`，远端更新则说明数据有变化。`last_updated` 只有在数据内容真的发生变化（数据库写入 / JSON 内容变更）时才会刷新，爬虫跑了但数据没变则保持原值。

### app_version.json — App 版本 & 升级配置

手动维护，App 启动时检查版本用。发版时更新此文件。

| 字段 | 类型 | 说明 |
|------|------|------|
| `latest_version` | string | 最新版本号（语义化版本，如 `1.2.0`） |
| `latest_version_code` | int | 最新版本号（纯数字，用于程序比较） |
| `minimum_version` | string | 最低兼容版本，低于此版本必须升级 |
| `minimum_version_code` | int | 最低兼容版本号（纯数字） |
| `force_update` | bool | 是否强制升级（`true` = 不升级无法使用） |
| `release_date` | string | 发布日期（`YYYY-MM-DD`） |
| `download_url` | string | 最新版下载地址 |
| `changelog.zh` | string | 更新日志（中文） |
| `changelog.en` | string | 更新日志（英文） |

> **升级判断逻辑**：App 端用 `version_code`（数字）比较大小，避免字符串比较的坑。低于 `minimum_version_code` 必须升级；高于等于最低版本但低于最新版本时，根据 `force_update` 判断是强制还是可选升级。

## 选手主页 URL 变更与多行归一化

### 问题从哪来

`player.page`（ufc.com 选手主页 URL）本来只是**网址的一段**，但项目把它当成了**选手的唯一标识**：

- `player.page` 是 `UNIQUE`，写入用 `INSERT OR REPLACE`（见 `pipelines/export_db.py`）；
- `pass_card.blue_page / red_page` 存的是选手主页 URL；
- 排名页和战卡页跳转选手详情，用的也是这个 URL。

ufc.com 改过亚洲选手的拼音顺序（如 `yadong-song` → `song-yadong`），同一个人的记录于是在库里断成两行：**战绩挂在旧 URL 上，而榜单给的是新 URL**，App 点进选手详情只查得到新 URL 名下那几场。

典型：宋亚东旧 URL 下 15 场、新 URL 下 4 场，用户在 App 里只看到 4 场。

### 怎么修

由 `ufcjson/normalize.py` 在**导出层**收尾，不改任何爬虫的抓取逻辑：

1. **分堆** — 按「归一化姓名 + 归一化首秀日」给 `player` 全表分堆，同一堆视为同一个人。
   - 姓名：NFKD 去音标 → 只留 `[a-z0-9]` → 小写（`Muhammad-Naimov` 和 `muhammad naimov` 归一）；
   - 首秀日：`Nov. 25, 2017` → `2017-11-25`。
   - ⚠️ 只用姓名会被同名不同人误伤：`bruno silva`（`bruno-silva-blindado` / `bruno-silva`）和 `joey gomez` 都是**真实的两个人**，靠首秀日才分得开。所以首秀日是必需的，不是可选项。
2. **选保留行** — 堆内 `record` 有效的行里，留 `id` 最大的那一行。
   - 依据：`player.id` 是 `AUTOINCREMENT`（严格递增、号不复用），而 `player` 的唯一写入者用 `INSERT OR REPLACE` 写 `page UNIQUE` —— REPLACE 的语义是**删旧行、重插新行**，每刷新一次 `id` 就变大一次，而旧 slug 从站点消失后再也抓不到。
   - 因此 **`id` 最大 = 最后被写入 = 站点当前 slug 行**。
3. **改写与落盘** — 其余行删除，同时把「旧 URL → 保留 URL」写进 `player_url_alias`，并按这张表改写 `pass_card.blue_page / red_page`。

### 两道保护

**① 空壳行守卫**（自动，无需配置）

只在 `record` 有效（总场次 > 0）的行里选 `id` 最大者；整堆都无效就整堆不动。防的是站点生成的空壳行 —— 例如 `casey-kenney-0` 的 `id` 比真行大得多，但没有战绩也没有任何 `pass_card` 引用，不挡就会反过来覆盖真数据。

**② 白名单**（`MERGE_WHITELIST`，需人工核对）

自动规则按「姓名 + 首秀日」分堆，够不着「首秀日也被改过」的情况。目前只有一条：

| 归一化姓名 | 保留的 URL | 说明 |
|---|---|---|
| `sumudaerji` | `.../athlete/su-mudaerji` | 两行首秀日不同（`Aug. 27, 2025` vs `Sep. 11, 2026`），但同昵称 `The Tibetan Eagle`、同战队 `Team Alpha Male`、同身高体重、同出身地，且被删行 history 的 8 个日期全部包含在保留行的 12 个里 |

新白名单项必须**逐项核对过人属性**才能加，键是归一化姓名，值是要保留的 `page`（须与库里的值逐字一致）。

### 历史战绩取并集

保留行的 `history` 通常已覆盖被删行，但偶尔会差一两场。合并时取并集（同日只留保留行那条），避免静默丢数据；history 变长后会同时清空 `history_cn`，否则翻译环节会误认为「已翻译」而跳过。

### 怎么跑

```bash
# 默认 dry-run：只打印将要合并的组、要删的行数、要改写的 pass_card 行数
python -m ufcjson.normalize

# 真正落盘（先 VACUUM INTO 备份，再单事务写完）
python -m ufcjson.normalize --apply

# 指定其他库（默认 output/db/ufc.db）
python -m ufcjson.normalize --db /tmp/ufc.db --apply
```

`run.py` 里已接入，每次跑完爬虫自动执行一次（在翻译和生成 `meta.json` **之前**）。

**幂等**：合并过的库里同一人只剩一行，第二次跑会报「0 组」。

### 影响面（以 3248 行 `player` / 9010 行 `pass_card` 为样本实测）

| 项目 | 数值 |
|---|---|
| 多人组 | 23 组（自动 22 + 白名单 1） |
| 删除 `player` 行 | 23 行（3248 → 3225） |
| 改写 `pass_card` 行 | 129 行 |
| 整堆跳过 | 1 组（两行都是 `0-0-0`） |
| 战卡战绩对拍 | 严格匹配 7581 → 7631（新增的 50 场全部落进「一致」） |

### 与 Android 端的关系

- 只改数据，**不动 Room 实体**，`UFC_DB_VERSION` 不需要 +1；
- 新增的 `player_url_alias` 表 App 端不声明，Room 不会因为库里多表而报错；
- 修完需要把 `output/db/ufc.db` 同步到 `UfcAndroid/app/src/main/assets/ufc.db`。

> 局限：这套方案认定「`id` 最大 = 当前 slug」。若库被全量重建导致 `id` 重排，判据失效 —— 但那种情况下只要 `athlete.py` 的去重键是 `page`，同一人本来就不会留两行，多行问题也不会产生。

## 中文翻译

翻译采用**两阶段**设计：爬虫阶段不发起任何翻译请求，只查缓存；爬虫全部跑完后，由 `run.py` 统一用大模型补齐。这样既能复用历史译文、避免重复调用，也能把同一条文本在多个表/多行里的翻译合并成一次请求。

### 阶段一：管线只查缓存

`ufcjson/pipelines/translate.py`（`TranslatorPipeline`）在爬虫运行时执行：

- 打开 `output/db/ufc_translate.db`，按原文查 `translate` 表；
- **命中** → 写入对应的 `*_cn` 字段；
- **未命中** → 留空，不发起网络请求；
- 列表型字段（如 `history`）只要有一个元素未命中，整列都不写入，全部交给阶段二。

### 阶段二：跑完后统一补翻

`run.py` 在所有爬虫结束后调用 `ufcjson/translator.py` 的 `translate_db_fields()`：

1. **收集** —— 扫描各表「原文非空、译文为空」的字段，去重后得到待翻译文本集合；
2. **过滤** —— 用 `ufc_translate.db` 的缓存剔除已翻译的文本；
3. **批量翻译** —— 剩余文本按批（默认 50 条/批）交给 `ufcjson/llm_translator.py`，使用 OpenAI 兼容的 chat completions 接口；
4. **写缓存** —— 每批成功即写入缓存，中途中断不丢已完成的部分；
5. **回填** —— 按译文映射更新各表的 `*_cn` 字段，提交事务。

**幂等**：已翻译的行下次直接命中缓存跳过；翻译失败的批次不写缓存，下次自动重试。

### 翻译范围

| 表 | 字段（原文 → 译文） |
|---|---|
| `player` | `name` / `nick_name` / `city` / `country` / `division` / `status` / `team` / `style` |
| `pass_event` | `name` / `title` / `address` |
| `pass_card` | `end_method` / `card_division` |

JSON 列单独处理（只翻译其中的文本，保持 JSON 结构）：

| 表 | 字段 | 规则 |
|---|---|---|
| `player` | `history` → `history_cn` | 字符串列表，整列翻译；**全部元素都翻译成功才写入** |
| `player` | `wins_stats` → `wins_stats_cn` | `[{"way", "times"}]`，只翻译 `way` |

> 排名榜单名（如 `Welterweight`）目前**没有中文** —— `UfcRankingItem` 在管线里是 `pass`，`ufc.db` 也没有 ranking 表，排名数据只落在 `ufc_ranking_data.json` 里。

### 配置

翻译后端从环境变量读取配置，未配置（或未安装 `openai`）时打印提示并跳过，不阻塞主流程：

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `LLM_API_BASE` | API 地址（如 `https://api.deepseek.com/v1`） | 空（必填） |
| `LLM_MODEL` | 模型名（如 `deepseek-chat`） | 空（必填） |
| `LLM_API_KEY` | API Key | 空（必填） |
| `LLM_BATCH_SIZE` | 每批条数 | `50` |
| `LLM_TIMEOUT` | 单次请求超时（秒） | `120` |
| `LLM_MAX_RETRIES` | 失败重试次数 | `3` |

### 领域提示词

`llm_translator.py` 内置了 MMA/UFC 领域提示词，让模型按中国格斗界和拳迷的通行说法翻译，而不是字面直译：

- **量级**：`Flyweight`=蝇量级、`Bantamweight`=雏量级、`Featherweight`=羽量级、`Welterweight`=次中量级……；
- **结束方式**：`Decision - Split`=分歧判定、`KO/TKO`=击倒/技术性击倒、`Submission`=降服、`NC`=无结果……；
- **人名**：按中国格斗媒体的常见音译；
- **地点**：按中文习惯从大到小（`Las Vegas, Nevada, United States`=美国内华达州拉斯维加斯）；
- **日期**：统一写成 `YYYY年M月D日`。

模型返回的 JSON 数组做了容错解析（剥离 ```json 围栏、截取首个 `[...]`），数量不足时补空串、多余则截断。

## 图片维护

爬虫运行过程中图片可能出现两种不一致情况：
1. **数据库有 URL 但本地没有图片** — 比如图片下载失败、旧版本 bug 导致漏下
2. **磁盘有图片但数据库没有引用** — 比如选手/赛事被删除、URL 变化导致重复下载、历史遗留

`scripts/image_maintenance.py` 提供两个命令来处理这些问题：

### 下载缺失图片

扫描数据库中所有图片 URL（`player.avatar`、`player.cover`、`pass_event.banner`），如果本地没有对应文件则下载，并补全 `*_local` 字段：

```bash
python -m scripts.image_maintenance --download
```

### 清理未引用图片

对比磁盘上的图片和数据库中的 `*_local` 字段，删除没有任何引用的"孤儿"图片：

```bash
# 预览模式 — 只列出不删除
python -m scripts.image_maintenance --cleanup --dry-run

# 实际删除（删除前会有二次确认）
python -m scripts.image_maintenance --cleanup
```

### 一键执行全部

```bash
python -m scripts.image_maintenance --all
```

> **建议**：每次全量爬取后执行一次 `--all`，保持图片目录和数据库同步。

### 图片命名规则

图片文件名 = 原始 URL 的 SHA1 哈希 + `.webp`，存储在 `output/images/full/` 目录下。
数据库中的 `avatar_local`、`cover_local`、`banner_local` 字段存的是相对路径，如 `full/abc123...webp`。

## 数据来源

所有数据均抓取自 [UFC 官网](https://www.ufc.com)，仅供学习研究使用。请遵守网站使用条款，合理控制爬取频率。

## 依赖

见 `requirements.txt`：

- **Scrapy** — 爬虫框架
- **openai** — 大模型翻译客户端（OpenAI 兼容接口）
- **pycountry** — 国家代码查询
- **PyRSS2Gen** — RSS Feed 生成
- **Pillow** — 图片处理


