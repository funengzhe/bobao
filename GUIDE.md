# Bobao 使用说明

给想自己动手、深入定制的人看。只想装上用，把链接交给智能体就行（见 [README](README.md)）。

## 自己装

需要 macOS 自带的 `python3`（没有的话运行 `xcode-select --install`）。Windows（测试版）的准备步骤见 [AGENTS.md 的「Windows」一节](AGENTS.md#windows)。

```bash
git clone https://github.com/funengzhe/bobao ~/bobao
```

```bash
alias bobao=~/bobao/bin/bobao
```

```bash
bobao init
```

```bash
bobao install
```

`init` 问你三个问题，直接回车就用默认值；会列出读哪些 App 的弹窗。`install` 把它装成开机自动运行，并播放安装提示。日志在 `~/.bobao/bobao.log`。

## 四个词

| 词 | 意思 | 例子 |
|---|---|---|
| **来源** | 消息从哪来 | 电脑上的弹窗、飞书群、你的系统（Webhook）、定时提醒 |
| **场景** | 一组现成的提醒，可以多选、可以改 | 上班、生意、开发、直播、生活、空白 |
| **说法** | 每种提醒念什么话 | "注意注意，有人在群里点你名了，快去看看吧" |
| **声音** | 谁来念 | 电脑自带的声音，或你在 RooYun（如云）选的声音 |

| 场景 | 默认会念 | 常见来源 |
|---|---|---|
| `work` 上班 | 有人 @你、会议快开始、审批结果；工作日 18:00 提醒下班 | 弹窗（飞书、企业微信、钉钉、日历）、定时 |
| `business` 生意 | 到账、新订单、大单、退款、日报 | 飞书群、Webhook |
| `dev` 开发 | 上线成功、构建失败、告警、恢复 | Webhook、飞书群 |
| `live` 直播 | 打赏、新粉丝、新订阅 | Webhook、弹窗 |
| `life` 生活 | 外卖、快递、家人消息；每晚 22:00 提醒休息 | 弹窗（微信、邮件、日历）、定时 |
| `blank` 空白 | 什么都不预设 | 任意 |

语气有三种：**正经**（`formal`，简洁）、**活泼**（`playful`，带点俏皮）、**贴心**（`warm`，关心你、夸你）。每个场景有自己的默认语气。

## 常见的定制

对智能体说就行。它改 `~/.bobao/config.json`，再念一遍给你听。

| 你想要 | 改什么 |
|---|---|
| 老板在群里 @我，就说"老板找你啦，快去看看" | 加一条规则：弹窗来自飞书，内容含"@你"，说法写这句 |
| 工作日下午六点提醒我下班 | `bobao remind add 18:00 "六点啦，准时下班" --days 工作日` |
| 到账超过一千块，加一句"大单来啦" | `"bigOrder": {"*": 1000}` |
| 晚上十一点以后别出声，告警除外 | `"schedule": {"quietHours": "23:00-08:00"}`，告警加 `"always": true` |
| 说话温柔一点 / 活泼一点 | 换语气 `"style": "warm"`，或者直接改说法 |
| 这条不用念了 | `bobao replay` 找到是哪条规则，给它加 `"skip": true` |
| 也念微信的弹窗 | `bobao notifications apps` 看 App 名，加进 `sources.notifications.apps` |

## 声音

- **默认用电脑自带的声音**，不用注册、不花钱，装好就能念。
- **想要好听的声音，就接入[RooYun（如云）](https://www.rooyun.com/?ref=9K3XD33J&ch=github-bobao)**：在试听页挑一个，用它把你的全部说法生成一遍，存在本机。之后每次播报都不再花钱，断网也能念。一整套说法通常只要一两个积分。
- **声音可以个性化定制**：试听页的 22 个只是推荐。RooYun（如云）里有更多音色，也可以在 RooYun 克隆你自己、家人的声音，或者描述一个声音让 RooYun 设计。做好后用 `bobao voices --all` 找到它的 id，再 `bobao voice use <id>`。

```bash
bobao rooyun login
```

```bash
bobao voice use 安然
```

```bash
bobao voice record
```

不需要另外安装 RooYun（如云）的工具。`login` 打开 RooYun 的授权页，登录（没有账号就注册）后点「授权」就行。`voice use` 报出用这个声音要生成多少句、多少积分（不想换了：`bobao voice use --cancel`）。`record` 生成，全部生成完才换成新声音，并念一句自我介绍。中途断了，重跑同一条命令就行，已经提交的句子不会重复扣费。以后改了说法、加了提醒，再运行一次 `bobao voice record`，只生成新增的句子。

```bash
bobao voices
```

```bash
bobao review
```

`voices` 列出推荐的 22 个声音。`review` 打开审听页，把你的所有说法放一遍，不满意的标出来重新生成。

## 来源

### 电脑上的弹窗

飞书、企业微信、钉钉、微信、日历、邮件……任何 App 弹出的通知，都能读到标题和预览文字（谁发的、说了什么前几句）。不需要公司开权限，最适合上班的人。

初始化时用 `--apps 飞书,企业微信,微信` 选 App（也可以写 App id 的一部分）。`install` 之后，在 系统设置 → 隐私与安全性 → 完全磁盘访问权限 里打开「Bobao 通知」。看看你的电脑上哪些 App 会弹窗、现在读了哪些：

```bash
bobao notifications apps
```

个人微信、钉钉不做接口或 hook（会有封号风险），只读弹窗。

### 定时提醒

```bash
bobao remind add 18:00 "六点啦，今天辛苦了，准时下班" --days 工作日
```

```bash
bobao remind list
```

`--days` 可以写 `工作日`、`周末`、`每天`，或 `1-5`、`6,7`（1 是周一）。说法里可以用 `{称呼}`。先听一遍用 `bobao remind test 编号 --play`，删除用 `bobao remind remove 编号`。定时提醒不受静音时段限制。

### 飞书群（用你自己的身份）

不建机器人、不用把机器人拉进群，就用你自己的飞书账号读你选的群。Windows 上推荐这样用。

```bash
npm install -g @larksuite/cli       # 先装 Node：winget install OpenJS.NodeJS.LTS（Mac：brew install node）
lark-cli config init --new          # 浏览器里一键建一个只属于你的应用
lark-cli auth login --scope "im:chat:read im:message:readonly im:message.group_msg:get_as_user"   # 只读权限，浏览器里点授权
bobao feishu me                     # 列出你所在的群
bobao feishu me --chats 产品群,项目群 --people
```

- 每 20 秒查一次（`pollSeconds`）；Windows 上一出现飞书弹窗就马上查，几秒内念出来。
- `--people`：人发的消息也按规则念，例如有人 @你、@所有人、请你审批。不加只念机器人发的通知。
- 含「测试」「模拟」的消息默认不念（`skipTitles`）。
- 只申请读群、读消息的权限，不能替你发消息。
- 授权 7 天没用到会过期（电脑一直关着之类），Bobao 会念一句「飞书的登录过期了」，重新运行上面那条 `lark-cli auth login` 就行。
- 一键建的应用叫「你的名字's Feishu Assistant」，名字是飞书起的。想改：打开 [飞书开发者后台](https://open.feishu.cn/app)，在应用信息里改名，再创建版本、发布。不影响 Bobao。

### 飞书群（机器人）

适合自己能建飞书应用的人和团队。在你的飞书里建一个自建应用「飞书播报」，把它的机器人拉进要播报的群：

- 只读被拉进去的群，不用你的个人账号授权。
- 4 项只读权限，在很多企业里不需要审核。
- 长连接接收推送，通知几秒内念出来。不需要服务器。
- 断线、睡眠醒来后会补查一遍；另外每 5 分钟全量检查一次。

机器人能看到群里人发的消息（飞书没有"只读机器人消息"的权限），Bobao 只念机器人发的通知，人的聊天直接丢掉，不保存。一个应用只能在一台电脑上运行。

建应用的每一步见 [AGENTS.md「飞书」](AGENTS.md#飞书用飞书群时)。连接时 App Secret 从剪贴板读，不会出现在对话或配置文件里：

```bash
pbpaste | bobao feishu login --app cli_xxx
```

```bash
bobao feishu groups
```

### 你的系统（Webhook）

```bash
curl -X POST http://127.0.0.1:8766/notify -H 'content-type: application/json' \
  -d '{"title": "充值到账", "platform": "我的店", "fields": {"金额": "¥99", "方式": "微信"}}'
```

请求体里可以直接带 `type`（例如 `"type": "收款"`），这样不经过规则判断。加 `"dry": true` 只返回会念什么，不出声。设置了 `sources.webhook.secret` 的话，请求要用 `X-Bobao-Secret` 请求头带上它。

### 智能体干完活

```bash
bobao agent install claude    # Claude Code：加上钩子（会先备份 ~/.claude/settings.json）
bobao agent install codex     # Codex：在 ~/.codex/config.toml 加一行 notify
```

一个回合超过 60 秒（`agents.minSeconds`），做完就念"智能体把活儿干完啦"；它要你批准命令时念"智能体在等你点头"。Bobao 没在运行时，钩子什么也不做，不影响智能体。

### GitHub 项目

```bash
bobao github add 用户名/仓库名
```

每 10 分钟看一次公开数据（不用登录），有新的 star、fork、Issue 或 PR 就念。第一次只记下现在的数字。

## 好玩的

### 做一句能分享的

```bash
bobao clip make "欢迎来我家玩，饮料在冰箱里自己拿" --voice 安然 --name 欢迎
```

先报价（一句一般几分钱积分），确认后用 RooYun（如云）生成，放到桌面：`Bobao-欢迎.mp3`；装了 ffmpeg 的话还有 `Bobao-欢迎.mp4`，微信、朋友圈里能直接播。`bobao clip list` 看做过的，`play`、`remove` 加名字。

### 让朋友来喊话

```bash
bobao shout on
```

电脑上会打开一个二维码。朋友的手机连上同一个 Wi-Fi，扫码就能打字，这台电脑马上念出来；你做过的句子也在页面上，点一下就播。适合聚会、开店、直播间。

- 打的字默认用电脑自带的声音，免费、立刻念。
- 想用好听的声音：`bobao shout on --voice 安然 --budget 2`，每句现生成，几秒后念，每天最多花 2 积分，超了改用电脑声音。
- 每 3 秒最多一句，每句最多 60 字；地址里有一段随机口令，不在你的 Wi-Fi 里打不开。
- `bobao shout link` 再看一次地址，`bobao shout off` 关掉。

## 搬到另一台电脑

```bash
bobao export
```

得到一个 zip，里面是设置、录好的声音和音效，没有任何密钥。把它和仓库地址一起交给对方，对方（或他的智能体）运行 `bobao import 文件.zip`，再连一次飞书就能用，不用重新生成声音。原来那台记得 `bobao uninstall`。

## 设置文件

所有设置都在 `~/.bobao/config.json`，改完立即生效。只写一行 `{"scenes": ["work"]}` 就能用；下面这些都是在场景的基础上再改。

```jsonc
{
  "scenes": ["work", "life"],            // 可以多个；第一个决定语气和称呼
  "称呼": "老板",
  "style": "warm",                       // formal 正经 / playful 活泼 / warm 贴心
  "engine": "rooyun",                    // rooyun 或 mac（电脑自带）
  "voices": {"default": {"voice": "Chinese (Mandarin)_News_Anchor"}},
  "rules": [                              // 你自己的规则，排在场景的规则前面
    {"when": {"source": "notifications", "app": ["lark"], "text": ["@你"]},
     "type": "提醒", "say": "{称呼}，老板找你啦，快去看看"},
    {"when": {"title": ["新订单"], "channel": ["店铺群"]}, "type": "收款", "platform": "我的店"},
    {"when": {"title": ["周报"]}, "type": "通知", "skip": true}
  ],
  "reminders": [                          // 写了就替换场景自带的定时提醒
    {"at": "18:00", "days": [1, 2, 3, 4, 5], "say": "六点啦，准时下班"}
  ],
  "bigOrder": {"*": 1000},               // 金额达到多少加一句"大单来啦"
  "types": {                              // 按类型改
    "告警": {"always": true, "cooldownMinutes": 10},
    "日报": {"enabled": false}
  },
  "schedule": {"days": [1, 2, 3, 4, 5], "hours": "09:00-21:00", "quietHours": "12:00-13:30"},
  "sources": {
    "notifications": {"enabled": true, "apps": ["lark", "wechat"]},
    "feishu": {"enabled": true, "profile": "bobao", "chats": ["店铺群"]},
    "webhook": {"enabled": true, "port": 8766, "secret": ""}
  }
}
```

**规则的 `when`** 里的词可以带 `{称呼}`（例如 `"@{称呼}"`）。可以用：`source`（`notifications` / `feishu` / `webhook`）、`app`（弹窗来自哪个 App，App id 的一部分）、`channel`（飞书群名）、`title`、`text`、`not`（含这些就不算）。每项写一个列表，含其中任意一个就算。

**说法里的空位**：`{称呼}` `{平台}` `{金额}` `{方式}` `{套餐}` `{名称}`。空位没有值时，它所在的那一小句会自动省掉。

**音效**：`coin` `register` `levelup` `gift` `bubble` `doorbell` `siren` `wahwah` `beeps` `oops` `redalert`（本机合成，免费），也可以用 macOS 系统音效名（`Glass`、`Ping`…）或你自己的音频文件路径。

**分享你的场景**：复制 `packs/scenes/` 里的一个文件，放到 `~/.bobao/packs/scenes/`，在配置里用文件名引用。欢迎提 PR（见 [CONTRIBUTING.md](CONTRIBUTING.md)）。

## 不乱报、不漏报

- 只有规则认出来的消息才出声。看起来很重要但没有规则的，念"有一条新通知"，并在日志里记下，方便补规则。
- 飞书群里人打的字不念。标题含"模拟""测试"的不念。
- 认出来但没念的，日志里都写明原因：不在播报时段、静音时段、冷却中、过期（比如电脑睡眠后补上来的旧消息）、已关闭。
- `bobao test "标题" --text "内容" --play` 看一条消息会被认成什么、念什么。`bobao replay` 把飞书群最近的消息按规则过一遍。`bobao voice plan` 列出你的设置可能说的每一句话，以及哪些还没生成。

```bash
python3 -m unittest discover tests
```

## 文件

| 位置 | 内容 |
|---|---|
| `~/.bobao/config.json` | 你的设置 |
| `~/.bobao/clips/` | 生成好的声音 |
| `~/.bobao/sounds/` | 音效 |
| `~/.bobao/bobao.log` | 日志 |
| `~/.bobao/share/` | 你做的分享句子 |
| `~/.bobao/recording.json` | RooYun（如云）任务记录（保证不重复扣费） |
| `~/.rooyun/credentials.json` | RooYun（如云）登录令牌（权限 0600） |

卸载：`bobao uninstall`，然后删除 `~/.bobao`。
