import PyRSS2Gen
import datetime
import html as html_lib
import os
import re
from html.parser import HTMLParser

class NoOutput:
    def __init__(self):
        pass
    def publish(self, handler):
        pass
# 用于解决PyRSS2Gen的desc转义字符的问题 https://stackoverflow.com/questions/5371704/python-generated-rss-outputting-raw-html/5400662#5400662
class CDATARSS(PyRSS2Gen.RSSItem):
    def __init__(self, **kwargs):
        PyRSS2Gen.RSSItem.__init__(self, **kwargs)

    def publish(self, handler):
        self.do_not_autooutput_description = self.description
        self.description = NoOutput() # This disables the Py2GenRSS "Automatic" output of the description, which would be escaped.
        PyRSS2Gen.RSSItem.publish(self, handler)

    def publish_extensions(self, handler):
        handler._write('<%s><![CDATA[%s]]></%s>' % ("description", self.do_not_autooutput_description, "description"))


# ---------------------------------------------------------------------------
# 战卡对比表（tale of the tape）的数值格式化
#
# ufc.com 选手页 bio 区存的是「裸数字」：height / reach 单位是英寸，weight 单位是磅，
# 例如 73.00 / 72.50 / 170.50。直接输出会显示成 "73.00"，与官方战卡的 6' 1" 观感不符，
# 因此在这里统一转成展示文案。已经是目标格式或无法解析的值原样返回。
# ---------------------------------------------------------------------------

_PLACEHOLDER = '—'


def _clean(value):
    return (value or '').strip()


def _fmt_text(value):
    """年龄 / 风格等纯文本字段：空值统一显示占位符。"""
    return _clean(value) or _PLACEHOLDER


def _fmt_height(value):
    """英寸 -> 英尺英寸，例如 '73.00' -> 6' 1" """
    s = _clean(value)
    if not s or s == _PLACEHOLDER:
        return _PLACEHOLDER
    if "'" in s or '"' in s or 'cm' in s.lower():
        return s
    try:
        total = int(round(float(s)))
    except ValueError:
        return s
    if total <= 0:
        return _PLACEHOLDER
    return "%d' %d\"" % (total // 12, total % 12)


def _fmt_weight(value):
    """磅 -> '170.5 磅'"""
    s = _clean(value)
    if not s or s == _PLACEHOLDER:
        return _PLACEHOLDER
    if '磅' in s or 'kg' in s.lower():
        return s
    try:
        lbs = float(s)
    except ValueError:
        return s
    if lbs <= 0:
        return _PLACEHOLDER
    return "%g 磅" % lbs


def _fmt_reach(value):
    """英寸 -> '72.5"'"""
    s = _clean(value)
    if not s or s == _PLACEHOLDER:
        return _PLACEHOLDER
    if '"' in s:
        return s
    try:
        inches = float(s)
    except ValueError:
        return s
    if inches <= 0:
        return _PLACEHOLDER
    return '%g"' % inches


def _fmt_record(value):
    """'20-1-0 (W-L-D)' -> '20-1-0'"""
    s = _clean(value)
    if not s:
        return _PLACEHOLDER
    return s.split('(')[0].strip() or s


def _parse_rank(value):
    """把各式写法的名次归一成整数，冠军 = 0；认不出返回 None。

    名次有两个来源、写法不统一：
      - `upcoming` 爬虫直接抄战卡页面上的文案，形如 '#5' 或 'C'
      - 每周三的榜单快照（`ufc_ranking_data.json`）给的是裸整数，冠军存 0

    int 要在 _clean 之前判：`_clean` 是 `(value or '')`，整数 0 是 falsy，
    先过 _clean 会把冠军悄悄变成空值。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    s = _clean(value).lstrip('#').strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s.lower() in ('c', 'champion', 'champ', '冠军'):
        return 0
    return None


def _fmt_rank(value):
    """名次展示：冠军 / #5，取不到才走占位符。

    认不出的**非空**值原样透出（页面偶尔写 `NR` = not ranked），那是有信息量的
    值，比当成「取不到」直接抹成 — 更诚实。
    """
    n = _parse_rank(value)
    if n is not None:
        return '冠军' if n == 0 else '#%d' % n
    return _clean(value) or _PLACEHOLDER


def _stat(fmt, key_suffix):
    """把「值 -> 文本」的格式化器适配成行的统一签名 fn(item, side) -> 文本。

    key 只写后缀（'Height'），前缀由 side 补上（'redHeight' / 'blueHeight'），
    省掉每行都把 red* / blue* 写两遍的重复。

    统一签名是为了让「国籍」这种要拼第二个字段（国旗）的行不必在渲染循环里
    开特殊分支 —— 它只是另一个同样签名的函数。
    """
    return lambda item, side: fmt(item.get(side + key_suffix))


def _country_value(item, side):
    """国籍取值：把国旗拼到国名「朝标签」的一侧，两面国旗正好夹住「国籍」标签。

    左列写「巴西 🇧🇷」、右列写「🇺🇸 美国」，镜像对称。此前国旗挂在照片下方，
    离标签隔着一整个选手名，要做对比还得先把视线从中间挪到两侧再挪回来。

    国旗缺失时退化为纯国名 —— pipeline 的兜底值是 🏳，与「查不到」同义，
    单独显示出来只会变成噪声；国家本身也缺失时才交给占位符。
    """
    country = _fmt_text(item.get(side + 'PlayerCountry'))
    flag = _clean(item.get(side + 'PlayerCountryEmoji'))
    if country == _PLACEHOLDER or not flag or flag == '🏳':
        return country
    return '%s %s' % (country, flag) if side == 'red' else '%s %s' % (flag, country)


# 行定义：(标签, 渲染函数)。渲染函数统一签名 fn(item, side) -> 文本。
# 顺序对齐官方战卡：身高 / 体重 / 年龄 / 臂展 / 腿展 / 风格 / 战绩，然后国籍、排名收尾。
# 后两行放最后而不是最前，是为了让「并排可比」：前面几行保持身体指标的固定次序，
# 换赛事时眼睛不用重新找位置；国籍与排名才是这张卡区别于其他卡的信息。
# 标签用中文：订阅端整体是中文内容，夹一组英文标签会显得割裂。
_STAT_ROWS = (
    ('身高', _stat(_fmt_height, 'Height')),
    ('体重', _stat(_fmt_weight, 'Weight')),
    ('年龄', _stat(_fmt_text, 'Age')),
    ('臂展', _stat(_fmt_reach, 'Reach')),
    ('腿展', _stat(_fmt_reach, 'LegReach')),
    ('风格', _stat(_fmt_text, 'Style')),
    ('战绩', _stat(_fmt_record, 'Record')),
    ('国籍', _country_value),
    ('排名', _stat(_fmt_rank, 'PlayerRank')),
)

# 版式只靠「内容本身的最小宽度」，不依赖列宽属性。
#
# 两轮踩坑的结论：
#   1. 手机端阅读器会剥掉内联 style（实测某个 iOS 阅读器渲染成白底黑字），
#      于是 flex / table-layout:fixed / width:100% 全失效 —— 所以改用
#      width / align / valign / border / cellpadding 这些老式 HTML 属性。
#   2. 但**连 td 上的 width 百分比也未必认**（同一阅读器，实测降级成自动布局）。
#      自动布局按「最小内容宽度」定列：中文可以在任意两字之间断行，
#      2 个字的标签最小能压到 1 个字，9 行标签就全部竖排成「身 / 高」，
#      整张卡被拉成一长条；照片列里的中文名（最大内容宽度 = 整个名字）
#      又会把数值列的宽度抢走，让数值也跟着折行。
#
# 因此现在的版式对「列宽属性全被忽略」是免疫的：
#   - 标签用 NBSP 连字（见 _label_html），最小宽度 = 整个标签，压不下去
#   - 名字移到数值列上方，不再挤占；表头格有半屏宽，长名最多折两次
#   - 整张表只剩 3 个数据列，各列最大内容宽度之和远小于视口宽，
#     自动布局即使按最大内容宽度分配也放得下，谁都不用折行
# width 属性仍然保留：在不剥属性的桌面阅读器里能拿到更均衡的比例。
_CELL_PADDING = 3
_VALUE_WIDTH = 38          # 左右数值列各占 38%，中间标签列 24%
_LABEL_WIDTH = 24

# 照片显示尺寸。原图比例是实测出来的（Range 取 PNG 头读 IHDR）：
# athlete_bio_full_body 这个版式，无论真人照还是占位剪影，一律 460×700；
# 只有 event_fight_card_upper_body_of_standing_athlete 的剪影是 185×624。
# 按 460×700 等比缩到 72 宽，高度是 72×700/460≈109.6，取整 110。
#
# 为什么写死宽高、而不是只给 width（或依赖 CSS 的 width:100%）：
#   - 「两个头像在同一条水平线上」不能靠 valign 碰运气。同一行里两个单元格的
#     内容高度一旦不等（比如一侧名字折了行、或某张图缺图），valign="middle"
#     会把两张照片各自垂直居中，高矮一错开就是上下不对齐。
#   - 只要两个 <img> 占据**完全相同**的矩形，再配合 valign="top"，无论阅读器
#     怎么算行高，两张照片的上下边都必然重合 —— 这是结构保证，不依赖任何样式。
#   - width 属性单独出现时，height 由原图比例推出来；比例不同的那张（185×624）
#     会被压变形，所以它按比例单独给一组宽高（110/624×185≈32.6）。
_PHOTO_SIZES = {
    'event_fight_card_upper_body_of_standing_athlete': (33, 110),
}
_PHOTO_SIZE_DEFAULT = (72, 110)

# 右（蓝方）照片做水平镜像，与左侧成轴对称。
#
# 只能走 CSS：UFC 的图片 CDN 上同一张图确实存在 _L_ / _R_ 两个朝向的变体
# （例如 BONFIM_GABRIEL_L_11-08.png 与 ..._R_...），但 URL 里的 ?itok= 是
# Drupal 按路径签发的，换掉路径里的 _L/_R 直接 403，所以换源图这条路走不通。
#
# 注意：这条内联 style 在不认内联样式的阅读器里会被丢掉，表现是「照片没镜像」
# 而不是版式崩坏 —— 属于可接受的降级。镜像不能挂在 td 上，那会连名字一起翻。
_PHOTO_MIRROR_STYLE = '-webkit-transform:scaleX(-1);transform:scaleX(-1);'


def _label_html(label):
    """标签列内容：字符之间插入 U+00A0，让最小内容宽度 = 整个标签。

    中文没有词边界，浏览器认为「身」「高」之间可以断行，于是列宽不够时就把
    标签折成两行。NBSP 是不可断行的空格，插进去以后这一格的最小宽度就是两个字，
    自动布局再怎么样也压不到一个字宽。

    零宽的连字 U+2060 更干净（不留空格），但兼容性不如 NBSP —— 遇到不支持的
    渲染器等于没写，所以选了 NBSP，代价只是两个字之间多了半个字宽。
    """
    return '\u00a0'.join(_clean(label))


def _photo_size(url):
    """按 URL 里的 image style 名取该图的显示宽高，未知版式走默认值。"""
    m = re.search(r'/styles/([^/]+)/', url)
    return _PHOTO_SIZES.get(m.group(1) if m else '', _PHOTO_SIZE_DEFAULT)


def _photo_cells(item):
    """表头行的两个选手格：全身照 + 名字，分别占满本侧的数值列。

    名字从照片列挪到了数值列上方。原因有两个：
      - 照片列只有 60~70px，中文名要折四五行的竖条，把整张卡撑得比九行数据还高
      - 它在自动布局里是最能抢宽度的一列（最大内容宽度 = 整个名字），
        数值列被挤窄之后连「31-12-0」都会折行
    挪到数值列上方之后名字有半屏可用，长名最多折两次，而且它天然成了
    本侧数值的列标题 —— 谁的名字在哪一侧一眼就能对上。

    img 的宽高都写死在属性上：一旦 width:100% 被剥掉，照片会以原始像素渲染并
    把整张卡片撑爆，固定像素尺寸没有这个风险；两侧尺寸一致再配合 valign="top"，
    两张照片就落在同一条水平线上（见 _PHOTO_SIZES 上方注释）。不使用
    max-height / overflow:hidden —— 那会把选手的脚裁掉。

    蓝方（右侧）照片额外加一条水平镜像的内联样式，与左侧成轴对称。镜像只加在
    img 上、不加在 td 上：加在 td 上会把名字文字一起翻过来。理由与降级见
    _PHOTO_MIRROR_STYLE 上方注释。
    """
    cells = []
    for side in ('red', 'blue'):
        url = item.get(side + 'PlayerBack') or ''
        name = _clean(item.get(side + 'PlayerName'))
        parts = []
        if url:
            width, height = _photo_size(url)
            attrs = [f'src="{html_lib.escape(url, quote=True)}"',
                     f'width="{width}"',
                     f'height="{height}"',
                     'border="0"']
            if side == 'blue':
                attrs.append(f'style="{_PHOTO_MIRROR_STYLE}"')
            attrs.append(f'alt="{html_lib.escape(name, quote=True)}"')
            parts.append('<img %s/>' % ' '.join(attrs))
        if name:
            if parts:
                parts.append('<br/>')
            parts.append('<b>%s</b>' % html_lib.escape(name, quote=False))
        cells.append(''.join(parts) or '&nbsp;')
    return (
        f'<td width="{_VALUE_WIDTH}%" align="center" valign="top">{cells[0]}</td>'
        f'<td width="{_LABEL_WIDTH}%" align="center" valign="top">&nbsp;</td>'
        f'<td width="{_VALUE_WIDTH}%" align="center" valign="top">{cells[1]}</td>'
    )


def _value_cells(left, label, right):
    """一行三个单元格：右对齐数值 · 居中标签 · 左对齐数值。

    数值贴近标签的一侧补一个 &nbsp;：列宽属性被剥掉时 cellpadding 也可能一起没，
    留一个不可断行的空格至少保证数值和标签不会黏成一片。
    """
    return (
        f'<td width="{_VALUE_WIDTH}%" align="right" valign="middle">'
        f'{left}&nbsp;</td>'
        f'<td width="{_LABEL_WIDTH}%" align="center" valign="middle">{label}</td>'
        f'<td width="{_VALUE_WIDTH}%" align="left" valign="middle">'
        f'&nbsp;{right}</td>'
    )


class RssMaker:
    def __init__(self, title, link, description):
        self.title = title
        self.link = link
        self.description = description

    def makeRss(self, rssList, path):
        if len(rssList)==0:
            return
        rssItems = []
        for content in rssList:
            #print("输出的数据是---->",content)
            rssItem = CDATARSS(
                title=content['title'],
                link=content['link'],
                description=content['description'],
                pubDate=content['time'])
            rssItems.append(rssItem)
        rss = PyRSS2Gen.RSS2(
            title=self.title,
            link=self.link,
            description=self.description,
            lastBuildDate=datetime.datetime.now(),
            items=rssItems
        )
        # 取出路径
        dir_path = os.path.dirname(path)
        # 判断路径是否存在,不存在则创建路径
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        # 将内容进行写入
        rss.write_xml(open(path, "w", encoding='utf-8'), encoding='utf-8')

    def get_html_str(self, item):
        """生成战卡对比表（tale of the tape）。

        版式：首行是两位选手的全身照 + 姓名（各占本侧数值列，充当列标题），
        其后九行数据，每行是「右对齐数值 | 居中标签 | 左对齐数值」。

        全部布局都走 HTML 属性（width / align / valign / border / cellpadding），
        不写一个内联 style —— 原因见 _STAT_ROWS 上方的注释。数值用 <b> 加粗
        拉开与标签的层次，<b> 是语义标签，清洗器一般不剥。
        """
        trs = [f'<tr>{_photo_cells(item)}</tr>']
        for label, render in _STAT_ROWS:
            # 文本节点只需转义 < > &，再转义引号会白白产出 &quot; / &#x27; 这种实体，
            # 在 description 的 CDATA 里没有任何必要
            cells = _value_cells(
                f'<b>{html_lib.escape(render(item, "red"), quote=False)}</b>',
                _label_html(label),
                f'<b>{html_lib.escape(render(item, "blue"), quote=False)}</b>',
            )
            trs.append(f'<tr>{cells}</tr>')

        return (
            '<div style="max-width:600px;margin:0 auto;">'
            f'<table width="100%" border="0" cellpadding="{_CELL_PADDING}" cellspacing="0">'
            f'{"".join(trs)}</table>'
            '</div>'
        )

    def get_news_html_str(self, item):
        """生成新闻条目的 RSS description。

        item 字段（均由 UfcCnNewsItem 提供）：
            title      标题，纯文本，内部会二次清洗
            type       Type 原始值 0=图文 / 1=图集 / 2=视频
            cover      封面完整 URL
            body       详情接口的富文本正文，内部清洗后再用
            details    列表接口的 50 字摘要，仅在 body 为空时兜底
            images     图集的 ImageList（[{Image, Title}, ...]）
            video_url  视频地址（Type=2 时详情接口的 Details 就是播放地址）
            link       原文链接，用于「阅读原文」
        """
        return _render_news_html(item)


# ---------------------------------------------------------------------------
# 新闻正文的清洗与渲染
#
# 详情接口 method=NewsDetails 返回的 Details 是站点富文本。实测（35 篇抽样）只用到
# <p> / <br> / <strong> / <a href> 四种标签，没有 script / style / img，
# 但夹带 &ldquo; &rsquo; &nbsp; &iacute; 等 HTML 实体，且每篇开头都带站内稿源前缀
# 「UFC中国讯」。直接塞进 RSS 会让订阅端看到 &ldquo; 这种原始转义，因此统一收敛：
#
#   1. 去掉第一段开头的「UFC中国讯」前缀
#   2. 白名单标签 + 其余标签丢弃，文本统一 html.escape
#   3. HTMLParser 的 convert_charrefs 顺带把实体还原成真实字符
#   4. 清掉空段落与连续 <br>，压平 &nbsp; 产生的 \xa0
#
# 列表接口的 Details 只有 50 字且被服务端硬截断（920/1000 以 "..." 结尾），
# 英文人名还会丢空格（BrendanAllen），因此只作为详情抓取失败时的兜底。
# ---------------------------------------------------------------------------

_NEWS_TYPE_LABEL = {0: '图文', 1: '图集', 2: '视频'}

_NEWS_P_STYLE = 'margin:0 0 12px;font-size:14px;line-height:1.7;color:#333;'
_NEWS_STRONG_STYLE = 'color:#111;font-weight:600;'
_NEWS_EM_STYLE = 'font-style:italic;'
_NEWS_LINK_STYLE = 'color:#d20a0a;text-decoration:none;'
_NEWS_MUTED_STYLE = 'margin:14px 0 0;font-size:12px;color:#999;'
_NEWS_BADGE_STYLE = ('background:#d20a0a;color:#fff;display:inline-block;'
                     'padding:2px 10px;font-size:12px;border-radius:3px;')

# 正文第一段开头的站内稿源前缀（偶有 <p> 之外的内联标签包裹）。
# 开头的 <p> 要单独捕获并在替换时还回去，否则第一段会丢掉段落样式。
_NEWS_PREFIX_RE = re.compile(
    r'^\s*(<p[^>]*>)?\s*(?:<(?:strong|b|span)[^>]*>)?\s*(?:【[^】]*】\s*)?'
    r'UFC\s*中国讯\s*(?:</(?:strong|b|span)>)?\s*[，,、：:]?\s*',
    re.IGNORECASE)

# 清洗后残留的空段落 / 连续换行
_EMPTY_P_RE = re.compile(r'<p[^>]*>\s*(?:<br\s*/?>\s*)*</p>')
_BR_RUN_RE = re.compile(r'(?:<br\s*/?>\s*){3,}')
_TAG_RE = re.compile(r'<[^>]*>')
_WS_RE = re.compile(r'[ \t\u00a0]+')


def clean_news_text(value):
    """标题等纯文本字段：还原实体、剥掉可能混入的标签、压平空白。"""
    if not value:
        return ''
    text = html_lib.unescape(str(value))
    text = _TAG_RE.sub('', text)
    text = _WS_RE.sub(' ', text)
    return text.strip()


class _NewsBodySanitizer(HTMLParser):
    """把站点富文本收敛成「白名单标签 + 转义文本」的安全片段。

    convert_charrefs=True 让 HTMLParser 在解析时就把 &ldquo; / &nbsp; / &iacute;
    还原成真实字符，再由 handle_data 里的 html.escape 重新编码，因此输出里不会
    再出现站点原始的转义写法。
    """

    _KEEP = ('p', 'br', 'strong', 'em', 'a')
    _ALIAS = {'b': 'strong', 'i': 'em'}
    _INLINE_STYLE = {
        'p': _NEWS_P_STYLE,
        'strong': _NEWS_STRONG_STYLE,
        'em': _NEWS_EM_STYLE,
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._open = []

    def handle_starttag(self, tag, attrs):
        tag = self._ALIAS.get(tag, tag)
        if tag not in self._KEEP:
            return
        if tag == 'br':
            self.parts.append('<br/>')
            return
        if tag == 'a':
            href = ''
            for key, value in attrs:
                if key.lower() == 'href' and value:
                    href = html_lib.unescape(value).strip()
                    break
            # 只保留可点的绝对地址，挡掉 javascript: 之类的伪协议
            if not href.lower().startswith(('http://', 'https://')):
                return
            self.parts.append(
                '<a href="%s" target="_blank" rel="noopener" style="%s">'
                % (html_lib.escape(href, quote=True), _NEWS_LINK_STYLE))
        else:
            self.parts.append('<%s style="%s">' % (tag, self._INLINE_STYLE.get(tag, '')))
        self._open.append(tag)

    def handle_endtag(self, tag):
        tag = self._ALIAS.get(tag, tag)
        if tag not in ('p', 'strong', 'em', 'a'):
            return
        # 只闭合与栈顶匹配的标签，避免源里嵌套错乱时结构彻底跑偏
        if self._open and self._open[-1] == tag:
            self._open.pop()
            self.parts.append('</%s>' % tag)

    def handle_data(self, data):
        if data:
            self.parts.append(html_lib.escape(data))

    def result(self):
        # 补齐源里未闭合的标签，防止溢出到后续内容
        while self._open:
            self.parts.append('</%s>' % self._open.pop())
        return ''.join(self.parts)


def clean_news_body(raw, strip_prefix=True):
    """把详情接口的富文本正文转成可直接嵌入 RSS description 的 HTML 片段。

    已经是安全内容时原样返回；空输入返回空串，由调用方决定兜底展示。
    """
    if not raw:
        return ''
    text = str(raw)
    if strip_prefix:
        # 把捕获到的首个 <p> 还回去，保住第一段的段落样式
        text = _NEWS_PREFIX_RE.sub(lambda m: m.group(1) or '', text, count=1)

    parser = _NewsBodySanitizer()
    parser.feed(text)
    parser.close()
    out = parser.result()

    # &nbsp; 还原后是 \xa0，统一成普通空格再压掉连续空白
    out = out.replace('\u00a0', ' ')
    out = _WS_RE.sub(' ', out)
    # 反复清空段落，处理 <p><p></p></p> 这类嵌套残留
    while True:
        stripped = _EMPTY_P_RE.sub('', out)
        if stripped == out:
            break
        out = stripped
    out = _BR_RUN_RE.sub('<br/><br/>', out)
    # 去掉段落标签之间的换行，减少 RSS 体积
    out = re.sub(r'>\s*\n\s*<', '><', out)
    return out.strip()


def _news_cover_block(cover, title):
    """封面图。空 URL 直接不出这一块，避免 RSS 里出现打不开的 img。"""
    if not cover:
        return ''
    return ('<p style="margin:0 0 12px;">'
            '<img src="%s" alt="%s" style="display:block;width:100%%;height:auto;border:0;"/>'
            '</p>' % (html_lib.escape(cover, quote=True), html_lib.escape(title, quote=True)))


def _news_gallery_block(images, limit=6):
    """图集类型没有正文，用 ImageList 拼一个三列缩略图网格代替空段落。"""
    cells = []
    for img in images[:limit]:
        if not isinstance(img, dict):
            continue
        src = (img.get('Image') or '').strip()
        if not src:
            continue
        caption = clean_news_text(img.get('Title'))
        src_attr = html_lib.escape(src, quote=True)
        cells.append(
            '<td width="33%%" valign="top" style="width:33%%;padding:0 3px 6px;">'
            '<img src="%s" alt="%s" style="display:block;width:100%%;height:auto;border:0;"/>'
            '<div style="font-size:11px;color:#888;line-height:1.4;margin-top:3px;">%s</div>'
            '</td>' % (src_attr, html_lib.escape(caption, quote=True), html_lib.escape(caption)))
    if not cells:
        return ''

    rows = []
    for i in range(0, len(cells), 3):
        chunk = cells[i:i + 3]
        # 补空格子，否则最后一行的图片会被拉宽
        chunk += ['<td width="33%" style="width:33%;"></td>'] * (3 - len(chunk))
        rows.append('<tr>%s</tr>' % ''.join(chunk))

    more = ''
    if len(images) > limit:
        more = ('<p style="margin:2px 0 12px;font-size:12px;color:#999;">'
                '本图集共 %d 张，点击下方链接查看全部</p>' % len(images))
    return ('<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0" '
            'style="width:100%%;border-collapse:collapse;table-layout:fixed;margin:0 0 6px;">%s'
            '</table>%s' % (''.join(rows), more))


def _render_news_html(item):
    """新闻 description 的实际渲染实现，见 RssMaker.get_news_html_str 的字段说明。

    注意：这里和 get_html_str 一样是纯函数，不依赖 self，放在模块级便于直接单测。
    """
    title = clean_news_text(item.get('title'))
    type_label = _NEWS_TYPE_LABEL.get(item.get('type'), '图文')
    cover = (item.get('cover') or '').strip()
    link = (item.get('link') or '').strip()
    video_url = (item.get('video_url') or '').strip()
    images = item.get('images') or []

    body = clean_news_body(item.get('body'))
    gallery = _news_gallery_block(images)

    # 正文抓取失败时退回列表摘要（仍是 50 字截断预览，但至少不是空白）
    if not body and not gallery and not video_url:
        body = clean_news_body(item.get('details'))

    blocks = ['<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
              'Roboto,sans-serif;max-width:600px;margin:0 auto;color:#333;">']
    blocks.append('<div style="margin:0 0 10px;">'
                  '<span style="%s">%s</span>'
                  '</div>' % (_NEWS_BADGE_STYLE, type_label))
    blocks.append(_news_cover_block(cover, title))

    if body:
        blocks.append(body)
    if gallery:
        blocks.append(gallery)
    if video_url:
        blocks.append('<p style="margin:0 0 12px;font-size:14px;line-height:1.7;">'
                      '<a href="%s" target="_blank" rel="noopener" style="%s;">'
                      '点击观看视频</a></p>'
                      % (html_lib.escape(video_url, quote=True), _NEWS_LINK_STYLE))
    if not body and not gallery and not video_url:
        blocks.append('<p style="%s">该条目暂无摘要内容，请点击原文查看。</p>' % _NEWS_P_STYLE)

    footer = '来源：UFC 中文站'
    if link:
        footer += (' · <a href="%s" target="_blank" rel="noopener" style="%s;">阅读原文</a>'
                   % (html_lib.escape(link, quote=True), _NEWS_LINK_STYLE))
    blocks.append('<p style="%s">%s</p>' % (_NEWS_MUTED_STYLE, footer))
    blocks.append('</div>')
    return '\n'.join(blocks)
