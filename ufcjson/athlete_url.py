# -*- coding: utf-8 -*-
"""选手主页 URL 归一化：把 ufc.com 的别名 slug 收敛到规范 slug。

背景
----
player.page              ← athlete.py:50          从 /athletes/all 列表页取 → 规范 slug
pass_card.blue/red_page  ← eventpass.py:167/171   从赛事页角标取        → 站点当下的写法

两者都是 ufc.com 的 URL，却由两个爬虫从两个页面分别抓取，ufc.com 自己也不保证它们一致。
实测：`/athlete/guram-kutateladze-1` 是张名扬的资料页别名，301 到 `/athlete/zhang-mingyang`。
App 端 `queryPlayer(page)` 是 `where page = ?` 精确等值（AppRoomDataBase.kt:300），
两侧不等即查不到 → 战卡那一格空白。

两个入口
--------
normalize_url()        单 URL 归一    —— eventpass 写库前调用（入口断源，防复发）
reconcile_pass_card()  全库对账回写   —— run.py 收尾调用（补历史 + 兜漏网）

归一顺序（逐级降级；本地命中就完全不发网络请求）
------------------------------------------------
1) 已在 player.page             → 原样返回（绝大多数情况）
2) 命中 player_url_alias        → 返回映射目标
3) 网络 follow 重定向取最终 URL → 登记别名表后返回（下次走第 2 步）
4) 都不行                       → 返回 None，调用方保持原值，绝不猜

网络通道说明
------------
ufc.com 对大陆 IP 会整站改写到 ufc.cn，本机取不到 301，只有生产服务器能直连。
online=False 时退化为纯本地归一（本机可跑，用于验证前两级）。
"""

import argparse
import sqlite3
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

DB_PATH = "output/db/ufc.db"
UFC_HOST = "https://www.ufc.com"
DEFAULT_TIMEOUT = 8.0
# ufc.com 对大陆 IP 会整站 30x 改写到 ufc.cn。若不加域名守卫，本机跑会把 slug 写成 ufc.cn 地址，
# 所以最终地址必须仍落在 ufc.com 上，否则一律视为解析失败。
ALLOWED_HOSTS = {"www.ufc.com", "ufc.com"}
# 探测结果缓存：成功的映射进 player_url_alias（永久），失败/无变化的重试窗口见 PROBE_TTL_DAYS。
# 没有这层缓存，run.py 每次收尾都会把全部缺失 URL 重新请求一遍。
PROBE_TTL_DAYS = 7
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def ensure_alias_table(conn):
    """别名表结构对齐已落库的 player_url_alias（id / old_page UNIQUE / new_page）"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS player_url_alias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            old_page TEXT NOT NULL UNIQUE,
            new_page TEXT NOT NULL
        )
        """
    )
    conn.commit()


def load_alias_map(conn):
    ensure_alias_table(conn)
    return {r[0]: r[1] for r in conn.execute("SELECT old_page, new_page FROM player_url_alias")}


def load_player_pages(conn):
    return {r[0] for r in conn.execute("SELECT page FROM player")}


def ensure_probe_table(conn):
    """探测结果缓存表（记录「查过了、结果是什么」），避免每轮重复请求"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS player_url_probe (
            url TEXT PRIMARY KEY,
            final TEXT NOT NULL DEFAULT '',
            checked_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()


def load_probe_map(conn):
    ensure_probe_table(conn)
    return {
        r[0]: (r[1], r[2])
        for r in conn.execute("SELECT url, final, checked_at FROM player_url_probe")
    }


def record_probe(conn, url, final, probe_cache=None):
    ensure_probe_table(conn)
    ts = int(time.time())
    conn.execute(
        "INSERT OR REPLACE INTO player_url_probe (url, final, checked_at) VALUES (?, ?, ?)",
        (url, final, ts),
    )
    conn.commit()
    if probe_cache is not None:
        probe_cache[url] = (final, ts)


def _probe_fresh(checked_at, ttl_days=PROBE_TTL_DAYS):
    try:
        return (time.time() - int(checked_at)) < ttl_days * 86400
    except (TypeError, ValueError):
        return False


def absolutize(url):
    """赛事页给的是绝对 URL，这里兜底相对写法"""
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return UFC_HOST + url
    return url


def record_alias(conn, old_page, new_page, alias_map=None):
    ensure_alias_table(conn)
    conn.execute(
        "INSERT OR REPLACE INTO player_url_alias (old_page, new_page) VALUES (?, ?)",
        (old_page, new_page),
    )
    conn.commit()
    if alias_map is not None:
        alias_map[old_page] = new_page


def _is_ufc_url(url):
    return urlparse(url).netloc.lower() in ALLOWED_HOSTS


def _is_athlete_url(url):
    """规范主页必须是 /athlete/<slug>。站点会把不存在/已下架的选手页 30x 到
    /search?query=... 或别的落地页，那不是规范主页，绝不能写进库。"""
    path = urlparse(url).path.rstrip("/")
    return path.startswith("/athlete/") and len(path) > len("/athlete")


def _is_valid_target(url):
    """可接受的规范主页：ufc.com 域下的 /athlete/<slug>。

    网络 301 与本地别名映射都要过这一关 —— 别名表可能残留脏映射
    （实测曾写进过 /search?query=... 这种落地页）。
    """
    return bool(url) and _is_ufc_url(url) and _is_athlete_url(url)


def resolve_redirect(url, timeout=DEFAULT_TIMEOUT, opener=None):
    """follow 重定向拿最终 URL。未发生重定向、请求失败或落到别的域返回 None。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    urlopen = opener.urlopen if opener is not None else urllib.request.urlopen
    try:
        response = urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as e:
        # 403/404：页面已关闭。若中途发生过重定向，最终地址在 e.url（经 fp 代理）。
        # 注意：HTTPError 本身没有 url 属性，fp 为空时取它会抛异常，必须兜住。
        try:
            final = e.url or ""
        except Exception:
            final = ""
        if not final:
            final = getattr(e, "filename", "") or ""
        return _accept_final(url, final)
    except Exception:
        return None
    try:
        final = response.geturl()
    except Exception:
        return None
    finally:
        try:
            response.close()
        except Exception:
            pass
    return _accept_final(url, final)


def _accept_final(url, final):
    if not final or final.rstrip("/") == url.rstrip("/"):
        return None
    if not _is_valid_target(final):
        return None
    return final


def normalize_url(conn, url, online=True, player_pages=None, alias_map=None,
                  probe_cache=None, timeout=DEFAULT_TIMEOUT, opener=None):
    """把单个主页 URL 归一到规范 slug；无法判定时返回 None（调用方保持原值）。"""
    url = absolutize(url)
    if not url.startswith("http"):
        return None

    pages = player_pages if player_pages is not None else load_player_pages(conn)
    if url in pages:
        return url

    amap = alias_map if alias_map is not None else load_alias_map(conn)
    hit = amap.get(url)
    if hit and hit != url and _is_valid_target(hit):
        return hit

    if not online or not _is_ufc_url(url):
        return None

    if probe_cache is None:
        probe_cache = load_probe_map(conn)
    probed = probe_cache.get(url)
    if probed and _probe_fresh(probed[1]):
        return probed[0] or None

    final = resolve_redirect(url, timeout=timeout, opener=opener)
    record_probe(conn, url, final or "", probe_cache=probe_cache)
    if not final:
        return None
    record_alias(conn, url, final, alias_map=amap)
    return final


def find_missing_urls(conn, player_pages=None):
    """pass_card 里所有不在 player 的主页 URL → {url: [受影响行 id, ...]}"""
    pages = player_pages if player_pages is not None else load_player_pages(conn)
    missing = {}
    for rid, blue, red in conn.execute("SELECT id, blue_page, red_page FROM pass_card"):
        for url in (absolutize(blue), absolutize(red)):
            if url and url not in pages:
                missing.setdefault(url, []).append(rid)
    return missing


def build_plan(conn, online=True, player_pages=None, alias_map=None,
               timeout=DEFAULT_TIMEOUT, opener=None):
    """产出 [(old_url, new_url_or_None, note), ...] 与统计。不写 pass_card。"""
    pages = player_pages if player_pages is not None else load_player_pages(conn)
    amap = alias_map if alias_map is not None else load_alias_map(conn)
    probe = load_probe_map(conn)
    missing = find_missing_urls(conn, pages)

    stats = {
        "missing_urls": len(missing),
        "resolved": 0,
        "unresolved": 0,
        "target_missing_in_player": 0,
    }
    plan = []
    for url in sorted(missing):
        target = normalize_url(conn, url, online=online, player_pages=pages,
                               alias_map=amap, probe_cache=probe,
                               timeout=timeout, opener=opener)
        if not target or target == url:
            stats["unresolved"] += 1
            plan.append((url, None, "无 301 目标 / 未发生重定向"))
            continue
        stats["resolved"] += 1
        note = ""
        if target not in pages:
            stats["target_missing_in_player"] += 1
            note = "目标不在 player，需补爬"
        plan.append((url, target, note))
    return plan, stats


def apply_plan(conn, plan):
    """按 plan 改写 pass_card，返回改写处数。"""
    rewritten = 0
    skipped_same_person = 0
    for old, new, _note in plan:
        if not new or new == old:
            continue
        for col in ("blue_page", "red_page"):
            rows = conn.execute(
                f"SELECT id, blue_page, red_page FROM pass_card WHERE {col} = ?", (old,)
            ).fetchall()
            for rid, blue, red in rows:
                other = red if col == "blue_page" else blue
                if other == new:
                    skipped_same_person += 1
                    continue
                conn.execute(f"UPDATE pass_card SET {col} = ? WHERE id = ?", (new, rid))
                rewritten += 1
    conn.commit()
    return rewritten, skipped_same_person


def reconcile_pass_card(conn, online=True, apply=False, timeout=DEFAULT_TIMEOUT,
                        opener=None, verbose=True):
    """全库对账：把 pass_card 里指向 player 之外的主页 URL 归一到规范 slug。

    apply=False 时只出清单不落盘。返回 (stats, plan)。
    """
    page_count = conn.execute("SELECT COUNT(*) FROM pass_card").fetchone()[0]
    plan, stats = build_plan(conn, online=online, timeout=timeout, opener=opener)
    stats["rows"] = page_count

    if apply:
        rewritten, skipped = apply_plan(conn, plan)
        stats["rewritten"] = rewritten
        stats["skipped_same_person"] = skipped
    else:
        stats["rewritten"] = 0
        stats["skipped_same_person"] = 0

    if verbose:
        mode = "APPLY" if apply else "DRY-RUN"
        net = "online" if online else "offline"
        print(f"[url] {mode} ({net}) pass_card {page_count} 行，"
              f"不在 player 的 URL {stats['missing_urls']} 个 → "
              f"可归一 {stats['resolved']}，未解 {stats['unresolved']}，"
              f"目标待补爬 {stats['target_missing_in_player']}")
        if apply:
            print(f"[url] 已改写 {stats['rewritten']} 处"
                  f"（跳过会使两侧同一人的 {stats['skipped_same_person']} 处）")
        for old, new, note in plan:
            arrow = new or "—"
            print(f"  {old.rsplit('/', 1)[-1]:<34} → {arrow.rsplit('/', 1)[-1]:<30} {note}")
    return stats, plan


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="选手主页 URL 归一化：把 pass_card 里的别名 slug 换成规范 slug"
    )
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--offline", action="store_true", help="只做本地归一，不发网络请求")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    try:
        reconcile_pass_card(conn, online=not args.offline, apply=args.apply,
                            timeout=args.timeout)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
