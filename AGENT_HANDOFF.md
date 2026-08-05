# 飞书文件归档 Aily 项目交接文档

> 面向对象：接手本项目的其他 Agent 或开发者  
> 更新时间：2026-07-29  
> 当前仓库：`Calvincheng-ops/-aily-`  
> 当前主分支：`main`

## 1. 一分钟了解项目

这是一个完全基于飞书 Aily 工作流、飞书卡片、云盘和多维表格的群文件归档
应用，不是常驻 Python 服务。

用户必须直接回复目标文件并 @机器人发送“归档”。技能 A 精确读取该文件、
查询当前群的目录映射、创建请求并发送文件确认卡片。用户每次点击卡片都会新
启动一次技能 B；技能 B 用 `request_id` 从多维表格恢复状态，完成文件确认、
目录浏览、最终确认和上传。

当前仓库中的代码和文档已经对齐，单元测试通过；但 Aily 控制台中的完整线上
流程尚未有“从发起到上传成功”的最终验收记录。不要把“本地代码完成”误认为
“Aily 应用已经搭完并发布”。

## 2. 先按这个顺序阅读

1. [README.md](./README.md)  
   了解目标、目录和核心规则。
2. [AGENT_HANDOFF.md](./AGENT_HANDOFF.md)  
   了解当前状态、边界和下一步。
3. [ARCHITECTURE_V2.png](./ARCHITECTURE_V2.png)  
   快速查看技能 A/B 和四张卡片的关系。
4. [AILY_TECHNICAL_NOTES_2026-07-29.md](./AILY_TECHNICAL_NOTES_2026-07-29.md)  
   了解已验证的 Aily、Base、卡片和错误处理技术细节。
5. [BUILD_GUIDE_V2.md](./BUILD_GUIDE_V2.md)  
   唯一逐步施工手册。用户实际搭建时按第 1 步到第 16 步执行。
6. [CLAUDE.md](./CLAUDE.md)  
   查看 Agent 工作红线和文件职责。
7. `aily_nodes/` 和 `tests/test_aily_nodes.py`  
   核对节点输入输出合同和自动化测试。

文档职责不能混用：

| 文档 | 作用 | 是否作为施工步骤 |
|---|---|---:|
| `BUILD_GUIDE_V2.md` | 一步一步搭建 Aily | 是 |
| `AILY_TECHNICAL_NOTES_2026-07-29.md` | 技术结论和排障知识 | 否 |
| `AGENT_HANDOFF.md` | 项目现状和接手入口 | 否 |
| `ARCHITECTURE_V2.mmd/png` | 总体流程 | 否 |

如有冲突：

1. 代码和实际 Aily 运行日志优先。
2. 施工节点名称、编号和绑定以 `BUILD_GUIDE_V2.md` 为准。
3. 修正后必须同步技术沉淀、交接文档和流程图中受影响的部分。

## 3. 当前真实状态

### 3.1 已完成

- 已删除旧的“大量读取群聊历史 + 智能体猜文件”逻辑。
- 已确定用户必须回复具体文件消息。
- 已确定即使只有一个候选文件，也必须经过卡片 1 确认。
- 已收敛为技能 A + 卡片触发技能 B 的异步架构。
- 已核对并记录 Base 表、字段、状态值和 URL/日期类型要求。
- 已补齐技能 A/B 所需的 13 个 Python 节点文件。
- 已补齐技能 B 的 action 状态转换、上传前重查和上传策略校验。
- 已生成四张卡片所需的变量对象。
- 已同步搭建手册、流程图源文件和 PNG。
- 已通过 26 项单元测试。
- 已推送上一轮代码到 GitHub `main`。

### 3.2 已从真实日志确认

- 触发消息可以取得 `parent_id`。
- `parent_id` 可以精确指向被回复的文件消息。
- 群映射表曾成功按 `chat_id` 命中唯一记录。
- Base 查询条件 `value` 传 string 会导致连接器返回全 `NULL`。
- URL 字段传字符串会报 `1254068 URLFieldConvFail`。
- 字段名末尾隐藏 Tab 会报 `1254045 FieldNameNotFound`。
- `property1` 是错误的默认字段名，不是 `trigger_message_id`。
- 之前出现过 `TRIGGER_CHAT_MISMATCH`，最终确认是 Aily 参数绑定错误，不是
  Python 校验逻辑错误。

### 3.3 尚未确认完成

以下内容不能从仓库推断为已完成：

- 技能 A 在 Aily 控制台是否已经按最新版手册全部重搭并发布。
- 技能 B 是否已经在 Aily 画布中搭完全部分支。
- 四张卡片是否都已按最新版变量刷新并发布。
- 下载消息资源节点在当前租户中的实际“文件内容”和“文件大小”输出字段名。
- 机器人是否已完成一次真实端到端上传。
- 快速并发点击下是否出现重复上传。

接手 Agent 应先向用户确认当前停在哪个 Aily 节点，并查看最近一次运行日志，
不能假设控制台状态与仓库完全同步。

## 4. 产品规则

必须保持：

1. 用户直接回复文件消息并 @机器人。
2. 不回复文件则提示并结束。
3. 不读取整段群聊历史。
4. 不用智能体猜文件。
5. 单文件也必须确认。
6. 只有原归档发起人可以继续点击。
7. 目录只能在当前群映射根目录内浏览。
8. 普通上传限制 `1..20 MB`。
9. 失败显示真实阶段错误。
10. 技能 A 发卡片后结束，不顺序调用技能 B。

## 5. 架构和状态

### 5.1 技能 A

```text
A0 开始
→ A0.1 当前时间
→ A1 校验群聊和归档指令
→ A2 获取触发消息
→ A2.1 标准化消息
→ A2.2 判断 parent_id
→ A3 获取被回复消息
→ A4 查询群映射
→ A5 生成并校验请求快照
→ A6 判断 A5.ok
→ A7 创建 Base 请求
→ A8 组装卡片 1
→ A9 判断 A8.ok
→ A10 发送卡片 1
→ 结束
```

### 5.2 技能 B 公共入口

```text
B0 开始（4 个自定义参数）
→ B0.1 当前时间
→ B0.2 request_id 数组适配
→ B0.3 筛选参数校验
→ B1 查询请求
→ B2 校验点击人、状态、有效期和白名单
→ B3 校验结果条件分支
→ B3.1 action 条件分支
```

“路由”不是 Aily 的特殊节点，文档中的路由全部表示“条件分支”节点。

### 5.3 技能 B 业务分支

| action | 结果 |
|---|---|
| `choose_file` | 写入真实选中文件，进入 `selecting_folder`，发送卡片 2 |
| `browse` | 进入白名单子目录，发送新卡片 2 |
| `back` | 返回路径上一级，发送新卡片 2 |
| `choose_current_folder` | 保存目标目录，进入 `waiting_confirm`，发送卡片 3 |
| `return_folder` | 清空目标选择，回到卡片 2 |
| `cancel` | 写 `cancelled` 并结束 |
| `confirm_upload` | `processing` → 下载 → 校验 → 上传 → 卡片 4 |

### 5.4 状态全集

```text
selecting_file
selecting_folder
waiting_confirm
processing
success
failed
cancelled
expired
```

不要添加中文状态、大小写变体或其他临时状态。

## 6. 外部资源

| 资源 | 标识 |
|---|---|
| Base App Token | `WHaibyXvuaXuJpsDraJcAAM9nIb` |
| 群目录映射 Table | `tblacRVYZZ4SJmWW` |
| 启用映射 View | `vewPOqHrk9` |
| 归档请求 Table | `tblyUgvj29jAL275` |
| GitHub | `https://github.com/Calvincheng-ops/-aily-.git` |
| 默认分支 | `main` |

技能 B 的真实 `skill_xxx`、卡片模板 ID 和当前机器人凭证不写入仓库。需要时
从 Aily/开放平台控制台读取。

## 7. 代码文件职责

| 文件 | 放入节点 | 主要输出 |
|---|---|---|
| `common_now_ms.py` | A0.1、B0.1 | `now_ms` |
| `a2_normalize_trigger_message.py` | A2.1 | 触发消息字段、`chat_id_filter_values` |
| `a7_build_archive_request.py` | A5 | 请求 ID、候选快照、根目录、URL object |
| `a9_build_file_confirm_card.py` | A8 | 卡片 1 变量、确认/取消回调对象 |
| `b0_prepare_request_filter.py` | B0.2 | `request_id_filter_values` |
| `b2_validate_callback.py` | B2 | 可信请求 JSON、选中文件/目录 JSON |
| `b3_prepare_action.py` | B4 | 非上传 action 的扁平更新字段 |
| `b_build_folder_card.py` | B7 | 目录选项、目录白名单、卡片 2 回调 |
| `b_build_confirm_card.py` | B11 | 卡片 3 变量和回调 |
| `b5_validate_processing_request.py` | B14 | 上传所需可信字段 |
| `b6_validate_upload_policy.py` | B17 | 实际大小和上传策略校验 |
| `common_build_url_object.py` | B19 | `url_object` |
| `b_build_result_card.py` | 结果节点 | 卡片 4 变量 |

不要因为文件名中的旧数字与当前画布节点不同而改动业务逻辑。若要重命名文件，
必须一次性更新搭建手册、README、CLAUDE、测试导入和所有链接。

## 8. Base 的关键合同

### 8.1 群目录映射

必须唯一命中当前 `chat_id`，且：

```text
enabled = true
root_folder_token 非空
root_folder_name 非空
root_folder_url 非空
allowed_file_types 包含文件扩展名
1 <= max_file_size_mb <= 20
```

### 8.2 归档请求

关键原则：

- `request_id` 是恢复状态的主查询键。
- `status` 使用固定八个单选值。
- URL 字段接收 `{text, link}` object。
- 日期时间字段接收 Unix 毫秒数字。
- `candidate_files_json`、`folder_path_json` 和白名单是请求快照。
- `created_at` 由 Base 自动生成。

完整字段表见 `BUILD_GUIDE_V2.md` 第 2.2 节。

## 9. 接手后的第一轮检查

### 9.1 仓库

```bash
git status --short
git log -3 --oneline --decorate
python3 -m py_compile aily_nodes/*.py tests/test_aily_nodes.py
python3 -m unittest discover -s tests -v
git diff --check
```

预期：

- 没有意外工作区修改。
- 13 个节点文件可编译。
- 26 项测试通过。

### 9.2 Aily 控制台

向用户取得当前画布或最近日志后，按顺序确认：

1. 技能 A 当前停在哪个节点。
2. A5 是否使用最新版完整 Python 文件。
3. A7 URL 字段是否绑定 object 输出。
4. 卡片 1 是否成功触发技能 B。
5. 技能 B 开始节点是否只有四个自定义参数。
6. B0.2 输出是否为真实数组。
7. B1 查询是否唯一命中请求。
8. B2 能否取得 `message.sender.openID`。
9. B4 之后各 action 是否使用条件分支。
10. 上传分支是否按 B12–B19 顺序搭建。

## 10. 日志排查顺序

每次用户提供 Aily 日志时：

1. 先看失败节点名称，不先猜业务原因。
2. 查看 `InputArgs` 中每个字段的实际运行时类型。
3. 判断 Base 查询的 `value` 是数组还是字符串。
4. 判断 URL 字段值是 object 还是字符串。
5. 检查字段名是否带 Tab/空格，是否出现 `property1`。
6. 检查 A/B 节点参数是否绑定了正确上游输出。
7. 查看当前 Base 请求的真实 `status`。
8. 最后再判断 Python 逻辑是否需要修改。

若用户明确说明是参数绑定错误，应撤回针对业务代码的错误修复，不要为了容忍
`undefined` 等错误输入而削弱校验。

## 11. 常见错误速查

| 表现 | 优先检查 |
|---|---|
| 查询节点输出全 `NULL` | `filter.conditions[].value` 是否为数组 |
| `FieldNameNotFound` | 字段名、隐藏 Tab、`property1` |
| `URLFieldConvFail` | 是否绑定真实 `{text, link}` object |
| `TRIGGER_CHAT_MISMATCH` | `chat_id` 上游绑定 |
| “没有映射”但查询成功 | 是否把其他错误写死成映射错误 |
| 目录 token 被拒绝 | 白名单是否先保存、表单字段名是否正确 |
| B 没收到参数 | 卡片对象的 `skill_id`、`skill_input`、开始参数名 |
| 旧卡片还能继续 | `update_card`、Base 状态、B2 允许状态 |
| 上传前字段为空 | choose_file/choose_current_folder 是否成功落库 |

## 12. 下一步建议

按照优先级：

1. 让用户说明 Aily 当前已搭到 `BUILD_GUIDE_V2.md` 的哪一步。
2. 完成技能 A 的卡片 1 回调联调。
3. 搭完技能 B 公共入口和 `choose_file` 分支。
4. 验证卡片 2 的表单字段可以进入 B。
5. 完成卡片 3 与返回目录。
6. 调试 B15 下载节点的实际输出字段。
7. 完成真实上传和结果写回。
8. 按搭建手册第 16.3 节逐条验收。
9. 验收通过后记录 Aily 技能版本、发布时间和最终测试日志。

## 13. 不要做的事情

- 不新增读取最近群消息节点。
- 不新增意图分类或文件选择智能体节点。
- 不让技能 A 在卡片后顺序调用 B。
- 不让技能 B引用技能 A 的历史节点变量。
- 不把 `request_id` 开始参数改成数组。
- 不把 Base 筛选条件 `value` 绑定成 string。
- 不把 URL 字符串直接写入 Base URL 字段。
- 不自动跳过单文件确认。
- 不删除强校验来兼容错误参数绑定。
- 不在仓库、文档、Base 或日志中保存密钥。

## 14. 安全交接

仓库中不包含应用密钥。开发对话中曾直接提供过应用凭证，建议用户在开放平台
轮换。接手 Agent：

- 不得把聊天历史中的凭证写入文件。
- 不得在回复中复述凭证。
- 需要访问飞书时使用平台连接器或已配置 profile。
- 修改 Base 或线上 Aily 应用前确认用户授权范围。

## 15. 完成定义

只有同时满足以下条件，才能宣称项目搭建完成：

- 技能 A/B 和四张卡片均已发布。
- 用户回复文件并 @机器人能够创建请求并显示卡片 1。
- 单文件不会跳过确认。
- 卡片 2 只能浏览映射根目录内的直属子目录。
- 卡片 3 显示正确文件和目标目录。
- 确认上传后文件真实出现在选定云盘目录。
- Base 写入 `success`、结果 token、URL、大小和完成时间。
- 失败路径写入真实错误。
- 取消、过期、伪造 token、错误操作者和超限文件均按预期处理。
- 搭建手册第 16.3 节全部验收通过。

