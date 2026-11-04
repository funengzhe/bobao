# 写给智能体

用户把这个仓库交给你，是想在**这台电脑**（macOS，或测试版的 Windows）上装好 Bobao：把他在意的消息，用他喜欢的声音、他想听的话念出来。你负责安装、按他的要求配置，以及之后帮他改。用户不需要懂任何技术细节，命令由你来运行，不要让他去跑（下面第 2 条红线里的那一步除外）。

下面的命令都写成 `bobao`，实际用 `~/bobao/bin/bobao`（Windows 的 cmd、PowerShell 里用 `%USERPROFILE%\bobao\bin\bobao.cmd`）。

## 目标

只念他要的，用他喜欢的声音，说他想听的话。做到这一点就够了，不用把 Bobao 的功能都装上。他没提的东西，你觉得他可能会喜欢，可以提一句，但要等他说要了才加。

## 红线

只有这几条必须照做。每条后面写了原因，遇到这里没写到的情况，按原因来判断。

1. **花钱前，先给他看要录哪些句子，再报价，等他明确同意。** 用 RooYun（如云）的声音要按句扣积分。`bobao voice quote` 会先列出要录的句子，再报句数、积分和大约要多久。把这些告诉他，他说"可以"再运行 `bobao voice record --yes`。他说过"你看着办"也一样要问，因为花的是他的钱，而且句子是他每天要听的。
2. **密钥不经过你。** 飞书机器人的 App Secret 让他复制后，在**他自己的终端**里运行 `pbpaste | ~/bobao/bin/bobao feishu login --app cli_xxx`。RooYun 和飞书的登录，都由他在浏览器里点「授权」。不要让他把密钥发到对话里，你也不要读取、打印或保存密钥。他已经贴进对话的话，提醒他去重置。
3. **授权链接一次只发一条，发出去就等他点。** 飞书授权和 RooYun 登录用的都是一次性链接：重新发起一次，上一条就作废了，他再点作废的那条就会看到「请求不合法」（错误码 20001）。他没反应时先问他点了没有，不要重发；确实过期了（超过 10 分钟）再重新发起。链接要用**系统浏览器**打开，飞书里的内置浏览器打不开这个页面。
4. **一个飞书机器人应用只在一台电脑上跑。** 飞书每条推送只发给一个连接，两台电脑用同一个应用，会互相漏播。

## 怎么做才顺

- **从他的需求出发，不从我们的场景出发。** 他只说了"你干完活叫我一声"，就只接智能体播报：不需要场景、不要到账、不要定时提醒。场景（上班、生意……）是现成的一组提醒，适合他说得比较宽泛的时候用，比如"生意上的消息都念给我听"。
- **先看真实的消息，再定念什么。** 他说"群里出单了提醒我"，先读这个群最近的消息（`bobao replay --chat 群名`），看清楚有哪几类、谁发的、卡片里有哪些字段、金额是什么币种。然后起草几句他会听到的话给他看，他满意了，再写规则、报价、录音。不要先把能想到的都录一遍，用不上的白花他的钱。
- **能自己查到的不问，该问的才问。** 他的群名、他的飞书名字，你自己查得到。想听什么、喜欢什么样的声音，要问他。
- **先小后大。** 挑声音时先选两三个：`bobao voice listen 名字` 能免费听预设的自我介绍；想用他自己的话听效果，用 `bobao clip make "他的一句话" --voice 名字`，一句几分钱，同样要先报价。他定了声音，再录整套。
- **改完就念给他听。** 改了说法用 `bobao test ... --play`，改了定时提醒用 `bobao remind test 编号 --play`，让他确认。
- **拿不准就问他。** 每条命令的 `--help` 和 [GUIDE.md](GUIDE.md) 里有全部细节，这份说明不会写到每一种情况。

## 你用来看实际情况的命令

| 想知道 | 命令 |
|---|---|
| 某条消息会不会念、念什么、用了哪条规则 | `bobao test "标题" --text "内容" --source ... [--play]` |
| 飞书群最近的消息分别会被念成什么 | `bobao replay --chat 群名` |
| 他现在的设置会说哪些话、哪些还没录 | `bobao voice plan` |
| 换成某个声音要录哪些句子、多少钱 | `bobao voice use 名字`（或 `bobao voice quote`） |
| 定时提醒有哪些，场景建议了哪些 | `bobao remind list` |
| 他的电脑上哪些 App 弹过通知（macOS） | `bobao notifications apps` |
| 后台在不在运行 | `bobao status`；日志在 `~/.bobao/bobao.log` |

## 安装

下面是参考做法。每一步做完都检查一下，不通过就停下来，告诉他是哪一步、什么原因。

### 1. 检查环境

macOS：`/usr/bin/python3 --version`。没有的话运行 `xcode-select --install`，请他在弹窗里点安装，装完再继续。Windows 先看下面的「Windows」一节。

### 2. 下载

```bash
git clone https://github.com/funengzhe/bobao ~/bobao
```

已经有了就更新到最新（设置和录音在 `~/.bobao`，不受影响）：

```bash
git -C ~/bobao fetch origin && git -C ~/bobao reset --hard origin/main
```

### 3. 设置

他给了你一个配置包（`bobao-xxx.zip`，别人用 `bobao export` 导出的）：运行 `bobao import 路径`。里面有设置和录好的声音，不用再生成。

否则先问他想听什么，再按他说的设置：

```bash
~/bobao/bin/bobao init --sources webhook
```

- `--sources`：消息从哪来，可以写几个，用逗号隔开。
  - `notifications`：电脑上的弹窗（**仅 macOS**），例如飞书、企业微信、钉钉、微信、日历、邮件。不用建应用、不碰账号。
  - `feishu`：飞书群。
  - `webhook`：他自己的系统推过来。智能体播报也走它。
  - `remind`：定时提醒。他提到了才加。
- `--scenes`：他说得比较宽泛时，选一组现成的提醒。可选 `work` 上班、`business` 生意、`dev` 开发、`live` 直播、`life` 生活。只要智能体播报或几条自己的规则，就不用选场景。
- 场景里有建议的定时提醒（比如下班、睡觉），**不会自动打开**。`init` 和 `remind list` 会列出来，他想要再用 `bobao remind add` 加。
- 其他参数：`--apps`（读哪些 App 的弹窗，例如 `飞书,微信`）、`--chats`（只播这些飞书群）、`--style formal|playful|warm`（语气）、`--name`（怎么称呼他，他说了才加）。

**检查**：输出里的来源、场景和他说的一致。

### 4. 装成后台运行

```bash
~/bobao/bin/bobao install
```

成功后会播一声风铃，然后小柚念一句安装提示。问他听到没有，没听到就检查音量和输出设备。

### Windows

Windows 版是测试版。能用：飞书（用他自己的身份读）、Webhook、定时提醒、智能体播报、GitHub、喊话页、分享句子、RooYun 的声音。**读不了微信和其他 App 的弹窗**，不要选 `notifications`，并跟他说明。

准备（每项先检查，已经有了就跳过）：
1. **Python**：`py -3 --version`（3.9 以上）。没有的话 `winget install Python.Python.3.12`，装完重新打开终端。系统自带的 `python` 可能只是打开应用商店的快捷方式，以 `py -3 --version` 为准。
2. **Git**：`git --version`，没有的话 `winget install Git.Git`。
3. 下载：`git clone https://github.com/funengzhe/bobao "%USERPROFILE%\bobao"`。
4. **中文语音**：`bobao install` 会检查。没有的话请他打开 设置 → 时间和语言 → 语音 → 添加语音，选「中文（简体，中国）」。
5. 用 RooYun 的声音时要用 ffmpeg 转换录音。电脑上没有的话，第一次录音前 Bobao 会自己从国内镜像下载（约 30 MB），不用另外装。

PowerShell 默认不让运行 `.ps1` 脚本文件，命令直接写在命令行里运行就行。

**后台**：`bobao install` 建一个 Windows 计划任务「Bobao」，登录时自动运行、出错自动重启，和你的终端无关，你的会话结束了它也照常运行。再运行一次 `bobao install` 就是更新并重启，不会出现两个。

**喊话页**：Windows 第一次打开时会弹出防火墙提示，请他勾选「专用网络」并点允许。

### 5. 接上消息来源

**电脑上的弹窗**（macOS，在第 4 步之后做）：请他打开 系统设置 → 隐私与安全性 → 完全磁盘访问权限，打开「Bobao 通知」（不在列表里就点「+」，选 `~/.bobao/app/Bobao 通知.app`）。然后用 `bobao notifications apps` 看他的电脑上哪些 App 弹过通知，问他要听哪些。

**飞书群，用他自己的身份**（不用建机器人，Windows 和 Mac 都能用）：
1. 需要 lark-cli：`lark-cli --version`。没有的话 `npm install -g @larksuite/cli --registry=https://registry.npmmirror.com`；没有 npm 就先装 Node（Windows：`winget install OpenJS.NodeJS.LTS`；Mac：`brew install node`）。
2. 运行 `bobao feishu connect`。它会打开两个页面，第一个建一个只属于他的飞书应用，第二个授权 Bobao 只读他的群消息。先告诉他：一共要点两次「同意」，在系统浏览器里点。这条命令会一直等到两次都点完，所以放在后台运行，从输出里读进度；它在等的时候不要重新运行它（见红线 3）。已经完成的步骤会自动跳过。
3. `bobao feishu me` 列出他的群，问他要播哪些：`bobao feishu me --chats 群1,群2`。人发的消息（@你、@所有人、审批）也要念，就加 `--people`。
4. 读这些群最近的消息（`bobao replay --chat 群名`），再按「怎么做才顺」里说的，跟他一起定要念什么。

**飞书群，用机器人**：见下面的「飞书机器人」一节。

**Webhook**：把这个示例给他或他的开发同事，让他们的系统有消息时发过来：

```bash
curl -X POST http://127.0.0.1:8766/notify -H 'content-type: application/json' \
  -d '{"title": "充值到账", "platform": "我的店", "fields": {"金额": "¥99", "方式": "微信"}}'
```

**定时提醒**：`bobao remind add 18:00 "六点啦，今天辛苦了，准时下班" --days 工作日`。

### 6. 换上好听的声音

电脑自带的声音比较生硬。装好后问他要不要换真人的声音，见下面的「换声音」一节。他说先不换，就不要再劝了。

### 7. 确认在运行

运行 `bobao status`，应该显示「运行中」。等来一条真实的消息，日志里出现「播报」那一行，才算完成。

## 你干完活，叫他一声

他说"你干完活叫我一声"，要接的是**你自己**，也就是正在跟他对话的这个智能体。下面的命令里，`--name` 填你自己的名字（例如 DeepSeek、WorkBuddy、Trae）。Bobao 会念这个名字，第一次用到时把它记下来，换声音、补录时会一起录上。

按下面的顺序，用最先能用的一种，**只用一种**，否则会念两遍：

1. **Claude Code**：`bobao agent install claude`。**Codex**：`bobao agent install codex`。这两条会改 `~/.claude/settings.json` 或 `~/.codex/config.toml`，改之前会备份，动手前先告诉他。
2. **你有"任务结束时运行命令"的设置**（钩子、通知、hooks.json 之类，查你自己的文档）：运行 `bobao agent setup --name 你的名字`，把它给出的命令填进去，再用 `bobao agent done --name 你的名字` 试一下。
3. **没有这种设置，但你的会话会存成文件**：先找到存会话的文件夹，查你自己的文档，或者看一下你的安装目录、用户目录。确认这个文件夹里的文件会随着这次对话增长，然后运行 `bobao agent watch --name 你的名字 --dir 那个文件夹`。Bobao 会盯着这个文件夹：文件停止增长 15 秒，就算这一轮做完。如果你的会话文件在每一轮结束时会写入明确的标记，用 `--done 标记的正则` 告诉它，判断更准，长时间跑工具时也不会提前念。设好后，等这一轮回复完，看日志里有没有「播报」那一行。
4. **以上都不行**：如实告诉他。退一步，可以在工作区的指令文件里约定每轮结束前运行 `bobao agent done --name 你的名字`，但要跟他说清楚：这要靠你每次都记得，不保证每次都念。

要他确认时用 `bobao agent waiting --name 你的名字`。

## 把他的话变成设置

设置在 `~/.bobao/config.json`，改完立即生效，不用重启。先读一遍现有内容再改，不要整个覆盖。每个字段的说明见 [GUIDE.md「设置文件」](GUIDE.md#设置文件)。下面是一些例子，照着思路改，不用照抄：

| 他说 | 可以这样做 |
|---|---|
| "老板在群里 @我就提醒我，说'老板找你啦'" | 在 `rules` 最前面加 `{"when": {"source": "notifications", "app": ["lark"], "text": ["@你", "@{称呼}"]}, "type": "提醒", "say": "{称呼}，老板找你啦，快去看看"}`。只认老板发的，就把老板的名字写进 `title` |
| "群里出单了告诉我，谁出的单、多少钱" | 先 `bobao replay --chat 群名` 看卡片长什么样。按标题和字段写规则，例如 `{"when": {"source": "feishu", "channel": ["群名"], "title": ["出单"]}, "type": "收款", "fields": {"金额": "成单金额"}, "capture": {"出单人": "恭喜(.+?)出单"}, "say": "{称呼}，{出单人}出单啦，成交{金额}"}`。`capture` 从标题里取出名字；用 RooYun 声音时，把群里出现过的名字写进 `values.出单人` 才会录上，没录过的名字会省掉不念 |
| "家里人发消息提醒我" | 生活场景按发消息的人认（弹窗标题）。把家人在微信里的备注名写进那条规则的 `title`：把场景里那条规则复制到 `rules`，再改 `title` |
| "工作日六点提醒我下班" | `bobao remind add 18:00 "..." --days 工作日` |
| "到账超过一千加一句大单" | `"bigOrder": {"*": 1000}` |
| 金额是美元或 USDT | 默认只录"元"。有别的币种，加 `"values": {"货币": ["元", "美元", "USDT"]}`，再补录 |
| "晚上十一点后别出声，告警除外" | `"schedule": {"quietHours": "23:00-08:00"}`，`"types": {"告警": {"always": true}}` |
| "说话温柔一点 / 活泼一点 / 正经一点" | `"style": "warm"` / `"playful"` / `"formal"`，或者直接改那几条说法 |
| "这条不用念了" | `bobao replay`（飞书群）或 `bobao test`（弹窗）找到是哪条规则，给它加 `"skip": true`，或者在它的 `when` 里加 `not` |
| "也念微信的消息" | `bobao notifications apps` 查 App id，加进 `sources.notifications.apps` |
| "有人给我的项目点 star 就告诉我" | `bobao github add 用户名/仓库名`，每 10 分钟看一次，新的 star、fork、Issue 都会念 |

只有已经打开的规则用到的句子，才算进 `bobao voice plan` 和报价。用 RooYun 声音时，改了说法要补录：`bobao voice quote` 先给他看句子和报价，他同意后再运行 `bobao voice record --yes`。

## 换声音

1. 给他试听页 <https://funengzhe.github.io/bobao/>（本地运行 `bobao gallery`），或者运行 `bobao voices` 列出推荐的 22 个声音。声音也可以个性化定制：RooYun（如云）里有更多音色，他也可以在 <https://www.rooyun.com/?ref=9K3XD33J&ch=github-bobao> 克隆自己或家人的声音，或者描述一个声音让 RooYun 设计。做好后运行 `bobao voices --all`（要先登录 RooYun）找到它，再运行 `bobao voice use <音色 id>`。
2. 运行 `bobao rooyun me`，看他有没有登录。没有的话运行 `bobao rooyun login`，请他在打开的 RooYun（如云）页面登录（没有账号就在那里注册），再点「授权」。Bobao 自己连 RooYun，不需要另外装 RooYun 的 skill 或工具。
3. 运行 `bobao voice use 名字`：它会列出要录的句子，报出积分和大约要多久，以及他的可用积分。告诉他，等他同意。可用积分不够的话，请他先到 <https://www.rooyun.com/?ref=9K3XD33J&ch=github-bobao> 充值。这时设置还没改；他不想换了，就运行 `bobao voice use --cancel`。
4. 运行 `bobao voice record --yes` 开始生成。全部生成完才会换成新声音，然后用新声音念一句自我介绍，问他听到没有。中途断了就重跑同一条命令，不会重复扣费。

## 好玩的：做一句分享、让朋友来喊话

- **做一句能发给别人的**（"用安然的声音说'欢迎来我家玩'"）：先运行 `bobao clip make "欢迎来我家玩" --voice 安然`，这一步只报价（一句一般几分钱）。**把价格告诉他，等他同意**，再加 `--yes` 生成。生成好的文件放在桌面，叫 `Bobao-名字.mp3`；有 ffmpeg 的话还会出一个 `.mp4`，发微信、朋友圈用视频版。这句话同时会变成喊话页上的一个按钮。管理这些句子：`bobao clip list / play / remove 名字`。
- **让来家里、店里的朋友喊话**（"有人来玩，我想让他们往电脑上发消息念出来"）：运行 `bobao shout on`。它打开一个二维码页面，朋友用手机（连同一个 Wi-Fi）扫码，打的字由这台电脑念出来，也能点他做好的句子。打的字默认用电脑自带的声音念，免费。想用好听的声音念，加 `--voice 安然 --budget 2`：每句都现生成，会花他的积分。**先说清楚每句大约多少钱（用 `bobao clip make` 报一次价就知道），以及每天最多花 `--budget` 积分，他同意了才加这两个参数。** 关掉：`bobao shout off`。
- 喊话页只在家里的 Wi-Fi 里能打开，地址里有一段随机口令。macOS 第一次打开时可能会问是否允许 python3 接受连接，请他点允许。

## 飞书机器人

适合能建飞书应用的团队：机器人只读被拉进去的群，消息几秒内就能念出来。

**已经有「飞书播报」应用**（例如配置包里写了 App ID）：直接到「连接」。

**还没有应用**：请他在 <https://open.feishu.cn/app> 里操作，你一步步告诉他点哪里：

1. 「创建企业自建应用」，名字叫「飞书播报」。
2. 左侧「添加应用能力」→「机器人」→「添加」。
3. 左侧「权限管理」→「开通权限」，搜索并勾选下面 4 项（都是应用身份、只读），点「确认开通权限」：
   - `im:message.group_msg.include_bot:read` 获取群组中用户和机器人发送的消息（收推送）
   - `im:message.group_msg` 获取群组中所有消息（断线后补查）
   - `im:message:readonly` 获取单聊、群组消息
   - `im:chat:read` 查看群信息
4. 左侧「凭证与基础信息」，请他把 **App ID** 告诉你（App ID 不是机密）。

**连接**：需要 lark-cli（安装见上面的「飞书群，用他自己的身份」）。请他复制 **App Secret**，在他自己的终端里运行下面这行（把 `cli_xxx` 换成他的 App ID，整行由你给他）：

```bash
pbpaste | ~/bobao/bin/bobao feishu login --app cli_xxx
```

再重启后台，长连接会随之连上：`~/bobao/bin/bobao install --quiet`。

**打开推送并发布**（新应用才需要），请他在开放平台上操作：

1. 「事件与回调」→「订阅方式」点编辑 → 选「使用长连接接收事件」→「保存」。保存前飞书会检查有没有客户端连上，所以要先完成上面的连接。
2. 同一页「添加事件」→ 搜「接收消息」→ 勾选 `im.message.receive_v1` →「添加」。
3. 「版本管理与发布」→「创建版本」，填版本号和说明。要进**外部群**（别的企业的群），勾选「允许机器人被添加到外部群中使用」。「保存」→「确认发布」。公司的飞书可能要管理员审批。

**把机器人拉进群**：请他在飞书客户端打开每个要播报的群 →「设置」→「群机器人」→「添加机器人」→ 搜应用名。外部群加不进去的话，要请那个群的群主操作。

**检查**：`bobao feishu groups` 应该列出这些群。机器人所在的群默认全部会播；只想播其中几个，用 `init --chats 群1,群2`。日志里会有「飞书推送已连接」。

## 出问题时

- 日志：`~/.bobao/bobao.log`
- 有消息没念：飞书群用 `bobao replay --chat 群名`，弹窗用 `bobao test "标题" --text "内容" --source notifications --channel App`，看认成了什么类型、为什么没念。
- 弹窗没反应：完全磁盘访问权限没开，或者那个 App 不在 `sources.notifications.apps` 里（用 `bobao notifications apps` 查）。
- 飞书「请求不合法」（20001）：点的是作废的链接，或者是在飞书内置浏览器里打开的。看 `lark-cli auth status`，可能其实已经授权成功了。
- 「机器人读不到群」：权限没开全，或者开了权限之后没发布版本。
- 「找不到飞书群」：机器人不在那个群里，或者群名写错了。
- 声音突然变成电脑自带的：那句话还没录，运行 `bobao voice plan` 看哪些没录，报价后补上。
