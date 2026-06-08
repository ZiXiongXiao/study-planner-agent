# Profile Schema

`ProfileMemoryAgent` 输出 JSON 时应尽量使用以下字段。字段可以为空，但不要输出 Markdown。

```json
{
  "level": "beginner|intermediate|advanced",
  "weekly_hours": 6,
  "background": "一句话描述用户背景",
  "preferences": ["偏项目实战", "希望解释通俗"],
  "resource_preferences": ["中文免费资源", "B站视频", "GitHub示例"],
  "constraints": ["普通上班族", "晚上学习", "不希望太难"],
  "output_format": "偏好的学习产物形式",
  "temporary_context": ["仅本次计划有效的限制或反馈"],
  "uncertain_notes": ["不确定但可能有用的信息"],
  "summary": "一句话画像总结"
}
```

## 字段说明

| 字段 | 说明 |
| --- | --- |
| `level` | 用户当前能力阶段，只能是 beginner / intermediate / advanced |
| `weekly_hours` | 每周可投入学习小时数；未知时用合理估计或 0 |
| `background` | 与学习目标相关的背景，不写无关隐私 |
| `preferences` | 稳定学习偏好 |
| `resource_preferences` | 稳定资源偏好 |
| `constraints` | 时间、难度、场景、工具条件等长期约束 |
| `output_format` | 用户希望最终得到的产物形式 |
| `temporary_context` | 本轮计划临时要求，后续不应默认继承 |
| `uncertain_notes` | 低置信信息，后续可被澄清覆盖 |
| `summary` | 给日志和展示使用的一句话总结 |

## 输出要求

- 只返回 JSON object，不返回解释文字。
- 不要输出 null，未知信息用空字符串、空数组或 0。
- 不要把 API Key 或任何密钥写入画像。
- 不要把用户一次性反馈直接写成长期偏好。
