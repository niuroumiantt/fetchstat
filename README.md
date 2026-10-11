# fetchstat：统计、费率与规则

这是独立采集仓库。先做可复核的小包，再扩来源；不建网站、不使用模型 API、不直接写研究正式库。Python 3.10+，运行核心只用标准库；本次适配器无需凭据或第三方包。

## 员工收到后立刻做

```sh
git clone git@github.com:niuroumiantt/fetchstat.git ~/code/fetchstat
cd ~/code/fetchstat
python3 collector.py check-config
python3 -m unittest discover -s tests -v
python3 collector.py run
```

最后一条命令输出 `package` 私有目录。把该实际目录传给：

```sh
python3 collector.py verify /实际输出的/package
```

仓库源码公开，使用标准Ubuntu托管Actions；真实资料保持私有。所有命令已实现；首次运行需已提交的源码。默认原件和交付包在 `~/.local/share/fetchstat/`，错误日志在 `~/.local/state/fetchstat/`。可用 `--data-root /私有目录`；不把这些目录、资料或账号提交到 Git。

## 首个闭环的明确目标

来源：[EIA](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_5_6_b)。适配器 `adapter.py` 已提取“Texas 工业电价 YTD”的一个指定字段。`sources.json` 登记 URL、负责队、来源身份、频率和适配器版本。

第一步只要求：一个真实原件、一条可定位候选、离线验包通过、原包重放不变。不是下载量比赛；暂时不要求几十条或全面覆盖。当前对象为 unresolved，交真实身份线索给研究端匹配；不造 canonical_id、不绑定 target_id。后续范围见 [本队任务书](docs/TEAM_TASK.md)，其中较大样本数量属于扩展阶段，不是第一步交付前提。

## 存量复用，不重复抓

```sh
python3 collector.py run --existing /授权原件.html --provenance /原目录或真实台账记录
```

只读原件，不修改旧库。必须是本适配器对应的原生资料。没有历史下载时间则 retrieved_at=null，另记复用时间及凭据；当前时间不冒充历史。大库先用索引筛选，不搬几百GB到员工电脑。第一版单文件上限20MiB；需要较大 PDF/分页源时另扩有界流式适配，不盲目调大。

## 交还给负责人

1. 源码 PR、提交 SHA、来源登记和修改说明。
2. 完整私有交付包：原生原件 + manifest.json + SHA256SUMS + observations.jsonl + errors.jsonl + run-report.json。
3. 测试输出、一次真实运行及重放记录；定位/单位/时间/限定条件逐条人工核对。
4. 未披露、冲突、身份不明及访问受阻清单；缺项不填零，冲突不覆盖旧值。

不必同时交 HTML/PDF/JSON：来源是什么格式就保存什么原件，逐条候选统一 JSONL。见 [交付合同](docs/DELIVERY_CONTRACT.md)。格式校验成功≠研究接收≠正式采用≠上线。研究端接口未接通时交包等联调，不冒充 Fetchspec、不编接收地址。

## 节奏与验收

- 第一次交付：运行已有适配器、核对一条、交包及重放证据。
- 第二次交付：加一个本队来源或指标，修复缺口；仍逐条验，不等整份资料读完。
- 接收联调通过后：负责人指定执行机与现有调度器，按 sources.json 建议频率安装；当前没有后台任务自动运行。
- 扩批只看真实原件、新候选、重复、线索、错误、已接收/采用/上线及耗时，各阶段分开。先实测再定吞吐指标。

## 维护边界

`collector.py` 为下载/内容寻址/打包入口，`helpers.py` 是原生 HTML 工具，`adapter.py` 只做本来源固定字段提取，`validate_handoff.py` 是统一交换格式的离线校验快照。四仓库用同一合同，更新合同需保持一致，不互相复制来源适配器。来源布局变化必须报错留原件；禁止静默填缺失值。原 URL 字节变化另存 SHA 版本，旧包保留。并发运行/大批量调度尚未验收，当前同一仓库一次只跑一个进程。
