# 飞书群聊文件归档智能体（aILY V2）

飞书群聊中的文件归档机器人。用户回复目标文件消息并 @机器人发起归档 → 机器人精确读取被回复文件 → 用户确认文件 → 逐层选择目标目录 → 最终确认后上传到云盘指定位置。

## 技术栈

- **平台**：飞书 aILY（智能伙伴创建平台）
- **架构**：两个 aILY 技能（技能 A 接收消息并发送卡片；用户点击后由卡片 `trigger_skill` 异步启动技能 B）
- **状态管理**：飞书多维表格（Base `WHaibyXvuaXuJpsDraJcAAM9nIb`）
- **交互**：4 张飞书卡片（确认文件 → 选目录 → 最终确认 → 结果）

## 文档

- [BUILD_GUIDE_V2.md](./BUILD_GUIDE_V2.md) — 从第 1 步做到第 16 步的唯一搭建操作手册
- [AILY_TECHNICAL_NOTES_2026-07-29.md](./AILY_TECHNICAL_NOTES_2026-07-29.md) — Aily、Base、卡片和上传流程的技术沉淀
- [AGENT_HANDOFF.md](./AGENT_HANDOFF.md) — 供其他 Agent 快速接手的项目现状与排障入口
- [ARCHITECTURE_V2.mmd](./ARCHITECTURE_V2.mmd) — 唯一架构流程图源文件
- [ARCHITECTURE_V2.png](./ARCHITECTURE_V2.png) — 与源文件同步生成的流程图图片
- [CLAUDE.md](./CLAUDE.md) — AI Agent 项目指令

## 目录

```
aily_nodes/   # aILY Python 节点代码（本地备份）
tests/        # 节点合同与关键产品规则测试
```

唯一有效实施方案是 Aily V2 重搭版：技能 A 不读取整段群聊历史，也不使用智能体猜文件；它只处理用户明确回复的文件消息。技能 A 使用上游变量生成卡片按钮的 `skill_input` 后结束，不在发送卡片后顺序调用技能 B。用户点击卡片时，卡片的 `trigger_skill` 才启动一次新的技能 B 运行；B 从系统点击人变量和开始节点自定义参数进入，再通过 `request_id` 从“归档请求”多维表格恢复状态。即使只有一个文件，也必须先发送卡片 1，由用户明确确认。

当前普通上传流程只支持 `1..20 MB` 文件。卡片按钮统一使用 `update_card=true` 降低重复提交；Base 状态检查属于防重复措施，不等同于严格原子幂等。
