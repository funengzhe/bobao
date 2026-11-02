# 写给智能体

用户把这个仓库交给你，是想在**这台 Mac** 上装好 Bobao：把他在意的消息，用他喜欢的声音、他想听的话念出来。你负责安装、按他的要求配置，以及之后帮他改。用户不需要懂任何技术细节，你自己运行命令，不要把命令甩给他去跑（第 4 条规矩里的那一步除外）。

下面的命令都写成 `bobao`，实际用 `~/bobao/bin/bobao`。

## 规矩

1. **先问清楚再动手，但只问三件事**：想听哪些提醒、消息从哪来、怎么称呼他。其余用默认值，装好后再按他的反馈改。
2. **花钱前必须报价**：生成如云声音会用积分。`bobao voice use` 或 `bobao voice quote` 会报出句数、积分和大约要多久，原样告诉用户，等他明确说"可以"，再运行 `bobao voice record --yes`。他之前说过"你看着办"也一样要问。
3. **改完就念给他听**：改了说法用 `bobao test ... --play`，加了定时提醒用 `bobao remind test 编号 --play`，念一遍让他确认。
4. **密钥不经过你**：飞书 App Secret 让用户复制后，在**他自己的终端**里运行 `pbpaste | ~/bobao/bin/bobao feishu login --app cli_xxx`；如云登录他在浏览器里点「授权」。不要让他把密钥发到对话里，也不要读取、打印或保存它。他已经贴进对话的话，提醒他去重置。
5. **一个飞书应用只在一台电脑上跑**。飞书只把每条推送发给一个连接，两台电脑用同一个应用会互相漏播。这个应用以前在别的电脑上用过的话，提醒用户在那台运行 `bobao uninstall`。

## 安装

每一步都有检查方法。检查不通过就停下来，告诉用户哪一步、什么原因，不要跳过。

### 1. 检查环境

```bash
sw_vers -productName
```

必须是 macOS。

```bash
/usr/bin/python3 --version
```

没有的话运行 `xcode-select --install`，请用户在弹窗里点安装，装完再继续。

### 2. 下载

```bash
git clone https://github.com/funengzhe/bobao ~/bobao
```

已经有了就 `git -C ~/bobao pull`。

### 3. 设置：二选一

**A. 用户给了你一个配置包**（`bobao-xxx.zip`，别人用 `bobao export` 导出的）：

```bash
~/bobao/bin/bobao import ~/Downloads/bobao-xxx.zip
```

里面有设置和生成好的声音，导入后不用再生成、也不花钱。按它的提示接着连飞书，然后到第 4 步。

**B. 从头开始**：问用户三个问题。

1. **你主要想听哪些提醒？** 可以多选，也可以直接描述，你来对应：
   - 上班 `work`：有人在群里 @你、会议、审批、到点下班
   - 生意 `business`：到账、订单、大单、退款
   - 开发 `dev`：上线、构建失败、告警
   - 直播 `live`：打赏、新粉丝、订阅
   - 生活 `life`：外卖、快递、家人消息、该休息了
   - 都不像的话用空白 `blank`，再按他说的加规则
2. **这些消息从哪来？** 可以多选：
   - 电脑上的弹窗 `notifications`：飞书、企业微信、钉钉、微信、日历、邮件。上班的人通常只能用这个（公司不让自己建应用）。
   - 飞书群里的机器人通知 `feishu`：他能在飞书里建应用时才选。
   - 他自己的系统 `webhook`：开发者、有自己后台的商家。
   - 定时提醒 `remind`：例如工作日六点提醒下班。
3. **怎么称呼你？** 你、老板、名字都行。

```bash
~/bobao/bin/bobao init --scenes work,life --sources notifications,remind --name 小王
```

可用的参数：`--scenes`（逗号隔开，中文名也行）、`--sources`、`--name`、`--apps`（读哪些 App 的弹窗，见下表；不给就按场景选，会多选一些）、`--style formal|playful|warm`、`--chats`（只播这些飞书群）。用户说了用哪些 App，就把它们写进 `--apps`。

| `--apps` 可以写 | 弹窗的 App id（`bobao test --channel` 用） |
|---|---|
| 飞书 | `com.electron.lark` |
| 企业微信 | `com.tencent.WeWorkMac` |
| 钉钉 | `com.alibaba.DingTalkMac` |
| 微信 | `com.tencent.xinWeChat` |
| 日历 | `com.apple.iCal` |
| 邮件 | `com.apple.mail` |
| 提醒事项 | `com.apple.reminders` |

别的 App 写 App id 的一部分；装好后 `bobao notifications apps` 能看到这台电脑上的真实 id。

**检查**：输出里的场景、来源、称呼、读哪些 App，和用户说的一致。

### 4. 装成后台运行

```bash
~/bobao/bin/bobao install
```

成功后会播一声门铃，然后小柚说一句安装提示（这一句是预先录好的，所以即使用电脑自带的声音也是小柚）。问用户听到没有。没听到就检查音量和输出设备。

### 5. 按来源补设置

**电脑上的弹窗**（要先完成第 4 步）：请用户打开 系统设置 → 隐私与安全性 → 完全磁盘访问权限，在列表里打开「Bobao 通知」（不在列表里就点「+」，选 `~/.bobao/app/Bobao 通知.app`）。然后：

```bash
~/bobao/bin/bobao notifications apps
```

它列出这台电脑最近弹过通知的 App，打勾的是正在读的。问用户还要听哪些，用 `init --apps 原有的,新的` 改。

**飞书群**：见下面「飞书」一节。

**Webhook**：把这个示例给用户或他的开发同事，让他们的系统在有消息时发过来：

```bash
curl -X POST http://127.0.0.1:8766/notify -H 'content-type: application/json' \
  -d '{"title": "充值到账", "platform": "我的店", "fields": {"金额": "¥99", "方式": "微信"}}'
```

**定时提醒**：场景自带的会自动加上。看一下、再按他的要求加：

```bash
~/bobao/bin/bobao remind list
```

```bash
~/bobao/bin/bobao remind add 18:00 "六点啦，今天辛苦了，准时下班" --days 工作日
```

### 6. 念几条给他听

从他选的场景里挑两三条他关心的提醒念出来，确认声音和说法他满意。弹窗用上面表里的 App id：

```bash
~/bobao/bin/bobao test "张三" --text "张三在群里@你" --source notifications --channel com.electron.lark --play
```

```bash
~/bobao/bin/bobao remind test 1 --play
```

输出里会写认成了什么类型、用了哪条规则、念什么。显示「不播：没有规则」说明这条消息他的场景里没有对应的提醒，按需要加一条。`bobao voice plan` 列出他的设置会说的每一句话。

### 7. 确认在运行

```bash
~/bobao/bin/bobao status
```

应该显示「运行中」。等来一条真实消息，日志里出现「播报」那一行，才算完成。

最后告诉用户：现在用的是电脑自带的声音；想换好听的，打开 <https://funengzhe.github.io/bobao/> 挑一个告诉你。

## 把用户的话变成设置

设置在 `~/.bobao/config.json`，改完立即生效，不用重启。先读一遍现有内容再改，不要整个覆盖。字段说明见 README「设置文件」。

| 用户说 | 你做 |
|---|---|
| "老板在群里 @我就提醒我，说'老板找你啦'" | 在 `rules` 最前面加 `{"when": {"source": "notifications", "app": ["lark"], "text": ["@你", "@{称呼}"]}, "type": "提醒", "say": "{称呼}，老板找你啦，快去看看"}`。要限定是谁发的，把老板的名字放进 `title`。企业微信、钉钉的弹窗写的是"@名字"，称呼不是他在公司的名字的话，把名字也加进 `text` |
| "家里人发消息提醒我" | 生活场景按发消息的人认（弹窗标题）。把家人在微信里的备注名加进那条规则的 `title`：复制场景里那条规则到 `rules`，改 `title` |
| "工作日六点提醒我下班" | `bobao remind add 18:00 "..." --days 工作日` |
| "到账超过一千加一句大单" | `"bigOrder": {"*": 1000}` |
| "晚上十一点后别出声，告警除外" | `"schedule": {"quietHours": "23:00-08:00"}`，`"types": {"告警": {"always": true}}` |
| "说话温柔一点 / 活泼一点 / 正经一点" | `"style": "warm"` / `"playful"` / `"formal"`；或者直接改那几条说法 |
| "这条不用念了" | `bobao replay`（飞书群）或 `bobao test`（弹窗）找到是哪条规则，给它加 `"skip": true`，或在它的 `when` 里加 `not` |
| "也念微信的消息" | `bobao notifications apps` 看 App id，加进 `sources.notifications.apps` |
| "再加上生活的提醒" | `bobao init --scenes 原有的,life` |

改完用 `bobao test ... --play` 念给他听。用的是如云声音的话，新说法要生成一次：`bobao voice quote` 报价，他同意后 `bobao voice record --yes`。

## 换声音

1. 给他试听页 <https://funengzhe.github.io/bobao/>（本地：`bobao gallery`），或者运行 `bobao voices` 列出推荐的 22 个声音。他也可以用如云里的其他声音，包括自己克隆的：`bobao voices --all`。
2. `bobao rooyun me` 看有没有登录。没有的话：`bobao rooyun login`，请他在打开的如云页面登录（没有账号就在那里注册）并点「授权」。Bobao 自己连如云，不需要另外安装如云的 skill 或工具。
3. `bobao voice use 安然`：报出用这个声音要生成多少句、多少积分、大约多久，以及他的可用积分。告诉他，等他同意。可用积分不够的话，请他先到 <https://www.rooyun.com> 充值。这时设置还没变；他不想换了就 `bobao voice use --cancel`。
4. `bobao voice record --yes`：生成。全部生成完才换成新声音，并念一句自我介绍，问他听到没有。中途断了重跑同一条命令，不会重复扣费。

## 飞书（用飞书群时）

**已经有「飞书播报」应用**（例如配置包里写了 App ID）：直接到第 3 步。

**还没有应用**：请用户在 <https://open.feishu.cn/app> 里操作，你一步步告诉他点哪里：

1. 「创建企业自建应用」，名字叫「飞书播报」。
2. 左侧「添加应用能力」→「机器人」→「添加」。
3. 左侧「权限管理」→「开通权限」，搜索并勾选下面 4 项（都是应用身份、只读），点「确认开通权限」：
   - `im:message.group_msg.include_bot:read` 获取群组中用户和机器人发送的消息（收推送）
   - `im:message.group_msg` 获取群组中所有消息（断线后补查）
   - `im:message:readonly` 获取单聊、群组消息
   - `im:chat:read` 查看群信息
4. 左侧「凭证与基础信息」，请他把 **App ID** 告诉你（App ID 不是机密）。

**连接**：需要 Node 和 lark-cli：

```bash
command -v lark-cli || npm install -g @larksuite/cli
```

没有 `npm` 的话，先请用户装 Node（<https://nodejs.org>，或 `brew install node`）。然后请用户复制 **App Secret**，在他自己的终端运行（把 `cli_xxx` 换成他的 App ID，你把整行给他）：

```bash
pbpaste | ~/bobao/bin/bobao feishu login --app cli_xxx
```

再重启后台，长连接会随之连上：

```bash
~/bobao/bin/bobao install --quiet
```

**打开推送并发布**（新应用才需要）：请用户在开放平台：

1. 「事件与回调」→「订阅方式」点编辑 → 选「使用长连接接收事件」→「保存」。保存前飞书会检查有没有客户端连上，所以必须先完成上面的连接。
2. 同一页「添加事件」→ 搜「接收消息」→ 勾选 `im.message.receive_v1` →「添加」。
3. 「版本管理与发布」→「创建版本」，填版本号和说明。要进**外部群**（别的企业的群），勾选「允许机器人被添加到外部群中使用」。「保存」→「确认发布」。公司飞书可能要管理员审批。

**把机器人拉进群**：请用户在飞书客户端打开每个要播报的群 →「设置」→「群机器人」→「添加机器人」→ 搜应用名。外部群加不进去的话，要请那个群的群主操作。

**检查**：

```bash
~/bobao/bin/bobao feishu groups
```

应该列出这些群。机器人所在的群默认全部会播；只想播其中几个，用 `init --chats 群1,群2`。日志里会有「飞书推送已连接」。

## 出问题时

- 日志：`~/.bobao/bobao.log`
- 有消息没念：飞书群用 `bobao replay --chat 群名`，弹窗用 `bobao test "标题" --text "内容" --source notifications --channel App`，看认成了什么、为什么不念。
- 弹窗没反应：完全磁盘访问权限没开，或者那个 App 不在 `sources.notifications.apps` 里（`bobao notifications apps` 查）。
- 「机器人读不到群」：权限没开全，或开了权限后没发布版本。
- 「找不到飞书群」：机器人不在那个群里，或群名写错。
- 声音突然变成电脑自带的：那句话还没生成，运行 `bobao voice plan` 看哪些没生成，报价后补上。
