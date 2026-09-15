"""run.py 中调用：爬虫落库后统一翻译未翻译的字段。

流程：收集三张表中所有「src 非空且 dst 为空」的文本（含 player 的 history / wins_stats
JSON 列），去重后按翻译缓存过滤，剩余交给大模型批量翻译（ufcjson.llm_translator），
新译文写回缓存，最后逐行回填。幂等：已翻译的行跳过，翻译失败的下次重试。
"""
import json
import os
import sqlite3

from ufcjson.llm_translator import translate_many

DB_PATH = "output/db/ufc.db"
TRANSLATE_DB_PATH = "output/db/ufc_translate.db"

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


def _ensure_cache_table(conn):
    conn.cursor().execute('''
        CREATE TABLE IF NOT EXISTS translate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original TEXT NOT NULL,
            translation TEXT
        )
    ''')


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
            rows = cursor.execute(
                f"SELECT id, {src} FROM {table} "
                f"WHERE {src} IS NOT NULL AND {src} != '' AND ({dst} IS NULL OR {dst} = '')"
            ).fetchall()
            for rid, raw in rows:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, list):
                    continue
                if kind == "str_list":
                    items = [str(x).strip() for x in data if x and str(x).strip()]
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
    """按翻译映射回填；JSON 列要求全部翻译成功才写入。"""
    updated = 0

    for table, rid, dst, src in plain_tasks:
        tr = combined.get(src, '')
        if tr:
            cursor.execute(f"UPDATE {table} SET {dst} = ? WHERE id = ?", (tr, rid))
            updated += 1

    for rid, items in history_tasks:
        tr_items = [combined.get(it, '') for it in items]
        if all(tr_items):
            cursor.execute(
                "UPDATE player SET history_cn = ? WHERE id = ?",
                (json.dumps(tr_items, ensure_ascii=False), rid)
            )
            updated += 1

    for rid, data in wins_tasks:
        ways = [s.get('way', '') for s in data if isinstance(s, dict) and s.get('way')]
        if all(combined.get(w, '') for w in ways):
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

    return updated


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
    print(f"[translate] 待翻译去重 {len(missing)} 条，开始大模型批量翻译...")
    tr_map = translate_many(missing, cache_conn=tconn)
    combined = {v: tr_map.get(v) or cache.get(v) or '' for v in values}

    # ③ 新译文写回缓存
    _save_cache(tconn, tr_map)

    # ④ 回填
    updated = _backfill(cursor, plain_tasks, history_tasks, wins_tasks, combined)
    conn.commit()
    conn.close()
    tconn.close()
    print(f"[translate] 完成，回填 {updated} 个字段")
