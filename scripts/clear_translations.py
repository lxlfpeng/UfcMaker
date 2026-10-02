"""清理 ufc.db 里的所有 _cn 字段 + 清空翻译缓存，用于用新的翻译链路全量重翻。

用法（在 UfcMaker 目录下执行）：
    python scripts/clear_translations.py

警告：不可逆操作！会清空：
- player 的 name_cn / nick_name_cn / city_cn / country_cn / division_cn /
  status_cn / team_cn / style_cn / history_cn / wins_stats_cn
- pass_event 的 address_cn / name_cn / title_cn
- pass_card 的 end_method_cn / card_division_cn
- ufc_translate.db 的 translate 缓存表

为什么连缓存一起清：translate_db_fields 翻译前会先查缓存，缓存里留着旧 Google 译文的话，
重翻会直接复用旧译文，达不到「用大模型重新翻译」的目的。

执行前会自动备份 ufc.db 和 ufc_translate.db 到 *.bak。
清完后再跑翻译：
    python -c "from ufcjson.translator import translate_db_fields; translate_db_fields()"
    # 或直接跑 run.py（会在爬虫后自动翻译）
"""
import os
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "output/db/ufc.db"
TRANSLATE_DB_PATH = "output/db/ufc_translate.db"

# 各表的 _cn 列
CN_COLUMNS = {
    "player": ["name_cn", "nick_name_cn", "city_cn", "country_cn", "division_cn",
               "status_cn", "team_cn", "style_cn", "history_cn", "wins_stats_cn"],
    "pass_event": ["address_cn", "name_cn", "title_cn"],
    "pass_card": ["end_method_cn", "card_division_cn"],
}


def _existing_columns(cursor, table):
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERR] 找不到 {DB_PATH}，请在 UfcMaker 目录下运行")
        sys.exit(1)

    # 备份
    shutil.copy(DB_PATH, DB_PATH + ".bak")
    if os.path.exists(TRANSLATE_DB_PATH):
        shutil.copy(TRANSLATE_DB_PATH, TRANSLATE_DB_PATH + ".bak")
    print("[clear] 已备份 ufc.db / ufc_translate.db 到 *.bak")

    # 清空各表 _cn 列
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cleared = 0
    for table, cols in CN_COLUMNS.items():
        existing = _existing_columns(cursor, table)
        for col in cols:
            if col in existing:
                cursor.execute(f"UPDATE {table} SET {col} = ''")
                cleared += 1
    conn.commit()
    conn.close()
    print(f"[clear] 已清空 {cleared} 个 _cn 列")

    # 清空翻译缓存
    if os.path.exists(TRANSLATE_DB_PATH):
        tconn = sqlite3.connect(TRANSLATE_DB_PATH)
        tconn.execute("DELETE FROM translate")
        tconn.commit()
        tconn.close()
        print("[clear] 翻译缓存已清空")
    else:
        print("[clear] 未找到翻译缓存库，跳过")

    print("[clear] 完成。接下来跑翻译：")
    print('    python -c "from ufcjson.translator import translate_db_fields; translate_db_fields()"')
    print("    # 或直接跑 run.py（会在爬虫后自动翻译）")


if __name__ == "__main__":
    main()
