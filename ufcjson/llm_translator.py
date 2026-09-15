"""大模型翻译后端：OpenAI 兼容 chat completions，配置从环境变量读取。

环境变量：
- LLM_API_BASE    API 地址（如 https://api.deepseek.com/v1）
- LLM_MODEL       模型名（如 deepseek-chat）
- LLM_API_KEY     API Key
- LLM_BATCH_SIZE  每批条数（默认 50）
- LLM_TIMEOUT     单次请求超时秒数（默认 120）
- LLM_MAX_RETRIES 失败重试次数（默认 3）

未配置环境变量或未安装 openai 包时，translate_many 打印提示并返回空 dict，
不阻塞调用方（run.py 照常执行）。
"""
import json
import os
import time

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# 领域提示词：让模型按中国格斗界/UFC 的标准说法翻译术语
SYSTEM_PROMPT = (
    "你是综合格斗（MMA）/ UFC 领域的中文翻译专家。把用户给出的英文短语逐条翻译成简体中文，"
    "使用中国格斗媒体与拳迷的标准说法。\n"
    "【量级】Strawweight=草量级、Flyweight=蝇量级、Bantamweight=雏量级、Featherweight=羽量级、"
    "Lightweight=轻量级、Welterweight=次中量级、Middleweight=中量级、Light Heavyweight=轻重量级、"
    "Heavyweight=重量级；Bout=比赛、Title Bout=冠军争夺战、Division=级别。\n"
    "【比赛结果/结束方式】Decision - Unanimous=一致判定、Decision - Split=分歧判定、"
    "Decision - Majority=多数判定、KO/TKO=击倒/技术性击倒、Submission=降服、"
    "DQ=取消资格、Draw=平局、NC=无结果、TBD=待定、Win=胜、Loss=负。\n"
    "【人名】使用中国格斗媒体的常见音译（如 Islam Makhachev=伊斯兰·马哈切夫、"
    "Khabib Nurmagomedov=哈比布·努尔马戈梅多夫）。\n"
    "【地点】按中文习惯从大到小翻译（如 Las Vegas, Nevada, United States=美国内华达州拉斯维加斯）。\n"
    "【专有名词】UFC 编号保留（如 UFC 308），Pound-for-Pound=综合实力榜，"
    "战队名用常见译名（如 American Top Team=美国顶级战队）。\n"
    "【日期】统一按中文习惯写成 YYYY年M月D日，如 (1/13/24)=2024年1月13日、"
    "Jun. 10, 2022=2022年6月10日。\n"
    "只输出一个 JSON 字符串数组，与输入数组一一对应，不要输出任何解释、注释或 markdown 标记。"
)


def _config():
    return {
        "api_base": os.environ.get("LLM_API_BASE", ""),
        "model": os.environ.get("LLM_MODEL", ""),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "batch_size": int(os.environ.get("LLM_BATCH_SIZE", "50")),
        "timeout": float(os.environ.get("LLM_TIMEOUT", "120")),
        "max_retries": int(os.environ.get("LLM_MAX_RETRIES", "3")),
    }


def is_configured():
    if OpenAI is None:
        return False
    cfg = _config()
    return bool(cfg["api_base"] and cfg["model"] and cfg["api_key"])


def translate_many(values, cache_conn=None):
    """批量翻译。返回 {原文: 译文}；未配置/失败时返回空 dict。

    values 内重复项会自动去重，空串忽略。
    cache_conn: 可选的翻译缓存库连接；传入则每批成功即写缓存，
    即使中途中断也不会丢已完成的批次。
    """
    values = list(dict.fromkeys(v for v in values if v))
    if not values:
        return {}
    if not is_configured():
        print("[llm] 未配置 LLM_API_BASE / LLM_MODEL / LLM_API_KEY（或未安装 openai），跳过翻译")
        return {}

    cfg = _config()
    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["api_base"],
                    timeout=cfg["timeout"], max_retries=cfg["max_retries"])

    result = {}
    batch_size = max(1, cfg["batch_size"])
    total_batches = (len(values) + batch_size - 1) // batch_size
    for i in range(0, len(values), batch_size):
        batch = values[i:i + batch_size]
        idx = i // batch_size + 1
        tr = _translate_batch(client, cfg["model"], batch, retries=cfg["max_retries"])
        if tr is None:
            print(f"[llm] 第 {idx}/{total_batches} 批翻译失败，跳过 {len(batch)} 条")
            continue
        result.update(tr)
        if cache_conn is not None:
            _save_batch_cache(cache_conn, tr)
        if idx == 1 or idx % 10 == 0 or idx == total_batches:
            print(f"[llm] 进度 {idx}/{total_batches}，已翻译 {len(result)} 条")
    return result


def _save_batch_cache(cache_conn, pairs):
    """把一批译文增量写入翻译缓存，中断不丢进度。"""
    cursor = cache_conn.cursor()
    for orig, tr in pairs.items():
        if tr:
            cursor.execute(
                "INSERT OR IGNORE INTO translate (original, translation) VALUES (?, ?)", (orig, tr)
            )
    cache_conn.commit()


def _translate_batch(client, model, batch, retries=3):
    attempt = 0
    while True:
        try:
            print("要翻译的数据是:"+ json.dumps(batch, ensure_ascii=False))
            resp = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(batch, ensure_ascii=False)},
                ],
            )
            content = resp.choices[0].message.content or ""
            print("翻译结果是:"+ content)
            break
        except Exception as e:
            attempt += 1
            if attempt > retries:
                print(f"[llm] 请求异常（重试 {retries} 次后仍失败）: {e}")
                return None
            print(f"[llm] 请求异常（第 {attempt}/{retries} 次重试）: {e}")
            time.sleep(2 * attempt)

    translated = _parse_array(content, len(batch))
    if translated is None:
        return None
    if len(translated) < len(batch):
        translated += [""] * (len(batch) - len(translated))
    translated = translated[:len(batch)]
    return {b: (t or "") for b, t in zip(batch, translated)}


def _parse_array(content, expected):
    """从 LLM 返回文本解析 JSON 数组，容错 markdown 围栏和多余文字。"""
    text = content.strip()
    # 剥掉可能的 ```json ... ``` 围栏
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # 先直接解析
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    # 再尝试从文本中截取第一个 [...] 解析
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return [str(x) for x in data]
        except json.JSONDecodeError:
            pass
    print(f"[llm] 无法解析翻译结果: {content[:200]!r}")
    return None
