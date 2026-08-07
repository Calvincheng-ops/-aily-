# 飞书 Aily 工作流应用技术沉淀

> 记录日期：2026-07-29  
> 适用项目：飞书群聊文件自动归档应用  
> 记录范围：2026-07-28 至 2026-07-29 的搭建、日志排查、代码验证和架构收敛；
> 2026-08-06 至 2026-08-07 的技能 B 联调、自定义连接器验证和上线（见第 17 节）  
> 施工手册：[BUILD_GUIDE_V2.md](./BUILD_GUIDE_V2.md)

本文记录本轮开发中已经通过 Aily 运行日志、飞书错误码或本地测试确认的
技术事实。本文不是逐步搭建教程；实际施工仍以 `BUILD_GUIDE_V2.md` 为唯一
操作手册。

## 1. 项目目标与最终交互

用户在飞书群聊中：

1. 先发送或找到一条文件消息。
2. 直接回复该文件消息。
3. 在回复中 @机器人并发送“归档”。
4. 在卡片 1 中确认文件。
5. 在卡片 2 中逐层选择云盘目录。
6. 在卡片 3 中最终确认。
7. 工作流下载原消息文件并上传到目标目录。
8. 卡片 4 返回成功或失败结果。

核心产品规则：

- 即使候选文件只有一个，也必须先由用户点击卡片确认。
- 不读取大量群聊历史，不让大模型猜测“最终文件”。
- 只能访问当前群映射根目录及其子目录。
- 上传硬上限 `1..100 MB`：≤20 MB 走 upload_all 普通上传，>20 MB 自动切换分片上传（2026-08-07 起，b9 节点内置）。
- 失败必须展示当前阶段的真实错误，不能统一误报为“没有目录映射”。

## 2. 最终架构结论

项目使用两个独立 Aily 技能：

```text
技能 A：接收群消息 → 精确读取被回复文件 → 查询群映射
       → 创建 selecting_file 请求 → 发送卡片 1 → 结束

用户点击卡片：
卡片 trigger_skill → 新启动一次技能 B

技能 B：读取开始参数和点击人 → 按 request_id 从 Base 恢复请求
       → 校验状态和权限 → 处理当前 action → 发下一张卡片或上传 → 结束
```

### 2.1 为什么不能在技能 A 后顺序连接技能 B

Aily 画布中的“工作流 B”节点是同步顺序调用。技能 A 执行到该节点时会立即
启动 B，不会暂停等待未来的卡片点击。

正确的 A → B 连接位于卡片按钮对象：

```json
{
  "aily_action": "trigger_skill",
  "skill_id": "skill_xxx",
  "skill_input": "{\"request_id\":\"archive_xxx\",\"action\":\"choose_file\"}"
}
```

每次点击都会创建一次新的技能 B 运行。技能 A 的节点变量不会自动跨越点击
保留到 B；跨运行状态必须通过 `request_id` 和多维表格恢复。

## 3. 技能 B 的输入边界

技能 B 开始节点只保留四个自定义参数：

| 参数 | 类型 | 必填 | 来源 |
|---|---|---:|---|
| `request_id` | string | 是 | 卡片 `skill_input` |
| `action` | string | 是 | 卡片 `skill_input` |
| `selected_file_id` | string | 否 | 卡片 1 |
| `selected_folder_token` | string | 否 | 卡片 2 表单 |

点击人不能作为自定义参数信任，必须读取 Aily 系统全局变量：

```text
message.sender.openID
```

以下业务字段不应由卡片传入：

- `chat_id`
- `file_key`
- `source_message_id`
- 目录路径
- 目标目录
- 请求状态
- 原发起人

这些字段全部通过 `request_id` 从 Base 重查。

## 4. 精确读取被回复文件

### 4.1 触发消息提供的关键字段

“获取指定消息”节点返回的触发消息中可以取得：

```text
message_id
chat_id
parent_id
root_id
sender.id
msg_type
```

本项目只使用 `parent_id` 定位用户直接回复的消息：

```text
触发消息 message_id
    ↓ 获取指定消息
parent_id
    ↓ 再次获取指定消息
被回复的 file 消息
```

`parent_id` 为空时直接提示用户必须回复文件，不使用 `root_id` 或最近消息回退
猜测。

### 4.2 消息结果存在多层包装

实际 Aily/OpenAPI 输出可能类似：

```json
{
  "code": "200",
  "data": {
    "code": 0,
    "data": {
      "items": []
    },
    "msg": "success"
  },
  "message": "OK"
}
```

因此不能在后续节点中手工依赖固定的深层选择器。项目使用
`a2_normalize_trigger_message.py` 解包并输出稳定字段。

成功输出至少包含：

```text
ok
message_id
parent_id
root_id
chat_id
chat_id_filter_values
sender_id
```

### 4.3 文件消息内容

飞书文件消息的 `body.content` 本身是 JSON 字符串：

```json
{
  "file_key": "file_v3_xxx",
  "file_name": "项目终版.md"
}
```

必须先解析 `body.content`，再读取 `file_key` 和 `file_name`。

## 5. 多维表格查询的数组参数陷阱

### 5.1 `filter.conditions[].value` 必须是数组

飞书多维表格查询节点中的条件值，即使只有一个值，也必须传真实字符串数组：

```json
{
  "field_name": "request_id",
  "operator": "is",
  "value": ["archive_xxx"]
}
```

错误形式：

```json
{
  "field_name": "request_id",
  "operator": "is",
  "value": "archive_xxx"
}
```

错误传入字符串时，Aily 连接器可能不显示明确异常，只返回：

```json
{
  "code": null,
  "data": null,
  "message": null
}
```

这不是“查询结果为 0 条”，而是连接器参数类型不正确。

### 5.2 开始参数仍然保持 string

技能 B 的 `request_id` 开始参数保持 `string` 是正确的。不要把卡片参数改成
数组。

使用 `b0_prepare_request_filter.py` 转换：

```text
输入：request_id = "archive_xxx"
输出：request_id_filter_values = ["archive_xxx"]
```

Base 查询节点绑定整个 `request_id_filter_values`，不能绑定数组第 0 项。

同理，技能 A 查询群映射使用：

```text
chat_id_filter_values = ["oc_xxx"]
```

### 5.3 空数组必须提前停止

转换节点输出 `ok=false` 或数组为空时，必须通过条件分支停止，不能让空数组
继续进入 Base 查询。技能 B 中对应 `B0.3_筛选参数校验`。

## 6. 多维表格字段类型合同

### 6.1 URL 字段必须接收对象

Base 的 URL/超链接字段不能接收普通字符串。正确值：

```json
{
  "text": "测试文件夹",
  "link": "https://example.feishu.cn/drive/folder/xxx"
}
```

仅把 Aily 创建/更新节点左侧类型下拉框改成 `object` 不会自动转换右侧变量。
如果右侧仍绑定字符串，运行时仍然是字符串，并会报：

```text
1254068 URLFieldConvFail
the value of 'Link' must be an object
```

项目代码分别输出：

```text
xxx_url          字符串，仅用于卡片展示
xxx_url_object   对象，仅用于写入 Base URL 字段
```

适用字段：

- `root_folder_url_snapshot`
- `current_folder_url`
- `target_folder_url`
- `result_file_url`

2026-08-06 线上验证：技能 A 创建归档请求节点的成功运行输入中，URL 字段的实际
提交值仅含 `link` 与 `text` 两个键，不带 `type` 键：

```json
"root_folder_url_snapshot": {
  "link": "https://westoeast.feishu.cn/drive/folder/xxx",
  "text": "测试文件夹"
}
```

同一次运行中 `expires_at` 以 float 毫秒数字提交成功；数字类字段只要不用引号
包裹即可通过。

### 6.2 日期时间字段必须传毫秒数字

Base 日期时间字段应传 Unix 毫秒数字：

```json
{
  "expires_at": 1785251887940
}
```

不要传字符串：

```json
{
  "expires_at": "1785251887940"
}
```

项目使用 `common_now_ms.py` 生成当前毫秒，并统一用于：

- `expires_at`
- `confirmed_at`
- `completed_at`

### 6.3 字段名可能包含不可见字符

实际错误曾出现：

```text
fields.allowed_child_folders_json\t
1254045 FieldNameNotFound
```

界面看起来像正确字段名，但末尾包含 Tab。可靠修复方式：

1. 删除整行字段绑定。
2. 刷新数据表字段列表。
3. 从下拉列表重新选择真实字段。

不要只在原输入框末尾按退格。

### 6.4 `property1` 不是业务字段

若创建记录运行输入中出现：

```json
{
  "property1": "om_xxx"
}
```

说明 Aily 没有选中真实的 `trigger_message_id` 字段，而是保留了默认占位字段。
删除整行后重新选择 `trigger_message_id`。

### 6.5 Base 富文本单元格需要标准化

Base 文本字段在查询结果中可能不是纯字符串，而是：

```json
[
  {
    "text": "oc_xxx",
    "type": "text"
  }
]
```

URL 字段则可能是：

```json
{
  "text": "测试文件夹",
  "link": "https://example/...",
  "type": "url"
}
```

项目 Python 节点通过 `_cell()` / `_first()` 统一转换为普通值，下游不要直接
依赖 Base 原始单元格结构。

## 7. 卡片回调对象合同

所有交互按钮对象都使用：

```json
{
  "x_aily_forbid_forward_callback": true,
  "aily_action": "trigger_skill",
  "skill_id": "skill_xxx",
  "skill_input": "{\"request_id\":\"archive_xxx\",\"action\":\"cancel\"}",
  "update_card": true,
  "success_message": "已取消本次归档"
}
```

关键点：

- `skill_id` 必须是已发布技能 B 的 `skill_xxx`，不是机器人 `cli_xxx`、
  卡片 ID 或应用 ID。
- `skill_input` 是 JSON 字符串，不是 Python/JavaScript 对象。
- `update_card=true` 用于降低旧卡片重复点击。
- `x_aily_forbid_forward_callback=true` 阻止转发后的卡片触发业务回调。
- 仍需依赖 Base 状态校验，不能只依赖卡片更新防重。

### 7.1 卡片 2 的表单字段

卡片 2 的目录下拉框和“进入选中的文件夹”按钮必须位于同一个表单容器。

下拉框名称必须精确为：

```text
selected_folder_token
```

按钮的 `skill_input` 只包含 `request_id` 和 `action=browse`；表单字段由卡片
运行时另外合并回技能 B 开始参数。

### 7.2 卡片变量与 Base 字段不能混用

卡片 URL 变量使用字符串：

```text
current_folder_url
target_folder_url
result_file_url
```

Base URL 字段使用对应 object。不要把 object 直接作为卡片正文文本，也不要
把卡片字符串直接写入 Base URL 字段。

## 8. 状态机

`status` 单选值必须完全一致：

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

主要状态转换：

```text
技能 A 创建请求
    → selecting_file

用户确认文件
    → selecting_folder

用户选择当前目录
    → waiting_confirm

用户确认上传
    → processing
    → success 或 failed

任意可取消卡片点击取消
    → cancelled

超过 expires_at
    → expired
```

动作允许状态：

| action | 允许的当前状态 |
|---|---|
| `choose_file` | `selecting_file` |
| `browse` | `selecting_folder` |
| `back` | `selecting_folder` |
| `choose_current_folder` | `selecting_folder` |
| `return_folder` | `waiting_confirm` |
| `confirm_upload` | `waiting_confirm` |
| `cancel` | `selecting_file`、`selecting_folder`、`waiting_confirm` |

## 9. 请求快照与信任边界

### 9.1 文件确认

技能 A 即使只找到一个文件，也只写入：

```text
candidate_files_json
status = selecting_file
```

以下字段必须保持空：

```text
selected_file_id
selected_file_key
selected_file_name
selected_file_type
source_message_id
```

用户点击卡片 1 后，技能 B 验证 `selected_file_id` 必须存在于
`candidate_files_json` 快照，验证通过后才写 `selected_file_*`。

### 9.2 目录白名单

卡片 2 只显示当前目录直属子文件夹。发送卡片前先把目录清单保存到：

```text
allowed_child_folders_json
```

后续 `browse` 回调中的 `selected_folder_token` 必须存在于该白名单，并且
`parent_token` 必须等于当前目录 token。

### 9.3 根目录边界

`folder_path_json` 的第一个 token 必须等于：

```text
root_folder_token_snapshot
```

返回上级时只允许从路径数组删除最后一级；路径只剩根目录时必须拒绝继续返回。

上传前再次检查：

```text
folder_path_json[0].token == root_folder_token_snapshot
folder_path_json[-1].token == target_folder_token
```

## 10. 上传前重查与校验

`confirm_upload` 分支不能直接下载。正确顺序：

```text
waiting_confirm
→ 更新 processing
→ 按 request_id 重查请求
→ 校验仍可上传
→ 下载消息资源
→ 按 chat_id 重查最新群映射
→ 用真实下载字节数校验大小
→ 上传
→ 写 success/failed
```

上传前重查请求的目的：

- 确认请求仍存在且唯一。
- 确认状态为 `processing`。
- 确认没有结果 token。
- 展开可信的 `source_message_id`、`file_key` 和目标目录。
- 再次验证路径没有越过映射根目录。

重查群映射的目的：

- 映射仍唯一。
- `enabled` 仍为 true。
- 文件扩展名仍被允许。
- 当前大小限制仍有效。

文件大小使用下载节点返回的实际字节数，不完全信任原消息中的大小。校验：

```text
actual_size > 0
actual_size <= min(max_file_size_mb, 20) * 1024 * 1024
```

## 11. 防重复能力边界

现有防重措施：

- 卡片 `update_card=true`。
- 技能 B 每次入口校验 action 与当前状态。
- 上传前写入 `processing` 并重查。
- 终态和已有 `result_file_token` 不再上传。

但 Base 的普通“先查再改”不是原子 Compare-And-Set。两个真正同时到达的
`confirm_upload` 回调仍可能同时写入 `processing` 并继续上传。

当前结论：

- 可以阻止顺序重复点击。
- 不承诺强并发下绝不重复上传。
- 若业务要求严格幂等，需要外部原子锁、唯一事务键或幂等上传服务。

## 12. 错误处理原则

### 12.1 请求创建前

读取消息、读取被回复消息、查询映射或文件校验失败时：

- 不创建请求。
- 发送当前节点真实错误。
- 直接结束。

### 12.2 请求创建后

如果下一张卡片无法组装/发送，或目录、下载、上传阶段无法继续：

- 尝试更新请求为 `failed`。
- 写入当前失败节点真实错误。
- 写入 `completed_at`。
- 发送文本错误或失败结果卡片。

### 12.3 不应覆盖原状态的校验错误

以下失败通常不更新请求：

- 点击人不是原发起人。
- action 不支持。
- 旧卡片状态不匹配。
- 伪造文件 ID。
- 伪造目录 token。
- 根目录继续返回上级。

`REQUEST_EXPIRED` 是例外，应写入 `expired` 和完成时间。

## 13. Python 节点合同

| 文件 | Aily 节点 | 核心职责 |
|---|---|---|
| `common_now_ms.py` | A0.1、B0.1 | 输出当前 Unix 毫秒 |
| `a2_normalize_trigger_message.py` | A2.1 | 解包触发消息并生成 `chat_id_filter_values` |
| `a7_build_archive_request.py` | A5 | 校验消息、文件、映射并生成请求快照 |
| `a9_build_file_confirm_card.py` | A8 | 生成卡片 1 变量和回调对象 |
| `b0_prepare_request_filter.py` | B0.2 | 把 string 请求 ID 转成 Base 查询数组 |
| `b2_validate_callback.py` | B2 | 校验点击人、状态、有效期和选项白名单 |
| `b3_prepare_action.py` | B4 | 六个非上传 action 的状态转换和字段展平 |
| `b_build_folder_card.py` | B7 | 校验目录清单、生成白名单和卡片 2 |
| `b_build_confirm_card.py` | B11 | 生成卡片 3 |
| `b5_validate_processing_request.py` | B14 | 上传前重查请求并展开可信字段 |
| `b8_compute_actual_size.py` | B15.5 | 计算下载内容的真实字节数（v2 用） |
| `b9_download_and_upload.py` | B15 | 下载消息资源并上传云盘（单节点；>20 MB 自动分片，硬上限 100 MB（飞书消息资源下载接口限制，错误码 234037）） |
| `b6_validate_upload_policy.py` | B17 | 重查映射并校验文件类型、真实大小 |
| `common_build_url_object.py` | B19 | 把上传结果 URL 转成 Base URL object |
| `b_build_result_card.py` | 结果卡片代码节点 | 生成卡片 4 |

文件名中的历史数字不一定等于当前 Aily 节点编号，以上表的“Aily 节点”列和
`BUILD_GUIDE_V2.md` 为准。

## 14. 已复现错误与判断方式

| 表现/错误码 | 已确认原因 | 处理 |
|---|---|---|
| 查询输出 `code/data/message=NULL` | Base 筛选 `value` 传了 string | 通过 Python 节点生成真实数组 |
| `1254045 FieldNameNotFound` | 字段名错误或带隐藏 Tab | 删除整行并从字段列表重选 |
| 输入出现 `property1` | 未选中真实 Base 字段 | 重选 `trigger_message_id` |
| `1254068 URLFieldConvFail` | URL 字段收到字符串 | 绑定 `{text, link}` object 输出 |
| `TRIGGER_CHAT_MISMATCH` | `chat_id` 参数绑定错误 | 使用标准化触发消息输出的 `chat_id` |
| `FILE_TYPE_NOT_ALLOWED` | 映射没有该扩展名 | 修正 `allowed_file_types`，不要误报映射不存在 |
| `INVALID_FOLDER_SELECTION` | token 不在本次白名单 | 检查卡片表单值和白名单保存顺序 |
| `REQUEST_EXPIRED` | 当前毫秒超过 `expires_at` | 写入 `expired` 并提示重新发起 |
| 自定义连接器把 `{param}` 字面值发出去 | 该编辑器不认识花括号占位 | 路径参数用冒号写法 `:param`，并在 Query 区声明同名参数使其成为节点入参（2026-08-06 验证） |
| `234008 The app is not the resource sender` | 用 `/im/v1/files/:file_key` 下载用户发送的文件 | 该接口只能下载应用自己上传的文件；消息附件必须用 `/im/v1/messages/:message_id/resources/:file_key?type=file` |
| `99992402 type is required`（下载消息资源） | 消息资源接口缺少 `type` query 参数 | Query 区保留 `type` 行，默认值 `file` |
| 下载成功但没有文件大小字段 | 消息资源接口只返回 `code/data/message`，内容在 `data` | 大小用 `b8_compute_actual_size.py` 按 UTF-8 字节数计算（2026-08-06 验证） |
| 上传报 `403 / 1061004 forbidden` | 应用身份没有目标文件夹的协作权限（新群新文件夹未共享） | 把映射根目录文件夹共享给机器人所在应用（可编辑）；每加新群必做（2026-08-07 实测） |

## 15. 已放弃的方案

以下方案已经明确不使用：

- 获取最近 20/30 条群聊消息。
- 将群聊历史整体交给智能体判断文件。
- 根据关键词“final/终版”猜文件。
- 单文件自动跳过确认。
- 技能 A 发送卡片后顺序调用技能 B。
- 自建 HTTP 卡片回调服务。
- 由卡片传递可信 `chat_id`、`file_key` 或目标目录。
- 把所有错误统一显示为“当前群没有归档目录映射”。

## 16. 验证状态

本地验证命令：

```bash
python3 -m py_compile aily_nodes/*.py tests/test_aily_nodes.py
python3 -m unittest discover -s tests -v
git diff --check
```

截至本文生成时：

- 13 个 Python 节点文件可编译。
- 26 项单元测试通过。
- 关键产品规则、数组筛选、URL object、状态校验、目录边界和上传策略已有
  自动化覆盖。
- 本地代码测试通过不等于 Aily 线上工作流已经端到端验收；仍需按搭建手册
  第 16 步完成真实群聊、卡片、云盘和 Base 联调。

## 17. 2026-08-07 技能 B 联调与上线沉淀

本节记录 2026-08-06 至 2026-08-07 技能 B 在真实画布上搭建、联调、上线过程中
验证出的技术事实。至此应用已完成端到端真实归档（含 11.7 MB PDF）。

### 17.1 条件分支的表达式写法（本租户为 `{{ }}` 表达式模式）

- 代码节点输出从 `.return` 下取：`{{ B2检验回调.return.ok }}`。
- 字符串常量必须加英文双引号：`{{ B4.return.next_step == "list_folder" }}`；
  不加引号的标识符解析为空，条件恒 false，会静默走不到目标分支。
- 布尔 `true`/`false` 和数字不加引号。
- AND 用 `&&`（或 `And`），OR 用 `||`，NOT 用 `!`。
- 多分支从上到下第一条命中；「默认/否则」分支一律接结束，不要接业务节点，
  否则条件写错时会静默走错路（实测 B3.1 把 confirm_upload 掉进了 B4）。

### 17.2 代码节点输出声明陷阱

- 新贴代码后必须先单独调试一次，让平台识别 `return` 的字段结构再接下游。
- 输出声明成 String：下游 `节点.return.字段` 全部解析为空。
- 输出声明为空对象：运行日志显示 `{}`，所有字段被剥掉，代码本身是对的。
- 在坏掉的输出结构上做的绑定全部是失效引用；修好结构后必须从选择器重新点选。

### 17.3 Base 更新/查询节点（本轮新增实测）

- 绑定路径错误（如缺 `.return`）的字段会被**静默丢弃**：更新执行成功但一个
  字段都不写，无任何报错。排查时先看更新节点 InputArgs 里有没有该字段。
- 数字字段收到字符串报 `1254061 NumberFieldConvFail`；该行的值类型改选「数字」。
- 单选字段（如 `status`）绑变量可能不生效；固定选单选值更稳。
- 字段名隐藏 Tab 报 `1254045 FieldNameNotFound`：整行删除后从字段列表重选，
  只在输入框按退格清不掉。

### 17.4 自定义连接器（结论）

- 路径参数：地址栏用**冒号写法** `:param`，并在 Query 区声明同名参数使其成为
  节点入参；`{param}` 花括号写法会被原样发送（实测报 `99992354`）。
- Query 区声明的参数会被自动拼到 `?` 后面。
- Body 字段类型只有 String/Float/Integer/Boolean/Object/List，**没有文件类型、
  不支持 multipart 表单**——文件上传做不了，这就是 b9 单节点方案的起因。
- 二进制下载类操作不要配置应用状态码 `code == 0`（成功响应是文件流，没有
  code 字段，会把成功误判为失败）。
- 认证类型「飞书应用身份认证」的凭证实例可在所有飞书连接器间复用。

### 17.5 代码节点可联网 + 凭证约定

- Aily 工作流 Python 代码节点可用 urllib 直接访问外网 HTTPS（实测完成
  tenant_access_token 获取、消息资源下载、云盘上传全流程）。
- 凭证约定（2026-08-07 用户确认）：真实 APP_ID/APP_SECRET 只填在画布节点
  代码里；仓库文件保持占位符，禁止提交真实值；上线稳定后建议轮换一次 Secret。

### 17.6 飞书接口实测结论

| 接口 | 结论 |
|---|---|
| `GET /im/v1/messages/{id}/resources/{key}?type=file` | 消息附件唯一下载口；≤100 MB（超限报 `234037`） |
| `GET /im/v1/files/:file_key` | 只能下载应用自己上传的文件（`234008`），不能用于消息附件 |
| `GET /drive/v1/files/:file_token/download` | 云盘文件下载，无大小限制（仅 5 QPS / 每天 10000 次） |
| `POST /drive/v1/files/upload_all` | ≤20 MB；`size` 必填；响应只有 `file_token`，URL 用 `https://<域名>/file/<file_token>` 拼接 |
| 分片上传 prepare/part/finish | 固定 4 MB 分片、seq 从 0 开始、可选 Adler-32 校验；无大小上限（受云空间容量约束） |
| 上传报 `403 / 1061004 forbidden` | 应用身份没有目标文件夹协作权限；每新增群映射必须把根目录共享给应用（可编辑） |

### 17.7 状态机运维实测

- `update_card=true` 的按钮点击后卡片就地变成 success_message，永久失去按钮；
  在 Base 里改状态不会复活卡片，恢复途径是重新发起一次归档。
- 上传中重复点击 confirm_upload 会被 B2 正确拒绝（实测 `INVALID_STATUS`）。
- 运行死在中途（如失败处理尚未接线的时期）会让记录卡在 `processing`；
  恢复方式：手动把 Base 该记录的 `status` 改为 `waiting_confirm` 或 `failed`。

## 18. 安全注意事项

- 仓库、Base、卡片变量和日志中不得保存 App Secret 或访问令牌。
- 应用凭证曾在开发对话中被直接提供过，建议在开放平台轮换；本文不记录旧值。
- 后续 Agent 不得从聊天历史复制凭证进代码。
- 飞书访问统一使用已配置身份/profile 或平台连接器。
- Base 里保存的是业务状态，不是认证凭据。

