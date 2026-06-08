# 记忆规则库

`soul-instr` 现在用于约束 Study Planner Agent 的长期记忆行为。

当前项目已经不再使用早期的双模式 prompt。新版主链路由 9 个 Agent 固定协作完成，记忆相关规则只服务于 `ProfileMemoryAgent`：

- 该记什么
- 不该记什么
- 如何把历史画像、全局记忆和本轮澄清合并
- 如何避免把一次性反馈误写成长期偏好

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `memory-policy.md` | 记忆边界、安全规则、可记/不可记内容 |
| `profile-schema.md` | 用户画像 JSON 字段说明 |
| `memory-merge-rules.md` | 历史画像与本轮输入的合并策略 |

这些文件会被 `ProfileMemoryAgent` 读取并注入画像生成 prompt，因此修改后会影响后续学习计划的画像记忆行为。
