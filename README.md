# Bobao 定制播报

把飞书群、你自己系统的 Webhook、微信/钉钉/邮件的系统通知，变成**你定制的声音**念出来：说什么、怎么称呼你、用什么语气、谁的声音、配什么音效，全部由你决定。

```
来源（飞书 / Webhook / 系统通知）
  → 规则：这是哪一类通知（收款、套餐、注册、日报、告警、恢复、提醒）
  → 风格：这一类怎么说（正经 / 俏皮 / 撩人，或你自己写）
  → 声音：如云配音（录一次，永久免费播放）或 Mac 自带声音
```

- **不接如云也能用**：默认用 Mac 自带声音，装好就能播。
- **想要好听，就接入如云**：可以选几十种音色，也可以用你自己克隆的声音。一整套声音大约 150–280 段，**一共两三个积分**。录一次存在本机，以后每次播报都不再花钱，断网也能播。
- 所有消息只在你的电脑上处理，不会上传。只有录音时，要念的句子会发给如云。

> 目前只支持 macOS。个人微信、钉钉不做接口或 hook（会有封号风险），只读它们弹出的系统通知。

## 先听一听

**在线试听：<https://funengzhe.github.io/bobao/>**

这个试听页面（源文件在 `docs/`），里面有 9 个场景、7 种风格、48 个如云音色、5 种情绪，以及 Mac 自带的免费声音。每一项都配了一段示例音频，还写好了对应的配置，复制就能用。在本地打开试听页面：

```bash
bobao gallery
```

| 场景 | 适合谁 | 播什么 | 什么时候播 |
|---|---|---|---|
| `shop` 电商店主 | 淘宝/抖店/Shopify/独立站 | 收款、注册、告警、日报、提醒 | 23:00–08:00 静音，告警全天 |
| `saas` 独立开发者 | 订阅产品、API、小程序 | 全部 | 00:00–08:00 静音，告警和恢复全天 |
| `store` 门店 / 餐饮 | 实体店、餐厅、奶茶店 | 收款、告警、提醒 | 09:00–23:00 |
| `sales` 销售团队 | 电销、地推、直播间 | 收款、注册、日报 | 周一到周六 09:00–21:00 |
| `support` 客服团队 | 客服、售后、社群运营 | 提醒（新工单、反馈、审批）、注册 | 工作日 09:00–18:00 |
| `oncall` 运维值班 | SRE、后端值班 | 只播告警和恢复 | 全天 |
| `creator` 主播 / 创作者 | 直播、知识付费 | 打赏、订阅、新粉丝 | 全天 |
| `finance` 财务 / 管理层 | 老板、财务 | 收款、日报、告警 | 工作日 08:30–19:00 |
| `private` 私人专属 | 一个人用 | 全部，撩人风格 | 00:00–08:00 静音，告警全天 |

| 风格 | 听起来像 |
|---|---|
| `formal` 正经播报 | 收款音箱、银行，简洁中性（默认） |
| `anchor` 新闻播报 | 电台整点新闻，字正腔圆 |
| `playful` 俏皮 | 活泼可爱，随机开头结尾，偶尔鼓励一句 |
| `hype` 销售喊麦 | 热血带节奏，成交就喊 |
| `boss` 霸总 | 低沉简短，有点傲 |
| `cute` 萌娃 | 奶声奶气的小朋友 |
| `flirty` 撩人 | 叫哥哥、会撒娇，私人使用 |

## 安装

需要 macOS 自带的 `python3`（装过 Xcode 命令行工具就有）。

```bash
git clone <本仓库> ~/bobao
```

```bash
alias bobao=~/bobao/bin/bobao
```

```bash
bobao init
```

`init` 先让你选一个场景，再确认风格、称呼、声音、通知来源和规则包，每一项都可以直接回车用场景的默认值。之后：

```bash
bobao test "充值到账" -f 金额='$19.9' -f 方式=支付宝 --play
```

```bash
bobao install
```

`install` 会把它装成开机自动运行的后台程序。日志在 `~/.bobao/bobao.log`。

### 接入如云配音

```bash
bobao rooyun login
```

```bash
bobao voice record
```

`login` 会打开如云的授权页，你点「授权」就行，不用复制令牌。`record` 会先列出要录多少句、要多少积分，你确认后才开始录。如云每分钟最多提交 10 句，录一整套大约 20–30 分钟。中途断了，重新运行同一条命令就行，已经提交的句子不会重复扣费。

```bash
bobao review
```

`review` 会打开审听页面，所有说法连音效放一遍。哪一段不满意，点一下，再按「重录」，然后再运行一次 `bobao voice record`，只会重录你标出来的那几段。

## 来源

| 来源 | 能拿到什么 | 怎么开 |
|---|---|---|
| 飞书群 | 机器人卡片的全部字段（金额、方式、套餐…） | 安装并登录 [lark-cli](https://github.com/larksuite/cli)，在 `init` 里选群 |
| Webhook | 你的系统推过来的任意 JSON | 默认开启，`POST http://127.0.0.1:8766/notify` |
| 系统通知 | 任何 App 弹窗的标题和预览文字 | `init` 里选 App；`install` 后给「Bobao 通知」打开完全磁盘访问权限 |

Webhook 示例：

```bash
curl -X POST http://127.0.0.1:8766/notify -H 'content-type: application/json' \
  -d '{"title": "充值到账", "platform": "我的店", "fields": {"金额": "¥99", "方式": "微信"}}'
```

请求体里可以直接带上 `type`（例如 `"type": "收款"`），这样就不经过规则判断。加上 `"dry": true` 只返回会念什么，不出声。如果在配置里设置了 `sources.webhook.secret`，请求时要用 `X-Bobao-Secret` 请求头带上它。

## 定制

所有设置都在 `~/.bobao/config.json`，改完立即生效，不用重启。只写一行 `{"scene": "shop"}` 就能用；下面这些都是在场景的基础上再改。

```jsonc
{
  "scene": "shop",                       // packs/scenes 里的场景，下面的设置会覆盖它
  "称呼": "老板",
  "style": "playful",                    // packs/styles 里的风格包
  "engine": "rooyun",                    // rooyun 或 mac
  "rulePacks": ["generic"],              // packs/rules 里的规则包，按顺序匹配
  "platforms": {                          // 平台名怎么念、只在哪些群生效
    "RooYun": {"say": "如云", "channels": ["店铺群"]}
  },
  "bigOrder": {"*": 1000},               // 金额达到多少加一句"大单来啦"
  "values": {"方式": ["支付宝", "微信"], "套餐": ["基础包"]},   // 录音时要覆盖的取值
  "aliases": {"微信支付": "微信"},         // 卡片上的长名字 → 念出来的短名字
  "types": {                              // 按类型覆盖风格包
    "收款": {"quietHours": "00:00-08:00", "sound": "coin",
             "voice": {"voice": "female-shaonv-jingpin"}},
    "日报": {"enabled": false},
    "告警": {"say": ["{称呼}，{平台}{名称}，快去看看"], "cooldownMinutes": 10}
  },
  "rules": [                              // 你自己的规则，排在规则包前面
    {"when": {"title": ["新订单"], "channel": ["店铺群"]}, "type": "收款", "platform": "我的店"},
    {"when": {"title": ["周报"]}, "type": "通知", "skip": true}
  ],
  "schedule": {                           // 所有类型的播报时间
    "days": [1, 2, 3, 4, 5],             // 周一到周五（7 = 周日）
    "hours": "09:00-18:00",              // 只在这个时段播
    "quietHours": "12:00-13:30"          // 这个时段不播（可以跨午夜，比如 23:00-08:00）
  },
  // 某一类不受全局时间限制，就在 types 里写 "always": true；也可以给某一类单独设 days / hours / quietHours
  "tease": {"chance": 0.3},               // 播完以后接一句话的概率
  "sources": {
    "feishu": {"enabled": true, "chats": ["店铺群"], "botsOnly": true},
    "webhook": {"enabled": true, "port": 8766, "secret": ""},
    "notifications": {"enabled": true, "apps": ["com.tencent.xinWeChat"]}
  }
}
```

**模板里可以用的空位**：`{称呼}` `{平台}` `{平台的}`（有平台名时念"我的店的"，没有就省掉）`{金额}` `{方式}` `{套餐}` `{名称}`（取自规则的 `name`）`{首单}` `{大单}` `{开头}` `{结尾}`（取自风格包的 `pick`，每次随机选一个）。空位没有值时，它所在的那一小句会自动省掉。

**写自己的风格包或规则包**：复制 `packs/styles/playful.json` 或 `packs/rules/generic.json`，放到 `~/.bobao/packs/styles/` 或 `~/.bobao/packs/rules/`，再在配置里用文件名引用它。欢迎提 PR 分享你的包（见 [CONTRIBUTING.md](CONTRIBUTING.md)）。

**音效**：可以用 `coin` `register` `levelup` `gift` `bubble` `doorbell` `siren` `wahwah` `beeps` `oops` `redalert`（都在本机合成，免费），也可以用 macOS 系统音效名（`Glass`、`Ping`…），或者你自己的音频文件路径。

## 保证不乱报、不漏报

- 只有规则认出来的通知才会出声。没有规则的不出声，除非它看起来很重要（`catchAll` 里的关键词），这时会念"有一条新通知"，并在日志里记下"未知通知类型"，方便你补一条规则。
- 飞书群里人打的字不读（`botsOnly`）。标题含"模拟""测试"的不读。
- 每条规则只在它所属平台的群里生效（`platforms.X.channels`），A 平台的告警词不会在 B 平台的群里触发。
- 支付方式、套餐名只念 `values` 里列出、已经录过音的，没录过的就略过不念，不会突然换成另一个声音。
- 凡是认出来但没有播的，日志里都会写明原因：不在播报日、不在播报时段、夜间不播、冷却中、过期未播（比如 Mac 睡眠后补上来的旧消息）、该类型已关闭。
- `bobao replay` 会把群里最近的消息按规则过一遍，看每条会怎么处理；`bobao voice plan` 会列出你的配置可能说的每一句话，以及哪些还没录。
- 测试会验证：任何一张卡片、任何一种随机组合念出来的话，都已经安排了录音。

```bash
python3 -m unittest discover tests
```

## 文件

| 位置 | 内容 |
|---|---|
| `~/.bobao/config.json` | 你的设置 |
| `~/.bobao/clips/` | 录好的声音，以及 `index.json`（按"音色 \| 情绪"分组） |
| `~/.bobao/sounds/` | 音效 |
| `~/.bobao/bobao.log` | 日志 |
| `~/.bobao/recording.json` | 如云任务记录（保证不重复扣费） |
| `~/.rooyun/credentials.json` | 如云登录令牌（权限 0600，和如云官方工具共用） |

卸载：`bobao uninstall`，然后删除 `~/.bobao`。

## 许可

源码公开，免费使用，但**不能拿去卖**。许可证是 [MIT + Commons Clause](LICENSE)：

- **可以**：个人或公司免费使用，包括在自己的业务里播报自己的通知；可以修改、克隆、转发，也可以提交改进。
- **必须**：克隆和转发时保留 [LICENSE](LICENSE) 和里面的版权声明，包括本仓库地址 `https://github.com/funengzhe/bobao`。
- **不可以**：把本软件或基于它改出来的东西，作为收费的产品或服务提供给别人，包括直接出售、收费托管或部署、收费技术支持。需要商用授权，请提 Issue 联系。
- **试听音频**（`docs/audio/`）只用于试听，不得提取、再分发或商用，详见 [docs/audio/LICENSE.md](docs/audio/LICENSE.md)。
- **你自己用如云录的声音**归你所有，按[如云](https://www.rooyun.com)的用户协议使用。
- 提交改进之前，请先看 [CONTRIBUTING.md](CONTRIBUTING.md)。

> 因为有"不能拿去卖"这条限制，本项目不属于 OSI 定义的"开源软件"，准确的说法是"源码公开"。2026-11-02 之前的提交使用 MIT 许可证。
