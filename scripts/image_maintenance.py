"""
图片维护脚本：
1. download_missing()  — 检查并下载数据库中引用了但本地不存在的图片，并补全 *_local 字段
2. cleanup_unused()     — 删除磁盘上存在但数据库中没有引用的图片

用法：
    python -m scripts.image_maintenance --download  # 下载缺失图片
    python -m scripts.image_maintenance --cleanup   # 清理未引用图片
    python -m scripts.image_maintenance --all       # 先下载再清理
    python -m scripts.image_maintenance --cleanup --dry-run  # 只预览不删除
"""

import os
import sys
import json
import hashlib
import sqlite3
import argparse
from io import BytesIO

import requests
from PIL import Image

# ========== 路径配置 ==========
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE_DIR, 'output', 'db', 'ufc.db')
IMAGES_DIR = os.path.join(BASE_DIR, 'output', 'images')
FULL_DIR = os.path.join(IMAGES_DIR, 'full')
# upcoming 赛事不入库，其 banner_local 只写在这个 JSON 里
COMING_JSON = os.path.join(BASE_DIR, 'output', 'json', 'ufc_coming_data.json')

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
)
REQUEST_HEADERS = {'User-Agent': USER_AGENT}


def _url_to_local_path(url):
    """根据 URL 计算本地相对路径 full/<sha1>.webp"""
    image_guid = hashlib.sha1(url.encode()).hexdigest()
    return f"full/{image_guid}.webp"


def _local_path_exists(local_path):
    """判断本地图片是否存在"""
    full_path = os.path.join(IMAGES_DIR, local_path)
    return os.path.isfile(full_path)


def _download_image(url):
    """下载图片并保存为 webp 格式，返回本地相对路径，失败返回 None"""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        img = img.convert("RGBA")
        image_guid = hashlib.sha1(url.encode()).hexdigest()
        filename = f"{image_guid}.webp"
        full_path = os.path.join(FULL_DIR, filename)
        os.makedirs(FULL_DIR, exist_ok=True)
        img.save(full_path, "WEBP")
        return f"full/{filename}"
    except Exception as e:
        print(f"  [WARN] 下载失败 {url[:80]}... : {e}", file=sys.stderr)
        return None


def _collect_missing_from_table(cursor, table, url_col, local_col):
    """从指定表中收集缺失的图片，返回 [(id, url, local_path)] 列表"""
    cursor.execute(
        f"SELECT id, {url_col} FROM {table} "
        f"WHERE {url_col} LIKE 'http%' AND ({local_col} IS NULL OR {local_col} = '')"
    )
    rows = cursor.fetchall()
    missing = []
    for row_id, url in rows:
        if not url:
            continue
        local_path = _url_to_local_path(url)
        if not _local_path_exists(local_path):
            missing.append((row_id, url, local_path))
    return missing


def download_missing():
    """检查并下载所有缺失的图片，并补全数据库中的 *_local 字段"""
    if not os.path.isfile(DB_PATH):
        print(f"[ERROR] 数据库不存在: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 需要检查的表和字段
    tables = [
        ("player", "avatar", "avatar_local"),
        ("player", "cover", "cover_local"),
        ("pass_event", "banner", "banner_local"),
    ]

    total_missing = 0
    total_downloaded = 0
    total_skipped = 0

    for table, url_col, local_col in tables:
        missing = _collect_missing_from_table(cursor, table, url_col, local_col)
        count = len(missing)
        total_missing += count
        print(f"\n[{table}.{local_col}] 缺失 {count} 张")

        downloaded = 0
        skipped = 0
        for i, (row_id, url, local_path) in enumerate(missing, 1):
            print(f"  ({i}/{count}) 下载: {url[:80]}...")
            result = _download_image(url)
            if result:
                cursor.execute(
                    f"UPDATE {table} SET {local_col} = ? WHERE id = ?",
                    (result, row_id)
                )
                downloaded += 1
            else:
                skipped += 1

        conn.commit()
        total_downloaded += downloaded
        total_skipped += skipped
        print(f"  -> 成功 {downloaded}，失败 {skipped}")

    conn.close()

    print(f"\n========== 下载完成 ==========")
    print(f"总计缺失: {total_missing}")
    print(f"下载成功: {total_downloaded}")
    print(f"下载失败: {total_skipped}")
    return True


def _collect_referenced_images(cursor):
    """收集所有被引用的本地图片路径集合（数据库 + upcoming JSON）"""
    referenced = set()

    # player 表
    for col in ["avatar_local", "cover_local"]:
        cursor.execute(
            f"SELECT DISTINCT {col} FROM player WHERE {col} IS NOT NULL AND {col} != ''"
        )
        for row in cursor.fetchall():
            if row[0]:
                referenced.add(row[0])

    # pass_event 表
    cursor.execute(
        "SELECT DISTINCT banner_local FROM pass_event "
        "WHERE banner_local IS NOT NULL AND banner_local != ''"
    )
    for row in cursor.fetchall():
        if row[0]:
            referenced.add(row[0])

    # upcoming 赛事未入库，引用只在 ufc_coming_data.json 里
    if os.path.isfile(COMING_JSON):
        try:
            with open(COMING_JSON, encoding='utf-8') as f:
                for row in json.load(f).get('data', []):
                    if row.get('banner_local'):
                        referenced.add(row['banner_local'])
        except (OSError, ValueError) as e:
            print(f"  [WARN] 读取 {COMING_JSON} 失败: {e}", file=sys.stderr)

    return referenced


def cleanup_unused(dry_run=False, auto_confirm=False):
    """清理磁盘上未被数据库引用的图片

    Args:
        dry_run: 为 True 时只列出不删除
        auto_confirm: 为 True 时跳过交互确认直接删除（用于自动化脚本）
    """
    if not os.path.isfile(DB_PATH):
        print(f"[ERROR] 数据库不存在: {DB_PATH}")
        return False
    if not os.path.isdir(FULL_DIR):
        print(f"[ERROR] 图片目录不存在: {FULL_DIR}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    referenced = _collect_referenced_images(cursor)
    conn.close()

    print(f"数据库引用的图片数: {len(referenced)}")

    # 遍历磁盘上的所有图片
    all_files = set()
    for filename in os.listdir(FULL_DIR):
        if filename.endswith('.webp'):
            all_files.add(f"full/{filename}")

    print(f"磁盘上的图片数: {len(all_files)}")

    unused = all_files - referenced
    print(f"未引用的图片数: {len(unused)}")

    if not unused:
        print("\n没有未引用的图片，无需清理。")
        return True

    # 计算总大小
    total_size = 0
    for local_path in sorted(unused):
        full_path = os.path.join(IMAGES_DIR, local_path)
        try:
            total_size += os.path.getsize(full_path)
        except OSError:
            pass

    size_mb = total_size / (1024 * 1024)
    print(f"未引用图片总大小: {size_mb:.1f} MB")

    if dry_run:
        print("\n[DRY-RUN] 以下图片将被删除:")
        for p in sorted(unused)[:20]:
            print(f"  {p}")
        if len(unused) > 20:
            print(f"  ... 还有 {len(unused) - 20} 张")
        return True

    # 确认删除（auto_confirm 时跳过）
    if not auto_confirm:
        confirm = input(f"\n确认删除 {len(unused)} 张图片 ({size_mb:.1f} MB)? (y/N): ")
        if confirm.lower() != 'y':
            print("已取消。")
            return False
    else:
        print(f"\n[自动确认] 删除 {len(unused)} 张图片 ({size_mb:.1f} MB)")

    deleted = 0
    for local_path in unused:
        full_path = os.path.join(IMAGES_DIR, local_path)
        try:
            os.remove(full_path)
            deleted += 1
        except OSError as e:
            print(f"  [WARN] 删除失败 {local_path}: {e}", file=sys.stderr)

    print(f"\n已删除 {deleted} 张图片。")
    return True


def main():
    parser = argparse.ArgumentParser(description='图片维护脚本')
    parser.add_argument('--download', action='store_true',
                        help='下载缺失的图片并补全数据库')
    parser.add_argument('--cleanup', action='store_true',
                        help='清理未引用的图片')
    parser.add_argument('--all', action='store_true',
                        help='先下载再清理')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅列出不实际删除（配合 --cleanup 使用）')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='跳过交互确认直接删除（配合 --cleanup 使用，自动化场景）')
    args = parser.parse_args()

    if not (args.download or args.cleanup or args.all):
        parser.print_help()
        return

    os.chdir(BASE_DIR)

    if args.download or args.all:
        download_missing()

    if args.cleanup or args.all:
        cleanup_unused(dry_run=args.dry_run, auto_confirm=args.yes)


if __name__ == '__main__':
    main()
