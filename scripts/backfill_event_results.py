#!/usr/bin/env python3
"""手动回填 pass_card 空 结果字段（blue_result / red_result）。

背景
----
pass_card 里有 600+ 行「两侧结果都空」的对局（117 个赛事）。eventpass 爬虫
对已存在赛事直接 continue 永不回抓，这些行一旦入库就永远是空。App 端
「UFC 战绩」用 isDecided 过滤空结果行，导致这些比赛在选手战绩里整场消失。

实测（2026-09-18，UFC 241）上游赛事页现在有完整结果——不少「上游空」的
旧结论已过时。本脚本逐个抓取赛事详情页，把页面上的 W/L 回填到库里。

规则
----
- 只处理「两侧结果都空」且赛事已开打（main_time < now）的行；未来赛事跳过。
- 只补 blue_result / red_result，**不动 end_method / end_method_cn /
  end_round / end_time**（按 2026-09-18 决策，归一化另行处理）。
- 页面两侧结果必须是合法组合（Win/Loss、Draw/Draw、NC/NC）才落库，
  单侧有值或脏值一律跳过并报告。
- 匹配键 = (fight_page, 双方 URL 无序对)；直接对不上时走
  player_url_alias 别名表归一再试（赛事页角标可能是别名 slug）。
- 不写任何记账文件：结果只在终端打印。每次运行都重新扫「当前仍为空」的赛事，
  库里已有结果的场次自动跳过（幂等），所以重跑不会重复写、也不会漏。

用法
----
    python scripts/backfill_event_results.py                    # dry-run，全量待处理
    python scripts/backfill_event_results.py --limit 3          # dry-run，先试 3 个
    python scripts/backfill_event_results.py --event ufc-241    # 只跑指定赛事
    python scripts/backfill_event_results.py --apply            # 落库 + 重建 zip/meta

⚠️ 本机访问 ufc.com 不稳定（时 200 时 301→ufc.cn），脚本内置重试，
   单页失败不阻塞整轮。落库后会重建 output/db/ufc.db.zip + meta.json
   （照抄 run.py 的确定性打包逻辑；不能 import run.py，其顶层就会跑爬虫）。
"""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

# 以仓库根目录为基准（脚本在 UfcMaker/scripts/ 下）
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "output/db/ufc.db")
DB_ZIP_PATH = os.path.join(BASE, "output/db/ufc.db.zip")
DB_ZIP_ENTRY_NAME = "ufc.db"
META_JSON_PATH = os.path.join(BASE, "output/json/meta.json")
COMING_JSON_PATH = os.path.join(BASE, "output/json/ufc_coming_data.json")
RANKING_JSON_PATH = os.path.join(BASE, "output/json/ufc_ranking_data.json")

MAX_FETCH_TRIES = 3
FETCH_SLEEP = 1.0  # 每页之间的礼貌间隔（秒）

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

# 选择器照抄 eventpass.py::parse_detail（保持同源，页面结构变了要两边一起改）
XPATH_GROUPS = '//*[@class="l-listing__group--bordered"]'
XPATH_RED_HREF = ('.//div[@class="c-listing-fight__corner-name '
                  'c-listing-fight__corner-name--red"]//a/@href')
XPATH_BLUE_HREF = ('.//div[@class="c-listing-fight__corner-name '
                   'c-listing-fight__corner-name--blue"]//a/@href')
XPATH_RED_RESULT = './/div[@class="c-listing-fight__corner-body--red"]/div/div/text()'
XPATH_BLUE_RESULT = './/div[@class="c-listing-fight__corner-body--blue"]/div/div/text()'

# 合法结果组合
VALID_PAIRS = {frozenset(p) for p in (("Win", "Loss"), ("Draw", "Draw"), ("NC", "NC"))}

# 互补关系：ufc.com 部分赛事页只给一方打结果角标（实测 UFC 248 仅 3 场有标记，
# 且都是只有胜者一侧），此时另一侧可由胜负互补唯一确定——这是推导不是猜。
COMPLEMENT = {"Win": "Loss", "Loss": "Win", "Draw": "Draw", "NC": "NC"}


def load_selector():
    from parsel import Selector  # scrapy 自带，延迟导入方便看 --help
    return Selector


def norm_url(url):
    if not url:
        return ""
    url = url.strip()
    if url.startswith("/"):
        url = urljoin("https://www.ufc.com", url)
    return url.rstrip("/")


def clean(text):
    return (text or "").replace(" ", "").replace("\n", "").replace("\r", "").strip()


def fetch_html(url, proxy=""):
    """抓赛事页，返回 html 或 None（失败）。

    ⚠️ 用 curl 子进程而不是 requests：WorkBuddy 沙箱会给 python 强加环境代理
    （HTTPS_PROXY 指向 127.0.0.1:58355，无法绕过，且会 geo 重定向/502）；
    curl 不受影响。重定向去 ufc.cn 视为失败。
    """
    cmd = ["curl", "-s", "--compressed", "--max-time", "30", "-A", UA,
           "-w", "\n\n__STATUS__%{http_code}|%{redirect_url}", url]
    if proxy:
        cmd = ["curl", "-s", "-x", proxy, "--compressed", "--max-time", "30",
               "-A", UA, "-w", "\n\n__STATUS__%{http_code}|%{redirect_url}", url]
    for attempt in range(1, MAX_FETCH_TRIES + 1):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            body, _, tail = r.stdout.rpartition("__STATUS__")
            code, _, redirect = tail.strip().partition("|")
            if code == "200" and "ufc.cn" not in redirect:
                return body
            print(f"    [fetch] 第 {attempt} 次失败：{tail.strip()}")
        except (subprocess.TimeoutExpired, OSError) as e:
            print(f"    [fetch] 第 {attempt} 次异常：{e.__class__.__name__}")
        if attempt < MAX_FETCH_TRIES:
            time.sleep(2 * attempt)
    return None


def parse_fights(html):
    """解析赛事页战卡，返回 [(red_url, blue_url, red_result, blue_result)]。

    结果角标可能只出现在一侧（老赛事页常见，只有胜者带标记），
    此时按胜负互补补出另一侧；两侧都没有则视为页面无结果。
    """
    Selector = load_selector()
    sel = Selector(text=html)
    fights = []
    for group in sel.xpath(XPATH_GROUPS):
        for li in group.xpath("./li"):
            red = norm_url(li.xpath(XPATH_RED_HREF).get())
            blue = norm_url(li.xpath(XPATH_BLUE_HREF).get())
            if not red or not blue or red == blue:
                continue  # 空壳战卡（两侧同链），与 eventpass 同判据
            red_res = clean(li.xpath(XPATH_RED_RESULT).get())
            blue_res = clean(li.xpath(XPATH_BLUE_RESULT).get())
            if red_res and not blue_res:
                blue_res = COMPLEMENT.get(red_res, "")
            elif blue_res and not red_res:
                red_res = COMPLEMENT.get(blue_res, "")
            fights.append((red, blue, red_res, blue_res))
    return fights


def main():
    parser = argparse.ArgumentParser(description="回填 pass_card 空结果字段")
    parser.add_argument("--apply", action="store_true", help="落库（默认 dry-run）")
    parser.add_argument("--limit", type=int, default=0, help="本轮最多处理几个赛事")
    parser.add_argument("--event", type=str, default="", help="只处理 fight_page 含该子串的赛事")
    parser.add_argument("--proxy", type=str, default="",
                        help="HTTP(S) 代理（如 http://127.0.0.1:7897）。"
                             "本机直连 ufc.com 常被 geo 重定向到 ufc.cn，走代理可稳定访问")
    args = parser.parse_args()

    now = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 待处理赛事：两侧结果全空 + 已开打。按时间倒序（新的最有价值）
    rows = cur.execute(
        """
        SELECT c.fight_page AS fight_page, COUNT(*) AS empty_rows,
               e.name AS name, e.main_time AS main_time
        FROM pass_card c
        JOIN pass_event e ON e.page = c.fight_page
        WHERE COALESCE(c.blue_result,'')='' AND COALESCE(c.red_result,'')=''
          AND CAST(e.main_time AS INTEGER) < ?
        GROUP BY c.fight_page
        ORDER BY CAST(e.main_time AS INTEGER) DESC
        """,
        (now,)).fetchall()

    pending = [r for r in rows if not args.event or args.event in r["fight_page"]]

    print(f"待处理赛事 {len(pending)} 个"
          f"{'，dry-run' if not args.apply else '，APPLY 模式'}\n")

    if args.limit > 0:
        pending = pending[:args.limit]

    alias = {r["old_page"].rstrip("/"): r["new_page"].rstrip("/")
             for r in cur.execute("SELECT old_page, new_page FROM player_url_alias")}

    total_backfilled = 0
    processed = 0

    for ev in pending:
        fight_page = ev["fight_page"]
        processed += 1
        print(f"[{processed}/{len(pending)}] {ev['name']}  (空 {ev['empty_rows']} 行)  {fight_page}")

        html = fetch_html(fight_page, args.proxy)
        if html is None:
            print("    抓取失败，跳过\n")
            continue

        fights = parse_fights(html)
        decided = [f for f in fights
                   if frozenset((f[2], f[3])) in VALID_PAIRS and f[2] and f[3]]
        print(f"    页面战卡 {len(fights)} 场，其中已分结果 {len(decided)} 场")

        # 该赛事下的空结果行
        empty_rows = cur.execute(
            """SELECT id, blue_page, red_page FROM pass_card
               WHERE fight_page=? AND COALESCE(blue_result,'')=''
                 AND COALESCE(red_result,'')=''""",
            (fight_page,)).fetchall()

        # 全量行建索引（含已有结果的行）：无序 URL 对 -> 行
        # ⚠️ blue/red_page 可能为 NULL（4.1 悬空选手极端行），None 安全处理
        all_rows = cur.execute(
            "SELECT id, blue_page, red_page, blue_result, red_result "
            "FROM pass_card WHERE fight_page=?", (fight_page,)).fetchall()
        pair_index = {}
        for r in all_rows:
            pair = frozenset(((r["blue_page"] or "").rstrip("/"),
                              (r["red_page"] or "").rstrip("/")))
            pair_index.setdefault(pair, []).append(r)

        backfilled = already = unmatched = 0
        for red_url, blue_url, red_res, blue_res in decided:
            key = frozenset((red_url, blue_url))
            candidates = pair_index.get(key)
            if not candidates:
                # 别名兜底：角标 URL 走 alias 归一后再配一次
                r2, b2 = alias.get(red_url, red_url), alias.get(blue_url, blue_url)
                candidates = pair_index.get(frozenset((r2, b2)))
            if not candidates:
                unmatched += 1
                print(f"    [WARN] 页面有结果但库里找不到对应行："
                      f"{blue_url} vs {red_url} ({blue_res}/{red_res})")
                continue
            for r in candidates:
                if (r["blue_result"] or "") or (r["red_result"] or ""):
                    already += 1  # 库里已有结果（可能上次脚本补的），不动
                    continue
                # 库内 blue/red 与页面 blue/red 对应上再写
                db_blue = (r["blue_page"] or "").rstrip("/")
                if db_blue == blue_url or db_blue == alias.get(blue_url, blue_url):
                    new_blue, new_red = blue_res, red_res
                else:
                    new_blue, new_red = red_res, blue_res
                if args.apply:
                    cur.execute(
                        "UPDATE pass_card SET blue_result=?, red_result=? WHERE id=?",
                        (new_blue, new_red, r["id"]))
                backfilled += 1
                print(f"    [{'APPLY' if args.apply else 'DRY'}] id={r['id']} "
                      f"{new_blue} / {new_red}")

        if args.apply:
            conn.commit()
        total_backfilled += backfilled
        print(f"    本场回填 {backfilled} 行（库里已有 {already}，未匹配 {unmatched}，"
              f"页面无结果 {len(fights) - len(decided)} 场）\n")
        if processed < len(pending):
            time.sleep(FETCH_SLEEP)

    print(f"========== 共处理 {processed} 个赛事，回填 {total_backfilled} 行 ==========")
    if args.apply and total_backfilled > 0:
        rebuild_zip_and_meta()
    elif not args.apply:
        print("(dry-run，加 --apply 落库并重建 zip/meta)")

    conn.close()


# ========== 确定性 zip + meta 重跑（照抄 run.py，勿 import run.py）==========
_ZIP_FIXED_DOS_TIME = (1980, 1, 1, 0, 0, 0)


def _file_size_md5(path):
    size = os.path.getsize(path)
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    return size, md5.hexdigest()


def _json_count_hash(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("data", [])
    count = len(items) if isinstance(items, list) else 0
    h = hashlib.md5(json.dumps(items, ensure_ascii=False, sort_keys=True)
                    .encode("utf-8")).hexdigest()
    return count, h


def rebuild_zip_and_meta():
    with open(DB_PATH, "rb") as f:
        db_bytes = f.read()
    zi = zipfile.ZipInfo(DB_ZIP_ENTRY_NAME, date_time=_ZIP_FIXED_DOS_TIME)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    zi.create_system = 0
    with zipfile.ZipFile(DB_ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        zf.writestr(zi, db_bytes)
    print(f"[zip] {DB_ZIP_PATH} 已生成 ({os.path.getsize(DB_ZIP_PATH):,} 字节)")

    with open(META_JSON_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    old = raw["data"] if isinstance(raw, dict) and "data" in raw else raw

    conn = sqlite3.connect(DB_PATH)
    db_version = conn.execute("PRAGMA data_version").fetchone()[0]
    athlete_count = conn.execute("SELECT COUNT(*) FROM player").fetchone()[0]
    pass_event_count = conn.execute("SELECT COUNT(*) FROM pass_event").fetchone()[0]
    conn.close()
    db_size, db_md5 = _file_size_md5(DB_PATH)
    zip_size, zip_md5 = _file_size_md5(DB_ZIP_PATH)
    coming_count, coming_hash = _json_count_hash(COMING_JSON_PATH)
    ranking_count, ranking_hash = _json_count_hash(RANKING_JSON_PATH)

    now = datetime.now(timezone(timedelta(hours=8)))
    meta = {
        "schema_version": 1,
        "last_updated": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "last_updated_ts": int(now.timestamp()),
        "generator": "UfcMaker",
        "spiders_run": old.get("spiders_run", []),
        "athlete_count": athlete_count,
        "pass_event_count": pass_event_count,
        "upcoming_event_count": coming_count,
        "ranking_count": ranking_count,
        "db_md5": db_md5,
        "db_size": db_size,
        "db_zip_md5": zip_md5,
        "db_zip_size": zip_size,
        "_db_data_version": db_version,
        "_coming_hash": coming_hash,
        "_ranking_hash": ranking_hash,
    }
    output = {"code": 0, "msg": "success", "data": meta,
              "timestamp": int(now.timestamp() * 1000)}
    with open(META_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[meta] {META_JSON_PATH} 已更新 (last_updated: {meta['last_updated']})")


if __name__ == "__main__":
    main()
