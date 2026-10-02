"""翻译质量抽样测试：从库里抽各类型的代表值，调大模型翻译，打印中英对照。

用法（在 UfcMaker 目录下执行，先设置环境变量）：
    export LLM_API_BASE=https://api.deepseek.com/v1
    export LLM_MODEL=deepseek-chat
    export LLM_API_KEY=sk-xxx
    python scripts/test_translation.py

也可以直接传要翻译的文本（不定长参数，只翻你给的，不跑库内抽样）：
    python scripts/test_translation.py "Welterweight" "Decision - Unanimous" "Islam Makhachev"
    python scripts/test_translation.py "He was stopped via strikes in the second round"

不带参数则跑：标准术语校验 + 库内各类别抽样。
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ufcjson.llm_translator import translate_many

DB = "output/db/ufc.db"

# 标准术语清单（来自真实数据里的值），用于校验领域提示词是否生效
KNOWN_TERMS = {
    "Welterweight Division": "次中量级",
    "Flyweight Division": "蝇量级",
    "Decision - Unanimous": "一致判定",
    "Decision - Split": "分歧判定",
    "KO/TKO": "击倒/技术性击倒",
    "Submission": "降服",
    "Flyweight Bout": "蝇量级比赛",
    "Women's Strawweight Title Bout": "女子草量级冠军争夺战",
    "Active": "现役",
    "Retired": "退役",
    "Not Fighting": "未在役",
    "Wins by Knockout": "击倒获胜",
    "Wins by Submission": "降服获胜",
}

# 各类别抽样 SQL（每类取几条代表值）
SAMPLES = {
    "量级": "SELECT DISTINCT division FROM player WHERE division!='' LIMIT 6",
    "状态": "SELECT DISTINCT status FROM player WHERE status!='' LIMIT 5",
    "风格": "SELECT DISTINCT style FROM player WHERE style!='' LIMIT 5",
    "结束方式": "SELECT DISTINCT end_method FROM pass_card WHERE end_method!='' LIMIT 8",
    "战卡级别": "SELECT DISTINCT card_division FROM pass_card WHERE card_division!='' LIMIT 8",
    "城市": "SELECT DISTINCT city FROM player WHERE city!='' LIMIT 8",
    "国家": "SELECT DISTINCT country FROM player WHERE country!='' LIMIT 6",
    "选手名": "SELECT name FROM player ORDER BY id LIMIT 8",
    "战队": "SELECT DISTINCT team FROM player WHERE team!='' LIMIT 6",
    "历史句子": "SELECT json_extract(history, '$[0]') FROM player WHERE history!='[]' LIMIT 5",
    "获胜方式": "SELECT DISTINCT json_extract(wins_stats, '$[0].way') FROM player WHERE wins_stats!='[]' LIMIT 5",
}


def _print_block(title, pairs):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")
    for src, tr in pairs:
        mark = "  ⚠️ 未翻译" if not tr else ""
        print(f"  {src}")
        print(f"    -> {tr}{mark}")


def main():
    # 命令行自定义翻译：python scripts/test_translation.py "文本1" "文本2" ...
    custom = sys.argv[1:]
    if custom:
        tr = translate_many(custom)
        _print_block("自定义翻译", [(v, tr.get(v, '')) for v in custom])
        return

    if not os.path.exists(DB):
        print(f"[ERR] 找不到 {DB}，请在 UfcMaker 目录下运行")
        sys.exit(1)

    conn = sqlite3.connect(DB)

    # ① 标准术语清单校验
    print("翻译标准术语清单...")
    tr_known = translate_many(list(KNOWN_TERMS.keys()))
    ok = 0
    results = []
    for src, expect in KNOWN_TERMS.items():
        got = tr_known.get(src, '')
        passed = expect in got
        ok += 1 if passed else 0
        results.append((src, f"{got}  (期望: {expect})", passed))
    _print_block(f"标准术语校验：{ok}/{len(KNOWN_TERMS)} 通过", [(s, f"{t}  {'✓' if p else '✗'}") for s, t, p in results])

    # ② 各类别抽样
    print("\n抽样真实数据...")
    values = []
    labels = []
    for label, sql in SAMPLES.items():
        rows = [r[0] for r in conn.execute(sql).fetchall() if r[0]]
        for v in rows:
            values.append(v)
            labels.append(label)
    conn.close()

    # 去重，保留第一次出现的类别标签
    seen = set()
    dedup = []
    dedup_labels = []
    for v, l in zip(values, labels):
        if v not in seen:
            seen.add(v)
            dedup.append(v)
            dedup_labels.append(l)

    print(f"共 {len(dedup)} 条（去重后）待翻译...")
    tr = translate_many(dedup)

    # 按类别分组打印
    for label in dict.fromkeys(dedup_labels):
        group = [(v, tr.get(v, '')) for v, l in zip(dedup, dedup_labels) if l == label]
        _print_block(f"{label} 抽样", group)


if __name__ == "__main__":
    main()
