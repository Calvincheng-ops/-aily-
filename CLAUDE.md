# 飞书文件归档机器人（aILY V2）

飞书群聊文件归档智能体，基于飞书 aILY 低代码平台搭建。用户必须回复目标文件消息并 @机器人。两个技能协作：技能 A 精确读取被回复文件并发送确认卡片 → 技能 B 处理卡片回调，通过多维表格「归档请求」表传递状态。

## 架构文档入口

| 文档 | 内容 |
|------|------|
| [BUILD_GUIDE_V2.md](./BUILD_GUIDE_V2.md) | 搭建手册：技能 A/B、四张卡片、上传、权限、联调验收 |
| [ARCHITECTURE_V2.mmd](./ARCHITECTURE_V2.mmd) | 唯一 Mermaid 架构流程图 |
| [ARCHITECTURE_V2.png](./ARCHITECTURE_V2.png) | 由 Mermaid 源文件同步导出的流程图图片 |

## 项目结构

```
aily_nodes/          # aILY Python 节点的本地备份代码
  common_now_ms.py                 # 技能 A/B：生成当前 Unix 毫秒时间
  a2_normalize_trigger_message.py  # 技能 A：提取触发消息并生成 Base 筛选数组
  a7_build_archive_request.py      # 技能 A / A5：验证直接回复文件和映射，生成请求快照
  a9_build_file_confirm_card.py    # 技能 A / A8：组装单文件确认卡片
  b0_prepare_request_filter.py     # 技能 B：生成 request_id Base 筛选数组
  b2_validate_callback.py          # 技能 B 自定义参数、状态和白名单校验
  b3_prepare_action.py             # 技能 B / B4：非上传 action 的状态转换与字段展平
  b5_validate_processing_request.py # 技能 B / B14：上传前重查请求
  b6_validate_upload_policy.py     # 技能 B / B17：上传策略与真实大小校验
  common_build_url_object.py       # 技能 B / B19：Base URL 字段 object 适配
  b_build_folder_card.py           # 技能 B：组装目录浏览卡片
  b_build_confirm_card.py          # 技能 B：组装最终确认卡片
  b_build_result_card.py           # 技能 B：组装归档结果卡片
tests/
  test_aily_nodes.py               # 节点合同和关键规则测试
```

## 红线

- **不再使用服务端 Python 版本**（Docker + 事件回调）。旧代码已删除，新架构完全是 aILY 工作流。
- App Secret / token 不得写入 Base、卡片变量或代码常量。
- 技能 A 不得读取大量群聊历史或使用智能体猜文件；只按触发消息 `parent_id` 读取用户明确回复的文件。
- 技能 A 使用上游变量生成卡片按钮的 `skill_input` 后结束；不要在发送卡片后顺序添加“工作流 B”节点，因为它会立即运行而不会等待点击。
- 卡片回调是一次新的技能 B 运行，由按钮的 `trigger_skill` 启动，从系统全局变量和 B 开始节点自定义参数进入，状态通过 `request_id` 从多维表格恢复。
- 即使只有 1 个文件，也必须先经过卡片 1 的用户确认；技能 A 不得提前写入选中文件。
- 群聊只能访问映射表指定根目录及其子目录。
- 上传前必须重新检查请求状态、20 MB 普通上传上限和目标目录边界；这是重复提交防护，不宣称 Base 普通更新具备原子幂等。
- 错误分支必须展示当前节点真实 `error`，禁止把文件类型错误误报为“没有映射”。

## 关键外部资源

- aILY 平台：https://aily.feishu.cn
- 飞书开放平台文档：https://open.feishu.cn
- 映射表 Base：`WHaibyXvuaXuJpsDraJcAAM9nIb`
  - 群目录映射 Table：`tblacRVYZZ4SJmWW`
  - 归档请求 Table：`tblyUgvj29jAL275`
- 飞书操作统一走 profile `feishu-download`（详见父级 [飞书/CLAUDE.md](../../CLAUDE.md)）
