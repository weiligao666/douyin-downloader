# 抖音视频下载器

一个用Python编写的抖音视频下载工具，可以下载抖音上的视频并保存为MP4文件。

## 功能特点

- ✅ 支持多种抖音URL格式（标准URL、短链接、`jingxuan?modal_id=` 精选页等）
- ✅ 自动提取视频ID和元数据（标题、作者、时长等）
- ✅ 多API端点 + Playwright 浏览器双通道回退，智能获取视频下载链接
- ✅ headless 被风控时自动切换有界面模式，支持手动过验证码
- ✅ 支持进度显示和断点续传
- ✅ Windows 文件名安全处理（保留字、长度限制、非法字符）
- ✅ `--dry-run` 模式：只解析视频信息不下载
- ✅ 支持批量下载
- ✅ 可选的FFmpeg视频优化
- ✅ 完善的错误处理和重试机制（单层重试，指数退避）
- ✅ Cookie 注入与自动检测（支持多种格式）
- ✅ 模块化设计，易于扩展

## 系统要求

- Python 3.8+
- requests 库
- playwright 库 + Chromium（API 失败时的浏览器回退）
- 可选：FFmpeg（用于优化视频）

## 安装

### 1. 克隆或下载本仓库

```bash
git clone <仓库地址>
cd "Web Crawler douyin"
```

### 2. 安装Python依赖

```bash
pip install requests playwright
python -m playwright install chromium
```

### 3. 可选：安装FFmpeg

- **Windows**: 从[FFmpeg官网](https://ffmpeg.org/download.html)下载并添加到系统PATH
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg` (Ubuntu/Debian) 或 `sudo yum install ffmpeg` (CentOS/RHEL)

## 使用方法

### 基本使用

```bash
# 交互式使用
python douyin_downloader.py

# 直接指定URL
python douyin_downloader.py "https://www.douyin.com/video/1234567890123456789"

# 精选页 URL（自动提取 modal_id）
python douyin_downloader.py "https://www.douyin.com/jingxuan?modal_id=7607107248062295784"

# dry-run 模式（只解析，不下载）
python douyin_downloader.py --dry-run "https://www.douyin.com/video/1234567890123456789"

# 指定输出目录
python douyin_downloader.py "https://www.douyin.com/video/1234567890123456789" -o "./my_videos"

# 使用FFmpeg优化视频
python douyin_downloader.py "https://www.douyin.com/video/1234567890123456789" --ffmpeg

# 自定义文件名
python douyin_downloader.py "https://www.douyin.com/video/1234567890123456789" -f "我的抖音视频"
```

### 命令行参数

```
usage: douyin_downloader.py [-h] [-o OUTPUT] [-f FILENAME] [--ffmpeg]
                            [--timeout TIMEOUT] [--retries RETRIES]
                            [--retry-delay RETRY_DELAY]
                            [--cookie-file COOKIE_FILE] [--check-cookie]
                            [--dry-run]
                            [url]

抖音视频下载器

positional arguments:
  url                   抖音视频URL（下载模式必填）

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        输出目录 (默认: 当前目录)
  -f FILENAME, --filename FILENAME
                        自定义文件名 (不含扩展名)
  --ffmpeg              使用FFmpeg优化视频
  --timeout TIMEOUT     请求超时时间 (默认: 30秒)
  --retries RETRIES     失败重试次数 (默认: 3)
  --retry-delay RETRY_DELAY
                        重试基准间隔秒数 (默认: 1.0)
  --cookie-file COOKIE_FILE
                        Cookie文件路径（支持 cookie header / Netscape / 浏览器表格复制）
  --check-cookie        仅检查Cookie关键字段，不执行下载
  --dry-run             只解析视频信息（标题/作者/时长/URL），不执行下载
```

### Cookie 注入与自检（推荐）

可在项目目录放置 `cookie.txt`，或通过参数指定：

```bash
# 只检查 Cookie 是否包含关键登录字段
python douyin_downloader.py --check-cookie --cookie-file "./cookie.txt"

# 使用 Cookie 下载视频
python douyin_downloader.py "https://v.douyin.com/xxxxxx/" --cookie-file "./cookie.txt"
```

支持的 `cookie.txt` 格式：

1. **Cookie header**（推荐）
```text
sessionid=xxx; sessionid_ss=xxx; sid_tt=xxx; msToken=xxx
```

2. **Netscape Cookie 文件**（浏览器插件常见导出格式）
3. **浏览器表格复制**（Name/Value/Domain/Path 的 tab 分隔）

脚本会自动进行：
- Cookie 字段注入
- 关键字段检测（`sessionid/sessionid_ss`）
- 脱敏日志输出（避免打印明文敏感值）

## 稳定性增强（关键修复）

当前版本已针对下载成功率做了关键增强：

- ✅ 自动解析 `v.douyin.com` 等短链接重定向，提取真实视频ID
- ✅ 请求失败自动重试（单层指数退避，不再嵌套导致 n² 请求）
- ✅ 多API端点 + 网页 SSR + **Playwright 浏览器**三级回退，提高可用性
- ✅ 视频URL标准化（处理转义字符、`playwm -> play`）
- ✅ 下载时先写入 `.part` 临时文件，成功后原子替换，避免产生损坏文件
- ✅ 检测返回HTML异常页（风控/失效链接），减少"假成功"
- ✅ 时间长度自动归一化（ms → s），不再出现 "143000 秒" 的显示
- ✅ Windows 文件名安全：过滤保留字（CON/NUL/...）、末尾点号/空格、限制长度 120 字符

### Playwright 浏览器回退

当所有 API 端点均无法返回有效数据时，脚本自动启动 Playwright Chromium：

1. **Headless 模式**：先以无界面方式尝试，拦截 `aweme/detail` API 响应 + DOM 提取
2. **Headed 回退**：如果被风控拦截（检测到"验证码"页面），自动关闭 headless 并以有界面模式重开
3. **手动验证码**：弹出浏览器窗口，用户手动完成滑块验证后程序自动继续提取

> 配合 `cookie.txt` 可显著降低触发验证码的概率。

### 在Python代码中使用

```python
from douyin_downloader import DouyinDownloader

# 创建下载器实例
downloader = DouyinDownloader(timeout=30)

# 下载单个视频
result = downloader.download(
    url="https://www.douyin.com/video/1234567890123456789",
    output_dir="./downloads",
    filename="我的视频",
    use_ffmpeg=True
)

if result:
    print(f"下载成功: {result}")
else:
    print("下载失败")

# 分步操作
video_id = downloader.extract_video_id(url)
video_info = downloader.get_video_info(video_id)
print(f"标题: {video_info['title']}")
print(f"作者: {video_info['author']}")
```

### 批量下载

1. 创建URL列表文件 `video_urls.txt`：
```
# 抖音视频URL列表
https://www.douyin.com/video/1234567890123456789
https://v.douyin.com/abc123def/
# 每行一个URL，以#开头的行是注释
```

2. 使用批量下载脚本：
```python
from douyin_downloader import DouyinDownloader

downloader = DouyinDownloader()

with open('video_urls.txt', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#'):
            result = downloader.download(line, output_dir="./batch_downloads")
            if result:
                print(f"✓ 下载成功: {result}")
            else:
                print(f"✗ 下载失败: {line}")
```

## 项目结构

```
Web Crawler douyin/
├── douyin_downloader.py      # 主程序
├── cookie.txt                # Cookie 文件（可选，提升成功率）
├── QUICK_START.md            # 快速开始
├── README.md                 # 使用说明
└── requirements.txt          # 依赖列表
```

## 模块说明

### 1. DouyinDownloader 类

主下载器类，提供完整的视频下载功能：

- `__init__()`: 初始化下载器，可自定义请求头和超时时间
- `extract_video_id()`: 从URL提取视频ID
- `get_video_info()`: 获取视频元数据
- `get_video_url_direct()`: 直接获取视频下载URL（备用方法）
- `download_video()`: 下载视频文件
- `download()`: 主下载方法

### 2. utils.py

工具函数模块：

- `validate_url()`: 验证抖音URL
- `sanitize_filename()`: 清理文件名
- `format_file_size()`: 格式化文件大小
- `create_progress_callback()`: 创建进度回调
- 各种打印函数（`print_success()`, `print_error()`等）

### 3. config.py

配置管理模块：

- `Config`类：管理所有配置项
- 支持从文件加载/保存配置
- 支持点号分隔的键访问（如 `config.get("headers.User-Agent")`）

## 注意事项

### 1. 法律和版权
- 请仅下载有权限的视频，遵守抖音服务条款
- 尊重内容创作者的版权
- 本工具仅供学习和研究使用

### 2. 技术限制
- 抖音可能会更改API，导致脚本失效
- 某些视频可能需要登录才能访问
- 视频URL通常有有效期，需要及时下载

### 3. 反爬虫机制
- 抖音有严格的反爬机制
- 建议合理设置请求间隔
- 可以使用代理IP避免被封

## 故障排除

### 1. 网络错误
```python
# 检查网络连接
from utils import check_internet_connection
if not check_internet_connection():
    print("网络连接失败")
```

### 2. SSL证书错误
```python
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
# 注意：不推荐用于生产环境
```

### 3. 视频URL获取失败
- 尝试使用备用方法：`get_video_url_direct()`
- 检查视频是否已被删除或设为私密
- 尝试使用不同的User-Agent

### 4. FFmpeg未找到
如果FFmpeg未安装，视频仍会下载但不会优化：
```bash
# 手动合并视频（如果需要）
ffmpeg -i temp_video.mp4 -c copy -movflags +faststart output.mp4
```

## 扩展功能

### 1. 添加代理支持
```python
downloader = DouyinDownloader()
downloader.session.proxies = {
    "http": "http://proxy.example.com:8080",
    "https": "http://proxy.example.com:8080",
}
```

### 2. 自定义请求头
```python
custom_headers = {
    "User-Agent": "自定义User-Agent",
    "Referer": "https://www.douyin.com/",
    "Cookie": "你的Cookie",  # 用于需要登录的视频
}
downloader = DouyinDownloader(headers=custom_headers)
```

### 3. 添加日志记录
```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='douyin_downloader.log'
)
```

## 更新日志

### v1.1.0 (2026-03-10)
- 新增 `--dry-run` 模式（只解析不下载）
- 新增 Playwright 浏览器回退（headless → headed 自动切换）
- 支持 `jingxuan?modal_id=` 精选页 URL 格式
- 修复双重重试嵌套导致 n² 请求的问题
- 修复时长显示（ms 自动归一化为 s）
- 增强 Windows 文件名安全处理（保留字/长度/末尾字符）
- 改进 SSR JSON 提取（多正则模式 + `re.DOTALL`）
- 修复 `makedirs` 并发竞态（`exist_ok=True`）

### v1.0.0 (2026-01-25)
- 初始版本发布
- 实现基本下载功能
- 添加进度显示和错误处理
- 支持批量下载
- 添加FFmpeg优化支持
- 创建完整文档和示例

## 许可证

本项目仅供学习和研究使用。请遵守相关法律法规和抖音的服务条款。

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 免责声明

本工具开发者不对使用本工具下载内容造成的任何法律问题负责。用户应自行承担使用风险。