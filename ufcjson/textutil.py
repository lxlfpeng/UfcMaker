"""跨模块共用的文本判定工具（唯一一份定义，其它模块一律 import，不要手抄）。

背景：球员页战绩区常有「`<br>` + 零宽空格」这种空文本节点，会变成 '\u200b'
这样的垃圾条目。`str.strip()` 去不掉它们（U+200B 的 isspace() 是 False），
一旦混进 player.history 就是个死结：

  - 它会被当成正常文本送进大模型，翻不出结果 ⇒ translator._backfill 的
    all() 判定失败 ⇒ 该选手**整段**中文战绩永不回填；
  - 更危险的是 history / history_cn 是**按位对齐**的。抓取端（athlete.py）、
    翻译端（translator.py 收集待翻译文本）、订正脚本
    （.workbuddy/scripts/fix_translate_dates.py）三处必须用**同一个**过滤函数，
    任何一处口径不同，第 k 条就会错位到第 k+1 条，把 A 场的译文写到 B 场上。

所以这里只保留一份定义。判定函数只做判断、不改写文本本身——译表的 key 是原文，
改写文本会让整个翻译缓存失效。
"""

# 5 个常见不可见字符：零宽空格 / 零宽非连接符 / 零宽连接符 / word joiner / BOM
INVISIBLE_CHARS = dict.fromkeys(map(ord, '\u200b\u200c\u200d\u2060\ufeff'))


def is_blank_text(text):
    """整条只由空白或不可见字符组成（或为 None）时返回 True。

    注意不需要额外把 NBSP(\u00a0) 替换成普通空格：`'\xa0'.isspace()` 为 True，
    无参数的 str.strip() 本来就会去掉它。
    """
    if text is None:
        return True
    return not str(text).translate(INVISIBLE_CHARS).strip()
