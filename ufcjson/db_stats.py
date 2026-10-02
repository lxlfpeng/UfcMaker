"""库内容盘点（`output/json/db_stats.json`）。

在 `run.py::generate_meta_json()` 里调用，对下发的 ufc.db 做一次全量盘点：
有哪些表、各有多少行、关键字段覆盖到什么程度、有没有异常、分布如何。

⚠️ 三条口径规则（2026-09-26 实测确立，改这个文件之前先读）：

1. **「非空」≠「有值」。** `pass_card.blue_odds` / `red_odds` 实测 100% 非空，
   但其中 5764 行是占位符 `-`，真实赔率只有 35.6%。所有文本列的有效性判定
   统一走 [_is_filled]，把 [PLACEHOLDERS] 里的占位符算作「空」。
   只写 `<> ''` 会给出 100% 的假数据——这正是本模块存在的意义。

2. **列可能不存在。** 建表用的是 `CREATE TABLE IF NOT EXISTS`，已存在的表不会被补列
   （沿革：pass_event 的 city / city_cn / country / country_cn 四列 2026-09-20 曾被摘除、
   2026-10-02 恢复——历史旧库用 `scripts/backfill_event_place.py` 补列补数）。
   所有统计先 [_has_column] 探一下，缺列时该维度记 `None`
   而不是抛异常——否则一次 schema 漂移会让整个 run.py 挂掉。

3. **`main_time` 是字符串形式的 Unix 秒**（如 `'1233439200'`），不能直接排序比较，
   取最早/最晚必须 `CAST(main_time AS INTEGER)`。字典序会把 `ufc-32`(`'993852000'`)
   排到 `ufc-331`(`'1789866000'`)前面。

输出 `output/json/db_stats_history.json`（**append-only 趋势账本，也是唯一产物**）：

- 每条 = 一次「库内容快照」，只留**会变、且值得跨版本对比**的指标（约 1 KB/条）。
- ⚠️ **最后一条就是当前状态** —— 2026-09-26 起不再产出覆盖式快照 `db_stats.json`，
  消费方要「现在」就读 `data.entries[-1]`。所以凡是快照里有、消费方要用的，必须在这里。
- 与上一条完全一致时**不追加**，避免每天一条纯时间戳噪声。
- 频率决定体积：`size ≈ 931 B × 条数`，每周 1 条 ≈ 47 KB/年，每天 1 条 ≈ 332 KB/年。
"""

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone

# ⚠️ 这是**文件格式**的版本（`entries` 条目的**结构**），不是数据库版本、也不是数据版本 ——
# 三者别混：App 的 `UFC_DB_VERSION`（Room 表结构）· 本条目的 `ts`/`date`（数据快照时间）·
# 这个 `SCHEMA_VERSION`（本文件怎么写）。meta.json 里也有同名的 `schema_version`，那是它自己的格式版本。
# **改动条目结构（加/删字段、改嵌套、改字段语义）必须 +1**，消费方据此判断能否解析。
#   v1 = 2026-09-26 首次定型
#   v2 = 2026-09-26 同日：去掉覆盖式快照 · tables 剔掉两张辅助表 · 删 coverage.player.avatar
#        · 补 coverage.player 的 birthdate / country / status · external 允许 null
#   v3 = 2026-09-26 同日：**删掉一切派生值** —— `record_total`（= 三张业务表之和）与
#        `idle_players`（= tables.player − referenced_players），客户端自己减一下就有；
#        另删 `external.ranking_count`（画布旧版「五行」用过、现已弃用）。
#        ⚠️ `coverage` 里存的是**分子**不是百分比，**不能删** —— 客户端没有库、数不出 473。
# 上线后再动结构，务必继续 +1。
SCHEMA_VERSION = 3
GENERATOR = "UfcMaker"

# 出现在列里时算「没有数据」的占位符——它们不是空串，但确实没有信息量
PLACEHOLDERS = ("", "-", "--", "null", "None", "[]", "{}")

BUSINESS_TABLES = ("player", "pass_event", "pass_card")


# ---------- 底层探针（全部容错，绝不抛异常） ----------

def _has_table(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _has_column(conn, table, column):
    if not _has_table(conn, table):
        return False
    return column in [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')")]


def _one(conn, sql, args=()):
    """执行聚合查询，出错返回 None"""
    try:
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def _all(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []


def _total(conn, table):
    if not _has_table(conn, table):
        return 0
    return _one(conn, f"SELECT COUNT(*) FROM {table}") or 0


def _is_filled(col):
    """SQL 片段：该列「有值」的判定（占位符算空）"""
    quoted = ",".join("'" + p.replace("'", "''") + "'" for p in PLACEHOLDERS)
    return f"TRIM(COALESCE({col},'')) NOT IN ({quoted})"


def _cov(conn, table, cond, total=None):
    """覆盖度 → {"n": 有值行数, "total": 总行数, "pct": 百分比}"""
    if total is None:
        total = _total(conn, table)
    n = _one(conn, f"SELECT COUNT(*) FROM {table} WHERE {cond}")
    if n is None:
        return None
    return {"n": n, "total": total, "pct": round(n * 100.0 / total, 1) if total else 0.0}


def _cov_col(conn, table, col, total=None):
    """按单列统计覆盖度；列不存在返回 None"""
    if not _has_column(conn, table, col):
        return None
    return _cov(conn, table, _is_filled(col), total)


# ---------- 各统计块 ----------

def _counts(conn):
    tables = [r[0] for r in _all(
        conn,
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    )]
    per_table = {t: _total(conn, t) for t in tables}
    present = set(tables)
    # 业务表 = App 真正查询的那三张；其余（player_url_alias / player_url_probe）是
    # 爬虫侧辅助表，App 端不声明、Room 也不会因为库里多表而报错。
    business = {t: per_table.get(t, 0) for t in BUSINESS_TABLES}
    return {
        "table_count": len(tables),
        # 缺哪张业务表时这个数会 < 3，是个有用的告警信号
        "business_table_count": len([t for t in BUSINESS_TABLES if t in present]),
        "aux_table_count": len([t for t in tables if t not in BUSINESS_TABLES]),
        "record_total": sum(business.values()),
        "tables": per_table,
    }


def _player_coverage(conn):
    t = _total(conn, "player")
    return {
        "avatar_local": _cov_col(conn, "player", "avatar_local", t),
        "cover_local": _cov_col(conn, "player", "cover_local", t),
        "name_cn": _cov_col(conn, "player", "name_cn", t),
        "division_cn": _cov_col(conn, "player", "division_cn", t),
        "record": _cov_col(conn, "player", "record", t),
        "country": _cov_col(conn, "player", "country", t),
        "flag": _cov_col(conn, "player", "flag", t),
        "birthdate": _cov_col(conn, "player", "birthdate", t),
        # 生日精度：完整日期 vs 只知年份（Sherdog 只能反推到年，见 DB-NOTES §1.9.6）
        "birthdate_full": _cov(conn, "player", "LENGTH(COALESCE(birthdate,''))=10", t),
        "history": _cov_col(conn, "player", "history", t),
        "history_cn": _cov_col(conn, "player", "history_cn", t),
        "wins_stats": _cov_col(conn, "player", "wins_stats", t),
        "wins_stats_cn": _cov_col(conn, "player", "wins_stats_cn", t),
        # 选手状态（Active / Not Fighting / Retired）—— 选手筛选功能要用
        "status": _cov_col(conn, "player", "status", t),
    }


def _event_coverage(conn):
    t = _total(conn, "pass_event")
    return {
        # 「有赛事封面的数量」——设计上赛事列表 / 详情页首图要用
        "banner_local": _cov_col(conn, "pass_event", "banner_local", t),
        "name_cn": _cov_col(conn, "pass_event", "name_cn", t),
        "title": _cov_col(conn, "pass_event", "title", t),
        "title_cn": _cov_col(conn, "pass_event", "title_cn", t),
        "address_cn": _cov_col(conn, "pass_event", "address_cn", t),
        "main_time": _cov_col(conn, "pass_event", "main_time", t),
        "prelims_time": _cov_col(conn, "pass_event", "prelims_time", t),
        "early_time": _cov_col(conn, "pass_event", "data_early_time", t),
        "all_three_times": _cov(
            conn, "pass_event",
            f"{_is_filled('main_time')} AND {_is_filled('prelims_time')} "
            f"AND {_is_filled('data_early_time')}",
            t,
        ),
        # 下面两项本地库实际没有这列（DDL 与库漂移），会是 None——保留是为了让漂移可见
        "city_cn": _cov_col(conn, "pass_event", "city_cn", t),
        "country_cn": _cov_col(conn, "pass_event", "country_cn", t),
    }


def _card_coverage(conn):
    t = _total(conn, "pass_card")
    return {
        "both_results": _cov(
            conn, "pass_card",
            f"{_is_filled('blue_result')} AND {_is_filled('red_result')}", t,
        ),
        "end_method": _cov_col(conn, "pass_card", "end_method", t),
        "end_method_cn": _cov_col(conn, "pass_card", "end_method_cn", t),
        # ⚠️ 走占位符口径：`-` 不算有赔率（只算非空会得到 100%）
        "odds_valid": _cov(
            conn, "pass_card",
            f"{_is_filled('blue_odds')} AND {_is_filled('red_odds')}", t,
        ),
        "card_division_cn": _cov_col(conn, "pass_card", "card_division_cn", t),
    }


_PAGE_SUFFIX_RE = re.compile(r"-\d+$")


def _slug_of(name):
    """人名 → 粗 slug（用于判断某个 page 是否与这名字对得上）"""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _page_matches_name(page, name):
    """page 末段（去掉 `-0`/`-1` 后缀）是否等于 name 的 slug。

    ⚠️ 这是必要的第三道判据：库里存在「page 与 name 完全对不上」的脏行
    （如 name=`Test Fighter2` / page=`.../shon-loffler-5`）。这类组**两条的引用数都是 0**，
    只看引用数+id 会**保留脏行、把好行标成冗余**（2026-09-26 实测踩到过）。
    """
    base = _PAGE_SUFFIX_RE.sub("", (page or "").rsplit("/", 1)[-1])
    return base == _slug_of(name)


def _duplicate_players(conn):
    """同名 + 同战绩的重复行（同一名选手因 slug 变更被拆成两行）。

    口径 = `name` 与 `record` **逐字相同**。`record` 存的是职业总战绩（含 UFC 之外的赛事），
    「同名且职业战绩一字不差」几乎不可能是两个人 → 判重足够安全。

    ⚠️ **不能拿 page 的 `-N` 后缀判重**：ufc.com 用 `-1`/`-2` 区分**同名不同人**，
    库里带后缀的 slug 有 103 条，多数是合法的。
    ⚠️ 也不能只看同名 —— 同名不同人确实存在，必须叠加 record。

    「哪条算冗余」的保留优先级（三级）：
      1. 被 pass_card 引用**多**的（业务价值高）
      2. page 与 name **对得上**的（`_page_matches_name`）
      3. id **小**的（先入库的）
    ⚠️ 这是**启发式建议，不是判决** —— 落到脏数据组（name/page 错配）时仍需人工看。

    返回 {"groups": 重复组数, "redundant_rows": 冗余行数, "redundant_pages": [建议清理的 page]}
    """
    groups = _all(
        conn,
        "SELECT name, record FROM player GROUP BY name, record HAVING COUNT(*) > 1",
    )
    if not groups:
        return {"groups": 0, "redundant_rows": 0, "redundant_pages": []}

    redundant = []
    for name, record in groups:
        if record is None:
            cond, args = "p.record IS NULL", (name,)
        else:
            cond, args = "p.record = ?", (name, record)
        rows = _all(
            conn,
            f"""SELECT p.id, p.page,
                       (SELECT COUNT(*) FROM pass_card cc
                         WHERE cc.blue_page = p.page OR cc.red_page = p.page) AS refs
                FROM player p WHERE p.name = ? AND {cond}""",
            args,
        )
        rows.sort(key=lambda row: (
            -(row[2] or 0),                                   # 引用多的优先
            0 if _page_matches_name(row[1], name) else 1,     # page 对得上名字的优先
            row[0],                                           # id 小的优先
        ))
        redundant.extend(row[1] for row in rows[1:])           # 第一条保留

    return {
        "groups": len(groups),
        "redundant_rows": len(redundant),
        "redundant_pages": sorted(redundant),
    }


def _fmt_date(ts):
    """Unix 秒 → 东八区 YYYY-MM-DD；空值返回 None"""
    if not ts:
        return None
    return datetime.fromtimestamp(ts, timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def _missing_dimensions(coverage):
    """汇总统计不到的维度（列不存在时该项为 None）——把 DDL 与真实库的漂移暴露出来。

    漂移项（None）会在这里被点名。历史例子：`pass_event.city_cn` / `country_cn` 曾在
    2026-09-20~10-02 期间缺列而稳定出现；2026-10-02 恢复四列后该项自动消失。
    看到漂移项 = 库 / DDL 需要一次对齐（重建或 `scripts/backfill_event_place.py`）。
    """
    return [
        f"{table}.{name}"
        for table, dims in coverage.items()
        for name, value in dims.items()
        if value is None
    ]


def _quality(conn, coverage):
    now_ts = int(time.time())
    players = _total(conn, "player")
    events = _total(conn, "pass_event")
    cards = _total(conn, "pass_card")

    referenced = _one(
        conn,
        "SELECT COUNT(DISTINCT p.page) FROM player p WHERE EXISTS("
        "  SELECT 1 FROM pass_card cc WHERE cc.blue_page=p.page OR cc.red_page=p.page)",
    )

    # main_time 是字符串 Unix 秒，必须 CAST 才能正确取最早/最晚
    ts_min = _one(
        conn, "SELECT MIN(CAST(main_time AS INTEGER)) FROM pass_event "
              "WHERE TRIM(COALESCE(main_time,''))<>''")
    ts_max = _one(
        conn, "SELECT MAX(CAST(main_time AS INTEGER)) FROM pass_event "
              "WHERE TRIM(COALESCE(main_time,''))<>''")

    result = {
        # 空壳行：两侧结果都空（= 缺失对局的疤痕，见 DB-NOTES §1.3）
        "shell_rows": _one(
            conn, "SELECT COUNT(*) FROM pass_card WHERE "
                  f"NOT ({_is_filled('blue_result')}) AND NOT ({_is_filled('red_result')})"),
        # 毒化占位值：end_time='00:00'（见 DB-NOTES §10）
        "poison_end_time": _one(
            conn, "SELECT COUNT(*) FROM pass_card WHERE TRIM(COALESCE(end_time,''))='00:00'"),
        # App 侧 queryPlayer(page) 是精确等值匹配，对不上就是战卡那一格空白
        "orphan_card_sides": _one(
            conn,
            "SELECT COUNT(*) FROM pass_card cc WHERE NOT ("
            "  EXISTS(SELECT 1 FROM player p WHERE p.page=cc.blue_page) AND "
            "  EXISTS(SELECT 1 FROM player p WHERE p.page=cc.red_page))"),
        "events_without_card": _one(
            conn,
            "SELECT COUNT(*) FROM pass_event e WHERE NOT EXISTS("
            "  SELECT 1 FROM pass_card cc WHERE cc.fight_page=e.page)"),
        "cards_without_event": _one(
            conn,
            "SELECT COUNT(*) FROM pass_card cc WHERE NOT EXISTS("
            "  SELECT 1 FROM pass_event e WHERE e.page=cc.fight_page)"),
        "referenced_players": referenced,
        # 库里但一场比赛都没引用到的选手（多半是 never-fought / 退役）
        "idle_players": (players - referenced) if referenced is not None else None,
        "distinct_fight_pages": _one(conn, "SELECT COUNT(DISTINCT fight_page) FROM pass_card"),
        "event_card_ratio": round(cards * 1.0 / events, 2) if events else None,
        "earliest_event_ts": ts_min,
        "earliest_event_ts_date": _fmt_date(ts_min),
        "latest_event_ts": ts_max,
        "latest_event_ts_date": _fmt_date(ts_max),
        "future_events": _one(
            conn, "SELECT COUNT(*) FROM pass_event "
                  f"WHERE CAST(COALESCE(main_time,'0') AS INTEGER) > {now_ts}"),
        # 同名 + 同战绩的重复选手行（slug 变更的后遗症，normalize_db 至今没合并掉）
        "duplicate_players": _duplicate_players(conn),
        # 列不存在导致的「统计不到」，集中列出来
        "missing_dimensions": _missing_dimensions(coverage),
    }
    return result


def _distribution(conn):
    def grouping(sql):
        return {str(k): v for k, v in _all(conn, sql) if k is not None and str(k).strip() != ""}

    top_div = [
        {"name": r[0], "n": r[1]}
        for r in _all(
            conn,
            "SELECT card_division_cn, COUNT(*) FROM pass_card "
            f"WHERE {_is_filled('card_division_cn')} "
            "GROUP BY card_division_cn ORDER BY 2 DESC LIMIT 10",
        )
    ]
    return {
        "card_type": grouping(
            "SELECT card_type, COUNT(*) FROM pass_card "
            f"WHERE {_is_filled('card_type')} GROUP BY card_type ORDER BY 2 DESC"),
        "result": grouping(
            "SELECT blue_result, COUNT(*) FROM pass_card "
            f"WHERE {_is_filled('blue_result')} GROUP BY blue_result ORDER BY 2 DESC"),
        "player_status": grouping(
            "SELECT status, COUNT(*) FROM player "
            f"WHERE {_is_filled('status')} GROUP BY status ORDER BY 2 DESC"),
        "top_divisions": top_div,
    }


# ---------- 历史趋势（append-only，唯一产物） ----------
# 每条只留「会变、且值得跨版本对比」的指标。全量 coverage 有 29 项，但多数恒为 100%
# （avatar_local / record / name_cn / division_cn…），每天存一份逐字相同的内容没意义：
# 全量约 5.7 KB × 365 天 ≈ 2 MB/年，而这里约 1 KB/条（每周一条 ≈ 47 KB/年）。
# 要加指标就往下加 —— 但别加恒定的那类。
#
# ⚠️ **`entries[-1]` 就是「当前状态」**：2026-09-26 起不再产出覆盖式快照 `db_stats.json`，
#   所以凡是消费方（App 数据内容卡 / 看板）要读的字段，都必须在这里有。
#
# ⚠️ 存**绝对数量**、不存百分比：
#   百分比是派生量，「分子分母同时增长」时会误导 —— 战绩明细 1047→1100 条，
#   但选手总数同期 3266→3500，百分比反而下降；且四舍五入有损（92.4 丢掉了 3019/3266）。
#   要百分比自己算：`coverage[表名][指标] / tables[表名]`。
#   嵌套成「表名 → 指标」是为了让分母能直取 tables —— 平铺的 `player_birthdate_full`
#   没法可靠地切出表名（指标名自身含下划线）。

# quality 里要留的标量（另外三个 —— duplicate_players / missing_dimensions / external —— 单独处理）
# ⚠️ 只放**原始值**：能从别的字段算出来的派生值一律不留 ——
#   `idle_players`（= tables.player − referenced_players）已于 v3 删除，客户端自己减。
#   `referenced_players` 必须留：它是原始值，客户端算不出「有多少选手被对局引用过」。
_HISTORY_QUALITY_SCALARS = (
    "shell_rows", "poison_end_time", "orphan_card_sides",
    "events_without_card", "cards_without_event",
    "referenced_players",
    "distinct_fight_pages",          # 与 tables.pass_event 对比 → 能看出「赛事无战卡」是否扩大
    "future_events",                 # 赛程抓取健康度，突降为 0 = 没抓到
    "earliest_event_ts",             # 数据覆盖向上扩张（补了更早的赛事）
    "latest_event_ts",               # 时间线进度：随新赛事前进
)


def _history_entry(data):
    """从全量统计里抽出一条精简记录。

    `coverage[表名][指标]` = 该指标有值的**行数**；分母是 `tables[表名]`，不重复存。
    coverage 里只放**低于 100%、还有提升空间**的维度 —— 恒定满格的放了也看不出变化，
    因为那类指标一旦坏掉，现象是**立刻可见**的（App 上一堆空白），不需要靠趋势发现。

    ⚠️ `coverage.player.avatar` 已删除（2026-09-26）：恒为 100%，且与任何字段都不互补
    （对比 `pass_card.both_results` —— 它虽有 100%，但补上了 `shell_rows` 覆盖不到的
    「只有一侧有结果」的契约违规区间，属于互补）。**别再加回来。**
    """
    coverage = data["coverage"]
    quality = data["quality"]

    def filled(group, key):
        item = coverage.get(group, {}).get(key)
        return item["n"] if isinstance(item, dict) else None

    all_tables = data["counts"]["tables"]

    entry = {
        "ts": data["generated_at_ts"],
        "date": data["generated_at"][:10],
        # ⚠️ 只留 3 张业务表。player_url_alias / player_url_probe 是爬虫内部工作数据，
        # 行数变化与数据质量无关，却**会触发判重**、产生无意义的版本记录 —— 必须排除。
        "tables": {t: all_tables.get(t, 0) for t in BUSINESS_TABLES},
        # ⚠️ 没有 record_total（v3 删）—— 客户端把这三张表加起来就有，存一份等于埋一个不同步的隐患
        "coverage": {
            "player": {
                # 生日成对记：birthdate = 至少有值（可能只到年），birthdate_full = 精确到日
                "birthdate": filled("player", "birthdate"),
                "birthdate_full": filled("player", "birthdate_full"),
                "country": filled("player", "country"),
                "status": filled("player", "status"),
                # 抓取覆盖 / 翻译覆盖成对记：history 是抓到了，history_cn 是译好了
                "history": filled("player", "history"),
                "history_cn": filled("player", "history_cn"),
                "wins_stats": filled("player", "wins_stats"),
                "wins_stats_cn": filled("player", "wins_stats_cn"),
            },
            "pass_event": {
                "banner": filled("pass_event", "banner_local"),
                # 三档开赛时间：赛程页要用；all_times = 三档齐全
                "prelims_time": filled("pass_event", "prelims_time"),
                "early_time": filled("pass_event", "early_time"),
                "all_times": filled("pass_event", "all_three_times"),
            },
            "pass_card": {
                # 结果完整率：虽恒定 100%，但补上了 shell_rows 覆盖不到的「单侧有值」区间
                "both_results": filled("pass_card", "both_results"),
                "odds": filled("pass_card", "odds_valid"),
                "division": filled("pass_card", "card_division_cn"),
            },
        },
        "quality": {
            **{k: quality.get(k) for k in _HISTORY_QUALITY_SCALARS},
            # 重复选手只留冗余行数（redundant_pages 是排查用的，不进历史）
            "duplicate_players": (quality.get("duplicate_players") or {}).get("redundant_rows"),
            # schema 漂移：DDL 改了但库没重建 → 稳定出现缺列；列表一变就是告警
            "missing_dimensions": quality.get("missing_dimensions"),
        },
    }

    # 库外指标（排名快照数 / 待更新赛事数）由调用方传入 —— 它们在 JSON 文件里，库里没有。
    # ⚠️ 值可能是 None（源文件缺失），**不要当成 0** —— 那会和「真的是 0」混淆。
    if data.get("external"):
        entry["external"] = data["external"]

    return entry


def _history_comparable(entry):
    """去掉时间字段后的可比内容——用来判断「数据是否真的变了」"""
    return {k: v for k, v in entry.items() if k not in ("ts", "date")}


def _load_history(path):
    """读历史 entries；文件缺失或损坏时返回 []（不抛，丢了就从头开始记）"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []
    data = raw.get("data", raw) if isinstance(raw, dict) else {}
    entries = data.get("entries") if isinstance(data, dict) else None
    return entries if isinstance(entries, list) else []


def _save_history(path, entries):
    payload = {
        "code": 0,
        "msg": "success",
        "data": {
            "schema_version": SCHEMA_VERSION,
            "entry_count": len(entries),
            "entries": entries,          # 正序：旧 → 新，追加即往末尾加
        },
        "timestamp": int(time.time() * 1000),
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def append_history(history_path, data):
    """与上一条一致则不追加。返回 True=追加了 / False=跳过。"""
    entries = _load_history(history_path)
    entry = _history_entry(data)

    if entries and _history_comparable(entries[-1]) == _history_comparable(entry):
        return False

    entries.append(entry)
    _save_history(history_path, entries)
    return True


# ---------- 对外入口 ----------

def build_stats(db_path, extra=None):
    """盘点 db_path；库不存在返回 None。

    `extra` = 库外指标（排名快照数 / 待更新赛事数等），原样带进输出的 `external` 块，
    并会被 `_history_entry()` 透传进历史条目。
    """
    if not os.path.exists(db_path):
        return None

    conn = sqlite3.connect(db_path)
    try:
        now = datetime.now(timezone(timedelta(hours=8)))
        counts = _counts(conn)
        coverage = {
            "player": _player_coverage(conn),
            "pass_event": _event_coverage(conn),
            "pass_card": _card_coverage(conn),
        }
        data = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "generated_at_ts": int(now.timestamp()),
            "generator": GENERATOR,
            "source_db": db_path.replace("\\", "/"),
            "counts": counts,
            "coverage": coverage,
            "quality": _quality(conn, coverage),
            "distribution": _distribution(conn),
        }
        if extra:
            data["external"] = extra
        return data
    finally:
        conn.close()


def write_stats_history(db_path, history_path, extra=None):
    """盘点 + 往趋势账本追加一条。库不存在时跳过。失败由调用方兜住。

    返回 True=已追加 / False=数据未变跳过 / None=库不存在。
    """
    data = build_stats(db_path, extra=extra)
    if data is None:
        print(f"[stats] 跳过：{db_path} 不存在")
        return None

    appended = append_history(history_path, data)
    counts = data["counts"]
    print(
        f"[stats] {history_path} "
        f"{'已追加新条目' if appended else '数据未变，跳过追加'}"
        f"（共 {len(_load_history(history_path))} 条；"
        f"表 {counts['table_count']} 张 / 记录 {counts['record_total']:,} 条）"
    )
    return appended
