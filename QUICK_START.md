# 抖音视频下载器 - 快速开始

## 安装

```bash
cd "Web Crawler douyin"

pip install requests playwright
python -m playwright install chromium
```

---

## 下载视频

```bash
# 普通视频 URL
python douyin_downloader.py "https://www.douyin.com/video/7607107248062295784"

# 短链接
python douyin_downloader.py "https://v.douyin.com/xxxxxx/"

# 精选页 URL（jingxuan?modal_id=...）
python douyin_downloader.py "https://www.douyin.com/jingxuan?modal_id=7607107248062295784"

# 图文/note 类型内容同样支持
python douyin_downloader.py "https://www.douyin.com/note/7589200843052764462"

# 指定输出目录
python douyin_downloader.py "https://www.douyin.com/video/7607107248062295784" -o "./downloads"

# 自定义文件名
python douyin_downloader.py "https://www.douyin.com/video/7607107248062295784" -f "我的视频"
```

---

## 常用选项

| 参数 | 说明 |
|------|------|
| `-o DIR` | 指定输出目录（默认：当前目录） |
| `-f NAME` | 自定义文件名（不含扩展名） |
| `--dry-run` | 只解析视频信息，不实际下载 |
| `--cookie-file FILE` | 指定 Cookie 文件路径 |
| `--check-cookie` | 仅检查 Cookie 字段，不下载 |
| `--ffmpeg` | 使用 FFmpeg 优化视频（需已安装） |
| `--retries N` | 失败重试次数（默认 3） |
| `--timeout N` | 请求超时秒数（默认 30） |

---

## Cookie（强烈推荐配置）

配置 Cookie 可以显著降低触发验证码的概率，从浏览器复制登录态后粘贴到 `cookie.txt`。

**支持三种格式：**

**1. Cookie header（推荐，一行粘贴）**
```
sessionid=abc123; sessionid_ss=abc123; sid_tt=abc123; uid_tt=123456
```

**2. 浏览器表格复制格式（Name/Value/Domain/Path 四列，Tab 分隔）**
```
sessionid    abc123    .douyin.com    /
```

**3. Netscape 格式（浏览器插件导出）**
```
.douyin.com	TRUE	/	FALSE	0	sessionid	abc123
```

**使用方式：**
```bash
# 检查 Cookie 是否包含关键字段
python douyin_downloader.py --check-cookie

# 指定 Cookie 文件路径
python douyin_downloader.py "URL" --cookie-file "./my_cookie.txt"
```

程序启动时若 `cookie.txt` 存在会自动加载，无需每次手动指定。

---

## 工作原理

下载时按以下顺序尝试，任一成功即停：

```
1. 多个 API 端点（iesdouyin / douyin aweme/detail）
        ↓ 全部失败（API 需要签名参数，未登录时返回空）
2. 网页 SSR HTML 提取
        ↓ 全部失败（抖音为纯客户端渲染，无 SSR 数据）
3. Playwright 浏览器（终极回退）
   ├─ headless 模式：拦截 aweme/detail API 响应
   └─ 若遇验证码 → 自动切换 headed 模式 → 等你手动滑验证码
```

**Playwright 还会自动判断内容类型：**
- 普通视频：访问 `/video/{id}`
- 图文/note：访问 `/note/{id}`（访问 `/video/{id}` 会得到占位视频 `uuu_265.mp4`）

---

## 在代码中使用

```python
from douyin_downloader import DouyinDownloader

downloader = DouyinDownloader()

# 下载（返回文件路径，失败返回 None）
path = downloader.download(
    url="https://www.douyin.com/video/7607107248062295784",
    output_dir="./downloads",
)

# 仅获取视频信息
video_id = downloader.extract_video_id(url)
info = downloader.get_video_info(video_id)
print(info['title'], info['author'], info['duration'])
```

---

## 项目结构

```
Web Crawler douyin/
├── douyin_downloader.py   # 主程序
├── cookie.txt             # Cookie 文件（可选，推荐配置）
├── requirements.txt       # 依赖列表
├── README.md              # 完整文档
└── QUICK_START.md         # 本文件
```

## 核心功能

1. **多种URL格式支持**：标准URL、短链接等
2. **视频信息提取**：标题、作者、时长等元数据
3. **智能下载**：自动获取最高质量视频
4. **进度显示**：实时下载进度
5. **错误处理**：完善的错误处理和重试机制
6. **Cookie注入**：支持 cookie.txt 注入和关键字段自检
7. **FFmpeg优化**：可选FFmpeg视频优化

## 常见问题

### Q: 安装依赖时遇到SSL证书错误怎么办？
A: 使用以下命令：
```bash
python -m pip install requests --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

### Q: 视频无法下载怎么办？
A: 
1. 检查网络连接
2. 确认URL是否正确
3. 检查视频是否可用（未被删除或设为私密）
4. 尝试使用不同的User-Agent

### Q: 需要登录才能下载的视频怎么办？
A: 推荐使用 `cookie.txt` + `--cookie-file`：
```bash
python douyin_downloader.py --check-cookie --cookie-file "./cookie.txt"
python douyin_downloader.py "https://v.douyin.com/xxxxxx/" --cookie-file "./cookie.txt"
```

如果缺少 `sessionid / sessionid_ss`，脚本会提示 Cookie 不完整。

### Q: 日志里会不会泄露完整 Cookie？
A: 不会。脚本只打印脱敏摘要（例如 `sess...abc`）。

## 注意事项

⚠️ **重要提示**：
- 请遵守相关法律法规和抖音的服务条款
- 仅下载你有权限的视频
- 尊重内容创作者的版权
- 本工具仅供学习和研究使用

## 获取帮助

- 查看完整文档：`README.md`
- 查看命令行帮助：`python douyin_downloader.py -h`
- Cookie自检：`python douyin_downloader.py --check-cookie --cookie-file "./cookie.txt"`

## 更新日志

### v1.0.0 (2026-01-25)
- 初始版本发布
- 实现基本下载功能
- 添加进度显示和错误处理
- 支持批量下载
- 添加FFmpeg优化支持
- 创建完整文档和示例