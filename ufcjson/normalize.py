# -*- coding: utf-8 -*-
"""导出层归一化：把同一名选手被拆成多行的记录合并回一行。

## 要解决什么

`player.page`（ufc.com 选手主页 URL 的最后一段）被当成了选手身份：它是
`player` 的主键值、`pass_card.blue_page / red_page` 的外键值、榜单的跳转键。
ufc.com 一改拼音，同一名选手在库里就变成两行——战绩挂在旧 URL 上，
而榜单给的是新 URL，App 点进去只能查到新行名下那几场。

## 怎么做

1. 按「归一化姓名 + 归一化首秀日」给 `player` 全表分堆，同一堆 = 同一个人；
2. 每堆只留一行：`record` 有效的行里 `id` 最大的那个。
   依据：`id` 是 `AUTOINCREMENT`（严格递增、号不复用），`player` 的唯一写入者
   `export_db.py` 用 `INSERT OR REPLACE` 写 `page UNIQUE`（REPLACE = 删旧行重插），
   旧 slug 从站点消失后再也抓不到 ⇒ **id 最大 = 最后被写入 = 站点当前 slug 行**；
3. 删掉堆里其余行，同时把「旧 URL → 保留 URL」写进 `player_url_alias`；
4. 按这张对照表改写 `pass_card.blue_page / red_page`。

只用姓名会被同名不同人误伤（`bruno silva`、`joey gomez` 是真的两个人），
所以首秀日是必需的；`MERGE_WHITELIST` 补的是自动规则够不着、
但人工逐项核对过的那一组。

## 跑法

    python -m ufcjson.normalize            # dry-run，只打印要改什么
    python -m ufcjson.normalize --apply    # 先备份再落盘

幂等：合并过的库里同一人只剩一行，第二次跑会报「0 组」。
"""

import argparse
import json
import os
import re
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import datetime

DB_PATH = 'output/db/ufc.db'

# 自动规则够不着、但人工核对确认为同一人的组。
# 键 = 归一化姓名，值 = 要保留的 page（必须与库里的值逐字一致）。
#
# `sumudaerji` 的两行首秀日不同（`Aug. 27, 2025` vs `Sep. 11, 2026`），分不到同一堆，
# 但证据齐全：同昵称 `The Tibetan Eagle`、同队伍 `Team Alpha Male`、
# 同身高 68 / 体重 125.5、同出身地 Sichuan，且被删行 history 的 8 个日期
# 全部包含在保留行的 12 个日期里。
MERGE_WHITELIST = {
    'sumudaerji': 'https://www.ufc.com/athlete/su-mudaerji',
}

_DEBUT_RE = re.compile(r'([A-Za-z]{3})\.?\s+(\d{1,2}),\s*(\d{4})')
_RECORD_RE = re.compile(r'\s*(\d+)-(\d+)-(\d+)')
_HISTORY_DATE_RE = re.compile(r'\((\d{1,2})/(\d{1,2})/(\d{2})\)')

_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def norm_name(value):
    """归一化姓名：去音标 → 只留字母数字 → 小写。

    `Muhammad-Naimov` / `muhammad naimov` / `Muhammad Naimov` 会归一成同一个键。
    """
    text = unicodedata.normalize('NFKD', value or '')
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', '', text.lower())


def norm_debut(value):
    """归一化首秀日：`Nov. 25, 2017` → `2017-11-25`；解析不出返回 None。"""
    match = _DEBUT_RE.search(value or '')
    if not match:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if not month:
        return None
    return f'{match.group(3)}-{month:02d}-{int(match.group(2)):02d}'


def record_total(value):
    """`22-8-1 (W-L-D)` → 31；解析不出返回 -1。

    用于挡住站点生成的空壳行（`0-0-0`）：这类行 `pass_card` 引用为 0，
    但 `id` 往往比真行大得多，不挡就会反过来覆盖真数据。
    """
    match = _RECORD_RE.match(value or '')
    if not match:
        return -1
    return sum(int(part) for part in match.groups())


def _history_items(raw):
    """history 列是 JSON 字符串列表，例如 `" (8/29/26) Song knocked out ..."`。"""
    try:
        items = json.loads(raw or '[]')
    except (json.JSONDecodeError, TypeError):
        return []
    return items if isinstance(items, list) else []


def _history_date(item):
    """从 `" (8/29/26) ..."` 里取出归一化日期；取不到返回 None。"""
    match = _HISTORY_DATE_RE.search(str(item))
    if not match:
        return None
    return f'20{match.group(3)}-{int(match.group(1)):02d}-{int(match.group(2)):02d}'


def merge_history(keep_raw, drop_raws):
    """把被删行独有的历史场次补进保留行；没有新增则返回 None。

    保留行的 history 通常已经覆盖被删行（实测 23 组里 20 组如此），
    但偶尔会差一两场，静默丢掉不好，所以取并集。同日只留保留行那条。
    """
    keep_items = _history_items(keep_raw)
    seen = {date for date in (_history_date(item) for item in keep_items) if date}
    added = []
    for raw in drop_raws:
        for item in _history_items(raw):
            date = _history_date(item)
            if date and date not in seen:
                seen.add(date)
                added.append(item)
    return keep_items + added if added else None


def plan_merges(rows):
    """算出要合并的组，返回 [(保留行, [被并入的行, ...]), ...]。"""
    by_name = defaultdict(list)
    for row in rows:
        key = norm_name(row['name'])
        if key:
            by_name[key].append(row)

    plans = []
    handled = set()

    # ① 白名单：按姓名整体合并，不受首秀日影响
    for name, target_page in MERGE_WHITELIST.items():
        group = by_name.get(name) or []
        if len(group) < 2:
            continue
        keep = next((row for row in group if row['page'] == target_page), None)
        if keep is None:
            keep = max(group, key=lambda row: row['id'])
            print(f'[normalize] ⚠️ 白名单 {name} 指定的 URL 不在库里，'
                  f'回退为 id 最大行：{keep["page"]}')
        plans.append((keep, [row for row in group if row['id'] != keep['id']]))
        handled.update(row['id'] for row in group)

    # ② 自动规则：按「姓名 + 首秀日」分堆
    by_key = defaultdict(list)
    for row in rows:
        if row['id'] in handled:
            continue
        key = (norm_name(row['name']), norm_debut(row['debut']))
        if key[0] and key[1]:
            by_key[key].append(row)

    for group in by_key.values():
        if len(group) < 2:
            continue
        valid = [row for row in group if record_total(row['record']) > 0]
        if not valid:
            # 整堆都是空壳行，留着不动 —— 至少不会更坏
            continue
        keep = max(valid, key=lambda row: row['id'])
        plans.append((keep, [row for row in group if row['id'] != keep['id']]))

    return plans


def _slug(page):
    return (page or '').rsplit('/', 1)[-1]


def normalize_db(db_path=DB_PATH, apply=False):
    """执行归一化。`apply=False` 只打印计划，不写盘。"""
    if not os.path.exists(db_path):
        print(f'[normalize] 数据库不存在，跳过：{db_path}')
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = [dict(row) for row in conn.execute(
        'SELECT id, name, page, record, debut, history FROM player')]
    total_rows = len(rows)

    plans = plan_merges(rows)
    if not plans:
        print(f'[normalize] 扫描 player {total_rows} 行，没有多行组（0 组）')
        conn.close()
        return

    # ---- 算影响面（dry-run 也要能看到）----
    details = []
    for keep, drops in plans:
        rewrite = 0
        for row in drops:
            rewrite += conn.execute(
                'SELECT COUNT(*) FROM pass_card WHERE blue_page = ? OR red_page = ?',
                (row['page'], row['page'])).fetchone()[0]
        merged = merge_history(keep['history'], [row['history'] for row in drops])
        details.append((keep, drops, rewrite, merged))

    details.sort(key=lambda item: -item[0]['id'])

    print(f'[normalize] 扫描 player {total_rows} 行，发现 {len(details)} 组多行')
    for keep, drops, rewrite, merged in details:
        extra = f'  补回历史 {len(merged) - len(_history_items(keep["history"]))} 场' if merged else ''
        merged_slug = '  '.join(_slug(row['page']) for row in drops)
        print(f'  {keep["name"]:<26} {merged_slug:<30} -> {_slug(keep["page"]):<28} '
              f'改写 pass_card {rewrite:>3} 行{extra}')

    total_drop = sum(len(drops) for _, drops, _, _ in details)
    total_rewrite = sum(rewrite for _, _, rewrite, _ in details)
    total_history = sum(1 for _, _, _, merged in details if merged)
    print(f'[normalize] 合计：删 {total_drop} 行 player，'
          f'改写 {total_rewrite} 行 pass_card，{total_history} 组补回历史场次')

    if not apply:
        print('[normalize] dry-run 结束，未写盘（加 --apply 才会落盘）')
        conn.close()
        return

    # ---- 落盘：先备份，再单个事务写完 ----
    backup_path = f'{db_path}.bak-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
    conn.execute('VACUUM INTO ?', (backup_path,))
    print(f'[normalize] 已备份到 {backup_path}')

    alias_pairs = [(row['page'], keep['page'])
                   for keep, drops, _, _ in details for row in drops]
    drop_ids = [row['id'] for _, drops, _, _ in details for row in drops]
    history_updates = [(json.dumps(merged, ensure_ascii=False), keep['id'])
                       for keep, _, _, merged in details if merged]

    conn.isolation_level = None
    conn.execute('BEGIN')
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS player_url_alias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                old_page TEXT NOT NULL UNIQUE,   -- 改版前的选手主页
                new_page TEXT NOT NULL           -- 合并后保留的主页
            )
        ''')
        conn.executemany(
            'INSERT OR REPLACE INTO player_url_alias (old_page, new_page) VALUES (?, ?)',
            alias_pairs)
        # 改写要在删行之前：pass_card 的 URL 靠对照表，与 player 行是否存在无关
        conn.executemany('UPDATE pass_card SET blue_page = ? WHERE blue_page = ?',
                         [(new, old) for old, new in alias_pairs])
        conn.executemany('UPDATE pass_card SET red_page = ? WHERE red_page = ?',
                         [(new, old) for old, new in alias_pairs])
        # history 变长了，history_cn 必须清空，否则 translator 认为是「已翻译」而跳过
        conn.executemany('UPDATE player SET history = ?, history_cn = ? WHERE id = ?',
                         [(raw, '', row_id) for raw, row_id in history_updates])
        conn.executemany('DELETE FROM player WHERE id = ?',
                         [(row_id,) for row_id in drop_ids])
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        conn.close()
        raise

    print(f'[normalize] 落盘完成：player {total_rows} -> {total_rows - total_drop} 行，'
          f'pass_card 改写 {total_rewrite} 行')
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='合并 player 表里同一名选手的多行记录')
    parser.add_argument('--apply', action='store_true',
                        help='真正写盘（默认只 dry-run 打印计划）')
    parser.add_argument('--db', default=DB_PATH, help=f'数据库路径（默认 {DB_PATH}）')
    args = parser.parse_args()
    normalize_db(args.db, apply=args.apply)


if __name__ == '__main__':
    main()
