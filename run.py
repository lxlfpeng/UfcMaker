import os
import json
import hashlib
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
import argparse

from ufcjson.translator import translate_db_fields

# ========== meta.json 相关常量 ==========
SCHEMA_VERSION = 1
GENERATOR = "UfcMaker"
META_JSON_PATH = "output/json/meta.json"
DB_PATH = "output/db/ufc.db"
COMING_JSON_PATH = "output/json/ufc_coming_data.json"
RANKING_JSON_PATH = "output/json/ufc_ranking_data.json"

log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log', 'scrapy_log.log')
if os.path.exists(log_path):
    os.remove(log_path)

# 通过启动附加参数获取到email的密码
parser = argparse.ArgumentParser(description='manual to this script')
parser.add_argument("--email_pwd", "--email_pass", type=str, default="", help='input email password')
os.environ['email_pwd'] = parser.parse_args().email_pwd


spiders_run = []

# 周三爬取排行榜和选手数据 分页爬取
if datetime.now().weekday() == 2:
    subprocess.run(["scrapy", "crawl", "ranking"], check=True)
    spiders_run.append("ranking")
    subprocess.run(["scrapy", "crawl", "athlete", "-a", "pagination=true"], check=True)
    spiders_run.append("athlete")

# 周天爬取已进行比赛的数据
if datetime.now().weekday() == 6:
    subprocess.run(["scrapy", "crawl", "eventpass"], check=True)
    spiders_run.append("eventpass")

# 每日爬取赛程
subprocess.run(["scrapy", "crawl", "upcoming"], check=True)
spiders_run.append("upcoming")

# 每日爬取 UFC 中文新闻（追加到 RSS）
subprocess.run(["scrapy", "crawl", "ufccn_news"], check=True)
spiders_run.append("ufccn_news")


# ========== 生成 meta.json ==========

def _read_old_meta():
    """读取已有的 meta.json，不存在返回 None（兼容旧格式和新的 API 包装格式）"""
    if not os.path.exists(META_JSON_PATH):
        return None
    try:
        with open(META_JSON_PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        # 新格式：外层是 API 响应包装，实际 meta 在 data 里
        if isinstance(raw, dict) and "data" in raw and "schema_version" in raw["data"]:
            return raw["data"]
        return raw
    except (json.JSONDecodeError, IOError):
        return None


def _get_db_data_version():
    """获取 SQLite data_version，数据库不存在返回 None"""
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA data_version")
        version = cursor.fetchone()[0]
        conn.close()
        return version
    except sqlite3.Error:
        return None


def _get_db_counts():
    """查询各表条目数，返回 dict"""
    counts = {"athlete_count": 0, "pass_event_count": 0}
    if not os.path.exists(DB_PATH):
        return counts
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for table, key in [("player", "athlete_count"), ("pass_event", "pass_event_count")]:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                counts[key] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                # 表不存在则保持 0
                pass
        conn.close()
    except sqlite3.Error:
        pass
    return counts


def _get_json_count_and_hash(file_path):
    """读取 JSON 文件，返回 (count, md5_hash)；文件不存在返回 (0, None)"""
    if not os.path.exists(file_path):
        return 0, None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        items = data.get("data", [])
        count = len(items) if isinstance(items, list) else 0
        content_hash = hashlib.md5(json.dumps(items, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
        return count, content_hash
    except (json.JSONDecodeError, IOError):
        return 0, None


def _get_db_file_info():
    """获取数据库文件的大小和 MD5，不存在返回 (0, None)"""
    if not os.path.exists(DB_PATH):
        return 0, None
    try:
        size = os.path.getsize(DB_PATH)
        md5 = hashlib.md5()
        with open(DB_PATH, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return size, md5.hexdigest()
    except OSError:
        return 0, None


def _has_update(old_meta, db_version, coming_hash, ranking_hash, db_md5):
    """对比新旧指纹，判断数据是否有变化"""
    if old_meta is None:
        return True

    old_db_version = old_meta.get("_db_data_version")
    old_coming_hash = old_meta.get("_coming_hash")
    old_ranking_hash = old_meta.get("_ranking_hash")
    old_db_md5 = old_meta.get("db_md5")

    # 任一指纹变化则视为有更新
    if db_version is not None and old_db_version != db_version:
        return True
    if coming_hash is not None and old_coming_hash != coming_hash:
        return True
    if ranking_hash is not None and old_ranking_hash != ranking_hash:
        return True
    # 数据库文件 MD5 变化（比如重建索引、VACUUM 等 data_version 不变但文件变了的情况）
    if db_md5 is not None and old_db_md5 != db_md5:
        return True

    return False


def generate_meta_json(spiders_run):
    """生成 meta.json 数据版本元信息"""
    old_meta = _read_old_meta()

    # 计算数据库指纹
    db_version = _get_db_data_version()
    db_size, db_md5 = _get_db_file_info()

    # 计算 JSON 文件指纹
    coming_count, coming_hash = _get_json_count_and_hash(COMING_JSON_PATH)
    ranking_count, ranking_hash = _get_json_count_and_hash(RANKING_JSON_PATH)

    # 获取各数据集计数
    db_counts = _get_db_counts()

    # 判断是否有更新
    now = datetime.now(timezone(timedelta(hours=8)))
    if _has_update(old_meta, db_version, coming_hash, ranking_hash, db_md5):
        last_updated = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        last_updated_ts = int(now.timestamp())
    else:
        # 沿用旧的更新时间
        last_updated = old_meta.get("last_updated", now.strftime("%Y-%m-%dT%H:%M:%S+08:00"))
        last_updated_ts = old_meta.get("last_updated_ts", int(now.timestamp()))

    meta = {
        "schema_version": SCHEMA_VERSION,
        "last_updated": last_updated,
        "last_updated_ts": last_updated_ts,
        "generator": GENERATOR,
        "spiders_run": spiders_run,
        "athlete_count": db_counts["athlete_count"],
        "pass_event_count": db_counts["pass_event_count"],
        "upcoming_event_count": coming_count,
        "ranking_count": ranking_count,
        # 数据库文件信息（客户端用于下载完整性校验）
        "db_md5": db_md5,
        "db_size": db_size,
        # 内部指纹字段，用于下次对比是否有更新
        "_db_data_version": db_version,
        "_coming_hash": coming_hash,
        "_ranking_hash": ranking_hash,
    }

    # 标准 API 响应包装
    output = {
        "code": 0,
        "msg": "success",
        "data": meta,
        "timestamp": int(datetime.now(timezone(timedelta(hours=8))).timestamp() * 1000),
    }

    # 确保目录存在
    os.makedirs(os.path.dirname(META_JSON_PATH), exist_ok=True)

    with open(META_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[meta] {META_JSON_PATH} 已更新 (last_updated: {last_updated})")


# ========== 翻译 ==========
# 爬虫落库后统一翻译未翻译的字段（缓存优先，失败不阻塞整个流程）
def run_translation():
    """翻译数据库中 src 非空且 dst 为空的字段。"""
    try:
        print("\n========== 翻译未翻译字段 ==========")
        translate_db_fields(DB_PATH, 'output/db/ufc_translate.db')
        print("========== 翻译结束 ==========\n")
    except Exception as e:
        print(f"[WARN] 翻译步骤失败: {e}")


# ========== 图片维护 ==========
# 每次爬取完成后自动补全缺失图片并清理未引用图片
def run_image_maintenance():
    """执行图片维护：下载缺失 + 清理未引用（自动确认，无人值守场景）"""
    try:
        from scripts.image_maintenance import download_missing, cleanup_unused
        print("\n========== 图片维护开始 ==========")
        download_missing()
        cleanup_unused(dry_run=False, auto_confirm=True)
        print("========== 图片维护结束 ==========\n")
    except Exception as e:
        print(f"[WARN] 图片维护失败: {e}")

# 只要跑过任意爬虫就执行一次翻译 + 图片维护
if spiders_run:
    run_translation()
    run_image_maintenance()

generate_meta_json(spiders_run)