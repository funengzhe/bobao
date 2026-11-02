# 参与贡献

欢迎提交新的风格包、规则包、场景，或者修 Bug、改进代码。

## 提交前请知道

只要你提交 Pull Request，就表示你同意下面两点：

1. 你提交的内容是你自己写的，或者你有权提交它。
2. 你把提交内容的使用权授予仓库所有者 funengzhe。授权是永久、全球、免费、不可撤销的，所有者可以用本仓库的许可证（MIT + Commons Clause）发布它，也可以用其他许可证发布它，包括商业授权。你自己仍然保留你写的内容的版权。

这样做是为了让项目以后能提供商业授权或者调整许可证，而不需要逐个去找每位贡献者签字。

## 怎么提交

- 风格包放在 `packs/styles/`，规则包放在 `packs/rules/`，场景放在 `packs/scenes/`。格式可以参考现有的文件。
- 提交前运行一遍测试：`python3 -m unittest discover tests`。新的风格包和场景会被自动检查，确认念出来的每一句话都能录音。
- 不要提交任何令牌、密钥、群 ID 或真实的用户数据。
- 不要提交 macOS 系统声音生成的音频。

---

By opening a pull request you confirm the contribution is yours to submit, and you grant funengzhe a perpetual, worldwide, royalty-free, irrevocable license to use, modify and relicense it, including under commercial terms. You keep your copyright.
