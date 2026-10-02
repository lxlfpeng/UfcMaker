"""pass_event 地点四列补齐：city / country / city_cn / country_cn（2026-10-02 恢复）。

背景：四列 2026-09-19 新增、09-20 被连带从 DDL/INSERT 摘除、2026-10-02 用户拍板恢复。
本仓爬虫 `EventpassSpider.parse_address` 一直在算 city/country（只是 INSERT 没写出去，
现已恢复写入）；**存量库用本脚本**：

  1. `ALTER TABLE ... ADD COLUMN` 幂等补列（旧库 `CREATE TABLE IF NOT EXISTS` 不补列）；
  2. 按 `address` 拆段回填 city / country——**与爬虫共用 `parse_address`**，保证口径同源；
  3. `--translate` 时顺带跑翻译管线，把 city_cn / country_cn 也补上（缓存命中不出网）。

用法（在 UfcMaker 目录下执行）：
    python scripts/backfill_event_place.py              # 补列 + 回填
    python scripts/backfill_event_place.py --dry-run    # 只报告，不写库
    python scripts/backfill_event_place.py --translate  # 回填后再跑翻译补 *_cn
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 与爬虫共用同一条拆分口径（含 Macao 特例），不要另写一套
from ufcjson.spiders.eventpass import EventpassSpider

DB = "output/db/ufc.db"
TRANSLATE_DB = "output/db/ufc_translate.db"
NEW_COLUMNS = ("city", "country", "city_cn", "country_cn")


def missing_columns(cursor):
    have = {row[1] for row in cursor.execute("PRAGMA table_info(pass_event)")}
    return [col for col in NEW_COLUMNS if col not in have]


def ensure_columns(cursor):
    """幂等补列，返回本次新增的列名。"""
    added = []
    for col in missing_columns(cursor):
        cursor.execute(f"ALTER TABLE pass_event ADD COLUMN {col} TEXT")
        added.append(col)
    return added


def main():
    ap = argparse.ArgumentParser(description="pass_event 地点四列：补列 + 按 address 拆段回填")
    ap.add_argument("--db", default=DB, help=f"目标库（默认 {DB}）")
    ap.add_argument("--dry-run", action="store_true", help="只报告不写入")
    ap.add_argument("--translate", action="store_true", help="回填后跑翻译补 city_cn / country_cn")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"[backfill] 找不到 {args.db}，请在 UfcMaker 目录下运行")

    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()

    if args.dry_run:
        missing = missing_columns(cursor)
        print(f"[backfill] 缺列: {missing if missing else '四列已齐'}")
    else:
        added = ensure_columns(cursor)
        print(f"[backfill] 补列: {added if added else '四列已齐，无需补列'}")

    rows = cursor.execute(
        "SELECT id, address, city, country FROM pass_event "
        "WHERE address != '' AND (city IS NULL OR city = '' OR country IS NULL OR country = '')"
    ).fetchall()
    fixed = skipped = 0
    for rid, address, _city, _country in rows:
        city, country = EventpassSpider.parse_address(address)
        if not country:
            skipped += 1
            continue
        if not args.dry_run:
            cursor.execute("UPDATE pass_event SET city = ?, country = ? WHERE id = ?",
                           (city, country, rid))
        fixed += 1
    if not args.dry_run:
        conn.commit()
    conn.close()
    print(f"[backfill] {'将' if args.dry_run else '已'}回填 {fixed} 行；"
          f"地址拆不出国家跳过 {skipped} 行")

    if args.translate:
        if args.dry_run:
            print("[backfill] --dry-run 与 --translate 同用时跳过翻译")
            return
        from ufcjson.translator import translate_db_fields
        translate_db_fields(args.db, TRANSLATE_DB)


if __name__ == "__main__":
    main()