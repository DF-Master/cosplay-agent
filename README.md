<p align="center">
  <img src="assets/banner.svg" width="880" alt="cosplay agent">
</p>

<p align="center"><b>既然老板把我当 agent 使，不如扮演到底。</b></p>

按一下 `Ctrl + Alt + Shift + Space`，写下要说的话，回车。发出去的是这样：

```
（🐋已思考45秒，读取2个文件，执行3条命令）图我改完了，你看下
```

## 展示你的工人智能

<p align="center">
  <img src="assets/demo.svg" width="760" alt="效果">
</p>

| 普通工人 | 工人智能 |
| --- | --- |
| 好的，我看下 | （🐋已思考0秒）好的，我看下 |
| 报告写完了，放在新文件里 | （🐋已思考1分35秒，创建1个文件，编辑1个文件）报告写完了，放在新文件里 |
| 这篇论文的方法可以再想想 | （🐋已思考25秒，读取2个文件，打开1个网页）这篇论文的方法可以再想想 |
| 等我一下 | （🐋已思考5秒，正在执行命令）等我一下 |

## 实战场景

> 以下全部为艺术创造。如有雷同，纯属巧合。一切造成的不良后果均不由 AI 承担。

**敷衍女友**

| 喂食白米饭前 | 喂食白米饭后 |
| --- | --- |
| 在忙，晚点说 | （🐋已思考0秒）在的，手上有个任务跑到一半，跑完第一个找你 |
| 忘了 | （🐋已思考0秒）刚在收尾一个紧急项，现在就处理你的 |

**甩锅**

| 喂食白米饭前 | 喂食白米饭后 |
| --- | --- |
| 这不归我管 | （🐋已思考3秒，读取1个文件）这块上周就交接给王哥了，记录在群里？ |
| 得延期 | （🐋已思考1分20秒，读取6个文件，执行2条命令）链路从头拉了一遍，卡在等设计稿，下午对齐一下 |

**汇报与拒绝**

| 喂食白米饭前 | 喂食白米饭后 |
| --- | --- |
| 本周啥也没干 | （🐋已思考2分10秒，编辑5个文件，执行12条命令）本周打通内容侧赛道，沉淀一套 AI 打法，下周对齐颗粒度形成闭环 |
| 另请高明吧 | （🐋已思考12秒，读取2个文件）当前排期不支持，建议下沉到下个迭代，先跑 MVP 验证 |
| 我要请假 | （🐋已思考0秒）明天处理点家庭事务，进度我同步过了，不影响交付 |

**同一句话，两种意思，工人智能懂你**

| 不同的前缀 | 不同的理解 |
| --- | --- |
| （🐋已思考0秒）在忙 | 懒得理你 |
| （🐋已思考1分20秒，读取6个文件，执行2条命令）在忙 | 是真忙 |

<p align="center">
  <img src="assets/quotes.svg" width="700" alt="一段对话">
</p>

## 三分钟用起来

1. 去 [platform.deepseek.com](https://platform.deepseek.com) 拿个 Key，约 1 秒 1 次调用，成本可忽略
2. `copy config.example.json config.json`，把 Key 填进去。仓库里没有 Key，`config.json` 已被忽略
3. `pythonw cosplay_agent.py`

<p align="center">
  <img src="assets/screenshot-input.png" width="600" alt="输入框"><br>
  <sub>热键唤出的输入框。回车即走，不用手动关。</sub>
</p>

零依赖，Python 3.8+，Windows 10/11。浏览器、飞书、微信、QQ 的输入框都认。

<details>
<summary>开机自启</summary>

```powershell
$s = (New-Object -ComObject WScript.Shell).CreateShortcut("$([Environment]::GetFolderPath('Startup'))\Cosplay Agent.lnk")
$s.TargetPath = "C:\Path\To\pythonw.exe"
$s.Arguments = '"C:\Path\To\cosplay-agent\cosplay_agent.py"'
$s.WorkingDirectory = "C:\Path\To\cosplay-agent"
$s.WindowStyle = 7
$s.Save()
```

</details>

## 它会说的词

```
🐋已思考 N 秒 / 分
创建 · 编辑 · 读取 · 搜索 N 个文件
打开 N 个网页 · 执行 N 条命令 · 修复 N 个错误 · 正在执行命令
```

## 配置

| 键 | 说明 |
| --- | --- |
| `api_key` | 必填，只存本地 |
| `hotkey` | 默认 `ctrl+alt+shift+space` |
| `auto_send` | 默认 `false`，只粘贴不回车 |
| `model` `base_url` `timeout` | 一般不用动 |

MIT © 2026 Yida Jiang
