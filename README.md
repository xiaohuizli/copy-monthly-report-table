# 月报表格技能使用说明

本技能把分平台工作内容或月报整理为可直接粘贴到 Excel、钉钉等表格的 TSV，并复制到系统剪贴板，同时在 Codex 对话中展示完整表格。人员和岗位可在配置文件中永久修改，也可在每次生成时临时指定。

面向其他用户的快速入门见 [分享使用说明](分享使用说明.md)。

## 文件与环境

- `SKILL.md`：供 Codex 读取的技能指令。
- `config.json`：默认人员和岗位。
- `scripts/copy_monthly_report_table.py`：表格转换、排期与复制脚本。
- `scripts/work_calendar.py`、`references/china-work-calendar.json`：工作日历逻辑与 2026 年日历数据。
- `examples/工作明细.md`：可运行的输入示例。
- `scripts/test_*.py`：验证脚本行为的测试。

需要 Python 3.10 或更高版本，默认使用标准库。macOS 通过 `pbcopy` 复制；Windows 使用系统剪贴板 API。Linux 可用 `--print-only` 输出，再自行复制。Windows 等系统如果缺少 `Asia/Shanghai` 时区数据，可执行 `python3 -m pip install tzdata`；Windows 上也可用 `py -3` 代替 `python3`。

## 在线安装

[在 skills.sh 查看本技能](https://skills.sh/xiaohuizli/copy-monthly-report-table/copy-monthly-report-table)。

```zsh
npx skills add xiaohuizli/copy-monthly-report-table --skill copy-monthly-report-table --agent codex --global -y
```

也可 [下载 ZIP](https://github.com/xiaohuizli/copy-monthly-report-table/releases/latest/download/copy-monthly-report-table.zip) 手动安装。首次使用请配置 `config.json` 中的人员与岗位；CLI 的安装位置以终端输出为准。

## 安装与调用

解压 ZIP，把完整的 `copy-monthly-report-table` 文件夹放入 Codex 技能目录，默认是 `~/.codex/skills/`；设置了 `CODEX_HOME` 时放入该目录下的 `skills/`。保留目录结构，不要只复制 `SKILL.md`。如果已存在同名技能，请先备份原目录，再替换。

无需安装，也可以进入解压后的技能目录直接运行 Python 脚本。脚本、配置和日历均按自身位置定位，不依赖打包时的电脑路径。

在 Codex 中可以这样说：

> 使用 $copy-monthly-report-table，把以下内容生成表格并复制，时间段为 2026-11-09 至 2026-11-13，人员张三，岗位前端，单项最多 3 天：……

Codex 负责理解聊天内容、按平台整理任务并评估缺失工时；Python 脚本接收 Markdown 表格，不直接接收自然语言段落。

## 永久配置人员与岗位

编辑技能目录下的 `config.json`，修改引号内的值并保存为 UTF-8：

```json
{
  "person": "张三",
  "role": "前端"
}
```

`person` 对应“人员”列，`role` 对应“工作岗位”列。包内初始值为“李晓辉”和“后端”。值不能为空，也不能包含制表符或换行；文件应为合法 JSON，不要添加注释或末尾多余逗号。

也可以在 Codex 中直接说：

> 把这个技能的默认人员改为张三、岗位改为前端，以后生成时使用。

多个配置可以分别保存为 `config-frontend.json`、`config-backend.json`，运行时用 `--config` 选择。相对配置路径以执行命令时的当前目录为准。

## 单次覆盖人员与岗位

进入解压后的 `copy-monthly-report-table` 目录：

```zsh
python3 scripts/copy_monthly_report_table.py examples/工作明细.md \
  --start-date 2026-11-09 --end-date 2026-11-13 \
  --person "王五" --role "测试" --print-only
```

这次使用“王五／测试”，不会改写配置文件。只指定 `--person` 时，岗位继续读取配置。优先级为：命令行参数 ＞ 选中的配置文件 ＞ 内置初始值。配置文件缺失、字段非法或 JSON 格式有误时直接报错，不会悄悄忽略。

使用另一个配置的示例：

```zsh
python3 scripts/copy_monthly_report_table.py examples/工作明细.md \
  --config config-frontend.json \
  --start-date 2026-11-09 --end-date 2026-11-13 --print-only
```

## 准备工作明细

输入为 UTF-8 Markdown 表格，至少包含开发平台、工作内容、预估天数。协作人员按任务填写，省略时第三列留空。完成状态缺省为“完成”，也支持旧输入列名“状态”。平台名称和大小写按原样保留。

```markdown
| 开发平台 | 协作人员 | 工作内容 | 预估天数 | 完成状态 |
| --- | --- | --- | --- | --- |
| woowu-ai | 李四 | 优化后台统计查询与媒体预览。 | 2 天 | 完成 |
| new-api |  | 完善发布恢复工具，完成离线验证，未执行生产发布。 | 1.5 天 | 待发布 |
```

工时支持 `1`、`1.5 天`、`2 人日` 等正数写法。技能指导 Codex 默认单项不超过 3 天；脚本本身不强制这一上限，不会擅自把更大的工时缩短。需要其他上限时在请求中说明。

每条任务的状态会保留。`--status "完成"` 会强制覆盖所有行状态，仅在确实要统一状态时使用。暂停、待验收、权限阻塞和未上线等情况应按实际填写，不能因为代码实现完成就删除这些说明。

## 生成与复制

先预览并核对九列的顺序、内容、人员、工时和日期：

```zsh
python3 scripts/copy_monthly_report_table.py examples/工作明细.md \
  --start-date 2026-11-09 --end-date 2026-11-13 --print-only
```

确认后去掉 `--print-only`，生成并复制：

```zsh
python3 scripts/copy_monthly_report_table.py examples/工作明细.md \
  --start-date 2026-11-09 --end-date 2026-11-13
```

在目标表格选中起始单元格，macOS 按 Command+V，Windows 按 Ctrl+V。默认无表头，列顺序为：

| 顺序 | 列名 |
| --- | --- |
| 1 | 开发平台 |
| 2 | 人员 |
| 3 | 协作人员 |
| 4 | 工作岗位 |
| 5 | 工作内容 |
| 6 | 预估天数 |
| 7 | 开始时间 |
| 8 | 完成时间 |
| 9 | 完成状态 |

需要表头时加 `--include-header`。脚本只复制到剪贴板，不自动写入外部表格。

通过 Codex 使用本技能时，每次生成、重新生成或重新复制后，最终回复都会同时展示完整 Markdown 表格，包含全部任务和九列数据，方便核对和直接查看。对话表格带列名，剪贴板仍默认不带表头，两者的数据与顺序一致。直接运行 Python 脚本时，使用 `--print-only` 查看 TSV 内容；完整对话表格由 Codex 按技能指令展示。复制失败时会明确说明，并展示已生成内容。

## 时间范围与排期

| 需求 | 参数 |
| --- | --- |
| 指定区间 | `--start-date 2026-11-09 --end-date 2026-11-13` |
| 指定整月 | `--month 2026-11` |
| 本月截至今天 | `--through-today`，按北京时间 |
| 所有任务从区间首个工作日开始 | `--start-mode shared` |
| 轮换任务起点，默认方式 | `--start-mode spread` |
| 使用其他工作日历 | `--calendar /path/to/calendar.json` |

起止日期必须在同一个月；跨月需求分月处理。排期排除节假日和普通周末，纳入调休上班日。随包仅提供 2026 年日历，其他年份需先核实官方年度安排并更新日历，缺少日历时脚本报错。

各任务独立排期，可以重叠，总工时允许超过时间段内的工作日数。如果要完全不重叠，必须提供足够的时间或调整任务范围；脚本没有无重叠排期模式。单项工时无法在区间内容纳时，会报错，不会延长到指定截止日之后。小数工时原样保留，日期跨度按工作日向上取整。

生成日期属于建议排期，不代表实际完成日期。脚本会重排所有任务，已有明确固定日期时不要用它直接覆盖。

## 验证技能包

在技能目录执行：

```zsh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

日历来源记录在 `references/china-work-calendar.json` 的 `source` 字段。更新年份时须同时维护放假区间与调休上班日期，不能只维护法定节日当天。
