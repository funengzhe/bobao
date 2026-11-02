# 给智能体的安装说明

用户把这个仓库地址交给你，是想在**这台 Mac** 上装好 Bobao，让通知被念出来。按下面的顺序做。每一步都有检查方法，检查不通过就停下来，告诉用户哪一步、什么原因，不要跳过。

## 三条规矩

1. **飞书 App Secret 和如云登录永远不经过你。** 不要让用户把 Secret 发到对话里，也不要读取、打印或保存它。让用户复制 Secret 后，在**他自己的终端**里运行 `pbpaste | ~/bobao/bin/bobao feishu login --app cli_xxx`。如果用户已经把 Secret 贴进了对话，提醒他去开放平台「凭证与基础信息」重置 Secret，再按上面的方式重新连接。
2. **花钱的事先问。** `bobao voice record` 会用如云积分。先运行 `bobao voice quote`，把句数和积分原样告诉用户，等他明确同意后再录。
3. **一个飞书应用只在一台 Mac 上运行。** 飞书只把每条推送发给一个连接。两台 Mac 用同一个应用，会互相漏播。如果这个应用之前在别的电脑上跑过，装好后提醒用户把那台停掉（那台运行 `bobao uninstall`）。

## 1. 检查环境

```bash
sw_vers -productName
```

必须是 macOS。

```bash
/usr/bin/python3 --version
```

没有的话运行 `xcode-select --install`，请用户在弹窗里点安装，装完再继续。

只有用飞书时才需要 Node 和 lark-cli：

```bash
command -v lark-cli || npm install -g @larksuite/cli
```

没有 `npm` 的话，先请用户装 Node（<https://nodejs.org>，或 `brew install node`）。

## 2. 下载

```bash
git clone https://github.com/funengzhe/bobao ~/bobao
```

已经有了就 `git -C ~/bobao pull`。下面的命令都用 `~/bobao/bin/bobao`。

## 3. 设置：二选一

**A. 用户给了你一个配置包**（`bobao-xxx.zip`，由别人在他的 Mac 上用 `bobao export` 导出）：

```bash
~/bobao/bin/bobao import ~/Downloads/bobao-xxx.zip
```

里面有规则、文案、录好的声音，导入后不需要再录音、也不花钱。它会提示下一步要连接的飞书应用。

**B. 从头开始**：先问用户做什么工作、想播哪些通知，从下面选一个场景。

```bash
~/bobao/bin/bobao packs
```

```bash
~/bobao/bin/bobao init --scene saas --name 老板 --sources feishu,webhook
```

可用的参数：`--scene`、`--style`、`--name`（怎么称呼用户）、`--engine mac|rooyun`、`--sources feishu,webhook,notifications`、`--rule-packs`、`--chats`。没给的用场景默认值。试听各种场景和风格：<https://funengzhe.github.io/bobao/>。

## 4. 接飞书（用飞书时）

**4.1 用户已经有「飞书播报」应用**（例如配置包里已经写了 App ID）：直接到 4.3。

**4.2 还没有应用**：请用户在 <https://open.feishu.cn/app> 里操作，你一步步告诉他点哪里：

1. 「创建企业自建应用」，名字叫「飞书播报」。
2. 左侧「添加应用能力」→「机器人」→「添加」。
3. 左侧「权限管理」→「开通权限」，搜索并勾选下面 4 项（都是应用身份、只读），点「确认开通权限」：
   - `im:message.group_msg.include_bot:read` 获取群组中用户和机器人发送的消息（收推送）
   - `im:message.group_msg` 获取群组中所有消息（断线后补查）
   - `im:message:readonly` 获取单聊、群组消息
   - `im:chat:read` 查看群信息
4. 左侧「凭证与基础信息」，把 **App ID** 告诉你（App ID 不是机密）。

**4.3 连接**：请用户复制 **App Secret**，在他自己的终端运行：

```bash
pbpaste | ~/bobao/bin/bobao feishu login --app cli_xxx
```

然后启动后台，长连接会随之连上：

```bash
~/bobao/bin/bobao install
```

**4.4 打开推送并发布**（新应用才需要）：请用户在开放平台：

1. 「事件与回调」→「订阅方式」点编辑 → 选「使用长连接接收事件」→「保存」。保存前飞书会检查有没有客户端连上，所以必须先做完 4.3。
2. 同一页「添加事件」→ 搜「接收消息」→ 勾选 `im.message.receive_v1` →「添加」。
3. 「版本管理与发布」→「创建版本」，填版本号和说明。要进**外部群**（别的企业的群），勾选「允许机器人被添加到外部群中使用」。「保存」→「确认发布」。公司飞书可能要管理员审批。

**4.5 把机器人拉进群**：请用户在飞书客户端打开每个要播报的群 →「设置」→「群机器人」→「添加机器人」→ 搜应用名。外部群如果加不进去，要请那个群的群主操作。

**检查**：

```bash
~/bobao/bin/bobao feishu groups
```

应该列出这些群。机器人所在的群默认全部会播；只想播其中几个，用 `init --chats 群1,群2`。

## 5. 试听

```bash
~/bobao/bin/bobao test "充值到账" -f 金额=¥99 -f 方式=微信 --play
```

请用户确认听到了声音、音量合适。没装 4.3 的 `install` 的话，现在运行 `~/bobao/bin/bobao install`。

## 6. 确认在运行

```bash
~/bobao/bin/bobao status
```

应该显示「运行中」。用飞书时，日志里会有「飞书推送已连接」。等群里来一条真实通知，看日志里出现「播报」那一行，才算完成。

## 7. 如云配音（可选）

`--engine rooyun` 且不是从配置包导入的，才需要录音：

```bash
~/bobao/bin/bobao rooyun login
```

```bash
~/bobao/bin/bobao voice quote
```

把价格告诉用户，同意后：

```bash
~/bobao/bin/bobao voice record --yes
```

## 出问题时

- 日志：`~/.bobao/bobao.log`
- 群里有通知但没播：`~/bobao/bin/bobao replay --chat 群名` 看每条会怎么处理、为什么不播。
- 「机器人读不到群」：权限没开全，或开了权限后没发布版本。
- 「找不到飞书群」：机器人不在那个群里，或群名写错。
