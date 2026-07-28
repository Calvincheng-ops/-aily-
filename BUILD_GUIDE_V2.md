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
| `max_file_size_mb` | 数字 | 当前流程只能填 `1..20` |
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

### 11.3 B3 添加“条件分支”节点，处理 B2 成功或失败

本文后面说的“路由”不是一个特殊节点，而是 Aily 的**条件分支节点**。它的作用只是根据某个变量的值，把连线分到不同出口。

在 B2 后添加一个“条件分支”节点，命名：

```text
B3_校验结果分支
```

按下面顺序建立三个出口。若界面提供“且/AND”，同一出口内的条件使用 AND。

#### 出口 1：`已过期`

```text
左值 1 = B2.ok
运算符 = 等于
右值 1 = false（布尔值，不是字符串）

AND

左值 2 = B2.error_code
运算符 = 等于
右值 2 = REQUEST_EXPIRED
```

连接到“更新多维表格记录”节点：

```text
record_id     = B2.request_record_id
status        = expired
error_message = B2.error
completed_at  = B0.1_当前时间.now_ms
```

更新成功后发送文本：

```text
{{B2.error}}
```

然后连接结束节点。

#### 出口 2：`其他失败`

```text
左值 1 = B2.ok
运算符 = 等于
右值 1 = false

AND

左值 2 = B2.error_code
运算符 = 不等于
右值 2 = REQUEST_EXPIRED
```

连接“发送消息”节点，内容绑定 `B2.error`，然后结束。不要在该分支更新请求状态，因为操作者错误、伪造 action 或旧卡片重复点击不应该覆盖原状态。

#### 出口 3：`校验成功`

```text
左值 = B2.ok
运算符 = 等于
右值 = true（布尔值）
```

连接下一节的 `B3.1_action分支`。

如果条件节点按“从上到下第一条命中”执行，务必保持顺序：

```text
已过期 → 其他失败 → 校验成功
```

B2 的作用只是校验，不更新 Base。它已经检查请求唯一、点击人、状态、有效期、根目录边界和卡片选项白名单。

### 11.4 B3.1 再添加一个“条件分支”节点，按 action 分流

在“校验成功”出口后再添加一个条件分支节点，命名：

```text
B3.1_action分支
```

建立七个出口。每个出口都使用：

```text
左值 = B2.action
运算符 = 等于
右值 = 下表固定字符串
```

| 出口名称 | 右值 | 接到哪里 |
|---|---|---|
| 确认文件 | `choose_file` | B4_准备状态更新 |
| 进入子目录 | `browse` | B4_准备状态更新 |
| 返回上级 | `back` | B4_准备状态更新 |
| 使用当前目录 | `choose_current_folder` | B4_准备状态更新 |
| 返回选目录 | `return_folder` | B4_准备状态更新 |
| 取消 | `cancel` | B4_准备状态更新 |
| 确认上传 | `confirm_upload` | 第 15 步上传分支，不经过 B4 |

如果 Aily 不允许六条出口汇入同一个 B4 节点，就复制六个相同的 B4 代码节点，分别命名为 `B4_choose_file`、`B4_browse` 等；每个节点的代码和输入完全相同。不要用智能体节点判断 action。

---

## 第 12 步：添加 B4 状态转换代码

新增一个 Python 代码节点，命名：

```text
B4_准备状态更新
```

复制完整文件：

[b3_prepare_action.py](./aily_nodes/b3_prepare_action.py)

该节点用于六个非上传 action：

```text
choose_file
browse
back
choose_current_folder
return_folder
cancel
```

输入绑定：

| 参数 | 值 |
|---|---|
| `action` | `B2.action` |
| `request_json` | `B2.request_json` |
| `selected_candidate_json` | `B2.selected_candidate_json` |
| `selected_folder_json` | `B2.selected_folder_json` |
| `now_ms` | `B0.1_当前时间.now_ms` |

六个非上传出口连接到 B4。B4 后添加“条件分支”节点，命名：

```text
B4.1_B4结果分支
```

两个出口：

```text
出口“成功”：B4.ok 等于 true
出口“失败”：B4.ok 等于 false
```

失败出口发送 `B4.error` 后结束。成功出口再添加一个条件分支节点：

```text
B4.2_next_step分支
```

按 `B4.next_step` 建立三个出口：

| 条件 | 含义 | 接到哪里 |
|---|---|---|
| `B4.next_step == list_folder` | 需要显示目录卡片 | 第 13 步目录处理 |
| `B4.next_step == send_confirm_card` | 已选择目标目录 | 第 14.1 步最终确认 |
| `B4.next_step == end` | 已取消 | 第 14.2 步取消落库 |

为什么还要看 `next_step`：`B2.action` 是用户点了什么，`B4.next_step` 是代码校验并转换状态后下一步真正要做什么。两者不要混用。

B4 会输出两套 URL：

```text
current_folder_url          字符串，只给卡片展示
current_folder_url_object   object，只写 Base URL 字段
target_folder_url           字符串，只给卡片展示
target_folder_url_object    object，只写 Base URL 字段
```

---

## 第 13 步：搭建目录选择相关分支

从 `B4.2_next_step分支` 的 `list_folder` 出口开始搭建。先添加一个条件分支节点：

```text
B4.3_目录动作分支
```

左值统一选择 `B2.action`，分别建立四个出口：

```text
choose_file
browse
back
return_folder
```

每个出口先更新同一条 Base 请求，之后再汇入 13.5 的公共目录段。

### 13.1 `choose_file` 出口：保存用户确认的文件

在 `B2.action == choose_file` 出口添加“更新多维表格记录”节点，命名：

```text
B5_choose_file_保存文件
```

参数：

```text
record_id = B2.request_record_id
```

字段：

| 字段 | B4 输出 |
|---|---|
| `source_message_id` | `source_message_id` |
| `source_type` | `source_type` |
| `selected_file_id` | `selected_file_id` |
| `selected_file_key` | `selected_file_key` |
| `selected_file_name` | `selected_file_name` |
| `selected_file_type` | `selected_file_type` |
| `selected_file_size` | `selected_file_size` |
| `status` | `status`，应为 `selecting_folder` |

此时才第一次写入 `selected_file_*`。

更新成功后连接 13.5。

### 13.2 `browse` 出口：进入用户选中的子目录

在 `B2.action == browse` 出口添加更新记录节点，命名：

```text
B5_browse_保存当前目录
```

参数：

```text
record_id = B2.request_record_id
```

| 字段 | B4 输出 |
|---|---|
| `current_folder_token` | `current_folder_token` |
| `current_folder_name` | `current_folder_name` |
| `current_folder_url` | `current_folder_url_object`，object |
| `folder_path_json` | `folder_path_json` |
| `allowed_child_folders_json` | 固定 `[]` |
| `status` | B4 `status` |

卡片展示使用字符串 `B4.current_folder_url`，只有 Base URL 字段使用 `current_folder_url_object`。

更新成功后连接 13.5。

### 13.3 `back` 出口：返回上一级目录

复制 `B5_browse_保存当前目录` 节点，命名：

```text
B5_back_保存上级目录
```

字段绑定完全相同。B4 已经从 `folder_path_json` 删除最后一级，并会在根目录阻止继续返回。更新成功后连接 13.5。

### 13.4 `return_folder` 出口：从最终确认返回目录选择

在 `B2.action == return_folder` 出口添加更新记录节点：

```text
record_id           = B2.request_record_id
status              = B4.status（selecting_folder）
target_folder_token = 空
target_folder_name  = 空
```

`target_folder_url` 是 URL 字段，不能写空字符串。若更新节点支持 `null`，将它设为 `null` 以清空；若不支持，本分支先不提交该 URL 字段，后续再次选择目录时会覆盖它。业务判断只以 `target_folder_token` 是否非空为准。

更新成功后连接 13.5。

### 13.5 公共“读取目录并发卡片 2”

把上面四个更新节点的成功出口连接到同一个公共段。若 Aily 不允许多条线汇入同一节点，就复制四套 13.5 节点；参数完全相同。

添加“获取文件夹下的清单”节点：

```text
B6_读取当前目录清单
folder_token = B4.current_folder_token
```

必须获取当前目录直属内容，不得使用个人云盘根目录。

添加 Python 节点，复制：

[b_build_folder_card.py](./aily_nodes/b_build_folder_card.py)

节点命名：

```text
B7_组装目录卡片
```

输入：

| 参数 | 值 |
|---|---|
| `folder_list_result` | 目录清单节点完整输出 |
| `request_id` | B2 `request_id` |
| `selected_file_name` | B4 `selected_file_name` |
| `current_folder_token` | B4 `current_folder_token` |
| `current_folder_name` | B4 `current_folder_name` |
| `current_folder_url` | B4 `current_folder_url` |
| `folder_path_json` | B4 `folder_path_json` |
| `requester_id` | B2 `requester_id` |
| `warning` | B4 `warning_message` |
| `callback_skill_id` | 固定 `skill_xxx` |

B7 后添加条件分支：

```text
B7.ok == false → 更新请求为 failed，写入 B7.error 和 completed_at
               → 发送 B7.error → 结束
B7.ok == true  → 保存目录白名单
```

“获取文件夹下的清单”节点失败时也执行同样的失败落库，`error_message`
必须绑定清单节点的真实错误。

成功出口添加更新记录节点：

```text
节点名 = B8_保存子目录白名单
record_id = B2.request_record_id
allowed_child_folders_json = B7.allowed_child_folders_json
```

必须先保存白名单再发送卡片，因为下一次 `browse` 回调要用这份白名单验证目录 token。

更新成功后添加“发送飞书卡片”节点，选择“归档-选择目录-V2”，命名：

```text
B9_发送目录卡片
```

变量绑定：

| 卡片变量 | B7 输出 |
|---|---|
| `selected_file_name` | `selected_file_name` |
| `breadcrumb` | `breadcrumb` |
| `current_folder_url` | `current_folder_url` |
| `warning` | `warning` |
| `initiator` | `initiator` |
| `folder_options` | `folder_options` |
| `disable_folder_browse` | `disable_folder_browse` |
| `disable_back` | `disable_back` |
| `skill_object_browse` | `skill_object_browse` |
| `skill_object_back` | `skill_object_back` |
| `skill_object_choose_current` | `skill_object_choose_current` |
| `skill_object_cancel` | `skill_object_cancel` |

如果发送节点要求目标会话：

```text
接收类型 = 群聊
chat_id = B2.chat_id
```

不要从卡片自定义参数接收 `chat_id`。发送成功后本次技能 B 运行结束；用户下一次点击卡片 2 时会启动一次新的 B 运行。

若保存白名单或发送卡片 2 失败，尝试把该请求更新为 `failed`，写入失败
节点的真实错误和 `B0.1_当前时间.now_ms`，然后结束；不得继续等待一张
实际上没有成功发出的卡片。

---

## 第 14 步：搭建最终确认和取消

### 14.1 `choose_current_folder`

从 `B4.2_next_step分支` 的：

```text
B4.next_step == send_confirm_card
```

出口开始。添加“更新多维表格记录”节点：

```text
节点名 = B10_保存目标目录
record_id = B2.request_record_id
```

| 字段 | B4 输出 |
|---|---|
| `target_folder_token` | `target_folder_token` |
| `target_folder_name` | `target_folder_name` |
| `target_folder_url` | `target_folder_url_object`，object |
| `status` | B4 `status`，应为 `waiting_confirm` |

更新成功后添加 Python 节点，命名：

```text
B11_组装最终确认卡片
```

复制：

[b_build_confirm_card.py](./aily_nodes/b_build_confirm_card.py)

输入：

| 参数 | 值 |
|---|---|
| `request_id` | B2 `request_id` |
| `callback_skill_id` | 固定 `skill_xxx` |
| `requester_id` | B2 `requester_id` |
| `selected_file_name` | B4 `selected_file_name` |
| `selected_file_type` | B4 `selected_file_type` |
| `target_folder_path` | B4 `target_folder_path` |
| `target_folder_url` | B4 `target_folder_url` |
| `warning` | B4 `warning_message` |

注意：卡片输入 `target_folder_url` 使用 B4 的字符串输出；只有上一步写 Base 时使用 `target_folder_url_object`。

B11 后添加条件分支：

```text
B11.ok == false → 更新请求为 failed，写入 B11.error 和 completed_at
                → 发送 B11.error → 结束
B11.ok == true  → 发送卡片 3
```

成功出口添加“发送飞书卡片”节点，选择“归档-最终确认-V2”，卡片变量绑定 B11 同名输出。目标会话：

```text
接收类型 = 群聊
chat_id = B2.chat_id
```

发送成功后结束本次 B 运行。

若发送卡片 3 失败，也将请求更新为 `failed`，写入发送节点的真实错误和
`B0.1_当前时间.now_ms`，然后结束。

### 14.2 `cancel`

从 `B4.2_next_step分支` 的：

```text
B4.next_step == end
```

出口添加“更新多维表格记录”节点：

```text
节点名       = B10_cancel_保存取消状态
record_id    = B2.request_record_id
status       = B4.status（cancelled）
completed_at = B4.completed_at_ms
```

更新成功后直接结束，不再发送新卡片。旧卡片由按钮回调对象的 `update_card=true` 更新成“已取消本次归档”。

---

## 第 15 步：搭建 `confirm_upload`

这是 `B3.1_action分支` 中唯一不经过 B4 的出口。

### 15.1 `confirm_upload` 出口：先锁定为 processing

在 `B2.action == confirm_upload` 出口添加“更新多维表格记录”节点：

```text
节点名        = B12_进入处理中
record_id     = B2.request_record_id
status        = processing
confirmed_at  = B0.1_当前时间.now_ms
error_message = 空
```

只有该更新成功才能继续；失败时发送节点真实错误并结束，不能下载文件。

### 15.2 重新查询最新请求

添加“查询多维表格记录”节点：

```text
节点名         = B13_重查处理中请求
Base App Token = WHaibyXvuaXuJpsDraJcAAM9nIb
Table ID       = tblyUgvj29jAL275
page_size      = 2
筛选字段         = request_id
operator         = is
value             = B0.2.request_id_filter_values
```

再添加 Python 节点：

```text
节点名 = B14_校验处理中请求
代码   = b5_validate_processing_request.py
```

输入：

| 参数 | 绑定 |
|---|---|
| `request_result` | B13 完整输出 |
| `request_id` | 开始节点 `request_id` |

如果 B13 查询节点本身失败，使用 `B2.request_record_id` 尝试把请求更新为
`failed`，写入 B13 的真实错误和完成时间，然后结束；不要继续下载。

B14 后添加条件分支节点，按顺序建三个出口：

| 出口 | 条件 | 处理 |
|---|---|---|
| 校验失败 | `B14.ok == false` | 若 `request_record_id` 非空且状态为 `processing`，更新 `failed/error_message/completed_at`；否则只发送 B14.error；然后结束 |
| 已经处理 | `B14.ok == true AND B14.should_upload == false` | 直接结束，不再下载和上传 |
| 可以上传 | `B14.ok == true AND B14.should_upload == true` | 进入 15.3 |

B14 会输出后续所需的扁平字段，不再让你从重查结果的深层 JSON 中手工选择：

```text
chat_id
chat_id_filter_values
source_message_id
selected_file_key
selected_file_name
selected_file_type
target_folder_token
target_folder_name
target_folder_url
target_folder_path
```

### 15.3 下载被回复的消息文件

从“可以上传”出口添加“获取消息资源/下载消息附件”节点：

```text
节点名   = B15_下载消息文件
消息 ID  = B14.source_message_id
文件 key = B14.selected_file_key
资源类型  = file
```

先单独调试一次该节点，记住它实际输出的“文件内容”和“文件大小”字段名；不同租户界面名称可能不同，后文简称为：

```text
B15.file_content
B15.actual_size
```

下载节点失败出口：

```text
更新 record_id = B14.request_record_id
status          = failed
error_message   = 下载节点真实错误
completed_at    = B0.1_当前时间.now_ms
```

然后进入 15.7 的失败结果卡片。

### 15.4 重查群映射并校验真实文件大小

下载成功出口添加“查询多维表格记录”节点：

```text
节点名         = B16_重查群映射
Base App Token = WHaibyXvuaXuJpsDraJcAAM9nIb
Table ID       = tblacRVYZZ4SJmWW
View ID        = vewPOqHrk9
page_size      = 2
筛选字段         = chat_id
operator         = is
value             = B14.chat_id_filter_values
```

运行输入必须是 `"value":["oc_xxx"]`。

如果 B16 查询节点本身失败，也更新请求为 `failed`，写入 B16 的真实错误，
然后进入失败结果卡片。

再添加 Python 节点：

```text
节点名 = B17_校验上传策略
代码   = b6_validate_upload_policy.py
```

输入：

| 参数 | 绑定 |
|---|---|
| `mapping_result` | B16 完整输出 |
| `chat_id` | B14 `chat_id` |
| `selected_file_type` | B14 `selected_file_type` |
| `actual_size` | B15 实际文件字节数 |

B17 后添加条件分支：

```text
B17.ok == false → 更新 failed、error_message=B17.error、completed_at → 失败结果卡片
B17.ok == true  → 上传文件
```

该代码会验证映射唯一且启用、文件类型仍允许、真实大小大于 0，并且不超过 `min(max_file_size_mb,20)`。

### 15.5 上传文件

成功出口添加普通“上传文件”节点：

```text
节点名      = B18_上传文件
文件内容     = B15 文件内容
文件名       = B14.selected_file_name
父目录 token = B14.target_folder_token
文件大小     = B17.actual_size
```

上传失败出口：

```text
record_id       = B14.request_record_id
status          = failed
error_message   = 上传节点真实错误
completed_at    = B0.1_当前时间.now_ms
```

然后进入失败结果卡片。

### 15.6 上传成功：把结果链接转换为 Base URL object

上传成功出口添加 Python 节点：

```text
节点名 = B19_转换结果链接
代码   = common_build_url_object.py
```

输入：

```text
url  = B18 上传结果中的文件链接
text = B14.selected_file_name
```

`B19.ok == false` 时不要写成功，改写 `failed` 并发送 `B19.error`。`B19.ok == true` 时更新请求：

```text
record_id         = B14.request_record_id
status            = success
result_file_token = B18 上传结果文件 token
result_file_url   = B19.url_object       # object，不是字符串
result_size       = B17.actual_size
error_message     = 空
completed_at      = B0.1_当前时间.now_ms
```

### 15.7 发送结果卡片

成功和失败都使用 [b_build_result_card.py](./aily_nodes/b_build_result_card.py)。如果 Aily 不支持多个分支汇入同一个代码节点，就在成功分支和每个失败分支各复制一个结果卡片代码节点。

公共输入：

| 参数 | 绑定 |
|---|---|
| `request_id` | B14 `request_id` |
| `requester_id` | B2 `requester_id` |
| `selected_file_name` | B14 `selected_file_name` |
| `selected_file_type` | B14 `selected_file_type` |
| `target_folder_name` | B14 `target_folder_name` |
| `target_folder_path` | B14 `target_folder_path` |
| `target_folder_url` | B14 `target_folder_url` |
| `completed_at` | B0.1 `now_ms` |

成功分支额外绑定：

```text
status          = success
result_file_url = B19.url
result_size     = B17.actual_size
error_message   = 空
```

失败分支额外绑定：

```text
status          = failed
result_file_url = 空
result_size     = 0 或 B17.actual_size
error_message   = 当前失败节点的真实 error
```

结果代码 `ok=true` 后发送“归档-结果-V2”，目标会话：

```text
接收类型 = 群聊
chat_id = B14.chat_id
```

卡片 4 没有回调按钮，发送后结束本次技能 B。

当前 Base 的“先查再改”不能提供严格原子 CAS；本流程能阻止顺序重复点击，但两个真正同时到达的回调仍可能并发进入。若业务必须保证绝不重复上传，需要额外的原子幂等服务。

---

## 第 16 步：统一错误分支、发布和验收

### 16.1 统一错误分支

在尚未创建请求，或校验失败不应改变请求状态时，代码节点使用：

```text
ok == true  → 继续
ok == false → 发送当前节点.error → 结束
```

请求已经创建且当前分支无法继续时，按下表先将请求更新为 `failed`，再发送
真实错误或失败结果卡片。不要用上面的简化规则覆盖下表。

“按需”具体按下表执行：

| 失败节点/阶段 | 是否更新请求 | 更新内容 | 是否继续发卡片 |
|---|---|---|---|
| 技能 A 读取触发消息、被回复消息或映射查询 | 否，此时请求尚未创建 | 无 | 发送真实文本错误后结束 |
| 技能 A 创建请求记录 | 否，创建本身失败 | 无 | 发送真实文本错误后结束 |
| 技能 A 创建请求成功，但卡片 1 组装或发送失败 | 是 | `status=failed`、`error_message=真实错误`、`completed_at=当前时间` | 不再发卡片 |
| 技能 B 查询不到请求或命中多条 | 无法安全更新 | 无 | 发送真实文本错误，交管理员处理 |
| B2 操作者、action、状态或白名单校验失败 | 否 | 保留原状态；`REQUEST_EXPIRED` 除外 | 发送 B2.error 后结束 |
| `REQUEST_EXPIRED` | 是 | `status=expired`、错误和完成时间 | 发送过期提示后结束 |
| B4 用户操作校验失败，例如根目录继续返回 | 否 | 保留可继续状态 | 发送 B4.error 后结束 |
| 技能 B 更新请求字段失败 | 更新节点本身失败，不能假设已写入 | 不继续执行后续目录/上传节点 | 发送更新节点真实错误 |
| 目录清单、目录卡片代码、保存白名单或发送卡片 2 失败 | 是 | `status=failed`、真实错误、完成时间 | 能发送时发送失败文本；不继续目录浏览 |
| 最终确认卡片代码或发送卡片 3 失败 | 是 | `status=failed`、真实错误、完成时间 | 发送失败文本后结束 |
| 把状态更新为 `processing` 失败 | 否，不允许下载 | 保留原状态 | 发送更新节点真实错误 |
| 上传预检、下载、大小校验或上传失败 | 是 | `status=failed`、真实错误、完成时间 | 尝试发送卡片 4 失败结果 |
| 上传成功但写回 Base 结果失败 | 写回本身失败 | 不得伪称记录已成功；日志保留上传返回 token/URL，发送文本告警并人工补记 | 不发送“已完整归档”的成功卡片 |
| Base 已写入 `success/failed`，但卡片 4 发送失败 | 否 | 保持已落库终态 | 记录发送错误；不要把业务结果改回失败 |

禁止统一写成：

```text
当前群没有找到归档目录映射
```

文件类型错误应显示：

```text
当前文件类型 .md 不在本群允许归档的类型中
```

目录权限错误、消息读取错误和上传错误也必须各自显示真实阶段。

### 16.2 重新发布并刷新卡片

1. 发布技能 B。
2. 确认技能 B ID 没变；如变更，更新所有代码节点的 `callback_skill_id`。
3. 发布四张卡片。
4. 回到每个“发送飞书卡片”节点点击“更新/刷新模板”。
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

#### 用例 10：文件大小

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
B3 条件分支：校验成功 / 已过期 / 其他失败
B3.1 条件分支：七个 action
B4 Python：b3_prepare_action.py
B4.1 条件分支：B4 成功 / 失败
B4.2 条件分支：list_folder / send_confirm_card / end

目录公共段：
B4.3 条件分支：choose_file / browse / back / return_folder
→ 各自更新请求 → 读取目录清单 → b_build_folder_card.py
→ 保存子目录白名单 → 卡片 2

最终确认段：
更新 target/status → b_build_confirm_card.py → 卡片 3

上传段：
processing → 重查 → b5_validate_processing_request.py
→ 下载 → 重查映射 → b6_validate_upload_policy.py
→ 上传 → common_build_url_object.py → 写结果
→ b_build_result_card.py → 卡片 4
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
