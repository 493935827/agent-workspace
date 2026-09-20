# 项目工作约定

- 接续项目工作时，先读 `progress/progress.md` 的当前概况并核对相关工作区状态；缺少细节时搜索对话索引，按需打开关联 handoff，不批量加载历史归档。实质进度变化时更新现有概况；用户请求 handoff 时保存对话归档并更新对应索引行。handoff 保持手动调用，`progress/` 是持久项目记录，不属于临时清理范围。
- `agentctl/` 保存 Python CLI 实现，`configs/` 保存分层环境配置，`tests/` 保存测试；给人的使用入口是 `README.md`。
- 用户主要使用 C 和 Python，具有嵌入式软件背景；解释陌生技术时使用浅显语言。
- `firmware-mentor` 仅在用户当前消息明确写出 `$firmware-mentor` 或附上该技能链接时加载。固件、嵌入式、C、Python、芯片及职业成长等主题本身不构成调用授权。
