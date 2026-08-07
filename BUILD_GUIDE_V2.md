# 飞书 Aily 文件归档应用：基于已配置 Base 的逐步重搭手册

> 目标：保留当前已经配置好的 Base，从空白 Aily 工作流开始，按本文第 1 步做到第 16 步，即可搭好“回复群文件并 @机器人归档 → 确认文件 → 选择目录 → 最终确认 → 上传云盘”的应用。
>
> 本文是仓库唯一实施手册。不要同时参考旧流程，不要添加智能体猜文件、读取大量群聊历史或自建 HTTP 回调。
>
> 本手册与仓库的 `aily_nodes/` 代码文件共同构成必备施工包。代码步骤必须点击本文链接并复制完整文件；不能只拿一篇 Markdown、缺少 Python 附件进行搭建。每个代码节点的完整 `main()` 入参绑定和关键输出合同都写在对应步骤中。

## 开工前先准备

准备以下内容，后文直接使用：

| 名称 | 当前值或填写方式 |
|---|---|
| Base App Token | `WHaibyXvuaXuJpsDraJcAAM9nIb` |
| 群目录映射 Table ID | `tblacRVYZZ4SJmWW` |
| 启用映射 View ID | `vewPOqHrk9` |
| 归档请求 Table ID | `tblyUgvj29jAL275` |
| 技能 A 名称 | `发起文件归档-V2` |
| 技能 B 名称 | `处理文件归档卡片-V2` |
| 技能 B ID | 完成第 3 步后取得，格式必须是 `skill_xxx` |
| 测试群 ID | 当前映射记录中的 `chat_id` |
| 测试根目录 | 当前映射记录中的 `root_folder_token` |

全程遵守四条规则：

1. 用户必须回复一条文件消息，再 @机器人发送“归档”。
2. 即使只有一个文件，也必须先发卡片 1，让用户确认。
3. 技能 B 每次点击都是一次新运行，只能靠卡片传入的 `request_id` 从 Base 恢复状态；技能 A 内可见的上游变量不会跨越用户点击自动保留。
4. App Secret、访问令牌不得写入代码、卡片、Base 或日志。

最终只有两条工作流：

```text
技能 A：开始 → 查触发消息 → 查被回复文件 → 查群映射 → 创建请求
       → 用 A 的上游变量组装卡片 1（按钮指向技能 B）→ 发卡片 1 → 结束

用户点击卡片：卡片 trigger_skill → 技能 B 新运行

技能 B：开始参数 → 按 request_id 查请求 → 校验点击人和状态 → action 分支
       ├─ choose_file / browse / back / return_folder → 卡片 2
       ├─ choose_current_folder → 卡片 3
       ├─ confirm_upload → 下载 → 上传 → 卡片 4
       └─ cancel → 结束
```

### 架构决定：不要把“工作流 B”顺序节点接在技能 A 的卡片后面

Aily 允许在技能 A 中添加“工作流 B”节点，并把该节点上方的变量绑定为 B 的输入。这是**顺序调用节点**：A 执行到该节点时就会发起 B，而不是等未来的卡片点击事件。

卡片点击是另一个时间点发生的**异步事件**。发送卡片节点不会暂停并等待用户点击，所以：

```text
错误：
A 创建请求 → 发卡片 1 → 工作流 B 节点
                         ↑ B 会立刻执行，用户还没有点击

正确：
A 创建请求 → 组装卡片按钮的 skill_input → 发卡片 1 → A 结束
用户点击按钮 → 卡片的 trigger_skill 启动 B → B 从 Base 恢复请求
```

本项目不在技能 A 中添加“工作流 B”顺序节点。A 的上游变量通过以下两步被安全使用：

1. `a9_build_file_confirm_card.py` 把 `A5.request_id`、固定 `action` 和候选文件内部 ID 写进按钮的 `skill_input`。
2. 用户点击后，卡片用 `skill_id=技能 B ID` 启动 B；B 只信任 `request_id` 和点击人的系统 `open_id`，其余业务状态从 Base 重查。

这样不会影响卡片回调，反而能避免 B 在用户确认前提前执行。以后若有与卡片点击无关、确实需要立即执行的公共计算，才考虑从 A 同步调用子工作流；不要用它传递异步回调状态。

---

## 第 1 步：配置应用能力和权限

在飞书开放平台/Aily 应用配置中完成：

1. 启用机器人能力。
2. 把机器人加入测试群。
3. 开通读取群消息、读取消息资源所需权限。
4. 开通读取和上传云盘文件所需权限。
5. 开通读取、创建和更新多维表格记录所需权限。
6. 将测试根目录共享给工作流节点实际使用的身份。
7. 将 Base 共享给工作流节点实际使用的身份。
8. 发布应用权限变更。

注意：

- 把文件夹链接写进 Base 不等于授予机器人权限。
- “目录清单”和“上传文件”节点必须使用同一个有权限的身份。
- 技能 A 要能读映射表并创建请求；技能 B 要能查询和更新请求。

完成检查：

- [ ] 机器人已经在测试群。
- [ ] 机器人身份可以读取 Base。
- [ ] 机器人身份可以读取测试根目录清单。
- [ ] 机器人身份可以向测试根目录上传一个测试文件。

任何一项失败都先修权限，不进入下一步。

---

## 第 2 步：核对多维表格

当前 Base 已经建好，不要重新创建。打开：

```text
https://westoeast.feishu.cn/base/WHaibyXvuaXuJpsDraJcAAM9nIb
```

### 2.1 核对“群目录映射”

Table ID：

```text
tblacRVYZZ4SJmWW
```

必须有以下字段：

| 字段 | 类型 | 填写规则 |
|---|---|---|
| `mapping_id` | 自动编号 | 自动生成 |
| `chat_id` | 文本 | `oc_...` |
| `chat_name` | 文本 | 仅展示 |
| `root_folder_token` | 文本 | 只填 token，不填完整链接 |
| `root_folder_name` | 文本 | 根目录名称 |
| `root_folder_url` | URL | 完整文件夹链接 |
| `enabled` | 复选框 | 必须勾选 |
| `allowed_file_types` | 多选 | 小写、不带点 |
| `max_file_size_mb` | 数字 | 填 `1..100`（≤20 普通上传，>20 自动分片） |
| `only_file_sender_can_archive` | 复选框 | 默认不勾选 |

当前测试记录应至少满足：

```text
enabled = true
allowed_file_types = pdf, docx, xlsx, pptx, zip, md
max_file_size_mb = 20
only_file_sender_can_archive = false
```

`root_folder_token` 正确示例：

```text
SDiif2417lQWmidJfFMcDIyXn1e
```

不要填：

```text
https://xxx.feishu.cn/drive/folder/SDiif2417lQWmidJfFMcDIyXn1e?from=...
```

### 2.2 核对“归档请求”

Table ID：

```text
tblyUgvj29jAL275
```

必须存在以下字段和类型：

| 字段 | 类型 |
|---|---|
| `request_id` | 单行文本，主字段 |
| `chat_id` | 单行文本 |
| `requester_id` | 单行文本 |
| `trigger_message_id` | 单行文本 |
| `candidate_files_json` | 多行文本 |
| `source_message_id` | 单行文本 |
| `source_type` | 单选：`message_file` |
| `selected_file_id` | 单行文本 |
| `selected_file_key` | 单行文本 |
| `selected_file_name` | 单行文本 |
| `selected_file_type` | 单行文本 |
| `selected_file_size` | 数字，整数 |
| `root_folder_token_snapshot` | 单行文本 |
| `root_folder_name_snapshot` | 单行文本 |
| `root_folder_url_snapshot` | URL |
| `current_folder_token` | 单行文本 |
| `current_folder_name` | 单行文本 |
| `current_folder_url` | URL |
| `folder_path_json` | 多行文本 |
| `allowed_child_folders_json` | 多行文本 |
| `target_folder_token` | 单行文本 |
| `target_folder_name` | 单行文本 |
| `target_folder_url` | URL |
| `warning_message` | 多行文本 |
| `status` | 单选，选项见下方 |
| `expires_at` | 日期时间，精确到毫秒 |
| `confirmed_at` | 日期时间，精确到毫秒 |
| `result_file_token` | 单行文本 |
| `result_file_url` | URL |
| `result_size` | 数字，整数 |
| `error_message` | 多行文本 |
| `completed_at` | 日期时间，精确到毫秒 |
| `created_at` | 系统创建时间 |

`status` 的单选值必须完全一致：

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

注意：

- 字段名是工作流合同，不要改成中文。
- URL 字段保持 URL 样式。
- `request_id` 是主查询键。
- `created_at` 由 Base 自动生成，创建记录节点不要给它赋值。
- 精确“30 分钟过期”由工作流比较 `expires_at`，不要依赖视图。

完成检查：

- [ ] 当前群的映射查询结果恰好 1 条。
- [ ] `allowed_file_types` 包含准备测试的扩展名。
- [ ] 根目录 token、名称、URL 都非空。
- [ ] “归档请求”字段和状态值已核对。
- [ ] 根目录文件夹已共享给机器人所在应用的身份（可编辑）。**每新增一个群的映射都必须做这一步**，否则上传报 `1061004 forbidden`（2026-08-07 实测）。

---

## 第 3 步：新建技能 B 的空壳

先建技能 B，因为所有交互卡片都需要它的 `skill_id`。

1. 在 Aily 新建技能。
2. 名称填：

```text
处理文件归档卡片-V2
```

3. 技能描述填：

```text
处理文件归档确认卡片的点击回调。通过 request_id 从多维表格恢复状态，执行选文件、浏览目录、最终确认、上传或取消。
```

4. 在开始节点添加四个自定义参数：

| 参数 | 类型 | 必填 | 默认值 |
|---|---|---:|---|
| `request_id` | string | 是 | 空 |
| `action` | string | 是 | 空 |
| `selected_file_id` | string | 否 | 空 |
| `selected_folder_token` | string | 否 | 空 |

5. 记住系统全局变量路径：

```text
本次点击人 open_id = message.sender.openID
```

不要添加：

```text
operator_open_id 自定义参数
file_key 自定义参数
folder_token 之外的目录状态参数
技能 A 节点变量
```

你在技能 A 的“工作流 B”节点里看到的上游变量选择器，只对“A 运行到该节点时直接调用 B”有效。本项目的 B 是由卡片点击启动，因此 B 开始节点仍只保留上面四个卡片参数；不要为了引用 A 的节点变量增加一批初始化参数。

6. 开始节点后添加 Python 节点 `B0.1_当前时间`，完整复制：

[common_now_ms.py](./aily_nodes/common_now_ms.py)

该节点无输入，输出：

```text
now_ms = 当前 Unix 毫秒
```

7. 临时接一个文本/调试输出节点，输出：

```json
{
  "request_id": "{{开始.request_id}}",
  "action": "{{开始.action}}",
  "selected_file_id": "{{开始.selected_file_id}}",
  "selected_folder_token": "{{开始.selected_folder_token}}",
  "operator_id": "{{message.sender.openID}}"
}
```

8. 发布技能 B。
9. 复制发布后的技能 ID，必须是：

```text
skill_xxx
```

把它记为：

```text
CALLBACK_SKILL_ID = skill_xxx
```

不要使用 `cli_xxx`、应用 ID、节点 ID或卡片模板 ID。

---

## 第 4 步：创建卡片 1“确认文件”

卡片名称：

```text
归档-确认文件-V2
```

### 4.1 创建变量

| 变量名 | 类型 |
|---|---|
| `request_id_text` | 文本 |
| `file_name` | 文本 |
| `file_type` | 文本 |
| `root_folder_name` | 文本 |
| `initiator` | 人员 |
| `skill_object_choose_file` | 对象 |
| `skill_object_cancel` | 对象 |

`initiator` 必须是人员变量，模拟值可填：

```json
{"id":"ou_demo"}
```

### 4.2 搭卡片内容

正文：

```text
待归档文件：{{file_name}}
文件类型：{{file_type}}
归档根目录：{{root_folder_name}}
请求编号：{{request_id_text}}

请确认是否归档这个文件。
```

按钮 1：

```text
文案：确认归档这个文件
事件：请求回调
参数类型：对象
绑定变量：skill_object_choose_file
```

按钮 2：

```text
文案：取消
事件：请求回调
参数类型：对象
绑定变量：skill_object_cancel
```

发布卡片。

注意：只有一个候选文件也必须经过这张卡片。

---

## 第 5 步：创建卡片 2“选择目录”

卡片名称：

```text
归档-选择目录-V2
```

### 5.1 创建变量

| 变量名 | 类型 |
|---|---|
| `selected_file_name` | 文本 |
| `breadcrumb` | 文本 |
| `current_folder_url` | 文本 |
| `warning` | 文本 |
| `initiator` | 人员 |
| `folder_options` | 选项数组 |
| `disable_folder_browse` | 布尔 |
| `disable_back` | 布尔 |
| `skill_object_browse` | 对象 |
| `skill_object_back` | 对象 |
| `skill_object_choose_current` | 对象 |
| `skill_object_cancel` | 对象 |

### 5.2 搭卡片内容

显示：

```text
文件：{{selected_file_name}}
当前位置：{{breadcrumb}}
目录链接：{{current_folder_url}}
提示：{{warning}}
```

添加一个表单容器，在同一个表单容器内放：

1. 目录下拉框。
2. “进入选中的文件夹”提交按钮。

下拉框配置：

```text
组件名称/表单项标识：selected_folder_token
选项：绑定 folder_options
必填：是
禁用：绑定 disable_folder_browse
```

表单提交按钮：

```text
文案：进入选中的文件夹
事件：请求回调
参数类型：对象
绑定：skill_object_browse
禁用：绑定 disable_folder_browse
```

表单外再放三个按钮：

| 按钮 | 绑定对象 | 禁用 |
|---|---|---|
| 使用当前目录 | `skill_object_choose_current` | 否 |
| 返回上一级 | `skill_object_back` | `disable_back` |
| 取消 | `skill_object_cancel` | 否 |

这三个按钮都必须配置：

```text
事件 = 请求回调
参数类型 = 对象
回传参数 = 绑定上表对应对象变量
```

不要创建成仅跳转链接或无事件的普通按钮。

发布卡片。

关键检查：

- [ ] 下拉框名称正好是 `selected_folder_token`。
- [ ] 下拉框与进入按钮在同一表单容器。
- [ ] 技能 B 开始节点存在同名参数。
- [ ] 空目录时仅禁用“进入”，仍允许“使用当前目录”。

---

## 第 6 步：创建卡片 3 和卡片 4

### 6.1 卡片 3“最终确认”

卡片名称：

```text
归档-最终确认-V2
```

变量：

```text
request_id_text        文本
selected_file_name     文本
selected_file_type     文本
target_folder_path     文本
target_folder_url      文本
warning                文本
initiator              人员
skill_object_confirm   对象
skill_object_return    对象
skill_object_cancel    对象
```

正文：

```text
文件：{{selected_file_name}}
类型：{{selected_file_type}}
目标目录：{{target_folder_path}}
目录链接：{{target_folder_url}}
提示：{{warning}}

确认后将立即上传。
```

按钮：

| 按钮 | 绑定对象 |
|---|---|
| 确认上传 | `skill_object_confirm` |
| 返回重新选择 | `skill_object_return` |
| 取消 | `skill_object_cancel` |

三个按钮都配置：

```text
事件 = 请求回调
参数类型 = 对象
回传参数 = 绑定上表对应对象变量
```

发布卡片。

### 6.2 卡片 4“归档结果”

卡片名称：

```text
归档-结果-V2
```

变量：

```text
is_success             布尔
result_title           文本
result_summary         文本
request_id_text        文本
selected_file_name     文本
selected_file_type     文本
target_folder_name     文本
target_folder_path     文本
target_folder_url      文本
result_file_url        文本
result_size_text       文本
completed_at_text      文本
error_message          文本
initiator              人员
```

正文至少展示：

```text
{{result_title}}
{{result_summary}}
文件：{{selected_file_name}}
目标目录：{{target_folder_path}}
文件链接：{{result_file_url}}
文件大小：{{result_size_text}}
完成时间：{{completed_at_text}}
失败原因：{{error_message}}
请求编号：{{request_id_text}}
```

卡片 4 不放任何回调按钮。发布卡片。

---

## 第 7 步：搭建技能 A 的开始和消息查询

新建技能：

```text
发起文件归档-V2
```

技能描述：

```text
在群聊中，用户回复一条文件消息并 @机器人发送“归档”时，创建归档请求并发送文件确认卡片。
```

### 7.0 把技能 A 挂到应用入口

在 Aily 应用的“技能/能力”列表中添加 `发起文件归档-V2`，并在技能触发配置中选择飞书消息入口。群聊触发规则设置为：

```text
会话类型 = 群聊
需要 @机器人 = 是
触发词包含 = 归档
目标技能 = 发起文件归档-V2
```

如果当前 Aily 版本由主智能体根据技能描述路由，不提供单独的触发词表，则：

1. 将上面的技能描述原样填入技能触发描述。
2. 在应用中启用该技能。
3. 保留 A1 的确定性条件作为第二道校验。
4. 不要在技能 A 内再添加意图分类智能体。

保存入口配置后立即做一次触发调试：

```text
在测试群回复任意消息并 @机器人发送“归档”
```

此时即使被回复内容不是文件，技能 A 的 A0 也必须出现一条新运行记录，并能看到 `chat_id / trigger_message_id / requester_id`。A0 没运行就先修应用入口，不继续搭后续节点。

### 7.1 A0 开始节点

从系统全局变量取值：

| 本文简称 | Aily 系统变量 |
|---|---|
| `trigger_text` | `query` |
| `chat_id` | 优先 `channel.larkChannelInfo.chat_id`；有标准变量时也可用 `channel.variables.chat_id` |
| `trigger_message_id` | `message.channelInfo.message_id` |
| `requester_id` | `message.sender.openID` |
| `chat_type` | `session.sessionType` |

第一次调试时核对真实值：

```text
chat_id 以 oc_ 开头
trigger_message_id 以 om_ 开头
requester_id 以 ou_ 开头
chat_type = group
```

若租户界面路径略有不同，以开始节点调试输出为准。不要使用 `session.sessionID` 充当 `chat_id`：日志里它可能是数字会话 ID，不是 `oc_...`。A2.1 还会从真实触发消息中再次取得并校验 `chat_id`。

在开始节点后添加 Python 节点 `A0.1_当前时间`，复制：

[common_now_ms.py](./aily_nodes/common_now_ms.py)

后续所有时间都绑定 `A0.1.now_ms`，不要手工填写旧时间戳。

### 7.2 A1 条件节点“是否为归档指令”

继续条件：

```text
chat_type == group
chat_id 非空
trigger_message_id 非空
requester_id 非空
trigger_text 包含 归档
```

不满足时发送：

```text
请在群里回复需要归档的文件消息，并 @机器人发送“归档”。
```

然后结束。

不要添加大模型或智能体节点。

### 7.3 A2 获取触发消息

添加“获取指定消息”节点：

```text
message_id = A0.trigger_message_id
```

需要保留节点完整输出，后续代码节点整体接收，不要只复制一段 JSON 文本。

在 A2 后添加 Python 节点，命名：

```text
A2.1_标准化触发消息参数
```

复制完整文件：

[a2_normalize_trigger_message.py](./aily_nodes/a2_normalize_trigger_message.py)

输入绑定：

| `main()` 参数 | 绑定值 |
|---|---|
| `message_result` | A2 完整输出 |
| `expected_message_id` | A0 `trigger_message_id` |

成功输出必须是：

```text
ok = true
message_id = om_xxx
parent_id = om_xxx
chat_id = oc_xxx
chat_id_filter_values = ["oc_xxx"]   ← 真实字符串数组
sender_id = ou_xxx
```

`chat_id_filter_values` 专门用于多维表格查询节点的筛选 `value`。不要把 `chat_id` 字符串直接绑定给筛选 `value`。

### 7.4 A3 获取被回复消息

先在 A2.1 后添加条件节点：

```text
A2.1.ok == false → 发送 A2.1.error 并结束
A2.1.ok == true 且 A2.1.parent_id 非空 → 继续查询被回复消息
A2.1.ok == true 且 A2.1.parent_id 为空 → 发送下方提示并结束
```

提示：

```text
请回复需要归档的文件消息，并 @机器人发送“归档”。
```

再添加一个“获取指定消息”节点：

```text
message_id = A2.1 输出的 parent_id
```

不要使用 `root_id` 回退猜文件。

---

## 第 8 步：技能 A 查询群目录映射

添加“查询多维表格记录”节点，命名：

```text
A4_查询群目录映射
```

参数：

```text
Base App Token = WHaibyXvuaXuJpsDraJcAAM9nIb
Table ID       = tblacRVYZZ4SJmWW
View ID        = vewPOqHrk9
page_size      = 2
```

筛选：

```text
字段       = chat_id
operator   = is
value      = A2.1.chat_id_filter_values
```

这里不要在查询节点里手工构造数组。把整个筛选 `value` 绑定到 A2.1 的 `chat_id_filter_values`；这个 Python 输出本身就是字符串数组。

正确的运行时输入：

```json
{
  "field_name": "chat_id",
  "operator": "is",
  "value": ["oc_xxx"]
}
```

错误输入：

```json
{
  "field_name": "chat_id",
  "operator": "is",
  "value": "oc_xxx"
}
```

如果错误地传字符串，Aily 的该连接器可能直接输出 `code/data/message = NULL`，这不是“查询结果为 0 条”，而是筛选参数类型校验失败。`View ID` 可以继续填写，但它不是本次 `NULL` 的原因。

不要按 `chat_name` 查询。

调试预期：

```text
total = 1
fields.enabled = true
fields.root_folder_token 非空
fields.allowed_file_types 包含测试文件扩展名
```

---

## 第 9 步：技能 A 创建请求

### 9.1 A5 代码节点“生成归档请求”

新增 Python 代码节点，把以下文件完整复制进去：

[a7_build_archive_request.py](./aily_nodes/a7_build_archive_request.py)

不要只复制 `main()`，要复制整个文件。

输入参数绑定：

| `main()` 参数 | 绑定值 |
|---|---|
| `mapping_result` | `A4_查询群目录映射`完整输出 |
| `trigger_message_result` | A2 完整输出 |
| `replied_message_result` | A3 完整输出 |
| `chat_id` | A2.1 `chat_id` |
| `requester_id` | A0 `requester_id` |
| `trigger_message_id` | A0 `trigger_message_id` |
| `trigger_text` | A0 `trigger_text` |
| `now_ms` | `A0.1_当前时间.now_ms` |

先调试代码节点，让 Aily 自动识别返回字段。

成功必须看到：

```text
ok = true
request_id = archive_xxx
candidate_count = 1
initial_status = selecting_file
selected_file_id = 空
selected_file_key = 空
selected_file_name = 空
folder_path_json = [{"token":"根目录..."}]
expires_at_ms = 当前时间 + 30 分钟
```

### 9.2 A6 条件节点

```text
如果 A5.ok == true  → 继续
如果 A5.ok == false → 发送 A5.error → 结束
```

失败文案必须绑定 `A5.error`，不能写死“没有目录映射”。

### 9.3 A7 创建“归档请求”记录

添加“创建多维表格记录”节点：

```text
Base App Token = WHaibyXvuaXuJpsDraJcAAM9nIb
Table ID       = tblyUgvj29jAL275
```

字段绑定：

| Base 字段 | 值 |
|---|---|
| `request_id` | `A5.request_id` |
| `chat_id` | `A5.chat_id` |
| `requester_id` | `A5.requester_id` |
| `trigger_message_id` | `A5.trigger_message_id` |
| `candidate_files_json` | `A5.candidate_files_json` |
| `root_folder_token_snapshot` | `A5.root_folder_token` |
| `root_folder_name_snapshot` | `A5.root_folder_name` |
| `root_folder_url_snapshot` | `A5.root_folder_url_object`，类型必须是 object |
| `current_folder_token` | `A5.root_folder_token` |
| `current_folder_name` | `A5.root_folder_name` |
| `current_folder_url` | `A5.current_folder_url_object`，类型必须是 object |
| `folder_path_json` | `A5.folder_path_json` |
| `allowed_child_folders_json` | 固定 `[]` |
| `warning_message` | `A5.warning` |
| `status` | 固定 `selecting_file` |
| `expires_at` | `A5.expires_at_ms` |

保存节点后刷新一次数据表字段列表，并在运行输入中做以下硬性检查：

```text
必须出现：trigger_message_id
不得出现：property1
expires_at 必须显示为 int/number，而不是 string
```

字段名必须从节点刷新后的 Base 字段列表中点选，不要复制粘贴或手工输入。Aily 的运行输入预览可能不会显示字段名末尾的 Tab、空格等不可见字符；必须以错误详情中单引号内的原始字段名为准。例如：

```text
fields.allowed_child_folders_json\t
```

并不是 `allowed_child_folders_json`，而是末尾多了一个 Tab，会返回 `1254045 FieldNameNotFound`。修复方式是删除整行字段绑定，再从字段列表重新选择真实字段；不要只在原输入框末尾按退格。

如果运行输入出现：

```text
"property1": "om_xxx"
```

说明添加字段时没有从 Base 字段列表中选中真实的 `trigger_message_id`，Aily 把该行保留成了默认字段名。删除这一行，刷新节点的数据表字段，再重新选择：

```text
trigger_message_id = A5.trigger_message_id
```

`expires_at` 是 Base 日期时间字段。飞书新增记录接口要求毫秒级时间戳数字，因此 A5 输出结构中的 `expires_at_ms` 必须声明为 `integer/number`。正确运行输入：

```text
"expires_at": 1785251887940
```

错误运行输入：

```text
"expires_at": "1785251887940"
```

`root_folder_url_snapshot` 和 `current_folder_url` 是 Base 超链接字段。仅把创建节点左侧的参数类型改为 `object` 不会转换右侧变量；如果右侧仍绑定 `A5.root_folder_url`，运行时得到的仍是字符串。

重新复制最新版 `a7_build_archive_request.py`，调试 A5 后确认新增两个 object 输出：

```json
{
  "root_folder_url_object": {
    "text": "测试文件夹",
    "link": "https://xxx.feishu.cn/drive/folder/xxx"
  },
  "current_folder_url_object": {
    "text": "测试文件夹",
    "link": "https://xxx.feishu.cn/drive/folder/xxx"
  }
}
```

创建记录节点右侧必须分别绑定这两个 object 输出，不再绑定字符串 `root_folder_url`。正确运行输入中应看到嵌套对象；如果 `fieldValue` 后面直接跟 `https://...`，说明仍绑定错了。

创建时以下字段必须留空：

```text
source_message_id
source_type
selected_file_id
selected_file_key
selected_file_name
selected_file_type
selected_file_size
target_folder_token
target_folder_name
target_folder_url
confirmed_at
result_file_token
result_file_url
result_size
error_message
completed_at
```

这是“即使一个文件也必须先确认”的实现点。

---

## 第 10 步：技能 A 发送卡片 1

### 10.1 A8 代码节点“组装文件确认卡片”

复制完整文件：

[a9_build_file_confirm_card.py](./aily_nodes/a9_build_file_confirm_card.py)

输入绑定：

| 参数 | 值 |
|---|---|
| `candidate_files_json` | `A5.candidate_files_json` |
| `request_id` | `A5.request_id` |
| `callback_skill_id` | 第 3 步取得的 `skill_xxx` |
| `requester_id` | `A5.requester_id` |
| `root_folder_name` | `A5.root_folder_name` |

调试成功：

```text
ok = true
skill_object_choose_file.skill_id = skill_xxx
skill_object_choose_file.skill_input 包含 request_id、action=choose_file、selected_file_id
skill_object_cancel.skill_input 包含 request_id、action=cancel
```

### 10.2 A9 条件节点

```text
A8.ok == true  → 发卡片
A8.ok == false → 更新 A7 请求为 failed，写入 A8.error 和 completed_at
               → 发送 A8.error → 结束
```

失败更新使用：

```text
record_id     = A7 创建记录节点返回的 record_id
status        = failed
error_message = A8.error
completed_at  = A0.1_当前时间.now_ms
```

### 10.3 A10 发送飞书卡片

选择第 4 步发布的：

```text
归档-确认文件-V2
```

绑定：

| 卡片变量 | A8 输出 |
|---|---|
| `request_id_text` | `request_id_text` |
| `file_name` | `file_name` |
| `file_type` | `file_type` |
| `root_folder_name` | `root_folder_name` |
| `initiator` | `initiator` |
| `skill_object_choose_file` | `skill_object_choose_file` |
| `skill_object_cancel` | `skill_object_cancel` |

发送节点底部 HTTP 回调地址留空。

如果发送节点要求填写接收会话：

```text
接收类型 = 群聊
chat_id = A5.chat_id
```

不要把卡片里的文本变量当接收人。

若 A10 发送卡片失败，同样使用 A7 返回的 `record_id` 将请求更新为
`failed`，`error_message` 写发送节点的真实错误，`completed_at` 写
`A0.1_当前时间.now_ms`，然后结束。

卡片发出后，技能 A 直接结束。技能 A 不等待技能 B。

不要在 A10 后面添加“工作流 B”节点。该节点会在卡片发送后立即调用 B，并不会等用户点击。

真正的 A → B 连接已经包含在 A8 输出的卡片按钮对象中：

```text
aily_action = trigger_skill
skill_id = 技能 B 的 skill_xxx
skill_input = {
  "request_id": "A5.request_id",
  "action": "choose_file 或 cancel",
  "selected_file_id": "确认按钮才携带"
}
```

这里的值由 A8 代码节点在运行时生成，不要在卡片编辑器里手写某一次测试的真实 `request_id`。

### 10.4 立即测试 A

在测试群：

1. 发送一个小于 20 MB 的 `.md` 文件。
2. 回复该文件消息。
3. @机器人发送：

```text
归档
```

预期：

- Base 新增一条 `selecting_file` 请求。
- `selected_file_*` 为空。
- 群里出现卡片 1。
- 点击“确认归档这个文件”会启动技能 B。
- 技能 B 调试入口收到 `request_id/action/selected_file_id`。

如果 B 没收到参数，先修卡片回调，不继续搭后续分支。

---

## 第 11 步：搭建技能 B 的公共入口

删除第 3 步的临时调试输出，开始正式搭建。

先理解技能 B 的运行方式：用户每点击一次卡片，就新启动一次技能 B；本次运行只处理这一次点击，然后结束。下一次点击会再次从 B0 开始。

```text
B0 读取本次点击参数
→ B1 按 request_id 查 Base
→ B2 校验点击是否合法
→ 条件分支判断 action
→ 只执行对应的一条业务分支
→ 发下一张卡片或结束
```

因此“分支”表示工作流画布上的不同连线，不代表同时执行所有 action。

### 11.1 B1 查询归档请求

把公共入口按下面顺序连接：

```text
B0 开始 → B0.1_当前时间 → B0.2_生成请求筛选数组
        → B0.3_筛选参数校验 → B1_查询归档请求
```

先添加 Python 节点：

```text
B0.2_生成请求筛选数组
```

复制完整文件：

[b0_prepare_request_filter.py](./aily_nodes/b0_prepare_request_filter.py)

输入绑定：

```text
request_id = 开始.request_id
```

调试输出必须是：

```text
request_id = archive_xxx
request_id_filter_values = ["archive_xxx"]
```

开始节点的 `request_id` 必须继续保持 `string`；卡片传字符串是正确的。B0.2 只为 Base 查询连接器额外生成数组形式。

在 B0.2 后添加“条件分支”节点：

```text
节点名 = B0.3_筛选参数校验

B0.2.ok == false → 发送 B0.2.error → 结束
B0.2.ok == true  → B1_查询归档请求
```

不要让空数组继续进入 Base 查询节点。

添加“查询多维表格记录”节点：

```text
Base App Token = WHaibyXvuaXuJpsDraJcAAM9nIb
Table ID       = tblyUgvj29jAL275
page_size      = 2
筛选字段         = request_id
operator         = is
value             = B0.2.request_id_filter_values
```

不要绑定数组中的第 0 项，否则又会退化成字符串。把整个筛选 `value` 绑定到 `request_id_filter_values`。运行时应为 `"value":["archive_xxx"]`，不能是 `"value":"archive_xxx"`。

### 11.2 B2 代码节点“校验回调”

复制完整文件：

[b2_validate_callback.py](./aily_nodes/b2_validate_callback.py)

输入绑定：

| 参数 | 值 |
|---|---|
| `request_result` | B1 完整输出 |
| `request_id` | 开始节点 `request_id` |
| `action` | 开始节点 `action` |
| `operator_id` | 系统变量 `message.sender.openID` |
| `selected_file_id` | 开始节点 `selected_file_id` |
| `selected_folder_token` | 开始节点 `selected_folder_token` |
| `now_ms` | `B0.1_当前时间.now_ms` |

### 11.3 第 11–16 步通用约定

从这里到第 16 步，每一步只做一件事。步骤按以下约定书写，不再逐步解释：

1. 「添加节点」指在画布上点击节点后面的「+」，选择节点类型。
2. 「绑定：`节点名.输出名`」指在参数输入框中从变量选择器里点选该上游输出，不要手工输入变量名。
3. 「固定：xxx」指直接在参数框中输入该固定值。
4. 所有「查询 / 创建 / 更新多维表格记录」节点统一先填：
   - Base App Token 固定：`WHaibyXvuaXuJpsDraJcAAM9nIb`
   - 归档请求 Table ID 固定：`tblyUgvj29jAL275`
   - 群目录映射 Table ID 固定：`tblacRVYZZ4SJmWW`，View ID 固定：`vewPOqHrk9`

   后文只写用哪张表，不再重复这四项。
5. Base 字段一律从节点刷新后的字段列表中点选，不要手工输入字段名。
6. 所有「发送飞书卡片」节点：底部 HTTP 回调地址留空；接收类型选「群聊」。
7. 所有「条件分支」节点按「从上到下第一条命中」执行，分支顺序必须严格按步骤给出的顺序建立。
8. 「失败出口」指节点配置中的失败 / 异常分支。若当前界面的节点没有失败出口，就在该节点后面添加一个「条件分支」节点：该节点的错误输出「非空」走失败处理，否则走继续。
9. 条件里的布尔右值必须选布尔类型的 `true` / `false`，不要选成字符串。
10. 代码节点步骤会给出仓库文件链接。必须完整复制整个文件粘贴到代码编辑区，不要只复制 `main()`。
11. 技能 B 每次改动后，先「发布技能 B」，再点击卡片做联调测试。
12. 本文中的「路由」一律指「条件分支」节点，不是特殊节点。
13. 条件分支若使用 `{{ }}` 表达式写法：代码节点输出从 `.return` 下取；字符串常量必须加英文双引号，布尔 `true`/`false` 和数字不加。示例：`{{ B4_准备状态更新.return.next_step == "list_folder" }}`。
14. 绑定数字类字段（`selected_file_size`、`result_size`、`confirmed_at`、`completed_at` 等）时，该行的值类型选「数字」，且上游 Python 节点的输出声明里对应字段必须是 `integer/number`。运行输入里这些值必须是不带引号的数字（`0`），不能是字符串（`"0"`），否则报 `1254061 NumberFieldConvFail`。
15. 条件分支节点的「默认 / 否则」分支一律接「结束」（可在结束前挂一个发送消息），不要接业务节点。
16. URL 字段（`current_folder_url`、`target_folder_url`、`result_file_url`、`root_folder_url_snapshot`）绑定时，该行的值类型选「对象」，绑定上游的 `*_url_object` 输出。线上已验证的提交格式只含两个键：`{"link": "https://...", "text": "目录名"}`，不要加 `type` 等其他键；绑成字符串会报 `1254068 URLFieldConvFail`。

### 11.4 添加 B3 校验结果分支

1. 在 B2 节点后面添加一个「条件分支」节点，节点名填：`B3_校验结果分支`。
2. 打开 B3 节点，建立第 1 个分支，分支名填：`已过期`。按下表建 2 个条件，条件之间选「且 / AND」：

   | 序号 | 左值 | 运算符 | 右值 |
   |---|---|---|---|
   | 1 | 绑定：`B2.ok` | 等于 | 布尔 `false` |
   | 2 | 绑定：`B2.error_code` | 等于 | 固定：`REQUEST_EXPIRED` |

3. 建立第 2 个分支，分支名填：`其他失败`。按下表建 2 个条件，条件之间选「且 / AND」：

   | 序号 | 左值 | 运算符 | 右值 |
   |---|---|---|---|
   | 1 | 绑定：`B2.ok` | 等于 | 布尔 `false` |
   | 2 | 绑定：`B2.error_code` | 不等于 | 固定：`REQUEST_EXPIRED` |

4. 建立第 3 个分支，分支名填：`校验成功`。按下表建 1 个条件：

   | 左值 | 运算符 | 右值 |
   |---|---|---|
   | 绑定：`B2.ok` | 等于 | 布尔 `true` |

5. 检查三个分支的顺序必须是：`已过期` → `其他失败` → `校验成功`。

### 11.5 搭建「已过期」分支

1. 在 `已过期` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`写入过期状态`。
2. `record_id` 绑定：`B2.request_record_id`。
3. 字段按下表设置：

   | Base 字段 | 值 |
   |---|---|
   | `status` | 固定：选单选值 `expired` |
   | `error_message` | 绑定：`B2.error` |
   | `completed_at` | 绑定：`B0.1_当前时间.now_ms` |

4. 在 `写入过期状态` 后面添加「发送消息」节点，消息内容绑定：`B2.error`。
5. 在「发送消息」节点后面添加「结束」节点。

### 11.6 搭建「其他失败」分支

1. 在 `其他失败` 分支后面添加「发送消息」节点，消息内容绑定：`B2.error`。
2. 在「发送消息」节点后面添加「结束」节点。
3. 该分支不要添加任何「更新多维表格记录」节点。

### 11.7 添加 B3.1 上传动作分流

B3.1 只负责把 `confirm_upload` 和其他 6 个 action 分开；6 个非上传 action 的细分由 B4 代码和 B4.3 完成，不在这里逐个分支。这样无论平台是否允许多条分支线汇入同一个节点，都不受影响。

1. 在 `校验成功` 分支后面添加一个「条件分支」节点，节点名填：`B3.1_上传动作分流`。
2. 建立第 1 个分支，分支名填：`确认上传`。条件：左值绑定 `B2.action`，运算符「等于」，右值固定 `confirm_upload`。

   若你的界面是表达式模式，条件写作：`{{ B2.return.action == "confirm_upload" }}`（`B2` 换成画布上的实际节点名；字符串常量必须加英文双引号）。

3. 建立第 2 个分支（默认 / 否则分支），分支名填：`其他动作`。
4. `确认上传` 分支的线暂时悬空（或临时接一个「结束」节点占位），第 15 步把 B12 接到这里。
5. `其他动作` 分支接第 12 步的 B4。

---

## 第 12 步：添加 B4 状态转换代码

### 12.1 添加 B4 代码节点

1. 添加一个 Python 代码节点，节点名填：`B4_准备状态更新`。
2. 完整复制 [b3_prepare_action.py](./aily_nodes/b3_prepare_action.py) 的全部内容，粘贴到代码编辑区。
3. 输入参数按下表绑定：

   | `main()` 参数 | 绑定 |
   |---|---|
   | `action` | `B2.action` |
   | `request_json` | `B2.request_json` |
   | `selected_candidate_json` | `B2.selected_candidate_json` |
   | `selected_folder_json` | `B2.selected_folder_json` |
   | `now_ms` | `B0.1_当前时间.now_ms` |

4. 先调试一次该节点，让 Aily 自动识别返回字段。
5. 把 B3.1 的 `其他动作` 分支连接到 B4 节点。
6. B4 代码内部按 action 处理 6 个非上传动作；`confirm_upload` 已被 B3.1 分流，不会到达 B4。即使误到 B4，代码也会返回 `INVALID_ACTION` 并在 B4.1 失败分支暴露，不会错误执行。

### 12.2 添加 B4.1 结果分支

1. 在 B4 后面添加「条件分支」节点，节点名填：`B4.1_B4结果分支`。
2. 建立第 1 个分支，分支名填：`B4失败`。条件：左值绑定 `B4.ok`，运算符「等于」，右值布尔 `false`。
3. 建立第 2 个分支，分支名填：`B4成功`。条件：左值绑定 `B4.ok`，运算符「等于」，右值布尔 `true`。
4. 在 `B4失败` 分支后面添加「发送消息」节点，内容绑定：`B4.error`。
5. 在「发送消息」节点后面添加「结束」节点。该分支不要添加更新节点。
6. `B4成功` 分支接 12.3。

### 12.3 添加 B4.2 next_step 分支

1. 在 `B4成功` 分支后面添加「条件分支」节点，节点名填：`B4.2_next_step分支`。
2. 按下表建立 3 个分支。每个分支的条件都是：左值绑定 `B4.next_step`，运算符「等于」，右值固定为表中的字符串：

   | 分支名 | 右值（固定字符串） | 后续接到哪里 |
   |---|---|---|
   | `显示目录卡片` | `list_folder` | 第 13 步 B4.3 |
   | `发最终确认` | `send_confirm_card` | 第 14.1 步 B10 |
   | `取消结束` | `end` | 第 14.3 步取消落库 |

3. 3 条分支线暂时悬空，第 13、14 步分别连接。

---

## 第 13 步：搭建目录选择相关分支

### 13.1 添加 B4.3 目录动作分支

1. 在 B4.2 的 `显示目录卡片` 分支后面添加「条件分支」节点，节点名填：`B4.3_目录动作分支`。
2. 按下表建立 4 个分支。每个分支的条件都是：左值绑定 `B2.action`，运算符「等于」，右值固定为表中的字符串：

   | 分支名 | 右值（固定字符串） | 后续接到哪里 |
   |---|---|---|
   | `确认文件` | `choose_file` | 13.2 |
   | `进入子目录` | `browse` | 13.3 |
   | `返回上级` | `back` | 13.4 |
   | `返回选目录` | `return_folder` | 13.5 |

### 13.2 「确认文件」分支：B5_choose_file_保存文件

1. 在 `确认文件` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B5_choose_file_保存文件`。
2. `record_id` 绑定：`B2.request_record_id`。
3. 字段按下表设置（全部绑定 B4 输出）：

   | Base 字段 | 绑定 |
   |---|---|
   | `source_message_id` | `B4.source_message_id` |
   | `source_type` | `B4.source_type` |
   | `selected_file_id` | `B4.selected_file_id` |
   | `selected_file_key` | `B4.selected_file_key` |
   | `selected_file_name` | `B4.selected_file_name` |
   | `selected_file_type` | `B4.selected_file_type` |
   | `selected_file_size` | `B4.selected_file_size` |
   | `status` | `B4.status`（运行时应为 `selecting_folder`） |

4. 该更新节点的失败出口：添加「发送消息」节点，内容绑定该更新节点的错误输出，后面接「结束」节点。
5. 该更新节点的成功出口：接 13.6 的 B6（先悬空，13.6 建好后连接）。

### 13.3 「进入子目录」分支：B5_browse_保存当前目录

1. 在 `进入子目录` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B5_browse_保存当前目录`。
2. `record_id` 绑定：`B2.request_record_id`。
3. 字段按下表设置：

   | Base 字段 | 值 |
   |---|---|
   | `current_folder_token` | 绑定：`B4.current_folder_token` |
   | `current_folder_name` | 绑定：`B4.current_folder_name` |
   | `current_folder_url` | 绑定：`B4.current_folder_url_object`（object） |
   | `folder_path_json` | 绑定：`B4.folder_path_json` |
   | `allowed_child_folders_json` | 固定：`[]` |
   | `status` | 绑定：`B4.status` |

   注意：`current_folder_url` 是 Base URL 字段，必须绑定 object 输出 `B4.current_folder_url_object`，不要绑定字符串 `B4.current_folder_url`。

4. 该更新节点的失败出口：添加「发送消息」节点，内容绑定该更新节点的错误输出，后面接「结束」节点。
5. 该更新节点的成功出口：接 13.6 的 B6。

### 13.4 「返回上级」分支：B5_back_保存上级目录

1. 复制 13.3 的 `B5_browse_保存当前目录` 节点，粘贴到 `返回上级` 分支后面，节点名改为：`B5_back_保存上级目录`。
2. 字段绑定与 13.3 完全相同，不要改动。
3. 失败出口和成功出口的接法与 13.3 相同。

### 13.5 「返回选目录」分支：B5_return_folder_清空目标目录

1. 在 `返回选目录` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B5_return_folder_清空目标目录`。
2. `record_id` 绑定：`B2.request_record_id`。
3. 字段按下表设置：

   | Base 字段 | 值 |
   |---|---|
   | `status` | 绑定：`B4.status`（运行时应为 `selecting_folder`） |
   | `target_folder_token` | 添加该字段，值留空（不绑定任何变量） |
   | `target_folder_name` | 添加该字段，值留空（不绑定任何变量） |

4. `target_folder_url` 是 URL 字段，不能写空字符串。如果更新节点支持提交 `null`，把该字段设为 `null`；如果不支持，本分支不要添加该字段（后续再次选择目录时会覆盖它）。
5. 该更新节点的失败出口：添加「发送消息」节点，内容绑定该更新节点的错误输出，后面接「结束」节点。
6. 该更新节点的成功出口：接 13.6 的 B6。

### 13.6 B6 读取当前目录清单

1. 添加「获取文件夹下的清单」节点，节点名填：`B6_读取当前目录清单`。
2. `folder_token` 绑定：`B4.current_folder_token`。
3. 把 13.2–13.5 四个更新节点的成功出口全部连接到 B6。如果平台不允许多条线汇入同一个节点，就复制 4 套 13.6–13.9 的节点，每个分支一套，参数完全相同。
4. B6 的失败出口：添加「更新多维表格记录」节点（归档请求表），节点名填：`B6失败_写入failed`。`record_id` 绑定 `B2.request_record_id`；`status` 固定选 `failed`；`error_message` 绑定 B6 的错误输出；`completed_at` 绑定 `B0.1_当前时间.now_ms`。
5. 在 `B6失败_写入failed` 后面添加「发送消息」节点，内容绑定 B6 的错误输出，后面接「结束」节点。

### 13.7 B7 组装目录卡片

1. 在 B6 的成功出口后面添加 Python 代码节点，节点名填：`B7_组装目录卡片`。
2. 完整复制 [b_build_folder_card.py](./aily_nodes/b_build_folder_card.py) 的全部内容，粘贴到代码编辑区。
3. 输入参数按下表绑定：

   | `main()` 参数 | 绑定 |
   |---|---|
   | `folder_list_result` | `B6_读取当前目录清单` 完整输出 |
   | `request_id` | `B2.request_id` |
   | `selected_file_name` | `B4.selected_file_name` |
   | `current_folder_token` | `B4.current_folder_token` |
   | `current_folder_name` | `B4.current_folder_name` |
   | `current_folder_url` | `B4.current_folder_url`（字符串） |
   | `folder_path_json` | `B4.folder_path_json` |
   | `requester_id` | `B2.requester_id` |
   | `warning` | `B4.warning_message` |
   | `callback_skill_id` | 固定：第 3 步记录的技能 B ID（`skill_xxx`） |

4. 先调试一次该节点，让 Aily 自动识别返回字段。
5. 在 B7 后面添加「条件分支」节点，节点名填：`B7.1_B7结果分支`。
6. 建立第 1 个分支，分支名填：`B7失败`。条件：左值绑定 `B7.ok`，运算符「等于」，右值布尔 `false`。
7. 建立第 2 个分支，分支名填：`B7成功`。条件：左值绑定 `B7.ok`，运算符「等于」，右值布尔 `true`。
8. 在 `B7失败` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B7失败_写入failed`。`record_id` 绑定 `B2.request_record_id`；`status` 固定选 `failed`；`error_message` 绑定 `B7.error`；`completed_at` 绑定 `B0.1_当前时间.now_ms`。
9. 在 `B7失败_写入failed` 后面添加「发送消息」节点，内容绑定 `B7.error`，后面接「结束」节点。

### 13.8 B8 保存子目录白名单

1. 在 `B7成功` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B8_保存子目录白名单`。
2. `record_id` 绑定：`B2.request_record_id`。
3. 字段只设置一项：`allowed_child_folders_json` 绑定 `B7.allowed_child_folders_json`。
4. B8 的失败出口：添加「更新多维表格记录」节点（归档请求表），节点名填：`B8失败_写入failed`。`record_id` 绑定 `B2.request_record_id`；`status` 固定选 `failed`；`error_message` 绑定 B8 的错误输出；`completed_at` 绑定 `B0.1_当前时间.now_ms`。
5. 在 `B8失败_写入failed` 后面添加「发送消息」节点，内容绑定 B8 的错误输出，后面接「结束」节点。
6. 顺序检查：必须先保存白名单（B8），再发卡片 2（13.9），不能调换。

### 13.9 B9 发送卡片 2

1. 在 B8 的成功出口后面添加「发送飞书卡片」节点，节点名填：`B9_发送目录卡片`，卡片模板选：`归档-选择目录-V2`。
2. 卡片变量按下表绑定（全部绑定 B7 同名输出）：

   | 卡片变量 | 绑定 |
   |---|---|
   | `selected_file_name` | `B7.selected_file_name` |
   | `breadcrumb` | `B7.breadcrumb` |
   | `current_folder_url` | `B7.current_folder_url` |
   | `warning` | `B7.warning` |
   | `initiator` | `B7.initiator` |
   | `folder_options` | `B7.folder_options` |
   | `disable_folder_browse` | `B7.disable_folder_browse` |
   | `disable_back` | `B7.disable_back` |
   | `skill_object_browse` | `B7.skill_object_browse` |
   | `skill_object_back` | `B7.skill_object_back` |
   | `skill_object_choose_current` | `B7.skill_object_choose_current` |
   | `skill_object_cancel` | `B7.skill_object_cancel` |

3. 接收会话：接收类型选「群聊」，`chat_id` 绑定：`B2.chat_id`。
4. B9 的失败出口：添加「更新多维表格记录」节点（归档请求表），节点名填：`B9失败_写入failed`。`record_id` 绑定 `B2.request_record_id`；`status` 固定选 `failed`；`error_message` 绑定 B9 的错误输出；`completed_at` 绑定 `B0.1_当前时间.now_ms`。后面接「结束」节点。
5. B9 的成功出口接「结束」节点。

### 13.10 联调检查点：卡片 2

1. 发布技能 B。
2. 在测试群回复一条文件消息，@机器人发送「归档」，点击卡片 1 的「确认归档这个文件」。
3. 打开 Base 归档请求表，核对该请求：`status` = `selecting_folder`；`selected_file_*` 已写入；`allowed_child_folders_json` 已写入当前目录的子目录清单。
4. 核对群里收到卡片 2：显示文件名、面包屑和目录下拉框。
5. 在卡片 2 选择一个子目录，点击「进入选中的文件夹」，核对 Base 的 `current_folder_*` 和 `folder_path_json` 变成该子目录。
6. 任一项不符合，先按 [AGENT_HANDOFF.md](./AGENT_HANDOFF.md) 第 10 节的日志排查顺序检查，再继续第 14 步。

---

## 第 14 步：搭建最终确认和取消

### 14.1 B10 保存目标目录

1. 在 B4.2 的 `发最终确认` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B10_保存目标目录`。
2. `record_id` 绑定：`B2.request_record_id`。
3. 字段按下表设置：

   | Base 字段 | 值 |
   |---|---|
   | `target_folder_token` | 绑定：`B4.target_folder_token` |
   | `target_folder_name` | 绑定：`B4.target_folder_name` |
   | `target_folder_url` | 绑定：`B4.target_folder_url_object`（object） |
   | `status` | 绑定：`B4.status`（运行时应为 `waiting_confirm`） |

   注意：`target_folder_url` 是 Base URL 字段，必须绑定 object 输出 `B4.target_folder_url_object`，不要绑定字符串 `B4.target_folder_url`。

4. B10 的失败出口：添加「发送消息」节点，内容绑定 B10 的错误输出，后面接「结束」节点。该出口不要添加更新节点。

### 14.2 B11 组装并发送卡片 3

1. 在 B10 的成功出口后面添加 Python 代码节点，节点名填：`B11_组装最终确认卡片`。
2. 完整复制 [b_build_confirm_card.py](./aily_nodes/b_build_confirm_card.py) 的全部内容，粘贴到代码编辑区。
3. 输入参数按下表绑定：

   | `main()` 参数 | 绑定 |
   |---|---|
   | `request_id` | `B2.request_id` |
   | `callback_skill_id` | 固定：第 3 步记录的技能 B ID（`skill_xxx`） |
   | `requester_id` | `B2.requester_id` |
   | `selected_file_name` | `B4.selected_file_name` |
   | `selected_file_type` | `B4.selected_file_type` |
   | `target_folder_path` | `B4.target_folder_path` |
   | `target_folder_url` | `B4.target_folder_url`（字符串，卡片展示用） |
   | `warning` | `B4.warning_message` |

4. 先调试一次该节点，让 Aily 自动识别返回字段。
5. 在 B11 后面添加「条件分支」节点，节点名填：`B11.1_B11结果分支`。
6. 建立第 1 个分支，分支名填：`B11失败`。条件：左值绑定 `B11.ok`，运算符「等于」，右值布尔 `false`。
7. 建立第 2 个分支，分支名填：`B11成功`。条件：左值绑定 `B11.ok`，运算符「等于」，右值布尔 `true`。
8. 在 `B11失败` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B11失败_写入failed`。`record_id` 绑定 `B2.request_record_id`；`status` 固定选 `failed`；`error_message` 绑定 `B11.error`；`completed_at` 绑定 `B0.1_当前时间.now_ms`。
9. 在 `B11失败_写入failed` 后面添加「发送消息」节点，内容绑定 `B11.error`，后面接「结束」节点。
10. 在 `B11成功` 分支后面添加「发送飞书卡片」节点，节点名填：`发送卡片3_最终确认`，卡片模板选：`归档-最终确认-V2`。
11. 卡片变量按下表绑定（全部绑定 B11 同名输出）：

    | 卡片变量 | 绑定 |
    |---|---|
    | `request_id_text` | `B11.request_id_text` |
    | `selected_file_name` | `B11.selected_file_name` |
    | `selected_file_type` | `B11.selected_file_type` |
    | `target_folder_path` | `B11.target_folder_path` |
    | `target_folder_url` | `B11.target_folder_url` |
    | `warning` | `B11.warning` |
    | `initiator` | `B11.initiator` |
    | `skill_object_confirm` | `B11.skill_object_confirm` |
    | `skill_object_return` | `B11.skill_object_return` |
    | `skill_object_cancel` | `B11.skill_object_cancel` |

12. 接收会话：接收类型选「群聊」，`chat_id` 绑定：`B2.chat_id`。
13. 该发送节点的失败出口：添加「更新多维表格记录」节点（归档请求表），节点名填：`卡片3失败_写入failed`。`record_id` 绑定 `B2.request_record_id`；`status` 固定选 `failed`；`error_message` 绑定该发送节点的错误输出；`completed_at` 绑定 `B0.1_当前时间.now_ms`。后面接「结束」节点。
14. 该发送节点的成功出口接「结束」节点。

### 14.3 cancel 落库

1. 在 B4.2 的 `取消结束` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B10_cancel_保存取消状态`。
2. `record_id` 绑定：`B2.request_record_id`。
3. 字段按下表设置：

   | Base 字段 | 值 |
   |---|---|
   | `status` | 绑定：`B4.status`（运行时应为 `cancelled`） |
   | `completed_at` | 绑定：`B4.completed_at_ms` |

4. 该更新节点的失败出口：添加「发送消息」节点，内容绑定该更新节点的错误输出，后面接「结束」节点。
5. 该更新节点的成功出口接「结束」节点。取消分支不发送任何新卡片，旧卡片会由按钮回调对象的 `update_card=true` 自动更新为「已取消本次归档」。

### 14.4 联调检查点：卡片 3 和取消

1. 发布技能 B。
2. 完整走一遍：回复文件消息 @机器人发「归档」→ 卡片 1 点「确认归档这个文件」→ 卡片 2 点「使用当前目录」。
3. 核对：群里收到卡片 3；Base 该请求 `status` = `waiting_confirm`，`target_folder_*` 已写入；此时云盘目录里不应出现文件。
4. 在卡片 3 点「返回重新选择」，核对：收到新的卡片 2；Base `status` 回到 `selecting_folder`，`target_folder_token` 已清空。
5. 重新走到卡片 3，点「取消」，核对：Base `status` = `cancelled`，`completed_at` 非空，旧卡片显示「已取消本次归档」。
6. 任一项不符合，先查日志，再继续第 15 步。

---

## 第 15 步：搭建 confirm_upload

本步从 B3.1 的 `确认上传` 分支开始搭建，这是唯一不经过 B4 的 action。15.1–15.10 先搭主链，失败出口全部暂时悬空；15.11 统一搭建失败处理段并接线。

> **版本说明（2026-08-07）**：v1 搭建精简主链：B12 → B13 → B14 → B15 → B18 → B19 → B20 → B21 → B22。**B15.5（计算文件大小）、B16（重查映射）、B17（上传策略校验，含 20 MB 上限）列为 v2 增补需求，v1 暂不搭建**；若上传节点要求填写文件大小，则保留 B15.5 一个节点。失败路径 v1 先用「更新 failed + 发送真实错误文本」，失败结果卡片（5 套）后补。16.3 的用例 10（文件大小）属于 v2 验收范围。

### 15.1 B12 锁定 processing

1. 在 B3.1 的 `确认上传` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B12_进入处理中`。
2. `record_id` 绑定：`B2.request_record_id`。
3. 字段按下表设置：

   | Base 字段 | 值 |
   |---|---|
   | `status` | 固定：选单选值 `processing` |
   | `confirmed_at` | 绑定：`B0.1_当前时间.now_ms` |
   | `error_message` | 添加该字段，值留空（清空旧错误） |

4. B12 的失败出口：添加「发送消息」节点，内容绑定 B12 的错误输出，后面接「结束」节点。该失败出口后面禁止连接任何下载节点。

### 15.2 B13 重查处理中请求

1. 在 B12 的成功出口后面添加「查询多维表格记录」节点（归档请求表），节点名填：`B13_重查处理中请求`。
2. `page_size` 固定：`2`。
3. 筛选条件：字段选 `request_id`，operator 选 `is`，`value` 绑定：`B0.2.request_id_filter_values`（整个数组，不要绑定数组第 0 项）。
4. B13 的失败出口：添加「更新多维表格记录」节点（归档请求表），节点名填：`B13失败_写入failed`。`record_id` 绑定 `B2.request_record_id`；`status` 固定选 `failed`；`error_message` 绑定 B13 的错误输出；`completed_at` 绑定 `B0.1_当前时间.now_ms`。
5. 在 `B13失败_写入failed` 后面添加「发送消息」节点，内容绑定 B13 的错误输出，后面接「结束」节点。

### 15.3 B14 校验处理中请求

1. 在 B13 的成功出口后面添加 Python 代码节点，节点名填：`B14_校验处理中请求`。
2. 完整复制 [b5_validate_processing_request.py](./aily_nodes/b5_validate_processing_request.py) 的全部内容，粘贴到代码编辑区。
3. 输入参数按下表绑定：

   | `main()` 参数 | 绑定 |
   |---|---|
   | `request_result` | `B13_重查处理中请求` 完整输出 |
   | `request_id` | 开始节点 `request_id` |

4. 先调试一次该节点，让 Aily 自动识别返回字段。
5. 在 B14 后面添加「条件分支」节点，节点名填：`B14.1_上传前校验分支`。
6. 按下面的顺序建立 3 个分支：

   | 顺序 | 分支名 | 条件 |
   |---|---|---|
   | 1 | `校验失败` | 左值绑定 `B14.ok`，等于，布尔 `false` |
   | 2 | `已经处理` | 左值绑定 `B14.ok`，等于，布尔 `true`；且左值绑定 `B14.should_upload`，等于，布尔 `false` |
   | 3 | `可以上传` | 左值绑定 `B14.ok`，等于，布尔 `true`；且左值绑定 `B14.should_upload`，等于，布尔 `true` |

7. 在 `已经处理` 分支后面直接添加「结束」节点。
8. 在 `校验失败` 分支后面添加「条件分支」节点，节点名填：`B14.2_安全落库判断`。
9. 在 B14.2 建立第 1 个分支，分支名填：`可以落库`。按下表建 2 个条件，条件之间选「且 / AND」：

    | 序号 | 左值 | 运算符 | 右值 |
    |---|---|---|---|
    | 1 | 绑定：`B14.request_record_id` | 非空 | 无 |
    | 2 | 绑定：`B14.status` | 等于 | 固定：`processing` |

10. 在 `可以落库` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B14失败_写入failed`。`record_id` 绑定 `B14.request_record_id`；`status` 固定选 `failed`；`error_message` 绑定 `B14.error`；`completed_at` 绑定 `B0.1_当前时间.now_ms`。
11. 在 `B14失败_写入failed` 后面添加「发送消息」节点，内容绑定 `B14.error`，后面接「结束」节点。
12. 在 B14.2 建立第 2 个分支（否则分支），分支名填：`只发错误`。在该分支后面添加「发送消息」节点，内容绑定 `B14.error`，后面接「结束」节点。
13. `可以上传` 分支接 15.4。

### 15.4 B15 下载并上传文件（Python 单节点）

当前租户官方连接器没有「下载消息附件」「上传文件」操作，自定义连接器编辑器又不支持 multipart 文件字段，因此 v1 把下载和上传合并为一个 Python 节点（2026-08-07 起，替代原连接器 B15 和第 15.7 节的 B18）。

1. 在 `可以上传` 分支后面添加 Python 代码节点，节点名填：`B15_下载并上传文件`。
2. 完整复制 [b9_download_and_upload.py](./aily_nodes/b9_download_and_upload.py) 的全部内容，粘贴到代码编辑区。
3. 在代码顶部的 `APP_ID`、`APP_SECRET` 两个常量中填入机器人应用的凭证（2026-08-07 用户确认接受凭证写在画布代码里；**只在画布填，仓库文件保持为空，不要把真实值提交到仓库**）。
4. 输入参数按下表绑定：

   | `main()` 参数 | 绑定 |
   |---|---|
   | `message_id` | `B14.source_message_id` |
   | `file_key` | `B14.selected_file_key` |
   | `file_name` | `B14.selected_file_name` |
   | `parent_node` | `B14.target_folder_token` |
   | `app_id` / `app_secret` | 留空（使用代码内常量） |

5. 先调试一次该节点。成功输出：`ok = true`、`file_token` 非空、`file_url` 已拼接完成、`actual_size` 为真实字节数。该节点内置空文件校验和大小限制（≤20 MB 普通上传，>20 MB 自动分片上传，硬上限 100 MB（飞书消息资源下载接口限制，错误码 234037）），若报 `TOKEN_FAILED` 且是网络错误，说明代码节点不能联网，停止施工并排查。
6. B15 的失败出口暂时悬空，15.11 统一处理。成功出口接 15.8 的 B19。

### 15.5 B16 重查群映射（v2 增补，v1 跳过）

1. 在 B15 的成功出口后面添加「查询多维表格记录」节点（群目录映射表，填 View ID），节点名填：`B16_重查群映射`。
2. `page_size` 固定：`2`。
3. 筛选条件：字段选 `chat_id`，operator 选 `is`，`value` 绑定：`B14.chat_id_filter_values`（整个数组，运行输入必须是 `"value":["oc_xxx"]`，不能是 `"value":"oc_xxx"`）。
4. B16 的失败出口暂时悬空，15.11 统一处理。

### 15.6 B17 校验上传策略（v2 增补，v1 跳过）

1. 在 B16 的成功出口后面添加 Python 代码节点，节点名填：`B17_校验上传策略`。
2. 完整复制 [b6_validate_upload_policy.py](./aily_nodes/b6_validate_upload_policy.py) 的全部内容，粘贴到代码编辑区。
3. 输入参数按下表绑定：

   | `main()` 参数 | 绑定 |
   |---|---|
   | `mapping_result` | `B16_重查群映射` 完整输出 |
   | `chat_id` | `B14.chat_id` |
   | `selected_file_type` | `B14.selected_file_type` |
   | `actual_size` | `B15.5_计算文件大小.actual_size` |

4. 先调试一次该节点，让 Aily 自动识别返回字段。
5. 在 B17 后面添加「条件分支」节点，节点名填：`B17.1_B17结果分支`。
6. 建立第 1 个分支，分支名填：`B17失败`。条件：左值绑定 `B17.ok`，运算符「等于」，右值布尔 `false`。
7. 建立第 2 个分支，分支名填：`B17成功`。条件：左值绑定 `B17.ok`，运算符「等于」，右值布尔 `true`。
8. `B17失败` 分支暂时悬空，15.11 统一处理。`B17成功` 分支接 15.7。

### 15.7 B18 上传文件（已并入 B15，无需搭建）

v1 的下载和上传由 `B15_下载并上传文件`（b9_download_and_upload.py）一个节点完成，没有独立的 B18 节点。B15 的成功出口直接接 15.8 的 B19。

### 15.8 B19 转换结果链接

1. 在 B15 的成功出口后面添加 Python 代码节点，节点名填：`B19_转换结果链接`。
2. 完整复制 [common_build_url_object.py](./aily_nodes/common_build_url_object.py) 的全部内容，粘贴到代码编辑区。
3. 输入参数按下表绑定：

   | `main()` 参数 | 绑定 |
   |---|---|
   | `url` | `B15_下载并上传文件.file_url` |
   | `text` | `B14.selected_file_name` |

4. 先调试一次该节点，让 Aily 自动识别返回字段。
5. 在 B19 后面添加「条件分支」节点，节点名填：`B19.1_B19结果分支`。
6. 建立第 1 个分支，分支名填：`B19失败`。条件：左值绑定 `B19.ok`，运算符「等于」，右值布尔 `false`。
7. 建立第 2 个分支，分支名填：`B19成功`。条件：左值绑定 `B19.ok`，运算符「等于」，右值布尔 `true`。
8. `B19失败` 分支暂时悬空，15.11 统一处理。`B19成功` 分支接 15.9。

### 15.9 B20 写回归档成功

1. 在 `B19成功` 分支后面添加「更新多维表格记录」节点（归档请求表），节点名填：`B20_写回归档成功`。
2. `record_id` 绑定：`B14.request_record_id`。
3. 字段按下表设置：

   | Base 字段 | 值 |
   |---|---|
   | `status` | 固定：选单选值 `success` |
   | `result_file_token` | 绑定：`B15_下载并上传文件.file_token` |
   | `result_file_url` | 绑定：`B19.url_object`（object，不是字符串 `B19.url`） |
   | `result_size` | 绑定：`B15_下载并上传文件.actual_size` |
   | `error_message` | 添加该字段，值留空 |
   | `completed_at` | 绑定：`B0.1_当前时间.now_ms` |

4. B20 的失败出口：添加「发送消息」节点，节点名填：`发送人工补记告警`。消息内容输入以下文本，并用变量选择器把三处值插进去：

   ```text
   文件已上传但归档结果写回 Base 失败，请管理员人工补记。
   请求：{{B14.request_id}}；文件 token：{{B18 上传结果文件 token}}；链接：{{B19.url}}。
   ```

5. 在 `发送人工补记告警` 后面添加「结束」节点。该失败出口不要发送成功结果卡片，不要再改 Base 状态。

### 15.10 B21/B22 组装并发送成功结果卡片

1. 在 B20 的成功出口后面添加 Python 代码节点，节点名填：`B21_组装成功结果卡片`。
2. 完整复制 [b_build_result_card.py](./aily_nodes/b_build_result_card.py) 的全部内容，粘贴到代码编辑区。
3. 输入参数按下表绑定：

   | `main()` 参数 | 值 |
   |---|---|
   | `status` | 固定：`success` |
   | `request_id` | 绑定：`B14.request_id` |
   | `requester_id` | 绑定：`B2.requester_id` |
   | `selected_file_name` | 绑定：`B14.selected_file_name` |
   | `selected_file_type` | 绑定：`B14.selected_file_type` |
   | `target_folder_name` | 绑定：`B14.target_folder_name` |
   | `target_folder_path` | 绑定：`B14.target_folder_path` |
   | `target_folder_url` | 绑定：`B14.target_folder_url` |
   | `result_file_url` | 绑定：`B19.url`（字符串） |
   | `result_size` | 绑定：`B15_下载并上传文件.actual_size` |
   | `completed_at` | 绑定：`B0.1_当前时间.now_ms` |
   | `error_message` | 留空 |

4. 先调试一次该节点，让 Aily 自动识别返回字段。
5. 在 B21 后面添加「发送飞书卡片」节点，节点名填：`B22_发送成功结果卡片`，卡片模板选：`归档-结果-V2`。
6. 卡片 14 个变量全部绑定 B21 的同名输出：`is_success`、`result_title`、`result_summary`、`request_id_text`、`selected_file_name`、`selected_file_type`、`target_folder_name`、`target_folder_path`、`target_folder_url`、`result_file_url`、`result_size_text`、`completed_at_text`、`error_message`、`initiator`。
7. 接收会话：接收类型选「群聊」，`chat_id` 绑定：`B14.chat_id`。
8. B22 的失败出口直接接「结束」节点（Base 已写入终态，不再改单）。B22 的成功出口也接「结束」节点。

### 15.11 搭建失败处理（v1 精简版）

v1 只剩两个失败出口要处理：B15（下载并上传）和 B19.1 的 `B19失败` 分支。每个失败出口各接三个节点：

1. 添加「更新多维表格记录」节点（归档请求表），节点名填：`B15失败_写入failed` / `B19失败_写入failed`。`record_id` 绑定 `B14.request_record_id`；`status` 固定选 `failed`；`error_message` 绑定该节点的真实错误（`B15.error` 或 `B19.error`）；`completed_at` 绑定 `B0.1_当前时间.now_ms`（数字类型）。
2. 后面添加「发送消息」节点，内容绑定同一个错误输出。
3. 后面添加「结束」节点。

失败结果卡片（卡片 4 的失败版本）列为 v2 增补，v1 不做。

### 15.12 联调检查点：真实上传

1. 发布技能 B。
2. 完整走一遍：回复文件消息 @机器人发「归档」→ 卡片 1 确认 → 卡片 2 选目录 → 卡片 3 点「确认上传」。
3. 核对 Base 该请求：`status` = `success`；`result_file_token`、`result_file_url`、`result_size`、`completed_at` 非空。
4. 核对云盘目标目录里真实出现了该文件。
5. 核对群里收到卡片 4，显示「归档成功」和文件链接。
6. 上传失败时核对：Base 写入 `failed` 和真实错误，群里收到卡片 4 显示「归档失败」和失败原因。

---

## 第 16 步：核对、发布和验收

### 16.1 逐项核对失败连线

只核对，不新增节点。逐条对照画布打勾：

- [ ] B3 的 `已过期` 分支：写入 `expired` + `B2.error` + `completed_at`，然后发送 `B2.error` 并结束。
- [ ] B3 的 `其他失败` 分支：只有发送 `B2.error` 和结束，没有任何更新节点。
- [ ] B4.1 的 `B4失败` 分支：只有发送 `B4.error` 和结束，没有更新节点。
- [ ] B6、B7、B8、B9 失败：各自写入 `failed` + 该节点真实错误 + `completed_at`，不继续发卡片 2。
- [ ] B10 失败：只发送 B10 的真实错误，没有更新节点。
- [ ] B11 失败、`发送卡片3_最终确认` 失败：各自写入 `failed` + 真实错误 + `completed_at`。
- [ ] B12 失败：只发送 B12 的真实错误，失败出口后面没有任何下载节点。
- [ ] B13、B14 失败：按 15.2 / 15.3 落库或发错误。
- [ ] B15–B19 的 5 套失败段：`error_message` 分别绑定各自节点的真实错误。
- [ ] B20 失败：只发人工补记告警，不发成功结果卡片。
- [ ] 所有发送卡片 4 的节点失败：直接结束，不再改 Base。
- [ ] 全文检查所有「发送消息」和 `error_message` 绑定：没有任何一处把错误写死成「当前群没有找到归档目录映射」。

### 16.2 发布

1. 发布技能 B。
2. 确认技能 B 的 skill_id 与第 3 步记录的 `CALLBACK_SKILL_ID` 相同。如果变了，更新三处 `callback_skill_id`：技能 A 的 A8 输入、B7 输入、B11 输入。
3. 发布四张卡片。
4. 逐个打开以下「发送飞书卡片」节点，点击「更新 / 刷新模板」：技能 A 的 A10、B9、`发送卡片3_最终确认`、B22、5 套失败段的发送结果卡片节点。
5. 发布技能 A。
6. 发布整个 Aily 应用。

### 16.3 按顺序验收

#### 用例 1：不回复文件

```text
直接 @机器人 归档
```

预期：

```text
提示必须回复文件消息
不创建请求
```

#### 用例 2：文件类型不允许

临时从映射中移除 `md`，回复 `.md` 文件。

预期：

```text
FILE_TYPE_NOT_ALLOWED
不显示“没有映射”
```

测试后把 `md` 加回。

#### 用例 3：单文件确认

预期：

```text
创建 selecting_file 请求
selected_file_* 为空
发送卡片 1
```

#### 用例 4：技能 B 回调

点击确认文件。

预期：

```text
技能 B 收到 request_id/action/selected_file_id
点击人来自 message.sender.openID
请求变为 selecting_folder
发送卡片 2
```

#### 用例 5：目录边界

预期：

```text
卡片 2 只显示当前目录直属子文件夹
任意伪造 token 被 INVALID_FOLDER_SELECTION 拒绝
根目录不能再返回上一级
```

#### 用例 6：最终确认

点击“使用当前目录”。

预期：

```text
status = waiting_confirm
卡片 3 显示正确文件和目录
此时尚未上传
```

#### 用例 7：上传

点击“确认上传”。

预期：

```text
waiting_confirm → processing → success
文件出现在选定目录
Base 写入 result_file_token/result_file_url/result_size
卡片 4 显示成功
```

#### 用例 8：重复点击

先测试顺序重复点击，再测试快速重复点击。

预期：

```text
旧卡片被 update_card 更新
顺序到达的后续回调被状态校验拒绝
不会把已完成请求重新变回 waiting_confirm
```

快速并发点击只记录观察结果：当前纯 Base 方案不作为“绝不重复上传”的验收项。若实际业务必须满足该指标，先接入原子锁/幂等服务，再验收并发场景。

#### 用例 9：取消

分别从卡片 1、2、3 点击取消。

预期：

```text
status = cancelled
completed_at 非空
不能继续操作旧卡片
```

#### 用例 10：文件大小（v2 验收项，v1 跳过）

测试空文件、20 MB 内文件、超过 20 MB 文件。

预期：

```text
空文件失败
20 MB 内成功
超过限制不调用上传
```

全部通过后，应用搭建完成。

---

## 最终节点清单

### 技能 A

```text
A0 开始
A0.1 Python：common_now_ms.py
A1 归档指令条件
A2 获取触发消息
A2.1 Python：a2_normalize_trigger_message.py
A2.2 ok / parent_id 条件
A3 获取被回复消息
A4 查询群目录映射
A5 Python：a7_build_archive_request.py
A6 ok 条件
A7 创建归档请求
A8 Python：a9_build_file_confirm_card.py
A9 ok 条件
A10 发送卡片 1
```

### 技能 B

```text
B0 开始（4 个自定义参数）
B0.1 Python：common_now_ms.py
B0.2 Python：b0_prepare_request_filter.py
B0.3 条件分支：筛选参数成功 / 失败
B1 按 request_id 查询请求
B2 Python：b2_validate_callback.py
B3 条件分支：已过期 / 其他失败 / 校验成功
B3.1 条件分支：confirm_upload / 其他动作
B4 Python：b3_prepare_action.py
B4.1 条件分支：B4 成功 / 失败
B4.2 条件分支：list_folder / send_confirm_card / end
B4.3 条件分支：choose_file / browse / back / return_folder
B5_choose_file_保存文件（更新记录）
B5_browse_保存当前目录（更新记录）
B5_back_保存上级目录（更新记录）
B5_return_folder_清空目标目录（更新记录）
B6_读取当前目录清单
B7 Python：b_build_folder_card.py
B7.1 条件分支：B7 成功 / 失败
B8_保存子目录白名单（更新记录）
B9_发送目录卡片（卡片 2）
B10_保存目标目录（更新记录）
B11 Python：b_build_confirm_card.py
B11.1 条件分支：B11 成功 / 失败
发送卡片3_最终确认（卡片 3）
B10_cancel_保存取消状态（更新记录）
B12_进入处理中（更新记录）
B13_重查处理中请求
B14 Python：b5_validate_processing_request.py
B14.1 条件分支：校验失败 / 已经处理 / 可以上传
B14.2 条件分支：可以落库 / 只发错误
B15_下载并上传文件（Python：b9_download_and_upload.py）
B16_重查群映射（v2 增补）
B17 Python：b6_validate_upload_policy.py（v2 增补）
B17.1 条件分支（v2 增补）
B19 Python：common_build_url_object.py
B19.1 条件分支：B19 成功 / 失败
B20_写回归档成功（更新记录）
B21 Python：b_build_result_card.py（成功）
B22_发送成功结果卡片（卡片 4）
失败处理（更新 failed + 真实错误文本）：
  B6 / B7 / B8 / B9 / B11 / 卡片3发送 / B13 / B14 的失败分支
  B15 / B19 的失败分支（失败结果卡片为 v2 增补）
```

## 代码文件对应表

| 文件 | 粘贴到 |
|---|---|
| [common_now_ms.py](./aily_nodes/common_now_ms.py) | 技能 A/B：取得可信当前毫秒时间 |
| [a2_normalize_trigger_message.py](./aily_nodes/a2_normalize_trigger_message.py) | 技能 A：提取触发消息并生成 Base 查询所需的字符串数组 |
| [a7_build_archive_request.py](./aily_nodes/a7_build_archive_request.py) | 技能 A / A5：生成请求 |
| [a9_build_file_confirm_card.py](./aily_nodes/a9_build_file_confirm_card.py) | 技能 A / A8：卡片 1 |
| [b0_prepare_request_filter.py](./aily_nodes/b0_prepare_request_filter.py) | 技能 B：把开始节点的 request_id 字符串转换为 Base 筛选数组 |
| [b2_validate_callback.py](./aily_nodes/b2_validate_callback.py) | 技能 B：公共回调校验 |
| [b3_prepare_action.py](./aily_nodes/b3_prepare_action.py) | 技能 B / B4：六个非上传 action 状态转换 |
| [b5_validate_processing_request.py](./aily_nodes/b5_validate_processing_request.py) | 技能 B / B14：上传前重查并展开可信请求字段 |
| [b8_compute_actual_size.py](./aily_nodes/b8_compute_actual_size.py) | 技能 B / B15.5：计算下载内容的真实字节数（v2 用，v1 已并入 b9） |
| [b9_download_and_upload.py](./aily_nodes/b9_download_and_upload.py) | 技能 B / B15：下载消息资源并上传云盘（单节点；>20 MB 自动分片，硬上限 100 MB（飞书消息资源下载接口限制，错误码 234037）） |
| [b6_validate_upload_policy.py](./aily_nodes/b6_validate_upload_policy.py) | 技能 B / B17：校验最新群映射、文件类型和真实字节数 |
| [common_build_url_object.py](./aily_nodes/common_build_url_object.py) | 技能 B / B19：把 URL 字符串转换为 Base 超链接 object |
| [b_build_folder_card.py](./aily_nodes/b_build_folder_card.py) | 技能 B：卡片 2 |
| [b_build_confirm_card.py](./aily_nodes/b_build_confirm_card.py) | 技能 B：卡片 3 |
| [b_build_result_card.py](./aily_nodes/b_build_result_card.py) | 技能 B：卡片 4 |

不要再添加：

```text
智能体节点
大模型选择文件节点
读取最近 20/30 条群消息节点
单候选跳过确认分支
技能 A 在发送卡片后顺序调用工作流 B 的节点
自建 HTTP 卡片回调节点
```
