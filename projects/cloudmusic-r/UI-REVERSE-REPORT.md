# 网易云音乐 PC 3.1.41 — UI 逆向报告

> 目标:`D:\App\CloudMusic\` 下网易云音乐 3.1.41.205564 (win32/CEF)
> 分析方式:纯静态(安装目录字节级分析,未运行目标、未注入、未修改任何文件)
> 产出目录:`D:\App\CloudMusic_R\`

---

## 1. 一句话结论

网易云 PC 客户端的 UI 是一个**藏在 `.ntpk` 自定义容器里的完整 Web 应用**(React + webpack,部分页面 Next.js)。
容器无加密、无混淆魔数,去掉 100 字节头就是标准 ZIP,可直接解包得到全部界面源码级资源。

---

## 2. 安装架构

```
D:\App\CloudMusic\
├── cloudmusic.exe / cloudmusic.dll (37MB)   ← C++ 壳(CEF host + 业务逻辑)
├── libcef.dll (155MB)                        ← Chromium Embedded Framework
├── resources.pak / v8_context_snapshot.bin   ← CEF 自身资源
├── package/
│   ├── orpheus.ntpk  (37.4MB) ★ 主 UI 资源包 = 100字节头 + ZIP(1411条目)
│   ├── common.skin / dark.skin (NTPK加密皮肤)
│   └── native.ntpk
├── resource/                                 ← 图标、提示音、translation.bin(i18n)
└── locales/                                  ← CEF 语言包
```

运行时存在 3 个 `cloudmusic.exe` 进程(主进程 + 渲染进程 + GPU/工具进程,CEF 典型结构)。

---

## 3. orpheus.ntpk 容器格式(逆向所得)

| 偏移 | 内容 |
|---|---|
| 0x00–0x23 | 36 字节 ASCII hex(校验/标识串,如 `0003f3efaaf702c76a85e4401a22460ea6ac`) |
| 0x24–0x63 | 64 字节二进制(未解析,疑为签名/密钥区) |
| 0x64 起 | **标准 ZIP 数据流**(未加密;EOCD 中央目录 1411 条目) |

解包方法:定位文件尾部 `PK\x05\x06`(EOCD),`zip_start = eocd_pos − cd_offset − cd_size`,截断前 100 字节即得普通 zip。
本次 1345 个文件全部提取成功,0 失败。

---

## 4. UI 技术栈

- **主窗口** `app.html`:React SPA(webpack 4 风格 runtime,`window.webpackJsonp`)
- **次窗口** `subApp.html`:同构 React(弹窗/子窗口宿主)
- **VIP 收银台** `index.html`:**Next.js**(buildId `38J_5S50zSSCPlbcJo-0J`,SSG 导出,含完整预渲染 HTML)
- 其他:`404.html`、`checkdata.html`
- 组件库:`vendors-rudio.pc-new.production.js`(`CMRudio["pc-new"]`,基于 React 的自研 UI 库,含 emotion 风格 atomic CSS)
- 特效:`pub/vendor/wasm/lyric-effect/`(2.8MB WASM,歌词动效时间轴引擎 `NeAVEditorTimeline`)
- 界面文案:代码内不含中文(`\u` 转义也不在主 chunk),走 **i18n 资源**(`resource/translation.bin` + CDN),注释里的中文以 `\uXXXX` 转义保留

**模块规模**:主 chunk `app.chunk`(5.2MB)+ `subApp.chunk`(4.9MB)+ 共享 vendors(3.4MB)+ 220+ 个懒加载功能 chunk + 127 个 CSS 文件。

---

## 5. 界面路由(app.chunk + subApp.chunk 提取,26 条)

```
/:cat /:id /:query /:url          — 动态路由
/album/ /album/batch/             — 专辑
/allSongsList/batch               — 全部歌曲
/audioDetail/ /audioDetail/batch/
/choice/vip                       — VIP 优选
/cloudDisk/track/batch            — 云盘
/community/topic/                 — 社区话题
/dailyRecommend/batch             — 每日推荐
/download/track/batch  /download/voice/batch
/listenToSong/listening           — 一起听
/petManager/detail                — 音乐宠物
/playlist/ /playlist/batch/ /playlist/edit/
/setting/account                  — 账号设置
/trashCan                         — 回收站
/userDetail/ /userDetail/artist/ /userDetail/nickname/ /userDetail/user/
```

---

## 6. UI ↔ 原生桥:OrpheusCommand(核心机制)

源码模块名 `CloudMusicDesktopNativeInft/src/native.ts`(vendor chunk 内保留 JSDoc 注释,含作者 `chenlei06@corp.netease.com`)。

### 平台判定
```js
getClientType() = UA 含 'Chrome/' ? 'win32-cef'
                : window.channel  ? 'darwin-webview'
                : 'darwin-wkwebview'
```

### 三平台通路(`EnvAdapter.doAdapter` 与事件层)
| 平台 | 通路 |
|---|---|
| win32-cef | **`window.channel[method](...args)`**(C++ 侧注入的全局 channel 对象) |
| darwin-webview | 同上(Electron 混合壳) |
| darwin-wkwebview | `window.prompt(JSON.stringify({method, params}))` + `window.MNBCallback` 回调队列 |

### 调用范式(源码注释还原)
```js
// 1) 调用即返回
await nativeCmder.call('os.getOsVer', ...)
// 2) call/callback 分离型(os.ping → os.onping)
const p = nativeCmder.createPromiseFromOrpheusEvent('os.onping')
nativeCmder.call('os.ping', arg)
// 3) 带 id 关联型(musiclibrary.execSql → musiclibrary.onexecsql,filter_result 匹配 task_id)
// 4) 持续事件型(app.setWatchNetStatus → app.onnetstatus,建议 Rx/xstream 封装)
```
实例全局暴露:`window.legacyNativeCmder`;事件路由用魔法前缀 `::[[native-intf]]::`,分隔符 `::::`。
原生侧对照源码(注释泄漏):`cloudmusic_win32:orpheus/src/framework/plugin/os/os.cpp`。

### 原生命令命名空间(1300 条,全文见 native-commands.txt)
`page.* / nm.* / music.* / musiclibrary.* / os.* / app.* / device.* / user.* /
payment.*(wxpay/alipay/iap/nepay) / karaoke.* / playlive.* / record.* /
calendar.* / toast.* / navigator.* / image.* / net.* / log.* / guardian.* …`

样例:`nm.play.getCurrentSong`、`nm.Page.getCurrentPageInfo`、`musiclibrary.execSql`(可执行 SQL 的本地库访问)、`music.bind.cellphoneChanged`、`page.setTopButton`。

---

## 7. orpheus:// 自定义协议面(30 端点,全文见 orpheus-protocol-endpoints.txt)

来自 CSP 白名单 + 代码引用,是 UI 访问本机资源的通道:

```
orpheus://appModal          orpheus://rnpage              (React Native 页面)
orpheus://openurl / openDevicesManage / openVipCashier / openSvipCashier
orpheus://route/musicDesktop[/noHighLight]                (深链路由)
orpheus://settings/bindaccount
orpheus://orpheus/storage/local / storage/customrequest   (存储/API代理)
orpheus://orpheus/pub/index  orpheus://orpheus/pub/public/  (资源镜像)
orpheus://orpheus/wasm/SDK   /wasm/resource                 (WASM 加载)
orpheus://orpheus/customskin /cacheresource /aioresource     (皮肤/缓存)
orpheus://localmusic/lyric  /localmusic/pic                 (本地音乐元数据)
orpheus://file  orpheus://cache  orpheus://image/
orpheus://desktop/mode/using                                (深色模式检测)
orpheus://song|playlist|album|djradio|program|mv|artist/<id>(深链跳转协议)
```

---

## 8. 服务端 API 面(542 端点,全文见 api-endpoints.txt)

从全部 JS 提取 `/api/...` 路径,涵盖:专辑/歌手/歌单、评论、每日推荐、云盘、榜单、黑名单、登录绑定、广告系统、活动、播客/声音、VIP 收银等。

样例:`/api/album/v4/detail`、`/api/artist/mvs`、`/api/chart/detail`、`/api/batch`(批量聚合)、
`/api/ad/sdk/pc/audit`、`/api/cellphone/existence/check`。

---

## 9. 静态资源(已全部提取)

`orpheus/` 目录内:407 PNG + 372 WebP + 165 SVG + 13 ICO + 2 CUR + 1 GIF + 247 JS + 127 CSS + 5 HTML + 1 WASM + 1 JSON。
界面图标集中在 `pub/public/assets/`(960 文件),包括 `svg/home-page/date-*`(按日期换图标)、`svg/menu/setting` 等。

---

## 10. 未完成项(记录在案)

| 项 | 状态 | 说明 |
|---|---|---|
| 皮肤 `.skin` NTPK | **加密** | 头部 `NTPK`+版本,数据非 zlib(暴力扫描 0 块命中);属私有加密格式,主题逻辑可从 CSS/`orpheus://orpheus/customskin` 协议侧入手 |
| `resource/translation.bin` | 未解析 | i18n 文本容器 |
| C++ 壳 `cloudmusic.dll` | 未分析 | `window.channel` 注入方、orpheus:// handler 在此;37MB 原生 PE,需 Ghidra/IDA 走原生逆向 |
| REA 应用图谱 | 部分覆盖 | 大 bundle 超时被取消,静态特征提取已完成主线 |

---

## 11. 复刻界面的可行路径

1. 资源层:直接复用 `orpheus/pub/public/assets/` 图标 + `pub/styles/*.css` 样式
2. 结构层:`index.html`(Next.js 页)是完整渲染好的 HTML,可作像素级参照;`app.html` 结构简单(`#root` 挂载),需起 Chrome DevTools 才能看渲染树
3. 交互层:界面 → 原生的调用全部收敛于 `window.legacyNativeCmder` / `window.channel`,复刻时只需模拟这条通道(如返回假数据)
4. 数据层:542 个 `/api/*` 端点即服务端契约清单

> 分析过程中生成的辅助脚本(`analyze-*.ps1`、`unpack-skin.ps1` 等)保留在工作目录,可复现全部分析。
