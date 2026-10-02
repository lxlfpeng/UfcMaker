# UfcMaker 数据侧待办

> 创建：2026-09-26　来源：核对客户端 PRD（`PRD-Release/`）时发现的数据侧问题
> 说明：本文件跟踪**数据侧**（爬虫 / 翻译 / 建库）改动，与客户端 PRD 分开管。客户端 PRD 不动这里。
> 详细取证见 `../.workbuddy/memory/DB-NOTES.md` 的「翻译链路与 ufc_translate.db」「不归一化的实测后果」两节。

---

## 一、量级翻译归一（优先做：客户端筛选与冠军榜都依赖它）

### 1.1 改 `output/db/ufc_translate.db` 的 `translate` 表

**为什么改缓存而不是重跑 LLM**：缓存是成品，改值即可，零模型成本、结果确定。提示词那条路留到第二步做「防未来」。

#### A. 去掉「级别」后缀 —— 8 条

| id | original | 现值 ❌ | 改为 |
|---|---|---|---|
| 40724 | `Featherweight Division` | 羽量级级别 | 羽量级 |
| 40806 | `Flyweight Division` | 蝇量级级别 | 蝇量级 |
| 48532 | `Lightweight Division` | 轻量级级别 | 轻量级 |
| 49121 | `Middleweight Division` | 中量级级别 | 中量级 |
| 52503 | `Women's Bantamweight Division` | 女子雏量级级别 | 女子雏量级 |
| 52506 | `Women's Featherweight Division` | 女子羽量级级别 | 女子羽量级 |
| 52510 | `Women's Flyweight Division` | 女子蝇量级级别 | 女子蝇量级 |
| 52514 | `Women's Strawweight Division` | 女子草量级级别 | 女子草量级 |

> ✅ 这 4 条**已干净，别动**：`Bantamweight Division`(39014)→雏量级、`Heavyweight Division`(41221)→重量级、`Light Heavyweight Division`(48525)→轻重量级、`Welterweight Division`(52418)→次中量级。
> ⚠️ 同一提示词下模型**时守时不守**，所以只有这 8 条脏。

#### B. 统一冠军战措辞：`冠军争夺战` → `冠军战` —— 5 条

| id | original | 现值 | 改为 |
|---|---|---|---|
| 39016 | `Bantamweight Title Bout` | 雏量级冠军争夺战 | 雏量级冠军战 |
| 40726 | `Featherweight Title Bout` | 羽量级冠军争夺战 | 羽量级冠军战 |
| 40808 | `Flyweight Title Bout` | 蝇量级冠军争夺战 | 蝇量级冠军战 |
| 41223 | `Heavyweight Title Bout` | 重量级冠军争夺战 | 重量级冠军战 |
| 51056 | `Strawweight Title Bout` | 草量级冠军争夺战 | 女子草量级冠军战 |

> 依据：设计稿实测用**短的**「蝇量级冠军战」（画布 `231:194`）。库里现状「XX冠军战」250 行 /「XX冠军争夺战」133 行，混着。
> 以下 8 条**已是「冠军战」，别动**：`Light Heavyweight`(48527) / `Lightweight`(48534) / `Middleweight`(49123) / `Welterweight`(52420) / 女子四个(52504/52507/52511/52515)。
> 临时冠军的 8 条（`XXX Interim Title Bout`）同理，若也按「冠军战」则一并对齐。

#### C. 新增 2 条（`草量级` 脏值的真因：**缺缓存 → 走了 LLM 现场翻译**）

| original | 状态 | 值 |
|---|---|---|
| `Strawweight` | **表里没有** → 新增 | 女子草量级 |
| `Strawweight Bout` | **表里没有** → 新增 | 女子草量级比赛 |

> 实测：`translate` 表里 Strawweight 相关短条目只有 5 条（`Strawweight Title Bout` / `Women's Strawweight` / `Women's Strawweight Bout` / `Women's Strawweight Division` / `Women's Strawweight Title Bout`）——**没有裸 `Strawweight`，也没有 `Strawweight Bout`**。
> 所以库里那 2 行 `草量级比赛` 是 **LLM 现场翻的**（没命中缓存）；而 `Strawweight Title Bout` 命中了缓存、却是「草量级冠军争夺战」。
> 补上这 2 条 + 改 B 表里的 51056 → `草量级` 从此绝迹。

### 1.2 清理 + 重翻

```bash
# 1) 只清 ufc.db 的 _cn 列，【保留】translate 缓存
#    ⚠️ 不要跑 scripts/clear_translations.py —— 它会 DELETE FROM translate（它服务于"换提示词全量重翻"那条路）
#    需要清：player.division_cn、pass_card.card_division_cn（以及同批其它 _cn 列，见 clear_translations.py 的 CN_COLUMNS）

# 2) 重翻（命中缓存 → 不调 LLM → 秒完）
python -c "from ufcjson.translator import translate_db_fields; translate_db_fields()"
```

### 1.3 验收标准

- `player.division_cn`：**13 种**（剔「无差别级」= **12 个量级**），且**零**「级别」后缀（现 18 种 / 1,774 行带后缀）
- `pass_card.card_division_cn`：**零**「冠军争夺战」（现 133 行），**零**裸 `草量级`（现 3 行）
- `player.division_cn` 应无「轻量级 vs 轻量级级别」这类同量级占两档（现 5 组）

---

## 二、提示词防未来（第一步做完后做，否则新词条还会脏）

`UfcMaker/ufcjson/llm_translator.py` 第 27–29 行：

```
"【量级】Strawweight=草量级、Flyweight=蝇量级、…Heavyweight=重量级；
 Bout=比赛、Title Bout=冠军争夺战、Division=级别。\n"
```

- **[必改]** `Division=级别` → 删除或改为「`Division` → 不译（字段已是中文量级）」——它是「轻量级级别」的**直接成因**
- **[必改]** `Title Bout=冠军争夺战` → `冠军战`（与设计稿口径一致）
- **[必改]** `Strawweight=草量级` → 补语境：裸 `Strawweight` 按**女子**草量级（UFC 无男子草量级）

---

## 三、让 `ufc_coming_data.json` 产出 `card_division_cn`（客户端 PRD 依赖）

- 现状：`card_division` 是干净英文，**`card_division_cn` 50 条全为 `null`** → 客户端只能自己做「英文→中文」映射（《即将到来赛程详情页》§2.3 现按此写）
- 做法：把翻译管道接上 coming 数据的导出
- ✅ **零 LLM 成本**：coming 的 **14 种** `card_division` 在 `translate` 表里**命中 14/14（100%）**
- 收益：客户端可撤掉「端内映射」条款，**不必自建量级映射表**

---

## 四、（可选）赛事 slug 归一

- `pass_event.name` 不以 `ufc-` 开头的有 **95 场**，其中 **94 场是正式 UFC 赛事**（`FOX`/`FUEL`/`FX`/`UFN`/`FIGHT`(Fight Night)/`TUF`/`THE`(TUF Finale)/`ULTIMATE`/`UFCLIVE`/`UVS`/`RIYADH`…）
- 真·非 UFC 赛事只有 **1 场**：`strikeforcer-heavyweight-grand-prix-final`
- ⚠️ 按域名也分不出来：**795 场的 `page` 全是 `https://www.ufc.com/event/…`**（连 Strikeforce 也是）
- 影响：383 场冠军战里 16 场落在非 `ufc-` slug 上 → 客户端若按「`ufc-` 前缀」过滤会**误杀 15 场正式冠军战**
- 建议：服务端加 `is_ufc_event` 标记字段，或把 slug 归一；否则客户端只能用**黑名单**（`NOT LIKE 'strikeforce%'`）
- 附带：Road to UFC 两种写法并存 —— `road-ufc-season-4-semifinals`（**少了 `to`**）与 `road-to-ufc-season-5-semifinals`

---

## 五、重新生成 + 下发

```bash
# run.py 会在爬虫后自动翻译；改完 translate 表后按 1.2 单独重翻即可
# 然后重生成 ufc.db → meta.json → 打包 → 上传服务端
```

- ⚠️ 本项目的老毛病：**改完忘了重生成 `meta.json` / `db_stats.json` 并上传服务端**
- ⚠️ 本次只改**数据值**、不动**表结构** → `UFC_DB_VERSION` **不用 +1**
- ✅ 但 `meta.db_md5` / `db_zip_md5` 会变 → 这正是触发客户端更新数据库的信号；改完确认它们确实变了

## 六、config.json 增加 `data_sources` 字段（2026-09-26 新增；2026-09-27 更新：Sherdog 本期开发）

**背景**：客户端《数据来源及图片地址》v2.5 已把 URL 定为三段式 `<节点> + <数据源前缀> + <文件路径>`，「设置 → 数据源」选择页切换的就是**前缀**；但现行 config.json **没有**数据源字段（前缀目前融合在 hosts 条目里），Sherdog 选项无法真正生效。

### 6.1 目标结构（在 `data` 节点下新增）

```json
"data_sources": [
  { "name": "UFC 官方", "prefix": "/lxlfpeng/UfcMaker/refs/heads/master/", "default": true },
  { "name": "Sherdog",  "prefix": "/lxlfpeng/DogMaker/refs/heads/main/",   "default": false }
]
```

- `name` = 选择页显示名（对应「UFC 官方 / Sherdog」）；`prefix` = 拼地址用的前缀（**首尾带斜杠**）；`default` = 出厂默认项（客户端渲染选中态用）
- ✅ 2026-09-27 已填入 Sherdog 真实路径 `/lxlfpeng/DogMaker/refs/heads/main/`（此前留空）
- ⚠️ **该文件目前未被 git 跟踪**（`git ls-files output/json/` 里没有 config.json）——需补 `git add`，否则丢失不可恢复

### 6.2 ✅ `hosts` 已改为「纯节点」形态（2026-09-27 拍板并执行）

现行 `hosts` 5 条全部是**融合形态**——master 仓库段已焊进节点：

```
https://gh-proxy.org/https://raw.githubusercontent.com/lxlfpeng/UfcMaker/refs/heads/master
```

端上按《Splash》§3.1 的现行规则会判定「节点已含仓库段 → **跳过前缀**、直接拼文件路径」，因此**即使 `data_sources[1].prefix` 填了 Sherdog，端上也会忽略它、仍取 master 数据**。

✅ **已于 2026-09-27 改为纯节点**（原为上述融合形态）：

```json
"hosts": [
  "https://gh-proxy.org/https://raw.githubusercontent.com",
  "https://v4.gh-proxy.org/https://raw.githubusercontent.com",
  "https://v6.gh-proxy.org/https://raw.githubusercontent.com",
  "https://cdn.gh-proxy.org/https://raw.githubusercontent.com",
  "https://axisnow.gh-proxy.org/https://raw.githubusercontent.com"
]
```

- 改后拼接 = 节点 + `data_sources[选中项].prefix` + `output/json/xxx.json`（三段齐全，切换生效）
- ⚠️ **已接受的兼容风险**：若有只实现两段式拼接的旧客户端（`UfcAndroid`，包名 `com.lxlfpeng.kotlinufc`），改后其取数会全挂——用户已确认本期就改；**上线前需确认旧端是否仍在分发**
- ⚠️ `config.schema_version` 保持 `1` 不变：PRD §1.1.3 把两种形态都纳入同一契约（端上做 `endsWith` 判定），不构成 breaking change

### 6.3 Sherdog（DogMaker）侧必须满足的同构前提

三段式复用同一套文件路径，因此 DogMaker 必须与 UfcMaker **路径与结构完全同构**，否则切过去会大面积失败：

| # | 前提 | 不满足的后果 |
|---|---|---|
| 1 | 产出同名同路径文件：`output/json/{config,app_version,meta,ufc_coming_data,ufc_ranking_data,ufc_pass_data,db_stats_history}.json` | 该页数据全空 |
| 2 | 有 `output/db/ufc.db.zip`，且 **13 张表 schema 与 master 一致** | 切源后重新「数据库更新」直接崩 |
| 3 | `meta.json` 提供自洽的 `db_zip_md5` / `db_zip_size` | 客户端无法判定是否需要更新 |
| 4 | `output/images/` 含**同样相对路径**的图片（`*_local` 值可解析） | 切源后图片全落占位图 |
| 5 | 时间字段口径一致（秒级字符串）、量级/级别中文口径一致 | 排序错乱、筛选失准 |

### 6.4 ✅ 已拍板：`config.json` 固定从 master 取，不随数据源切换

`config.json` 决定 `hosts` 与 `data_sources`，但它自身也走三段式地址——若不明确取源，切到 Sherdog 后可能取到「指向自己的 config」形成回环。

**2026-09-27 拍板：`config.json` 固定从 `data_sources` 中 `default: true` 的项（即 master）取，不随用户选择切换。**

- 端上实现：取 config 时**忽略用户当前选中的数据源**，固定用默认项 `prefix` 拼接
- 定位：config 是**引导文件**，不是业务数据，故不参与数据源切换
- ⚠️ 需写入 PRD《数据来源及图片地址》§1.1（**目前未定义**）与 Android 端技术规格
- 推论：DogMaker **不需要**自带 config.json（若产出也无害，端上不会去取它）

### 6.5 验收

- config 下发含 `data_sources`，Sherdog 项 `prefix` 非空 → 选择页 Sherdog **可选**（不再是置灰态）
- `hosts` 改为纯节点后，切换数据源能真实取到 DogMaker 的文件
- 字段缺失/解析失败 → 端上兜底 master（选择页只显示「UFC 官方」）
- ⚠️ PRD《数据来源及图片地址》§1.1「本期冻结说明」、《设置抽屉与设置流》§3 需同步改写（原写「本期仅 master 可用、Sherdog 置灰、切换无实际效果」）
