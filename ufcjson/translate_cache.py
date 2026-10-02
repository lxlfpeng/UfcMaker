"""翻译缓存表 `translate` 的建表 / 去重 / 唯一索引（唯一出口，别处不要再手写 DDL）。

表结构只有 (original, translation)：一个原文一行，天然该有唯一约束。但建表语句
历史上漏了 UNIQUE，而写入端用的是 `INSERT OR IGNORE`
（translator._save_cache、llm_translator._save_batch_cache）——
没有唯一索引时 IGNORE 形同虚设，同一批译文在一次 run 内就会被写两遍
（llm_translator 按批增量写一次，translator 收尾再写一次），日积月累重复行白占体积。

这里统一出口：建表 + 去重 + 建唯一索引。新库和老库走同一条路径，
之后 INSERT OR IGNORE 才真的能忽略。

另有一张 `translate_miss`：记录「问过大模型但没拿到译文」的原文及其尝试次数。
专有名词（Noche UFC / UFC on ESPN 这类）模型可能永远答不出，光靠「失败下轮重试」
会每天都重发一次。累计到上限后搁置，不再进请求队列。
想重新尝试：`DELETE FROM translate_miss`（或把某些行的 tries 清零）。
"""
import sqlite3

# 故意不把 UNIQUE 写进建表语句：老库里已经有表了，`CREATE TABLE IF NOT EXISTS`
# 什么也不会改；统一靠下面那条命名唯一索引来约束，新库老库才是同一条代码路径。
# （若把 UNIQUE 写进 DDL，新库会生出 sqlite_autoindex_translate_1，
#  命名索引再建一遍就是重复索引。）
_CREATE_TABLE = '''
    CREATE TABLE IF NOT EXISTS translate (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original TEXT NOT NULL,     -- 原文
        translation TEXT            -- 译文
    )
'''

_CREATE_UNIQUE_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_translate_original ON translate(original)"
)

# 同一原文多行时保留哪一行：优先保留有译文的行；该原文所有行都没译文时，保留最后
# 写入的那行（id 最大）。这与 translator._load_cache「按行序后写覆盖前写」的语义一致。
_DEDUP = '''
    DELETE FROM translate WHERE id NOT IN (
        SELECT COALESCE(
            MAX(CASE WHEN translation IS NOT NULL AND translation != '' THEN id END),
            MAX(id)
        )
        FROM translate GROUP BY original
    )
'''

# 「问过大模型但没拿到译文」的原文。tries 累加，last_tried_at 只作排查用。
_CREATE_MISS = '''
    CREATE TABLE IF NOT EXISTS translate_miss (
        original TEXT PRIMARY KEY,
        tries INTEGER NOT NULL DEFAULT 0,
        last_tried_at TEXT
    )
'''


def dedup_cache(conn, vacuum=True):
    """删除同一 original 的重复行，返回删除的行数。"""
    cursor = conn.cursor()
    cursor.execute(_DEDUP)
    removed = cursor.rowcount
    conn.commit()
    if removed and vacuum:
        # 不 VACUUM 的话删掉的行只是进了空闲页表，文件大小一点不变
        # （实测删 10821 行后仍占 3.34MB / 295 个空闲页），白占的体积并没有还回来。
        # 只在真删了行时做这一次，失败也不影响功能（例如调用方正处在事务里）。
        try:
            conn.execute("VACUUM")
        except sqlite3.Error as e:
            print(f"[translate] VACUUM 跳过：{e}")
    return removed


def ensure_cache_table(conn):
    """建表（如缺）→ 去重 → 建唯一索引。幂等，可在每次拿到连接后调用。

    正常情况（索引已存在）只做一次元数据检查，几乎零开销；
    只有遇到没有索引且带重复行的老库时才会触发一次去重。
    返回本次删除的重复行数（通常是 0）。
    """
    cursor = conn.cursor()
    cursor.execute(_CREATE_TABLE)
    cursor.execute(_CREATE_MISS)
    try:
        cursor.execute(_CREATE_UNIQUE_INDEX)
    except sqlite3.IntegrityError:
        # 唯一索引建不上 ⇒ 库里还有重复 original，先去重再建
        removed = dedup_cache(conn)
        cursor.execute(_CREATE_UNIQUE_INDEX)
        conn.commit()
        return removed
    return 0


# ---------------------------------------------------------- 失败记账（translate_miss）

def load_given_up(conn, max_tries):
    """返回已搁置的原文集合（累计尝试次数 >= max_tries），这些不再进请求队列。"""
    rows = conn.execute(
        "SELECT original FROM translate_miss WHERE tries >= ?", (max_tries,)
    ).fetchall()
    return {o for (o,) in rows}


def record_failure(conn, values):
    """给「问过但没拿到译文」的原文累加尝试次数（无则新建）。返回写入条数。"""
    values = list(values)
    if not values:
        return 0
    conn.cursor().executemany(
        "INSERT INTO translate_miss (original, tries, last_tried_at) "
        "VALUES (?, 1, datetime('now')) "
        "ON CONFLICT(original) DO UPDATE SET tries = tries + 1, last_tried_at = datetime('now')",
        [(v,) for v in values],
    )
    conn.commit()
    return len(values)


def clear_miss(conn, values):
    """清掉已拿到译文的原文的失败记录（模型/提示词改进后不该被陈旧记录继续搁置）。"""
    values = list(values)
    if not values:
        return 0
    conn.cursor().executemany(
        "DELETE FROM translate_miss WHERE original = ?", [(v,) for v in values]
    )
    conn.commit()
    return len(values)

