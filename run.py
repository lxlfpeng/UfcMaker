import os
import json
import hashlib
import sqlite3
import subprocess
import zipfile
from datetime import datetime, timezone, timedelta
import argparse

from ufcjson.normalize import normalize_db
from ufcjson.athlete_url import reconcile_pass_card
from ufcjson.translator import translate_db_fields

# ========== meta.json 相关常量 ==========
SCHEMA_VERSION = 1
GENERATOR = "UfcMaker"
META_JSON_PATH = "output/json/meta.json"
DB_PATH = "output/db/ufc.db"
DB_ZIP_PATH = "output/db/ufc.db.zip"
DB_ZIP_ENTRY_NAME = "ufc.db"
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


def _get_file_size_md5(file_path):
    """获取任意文件的大小和 MD5，不存在返回 (0, None)"""
    if not os.path.exists(file_path):
        return 0, None
    try:
        size = os.path.getsize(file_path)
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return size, md5.hexdigest()
    except OSError:
        return 0, None


def _get_db_file_info():
    """获取数据库文件的大小和 MD5，不存在返回 (0, None)"""
    return _get_file_size_md5(DB_PATH)


# ========== 数据库打包（客户端下发的是 zip） ==========
# 分发通道是 GitHub raw / Gitee raw / gh-proxy，它们对二进制不做压缩，
# 裸库 6.4 MB 会全额计入用户流量；zip(deflate 9) 后约 1.4 MB（22%）。
#
# ⚠️ 打包必须是确定性的：同一份 db 内容必须产出逐字节相同的 zip。
#    否则 CI 每天 `git add .` 都会提交一个新的 1.4 MB blob（仓库无限膨胀），
#    而数据本身其实一行没变。为此固定时间戳 / 权限位 / 宿主系统三个字段。
_ZIP_FIXED_DOS_TIME = (1980, 1, 1, 0, 0, 0)


def build_db_zip():
    """把 DB_PATH 打包为 DB_ZIP_PATH（确定性输出；失败不阻塞主流程）"""
    if not os.path.exists(DB_PATH):
        print(f"[zip] 跳过：{DB_PATH} 不存在")
        return
    try:
        os.makedirs(os.path.dirname(DB_ZIP_PATH), exist_ok=True)
        zip_info = zipfile.ZipInfo(DB_ZIP_ENTRY_NAME, date_time=_ZIP_FIXED_DOS_TIME)
        zip_info.compress_type = zipfile.ZIP_DEFLATED
        # 固定权限位与宿主系统标识，跨机器输出才一致
        zip_info.external_attr = 0o644 << 16
        zip_info.create_system = 0

        with open(DB_PATH, 'rb') as f:
            db_bytes = f.read()

        with zipfile.ZipFile(DB_ZIP_PATH, 'w',
                             compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9) as zf:
            zf.writestr(zip_info, db_bytes)

        print(f"[zip] {DB_ZIP_PATH} 已生成 "
              f"({os.path.getsize(DB_ZIP_PATH):,} 字节, 原始 {len(db_bytes):,} 字节)")
    except Exception as e:
        print(f"[WARN] 打包 db 失败: {e}")


def _get_db_zip_info():
    """获取下发 zip 的大小和 MD5，不存在返回 (0, None)"""
    return _get_file_size_md5(DB_ZIP_PATH)


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
    db_zip_size, db_zip_md5 = _get_db_zip_info()

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
        # db_* 描述的是解压后的 ufc.db 本体，db_zip_* 描述的是实际下发的压缩包。
        # 客户端先用 db_zip_* 校验包，解压后再用 db_* 校验库本体。
        "db_md5": db_md5,
        "db_size": db_size,
        "db_zip_md5": db_zip_md5,
        "db_zip_size": db_zip_size,
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


# ========== 导出层归一化 ==========
# 选手主页 slug 变更后，同一名选手会在 player 表里留下两行，战绩被拆到旧 URL 上。
# 这里在爬虫全部跑完之后把多行合成一行，并把 pass_card 里的旧 URL 改写过去。
def run_normalization():
    """合并同一名选手的多行，并改写 pass_card 的旧 URL（失败不阻塞整个流程）"""
    try:
        print("\n========== 选手多行归一化 ==========")
        normalize_db(DB_PATH, apply=True)
        print("========== 归一化结束 ==========\n")
    except Exception as e:
        print(f"[WARN] 归一化步骤失败: {e}")


# ========== 选手主页 URL 对账 ==========
# 赛事页角标给的主页 URL 可能是 ufc.com 的别名 slug（如 guram-kutateladze-1 实际是张名扬），
# 与 athlete.py 写进 player.page 的规范 slug 不一致。App 端 queryPlayer(page) 是精确等值匹配，
# 两侧不等就查不到选手 → 战卡那一格空白，且 eventpass 对已有赛事 skip、永不重抓，脏数据不会自愈。
# 这里在爬虫全部跑完之后把 pass_card 里指向 player 之外的 URL 过一遍 301 归一。
def run_url_reconcile():
    """把 pass_card 里的别名主页 URL 归一到规范 slug（失败不阻塞整个流程）"""
    try:
        print("\n========== 选手主页 URL 对账 ==========")
        conn = sqlite3.connect(DB_PATH)
        try:
            reconcile_pass_card(conn, online=True, apply=True)
        finally:
            conn.close()
        print("========== 对账结束 ==========\n")
    except Exception as e:
        print(f"[WARN] URL 对账步骤失败: {e}")


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

# 只要跑过任意爬虫就执行一次归一化 + URL 对账 + 翻译 + 图片维护
if spiders_run:
    run_normalization()
    run_url_reconcile()
    run_translation()
    run_image_maintenance()

# 打包必须在所有会改动 db 的步骤（归一化 / 对账 / 翻译 / 图片维护）之后、
# 生成 meta 之前：meta 里的 db_zip_* 指纹要对应最终下发的那个包。
build_db_zip()

generate_meta_json(spiders_run)