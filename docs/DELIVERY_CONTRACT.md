# 四队共同交付规范

版本 `fetchdata-handoff/1`。这是员工与研究端联调的**候选交换格式**，不是现有 Fetchspec 接收 API 的请求格式。现有接收器限制 `provider_id=fetchspec`；四队不得改名冒充它。正式接收适配由研究端负责人实现并验收，员工先按本文交包、离线验包。供应主合同仍是 [supply_contract.json](https://github.com/niuroumiantt/InResearch.ai/blob/main/framework/supply_contract.json)。

## 文件格式：保留原件，另交结构化信息

| 来源提供什么 | 原件交什么 | 还要交什么 |
|---|---|---|
| 网页 | 实际取得的 HTML 字节；动态内容优先保留官方数据接口响应或必要渲染快照 | URL、下载时间、关键片段定位；动态页记录取得方法 |
| PDF 报告/费率/财报 | 原生 PDF，不用打印网页替代原报告 | 物理页号、表/图/段落、必要脚注；文本/OCR 是派生文件 |
| API / XBRL | 原始响应 JSON/XML/XBRL，保留请求参数与分页清单 | 原生系列/字段/维度/期间，JSON Pointer 或 XBRL context |
| 表格 | 原生 CSV/XLSX 等；不要先转 PDF 丢表头 | 表名、行列或单元格、单位、脚注 |
| 同文同时有网页与 PDF | 优先能保留完整关键上下文的原件；另一形式有额外信息再收 | 两者关系及各自 SHA，不为凑格式重复抓 |

不要求每条都有 HTML + PDF + JSON 三份。**每条都要能回到原件，结构化候选统一 JSONL。** 截图只能补视觉证据，不能替代可取得的原件。不得将错误页、登录页当正文，也不得用翻译改写后的文件冒充原件。原件保存不等于整篇必须读完才能提取一条信息。

## 包目录

```text
delivery-<team>-<UTC时间>-<批号>/
  manifest.json         原件目录、来源与采集器身份
  SHA256SUMS            每个不同原件：<sha256><两个空格><相对路径>
  originals/<sha256>.<扩展名>
  observations.jsonl    一行一条候选；没有可提取信息时可以为空
  errors.jsonl          每次失败/缺口一行；正常时空文件
  run-report.json       运行计数和耗时，包含成功及失败的分母
```

源码进 Git，真实原件、包、运行 SQLite 和凭据走私有数据目录，不进 Git。原件同 SHA 一份、可有多个 URL/引用；字节变化另存版本，不覆盖旧文件。派生文本另存并记录 `derived_from_sha256`，不放进原件清单冒充原件。历史文件保留实际取得时间；没有历史下载时间就留未知，当前复用不能伪造当年接收。

模板和四种合成样例由 [make_sample.py](../tests/test_collector.py) 生成；字段说明如下。额外字段可扩展，关键字段不能改名。

## manifest.json

- `contract` 固定 `fetchdata-handoff/1`；`provider_id` 是四队之一；`delivery_id` 在本队唯一，重试保持不变。
- `collector_revision` 是实际源码 40 位提交 SHA；未提交开发包不能报生产交付。`generated_at` 为有时区的包生成时刻。
- `items[]`：`item_id`、`source_id`、`source_item_id`、`url`、`title`、`publisher`、`retrieved_at`、`sha256`、`path`、`content_type`、`access_scope`、`completeness`、`version_of`。
- `source_item_id` 采用来源原生身份，例如 SEC accession、报告 DOI/版本、数据系列+查询范围。`version_of` 指已知旧版本身份，未知为 null。`access_scope` 为 `public`/`restricted`/`unknown`，受限材料可登记但不公开原文；员工第一批先做公开源。
- `completeness` 为 `complete`/`partial`/`unknown`，指取得内容是否完整，不指已全文阅读。分页 API 未取齐标 partial，不得称全量。
- `retrieved_at` 是本次真正取得这些字节的时刻；存量原件未知则 null，另交 `reused_at` 和已有来源凭据标识，研究端核实，不能把当前时间写成历史下载时间。

## observations.jsonl：一个对象、一个指标、一个证据范围

必备：`observation_id`、`source_item_id`（引用本包 item_id）、`object`、`metric`、`value`、`unit`、`scope`、`kind`、`effective_time`、`published_time`、`evidence`、`revision_of`、`conflicts_with`。研究需求 `target_ids` 可选且允许 []。

`object` 包含：

- `type`：`site` / `company` / `product` / `statistic_series` / `study`。
- `match_status`：`matched` 或 `unresolved`。matched 交研究端既有 `canonical_id` 和 `match_basis`；它仍需研究端复核，不因员工填了 ID 自动采用。unresolved 的 ID 为 null，保留原名及地点/注册号/型号等识别线索。
- `name`：原文名称；`identifiers`：可得的国家、省州、城市、街区、地址、坐标、CIK/LEI、型号、系列代码等。未知为 null 或不填，不用 `multiple` 当法律主体。

不要把公司和园区混为同一对象。集团披露的总资本开支不能分配到某个园区；一个集群不是唯一地块。统计序列按发布机构、系列、地区、单位和口径识别；具体期间进观测，不为每个月重建序列身份。公司角色分业主、开发商、运营商、施工承包商、直接租户、最终用户、债权人/投资人/借款法律主体；角色带有效时间，不把施工方叫业主。

`metric` 采用队内登记的稳定名称，具体名见任务书。`value` 结构：

```json
{"type":"number","number":600,"raw":"600 MW"}
{"type":"range","lower":500,"upper":700,"raw":"500–700 MW"}
{"type":"text","text":"暂停建设","raw":"construction paused"}
```

三行是三个独立示意，不是一个 JSON 文件。区间保留上下界，不能取中点；单边界另外交 `constraints`，不要补造另一端。数值用 JSON 数字，`unit` 独立填写；保留原始单位和币种，换算另记 `derivation` 的公式、输入和假设，不覆盖原值。`kind` 为 `reported` / `measured` / `estimated` / `calculated` / `forecast` / `offer`，按原文性质填写。规划/目标/预计不是实际投运，电网接入/设施总功率不是 IT 功率。`scope` 写对象范围、期间、配置/地域/分部、容量口径或报价条件，不能只有一个模糊标签。

## 时间分别记录

每个 `effective_time`、`published_time` 都是 `{"value":null,"precision":"unknown","basis":null}`，或 `{"value":"2026-09","precision":"month","basis":"原文说明统计期为2026年9月"}`。支持 year/month/day/datetime，精度与值一致；datetime 带时区。

1. **信息有效时间 effective_time：** 数据描述哪个时点/期间；统计期、报价时点或计划目标时间。期间另加 `period_start`/`period_end`，保留原财政年度标签。
2. **披露时间 published_time：** 这版来源何时发表。不能自动当信息有效时间；报道没有独立状态日期时，可明确标为“截至报道日”的有依据观测，不声称确切发生日。
3. **首次接收时间：** 研究接收端首次收到该内容身份的不可变回执。员工不生成 `first_received_at`；其 `retrieved_at` 不是研究端接收时间。

审核/核实时间及正式写入时间也由执行审核/采用的研究端写。下载一次不能更新“最后核实”。未知有效时间允许登记，不伪造精度，也不凭披露新就覆盖已核实旧状态。

## 证据、缺失、冲突与修订

- `evidence` 必须有 `locator`、`quote`、`context`：例如“物理页12，表3，Texas行，工业电价列及脚注1”；quote 是原文短引，context 保存影响结论的限定/分母/脚注。JSON 指针如 `/response/data/0/price`，还要保留同一行期间、单位、地区。定位和引文须实际核对，不以模型生成的总结当原文。
- 没找到就不交该指标，已找到的照交；`errors.jsonl` 可记 `not_disclosed`，不是请求无限重试。可提取一条就交一条，不等整篇所有指标齐全。
- `revision_of` 指已知旧候选/观测，否则 null；`conflicts_with` 是已知冲突 ID 数组，未知 []。同对象同指标只有范围、期间、单位一致才比较冲突；时间变化或计划/实际不同不是自动冲突。
- 新披露不是自动替代，旧版本始终保留。身份不明确交 unresolved；研究端审核后匹配、追加或保留争议，不能让供应方直接覆盖正式库。

## 离线验包与正式接收的区别

```sh
python3 validate_handoff.py /私有路径/delivery-...
```

工具只读，检查文件完整性、路径、SHA、引用、关键字段、时间/数值结构，逐条报告坏候选，退出 0 才算本地包校验通过。它不联网、不解包压缩包、不检查研究真假、不确认 canonical_id，也不写数据库。真实下载器还须实现请求/重试/容量限制和日志脱敏；研究端仍需对象与证据核对、逐条审核、正式追加及网站回执。单项候选错误可以隔离修好后重交，不能因一条坏候选删除原件或丢掉本包其它有用信息。
