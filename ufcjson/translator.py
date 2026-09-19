"""run.py 中调用：爬虫落库后统一翻译未翻译的字段。

流程：收集三张表中所有「src 非空且 dst 为空」的文本（含 player 的 history / wins_stats
JSON 列），去重后按翻译缓存过滤，剩余交给大模型批量翻译（ufcjson.llm_translator），
新译文写回缓存，最后逐行回填。幂等：已翻译的行跳过，翻译失败的下次重试；
但同一原文累计 MAX_TRANSLATE_TRIES 次仍拿不到译文就搁置（不再每天重发），
记在 translate_miss 表里。

「还没翻译」的判定：dst 为 NULL、空串，或 JSON 列的 '[]'——老版本 export_db 把空值
落成了字面量 '[]'，只认空串会让这批行永远进不了队列。新版本 export_db 已统一写空串，
这里的 '[]' 分支是为存量数据保留的。
"""
import json
import os
import sqlite3

from ufcjson.llm_translator import translate_many
from ufcjson.textutil import is_blank_text
from ufcjson.translate_cache import (
    clear_miss,
    ensure_cache_table,
    load_given_up,
    record_failure,
)

DB_PATH = "output/db/ufc.db"
TRANSLATE_DB_PATH = "output/db/ufc_translate.db"

# 同一原文最多问大模型几次。专有名词（Noche UFC / UFC on ESPN 之类）模型可能永远答不出，
# 光靠「失败下轮重试」会每天都重发一次（实测 121 条 / 29 行）。累计到这个次数仍拿不到
# 译文就搁置（记在 translate_miss），不再进请求队列；想重试见 translate_cache 模块说明。
MAX_TRANSLATE_TRIES = 3

# 各表普通字符串字段需要翻译的 (原文字段, 中文字段)
TRANSLATE_FIELDS = {
    "player": [
        ("name", "name_cn"),
        ("nick_name", "nick_name_cn"),
        ("city", "city_cn"),
        ("country", "country_cn"),
        ("division", "division_cn"),
        ("status", "status_cn"),
        ("team", "team_cn"),
        ("style", "style_cn"),
    ],
    "pass_event": [
        ("name", "name_cn"),
        ("title", "title_cn"),
        ("address", "address_cn"),
    ],
    "pass_card": [
        ("end_method", "end_method_cn"),
        ("card_division", "card_division_cn"),
    ],
}

# JSON 列：只翻译其中的文本，保持原 JSON 结构
#   history    -> 字符串列表，整列翻译
#   wins_stats -> [{"way": ..., "times": ...}]，只翻译 way
JSON_TRANSLATE_FIELDS = {
    "player": [
        ("history", "history_cn", "str_list"),
        ("wins_stats", "wins_stats_cn", "dict_list"),
    ],
}

# 零宽字符的判定见 ufcjson/textutil.py（唯一一份定义）：页面里「整条只有不可见
# 字符」的垃圾条目被当成正常文本送去翻译，译不出来 ⇒ _backfill 的 all() 失败 ⇒
# 该选手整段中文战绩永不回填。抓取端 / 翻译端 / 订正脚本必须共用同一个函数，
# 否则 history 与 history_cn 会按位错位。


def _ensure_cache_table(conn):
    """建 translate 表并保证 original 唯一（老库会在这里做一次去重）。"""
    removed = ensure_cache_table(conn)
    if removed:
        print(f"[translate] 缓存表清理重复原文 {removed} 行")


def _load_cache(tconn):
    rows = tconn.cursor().execute("SELECT original, translation FROM translate").fetchall()
    return {orig: tr for orig, tr in rows if tr}


def _save_cache(tconn, pairs):
    cursor = tconn.cursor()
    for orig, tr in pairs.items():
        if tr:
            cursor.execute(
                "INSERT OR IGNORE INTO translate (original, translation) VALUES (?, ?)", (orig, tr)
            )
    tconn.commit()


def _collect_pending(cursor):
    """收集所有待翻译文本。

    返回 (values, plain_tasks, history_tasks, wins_tasks)
    - values: 待翻译文本去重集合
    - plain_tasks: [(table, row_id, dst, src)] 普通字符串字段
    - history_tasks: [(row_id, [item, ...])] history JSON 列表
    - wins_tasks: [(row_id, [{way, times}, ...])] wins_stats JSON 列表
    """
    values = set()
    plain_tasks = []
    history_tasks = []
    wins_tasks = []

    for table, pairs in TRANSLATE_FIELDS.items():
        for src, dst in pairs:
            rows = cursor.execute(
                f"SELECT id, {src} FROM {table} "
                f"WHERE {src} IS NOT NULL AND {src} != '' AND ({dst} IS NULL OR {dst} = '')"
            ).fetchall()
            for rid, val in rows:
                values.add(val)
                plain_tasks.append((table, rid, dst, val))

    for table, pairs in JSON_TRANSLATE_FIELDS.items():
        for src, dst, kind in pairs:
            # dst 可能是 ''、NULL 或 '[]'：'[]' 是历史版本 export_db 的落库值
            # （表示「还没翻译」），必须一起认，否则这批行永远进不了队列。
            # src = '[]' 表示该选手确实没有战绩，没有可翻译的内容，跳过。
            rows = cursor.execute(
                f"SELECT id, {src} FROM {table} "
                f"WHERE {src} IS NOT NULL AND {src} != '' AND {src} != '[]' "
                f"AND ({dst} IS NULL OR {dst} = '' OR {dst} = '[]')"
            ).fetchall()
            for rid, raw in rows:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, list):
                    continue
                if kind == "str_list":
                    items = [str(x).strip() for x in data if x and not is_blank_text(x)]
                    history_tasks.append((rid, items))
                    values.update(items)
                elif kind == "dict_list":
                    wins_tasks.append((rid, data))
                    values.update(
                        s.get('way', '') for s in data
                        if isinstance(s, dict) and s.get('way')
                    )

    return values, plain_tasks, history_tasks, wins_tasks


def _backfill(cursor, plain_tasks, history_tasks, wins_tasks, combined):
    """按翻译映射回填；JSON 列要求全部翻译成功才写入。

    JSON 列故意保持「全有或全无」：history_cn 与 history 是按位对应的，只写一半
    会让剩下的条目错位。写不进去的行连同缺失条目一起返回，由调用方打印出来——
    以前这里是静默跳过，出问题时看不出来。

    返回 (updated, stuck)；stuck = [(row_id, 列名, 缺失的原文列表)]。
    """
    updated = 0
    stuck = []

    for table, rid, dst, src in plain_tasks:
        tr = combined.get(src, '')
        if tr:
            cursor.execute(f"UPDATE {table} SET {dst} = ? WHERE id = ?", (tr, rid))
            updated += 1

    for rid, items in history_tasks:
        tr_items = [combined.get(it, '') for it in items]
        missing = [it for it, tr in zip(items, tr_items) if not tr]
        if missing:
            stuck.append((rid, 'history_cn', missing))
            continue
        cursor.execute(
            "UPDATE player SET history_cn = ? WHERE id = ?",
            (json.dumps(tr_items, ensure_ascii=False), rid)
        )
        updated += 1

    for rid, data in wins_tasks:
        ways = [s.get('way', '') for s in data if isinstance(s, dict) and s.get('way')]
        missing = [w for w in ways if not combined.get(w, '')]
        if missing:
            stuck.append((rid, 'wins_stats_cn', missing))
            continue
        tr_data = []
        for s in data:
            tr = dict(s)
            if tr.get('way'):
                tr['way'] = combined.get(tr['way'], '')
            tr_data.append(tr)
        cursor.execute(
            "UPDATE player SET wins_stats_cn = ? WHERE id = ?",
            (json.dumps(tr_data, ensure_ascii=False), rid)
        )
        updated += 1

    return updated, stuck


def translate_db_fields(db_path=DB_PATH, translate_db_path=TRANSLATE_DB_PATH):
    """扫描各表，翻译 src 非空且 dst 为空的字段（含 history / wins_stats JSON 列）。"""
    if not os.path.exists(db_path):
        print(f"[translate] 找不到 {db_path}，跳过")
        return

    conn = sqlite3.connect(db_path)
    tconn = sqlite3.connect(translate_db_path)
    _ensure_cache_table(tconn)
    cursor = conn.cursor()

    # ① 收集待翻译文本与回填任务
    values, plain_tasks, history_tasks, wins_tasks = _collect_pending(cursor)
    if not values:
        print("[translate] 没有需要翻译的字段")
        conn.close()
        tconn.close()
        return

    # ② 缓存过滤 + 批量翻译
    cache = _load_cache(tconn)
    missing = sorted(v for v in values if v not in cache)
    given_up = load_given_up(tconn, MAX_TRANSLATE_TRIES)
    to_send = [v for v in missing if v not in given_up]
    parked = len(missing) - len(to_send)
    print(f"[translate] 待翻译去重 {len(to_send)} 条"
          + (f"（另有 {parked} 条已搁置，不再重发）" if parked else "")
          + "，开始大模型批量翻译...")
    # unanswered：问过、但模型没给出译文的原文（整批网络失败不算）
    unanswered = set()
    tr_map = translate_many(to_send, cache_conn=tconn, unanswered=unanswered)
    combined = {v: tr_map.get(v) or cache.get(v) or '' for v in values}

    # ③ 新译文写回缓存
    _save_cache(tconn, tr_map)

    # ④ 失败记账：拿到译文的清掉旧记录，没拿到的累加次数，达上限即搁置。
    #    只在「模型确实被问过」时记账——未配置大模型时 translate_many 直接返回，
    #    unanswered 与 tr_map 都是空的，这里就不动账本，免得本地空跑几轮把队列全搁置。
    if unanswered or tr_map:
        clear_miss(tconn, [v for v in to_send if v not in unanswered])
        record_failure(tconn, unanswered)
        parked_now = sorted(load_given_up(tconn, MAX_TRANSLATE_TRIES) - given_up)
        if parked_now:
            print(f"[translate] 新搁置 {len(parked_now)} 条"
                  f"（连续 {MAX_TRANSLATE_TRIES} 次未翻出，不再重发）："
                  + "、".join(repr(v) for v in parked_now[:5])
                  + ("…" if len(parked_now) > 5 else ""))
            print("[translate] 想重新尝试：DELETE FROM translate_miss;")

    # ⑤ 回填
    updated, stuck = _backfill(cursor, plain_tasks, history_tasks, wins_tasks, combined)
    conn.commit()
    conn.close()
    tconn.close()
    print(f"[translate] 完成，回填 {updated} 个字段")
    if stuck:
        print(f"[translate] {len(stuck)} 个 JSON 字段因存在未翻译条目而跳过"
              f"（条目未搁置的下轮重试）：")
        for rid, col, missing in stuck[:10]:
            print(f"  player.id={rid} {col} 缺 {len(missing)} 条，例：{missing[0][:90]!r}")
        if len(stuck) > 10:
            print(f"  …（其余 {len(stuck) - 10} 个省略）")
