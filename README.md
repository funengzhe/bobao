# Bobao 定制播报

**把你在意的消息，用你喜欢的声音、你想听的话念出来。**

| 谁 | 典型提醒 |
|---|---|
| 上班的人 | 有人在群里 @你、会议快开始、审批通过、到点下班 |
| 商家、店主、创业者 | 到账、新订单、大单、退款 |
| 开发、运维 | 上线成功、构建失败、告警、恢复 |
| 主播、创作者 | 打赏、新粉丝、新订阅 |
| 每个人的生活 | 外卖、快递、家人消息、该休息了 |

- **有人替你盯着，而且分轻重**：不用一直看手机。小事轻轻提一句，大事语气一紧。
- **情绪价值**：赚了钱有人夸，加班有人心疼，出事有人陪你急。
- **好玩**：用新闻主播、御姐、机器人、小朋友的声音念日常通知。

每一句念什么、怎么称呼你、谁来念，都由你定。所有消息只在你的电脑上处理，不上传。目前只支持 macOS。

## 先听一听

**<https://funengzhe.github.io/bobao/>**

- **能做什么**：小柚念 18 句不同场景的示范。
- **谁来念**：22 个声音，每个念一句自我介绍。挑一个你喜欢的。

## 最快的装法：交给智能体

把这个链接发给你的智能体（Claude Code、Codex、Cursor 等），说一句：

```
帮我装上 Bobao：https://github.com/funengzhe/bobao
```

它会照着 [AGENTS.md](AGENTS.md) 一步步做，过程中问你三个问题：想听哪些提醒、消息从哪来、怎么称呼你。装好时你会听到一声门铃，然后是一句安装提示。之后想换声音、改说法、加提醒，也直接跟它说。

## 自己装

需要 macOS 自带的 `python3`（没有的话运行 `xcode-select --install`）。

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
| **声音** | 谁来念 | 电脑自带的声音，或你在如云选的声音 |

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
- **想要好听的声音，就接入[如云](https://www.rooyun.com)**：在试听页挑一个，用它把你的全部说法生成一遍，存在本机。之后每次播报都不再花钱，断网也能念。一整套说法通常只要一两个积分。也可以用如云里的其他声音，包括你自己克隆的。

```bash
bobao rooyun login
```

```bash
bobao voice use 安然
```

```bash
bobao voice record
```

`login` 打开如云的授权页，你点「授权」就行。`voice use` 报出用这个声音要生成多少句、多少积分（不想换了：`bobao voice use --cancel`）。`record` 生成，全部生成完才换成新声音，并念一句自我介绍。中途断了，重跑同一条命令就行，已经提交的句子不会重复扣费。以后改了说法、加了提醒，再运行一次 `bobao voice record`，只生成新增的句子。

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
| `~/.bobao/recording.json` | 如云任务记录（保证不重复扣费） |
| `~/.rooyun/credentials.json` | 如云登录令牌（权限 0600） |

卸载：`bobao uninstall`，然后删除 `~/.bobao`。

## 许可

源码公开，免费使用，但**不能拿去卖**。许可证是 [MIT + Commons Clause](LICENSE)：

- **可以**：个人或公司免费使用，包括在自己的业务里播报自己的消息；可以修改、克隆、转发，也可以提交改进。
- **必须**：克隆和转发时保留 [LICENSE](LICENSE) 和里面的版权声明，包括本仓库地址 `https://github.com/funengzhe/bobao`。
- **不可以**：把本软件或基于它改出来的东西，作为收费的产品或服务提供给别人，包括直接出售、收费托管或部署、收费技术支持。需要商用授权，请提 Issue 联系。
- **试听音频**（`docs/audio/`）和安装提示（`assets/`）只用于试听和安装提示，不得提取、再分发或商用，详见 [docs/audio/LICENSE.md](docs/audio/LICENSE.md)。
- **你自己用如云生成的声音**归你所有，按[如云](https://www.rooyun.com)的用户协议使用。
- 提交改进之前，请先看 [CONTRIBUTING.md](CONTRIBUTING.md)。

> 因为有"不能拿去卖"这条限制，本项目不属于 OSI 定义的"开源软件"，准确的说法是"源码公开"。2026-11-02 之前的提交使用 MIT 许可证。
