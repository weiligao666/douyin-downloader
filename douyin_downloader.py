#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抖音视频下载器
基于抖音网页版实现视频下载功能
"""

import requests
import json
import re
import os
import sys
import time
from urllib.parse import urlparse, parse_qs, unquote
import subprocess
from requests.exceptions import RequestException


class DouyinDownloader:
    """抖音视频下载器主类"""
    
    def __init__(self, headers=None, timeout=30, max_retries=3, retry_delay=1.0):
        """
        初始化下载器
        
        Args:
            headers: 自定义请求头
            timeout: 请求超时时间
            max_retries: 最大重试次数
            retry_delay: 重试基准间隔（秒）
        """
        self.session = requests.Session()
        self.timeout = timeout
        self.max_retries = max(1, int(max_retries))
        self.retry_delay = max(0.2, float(retry_delay))
        self.last_resolved_url = None
        
        # 默认请求头
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        if headers:
            self.headers.update(headers)
            
        self.session.headers.update(self.headers)
        self.loaded_cookie_keys = set()
        # 说明：重试逻辑统一在 _request_with_retry 中实现，
        # 避免对运行环境中的 urllib3 版本/编辑器解析产生耦合。

    def _mask_value(self, value, head=4, tail=3):
        """脱敏显示敏感值"""
        if value is None:
            return ""
        value = str(value)
        if len(value) <= head + tail + 2:
            return "*" * len(value)
        return f"{value[:head]}...{value[-tail:]}"

    def _parse_cookie_text(self, text):
        """解析 cookie 文本，兼容 raw/header、Netscape、表格复制格式"""
        entries = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # 跳过注释（保留 Netscape 的 #HttpOnly_ 行）
            if line.startswith('#') and not line.startswith('#HttpOnly_'):
                continue

            # 1) 处理 tab 分隔格式（Netscape 或浏览器表格复制）
            if '\t' in raw_line:
                cols = [c.strip() for c in raw_line.split('\t')]

                # Netscape cookie 格式:
                # domain, include_subdomain, path, secure, expires, name, value
                if len(cols) >= 7 and (cols[0].startswith('#HttpOnly_') or cols[1] in ('TRUE', 'FALSE')):
                    domain = cols[0].replace('#HttpOnly_', '').strip()
                    path = cols[2].strip() if cols[2].strip() else '/'
                    name = cols[5].strip()
                    value = cols[6].strip()
                    if name:
                        entries.append({
                            'name': name,
                            'value': value,
                            'domain': domain or None,
                            'path': path,
                        })
                    continue

                # 常见浏览器复制表格格式：name value domain path ...
                if len(cols) >= 2:
                    name = cols[0].strip()
                    value = cols[1].strip()
                    domain = cols[2].strip() if len(cols) >= 3 and cols[2].strip() else None
                    path = cols[3].strip() if len(cols) >= 4 and cols[3].strip().startswith('/') else '/'
                    if name and '=' not in name:
                        entries.append({
                            'name': name,
                            'value': value,
                            'domain': domain,
                            'path': path,
                        })
                        continue

            # 2) 处理 Cookie header 字符串（k=v; k2=v2）
            parts = [p.strip() for p in line.split(';') if p.strip()]
            for part in parts:
                if '=' not in part:
                    continue
                key, value = part.split('=', 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    continue

                # 忽略 cookie 属性键
                if key.lower() in {'path', 'domain', 'expires', 'max-age', 'secure', 'httponly', 'samesite'}:
                    continue

                entries.append({
                    'name': key,
                    'value': value,
                    'domain': None,
                    'path': '/',
                })

        # 去重：同名同域保留最后一条
        dedup = {}
        for item in entries:
            dedup[(item['name'], item.get('domain') or '')] = item
        return list(dedup.values())

    def set_cookies(self, cookie_entries):
        """向 Session 注入 cookies"""
        applied = 0
        latest_value_by_name = {}

        for item in cookie_entries:
            name = item.get('name')
            value = item.get('value', '')
            domain = item.get('domain')
            path = item.get('path') or '/'

            if not name:
                continue

            try:
                if domain:
                    self.session.cookies.set(name, value, domain=domain, path=path)
                else:
                    self.session.cookies.set(name, value, path=path)
                applied += 1
                latest_value_by_name[name] = value
            except Exception:
                continue

        self.loaded_cookie_keys = set(latest_value_by_name.keys())

        # 仅打印脱敏摘要
        preview_keys = sorted(list(self.loaded_cookie_keys))[:8]
        if preview_keys:
            preview = ', '.join(
                [f"{k}={self._mask_value(latest_value_by_name.get(k, ''))}" for k in preview_keys]
            )
            print(f"已注入Cookie字段 {len(self.loaded_cookie_keys)} 个（脱敏预览）: {preview}")
        else:
            print("未注入任何Cookie字段")

        return applied

    def load_cookies_from_file(self, cookie_file):
        """从文件加载并注入 Cookie"""
        if not os.path.exists(cookie_file):
            raise FileNotFoundError(f"Cookie文件不存在: {cookie_file}")

        with open(cookie_file, 'r', encoding='utf-8') as f:
            text = f.read()

        cookie_entries = self._parse_cookie_text(text)
        if not cookie_entries:
            raise ValueError("Cookie文件中未解析到有效字段")

        applied = self.set_cookies(cookie_entries)
        print(f"Cookie注入完成: {applied} 条")
        return applied

    def check_cookie_health(self):
        """检查 Cookie 关键字段完整性"""
        current_keys = {c.name for c in self.session.cookies}
        if not current_keys:
            print("未检测到已加载Cookie")
            return False

        critical = ['sessionid', 'sessionid_ss']
        important = ['sid_tt', 'sid_guard', 'uid_tt', 'uid_tt_ss', 'passport_csrf_token', 'msToken']

        missing_critical = [k for k in critical if k not in current_keys]
        missing_important = [k for k in important if k not in current_keys]

        print(f"当前Cookie字段数: {len(current_keys)}")
        if missing_critical:
            print(f"⚠️ 缺少关键登录字段: {', '.join(missing_critical)}")
            if missing_important:
                print(f"ℹ️  另外缺少常见辅助字段: {', '.join(missing_important)}")
            return False

        print("✅ 已检测到关键登录字段（sessionid/sessionid_ss）")
        if missing_important:
            print(f"ℹ️  缺少部分辅助字段: {', '.join(missing_important)}")
        return True

    def _extract_first_url(self, text):
        """从文本中提取第一个URL（兼容分享口令里夹杂中文）"""
        if not text:
            return None
        match = re.search(r'https?://[^\s]+', text)
        return match.group(0).rstrip('。.,，!！?？)）') if match else text.strip()

    def _normalize_video_url(self, url):
        """清洗并标准化视频URL"""
        if not url:
            return None

        # 过滤不可下载的协议和占位视频
        if url.startswith('blob:'):
            return None
        if self._is_placeholder_video(url):
            return None

        clean_url = (
            url.replace('\\u002F', '/')
            .replace('\\/', '/')
            .replace('\\u0026', '&')
            .replace('\\u003D', '=')
            .replace('&amp;', '&')
        )
        clean_url = unquote(clean_url)

        if clean_url.startswith('//'):
            clean_url = 'https:' + clean_url

        # 常见去水印替换
        clean_url = clean_url.replace('playwm', 'play')
        return clean_url

    def _normalize_duration_seconds(self, duration_value):
        """将接口时长值规范为秒（抖音常见为毫秒）"""
        try:
            value = float(duration_value)
        except (TypeError, ValueError):
            return 0.0

        if value < 0:
            return 0.0

        # 抖音接口常返回毫秒，超过1000通常可按毫秒处理
        if value >= 1000:
            value = value / 1000.0

        return round(value, 2)

    def _request_with_retry(self, url, headers=None, stream=False, allow_redirects=True):
        """请求封装：应用业务层重试与退避"""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    stream=stream,
                    allow_redirects=allow_redirects,
                )

                # 明确把高频失败状态纳入重试
                if response.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {response.status_code}")
                return response
            except RequestException as e:
                last_error = e
                if attempt >= self.max_retries:
                    break
                sleep_s = self.retry_delay * (2 ** (attempt - 1))
                print(f"请求失败，{sleep_s:.1f}秒后重试({attempt}/{self.max_retries}): {e}")
                time.sleep(sleep_s)

        raise last_error if last_error else RuntimeError("请求失败")

    def resolve_share_url(self, url):
        """解析短链/分享链接，返回最终URL"""
        candidate = self._extract_first_url(url)
        if not candidate:
            raise ValueError("URL为空")

        response = self._request_with_retry(candidate, allow_redirects=True)
        final_url = response.url or candidate
        self.last_resolved_url = final_url
        return final_url

    def _extract_video_url_from_item(self, item):
        """从API返回的item结构中提取视频URL"""
        video = item.get('video', {}) if isinstance(item, dict) else {}
        candidate_urls = []

        # 常见字段
        for key in ('play_addr', 'play_addr_h264', 'play_addr_265', 'download_addr', 'play_api'):
            addr = video.get(key, {})
            if isinstance(addr, dict):
                candidate_urls.extend(addr.get('url_list', []) or [])

        # 码率列表中也常有更稳的URL
        bit_rates = video.get('bit_rate', [])
        if isinstance(bit_rates, list):
            for br in bit_rates:
                if not isinstance(br, dict):
                    continue
                play_addr = br.get('play_addr', {})
                if isinstance(play_addr, dict):
                    candidate_urls.extend(play_addr.get('url_list', []) or [])

        for raw_url in candidate_urls:
            clean_url = self._normalize_video_url(raw_url)
            if clean_url and clean_url.startswith('http'):
                return clean_url
        return None

    def _extract_video_url_from_html(self, html):
        """从网页HTML中提取视频URL（备用）"""
        if not html:
            return None

        patterns = [
            r'"playAddr"\s*:\s*"([^\"]+)"',
            r'"downloadAddr"\s*:\s*"([^\"]+)"',
            r'"video_url"\s*:\s*"([^\"]+)"',
            r'src="(https?://[^\"]+\.mp4[^\"]*)"',
            r'"url_list"\s*:\s*\[\s*"([^\"]+)"',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html)
            for raw_url in matches:
                clean_url = self._normalize_video_url(raw_url)
                if clean_url and clean_url.startswith('http') and ('mp4' in clean_url or 'play' in clean_url):
                    return clean_url

        # 从 SSR 数据中尽力提取
        ssr_patterns = [
            r'window\._SSR_HYDRATED_DATA\s*=\s*(\{.*?\})\s*;?\s*</script>',
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>',
        ]

        for ssr_pattern in ssr_patterns:
            match = re.search(ssr_pattern, html, flags=re.DOTALL)
            if not match:
                continue

            try:
                data = json.loads(match.group(1))

                def deep_find_url(obj, depth=0):
                    if depth > 12:
                        return None
                    if isinstance(obj, dict):
                        for _, value in obj.items():
                            if isinstance(value, str):
                                clean_url = self._normalize_video_url(value)
                                if clean_url and clean_url.startswith('http') and ('mp4' in clean_url or 'play' in clean_url):
                                    return clean_url
                            elif isinstance(value, (dict, list)):
                                found = deep_find_url(value, depth + 1)
                                if found:
                                    return found
                    elif isinstance(obj, list):
                        for item in obj:
                            found = deep_find_url(item, depth + 1)
                            if found:
                                return found
                    return None

                found = deep_find_url(data)
                if found:
                    return found
            except Exception:
                continue

        return None
    
    def extract_video_id(self, url):
        """
        从抖音URL提取视频ID
        
        Args:
            url: 抖音视频URL
            
        Returns:
            str: 视频ID
        """
        clean_url = self._extract_first_url(url)
        if not clean_url:
            raise ValueError("URL为空")

        # 短链接先解析重定向
        resolved_url = clean_url
        try:
            host = (urlparse(clean_url).netloc or '').lower()
            if 'v.douyin.com' in host or 'iesdouyin.com' in host:
                resolved_url = self.resolve_share_url(clean_url)
                print(f"   短链解析后URL: {resolved_url}")
        except Exception:
            # 解析失败时继续按原URL提取
            resolved_url = clean_url

        self.last_resolved_url = resolved_url

        # 处理多种抖音URL格式
        patterns = [
            r'/video/(\d{8,25})',
            r'/share/video/(\d{8,25})',
            r'/note/(\d{8,25})',
            r'aweme_id=(\d{8,25})',
            r'item_id=(\d{8,25})',
            r'video_id=(\d{8,25})',
            r'/(\d{8,25})(?:[/?]|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, resolved_url)
            if match:
                return match.group(1)
        
        # 尝试从查询参数中获取
        parsed = urlparse(resolved_url)
        query_params = parse_qs(parsed.query)
        
        # 检查常见参数（含精选页 modal_id）
        for param in ['modal_id', 'video_id', 'id', 'vid', 'itemId', 'aweme_id', 'item_id']:
            if param in query_params:
                return query_params[param][0]
        
        raise ValueError(f"无法从URL中提取视频ID: {clean_url}")
    
    def get_video_info(self, video_id):
        """
        获取视频信息
        
        Args:
            video_id: 视频ID
            
        Returns:
            dict: 视频信息
        """
        # 抖音API端点（可能会变化）
        api_urls = [
            f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={video_id}",
            f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}",
            f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}&aid=6383",
            f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}&device_platform=webapp",
        ]

        api_headers = {
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json, text/plain, */*",
        }
        
        for api_url in api_urls:
            try:
                print(f"尝试API: {api_url}")
                response = self._request_with_retry(api_url, headers=api_headers)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        continue
                    
                    # 检查不同API的响应格式
                    if 'item_list' in data and len(data['item_list']) > 0:
                        item = data['item_list'][0]
                    elif 'aweme_detail' in data:
                        item = data['aweme_detail']
                    else:
                        continue
                    
                    # 提取视频信息
                    normalized_duration = self._normalize_duration_seconds(item.get('duration', 0))

                    video_info = {
                        'video_id': video_id,
                        'title': item.get('desc', '无标题'),
                        'author': item.get('author', {}).get('nickname', '未知作者'),
                        'author_id': item.get('author', {}).get('uid', ''),
                        'create_time': item.get('create_time', 0),
                        'duration': normalized_duration,
                        'statistics': item.get('statistics', {}),
                        'video_url': None,
                        'cover_url': item.get('video', {}).get('cover', {}).get('url_list', [None])[0],
                    }
                    
                    # 获取视频URL
                    video_info['video_url'] = self._extract_video_url_from_item(item)
                    
                    return video_info
                    
            except Exception as e:
                print(f"API请求失败: {e}")
                continue
        
        raise ValueError("无法获取视频信息，请检查视频ID或网络连接")

    # ------------------------------------------------------------------
    # Playwright 浏览器回退（处理 JS 渲染 + 签名参数）
    # ------------------------------------------------------------------

    @staticmethod
    def _is_placeholder_video(url):
        """检测是否为抖音占位/默认视频 URL"""
        if not url:
            return False
        placeholder_markers = ['uuu_265.mp4', '/uuu_', 'douyin-pc-web/uuu_']
        return any(m in url for m in placeholder_markers)

    def _get_video_info_playwright(self, video_id, original_url=None):
        """
        使用 Playwright 加载视频页面，拦截 API 响应或从 DOM 提取视频信息。
        作为 requests 方案的终极回退。

        会按顺序尝试: 原始 URL → /video/{id} → /note/{id}
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("   Playwright 未安装，跳过浏览器回退")
            return None

        # 构建候选 URL 列表（去重）
        video_page = f"https://www.douyin.com/video/{video_id}"
        note_page = f"https://www.douyin.com/note/{video_id}"
        candidate_urls = []
        if original_url and original_url != video_page:
            candidate_urls.append(original_url)
        candidate_urls.append(video_page)
        candidate_urls.append(note_page)

        page_url = candidate_urls[0]
        print(f"   启动浏览器访问: {page_url}")

        video_info = {
            'video_id': video_id,
            'title': '未命名视频',
            'author': '未知作者',
            'author_id': '',
            'create_time': 0,
            'duration': 0,
            'statistics': {},
            'video_url': None,
            'cover_url': None,
        }

        captured_detail = {}  # 用于存储拦截到的 API 响应

        def _on_response(response):
            """拦截 aweme/detail 接口响应"""
            try:
                url = response.url
                if 'aweme/v1/web/aweme/detail' in url or 'aweme/iteminfo' in url:
                    if response.status == 200:
                        data = response.json()
                        if data:
                            captured_detail['data'] = data
            except Exception:
                pass

        def _build_cookie_list():
            """从 session 构建 Playwright 兼容的 cookie 列表"""
            cookie_list = []
            for c in self.session.cookies:
                domain = c.domain if c.domain else '.douyin.com'
                if '.' not in domain:
                    continue
                cookie_list.append({
                    'name': c.name,
                    'value': c.value,
                    'domain': domain,
                    'path': c.path if c.path else '/',
                })
            return cookie_list

        def _extract_from_page(page):
            """从已加载的页面提取视频信息"""
            # 优先从拦截到的 API 响应提取
            if captured_detail.get('data'):
                data = captured_detail['data']
                item = None
                if 'item_list' in data and data['item_list']:
                    item = data['item_list'][0]
                elif 'aweme_detail' in data:
                    item = data['aweme_detail']

                if item and isinstance(item, dict):
                    video_info['title'] = item.get('desc', video_info['title'])
                    video_info['author'] = item.get('author', {}).get('nickname', video_info['author'])
                    video_info['author_id'] = item.get('author', {}).get('uid', '')
                    video_info['create_time'] = item.get('create_time', 0)
                    video_info['duration'] = self._normalize_duration_seconds(item.get('duration', 0))
                    video_info['statistics'] = item.get('statistics', {})
                    video_info['cover_url'] = item.get('video', {}).get('cover', {}).get('url_list', [None])[0]
                    video_info['video_url'] = self._extract_video_url_from_item(item)

            # 如果 API 拦截没拿到视频 URL，从 DOM 提取
            if not video_info['video_url']:
                try:
                    video_el = page.query_selector('video source') or page.query_selector('video')
                    if video_el:
                        src = video_el.get_attribute('src')
                        if src and not src.startswith('blob:'):
                            video_info['video_url'] = self._normalize_video_url(src)
                except Exception:
                    pass

            # 从 DOM 补充标题/作者
            if video_info['title'] == '未命名视频':
                try:
                    title_el = page.query_selector('[data-e2e="video-desc"]') or page.query_selector('title')
                    if title_el:
                        text = title_el.inner_text().strip()
                        if text and text != '抖音':
                            video_info['title'] = text[:100]
                except Exception:
                    pass

            if video_info['author'] == '未知作者':
                try:
                    author_el = page.query_selector('[data-e2e="video-author-name"]')
                    if author_el:
                        video_info['author'] = author_el.inner_text().strip()[:50]
                except Exception:
                    pass

        def _is_captcha_page(page):
            """检测是否命中验证码页面"""
            try:
                title = page.title()
                if '验证' in title:
                    return True
                if page.query_selector('#captcha-verify-image') or page.query_selector('.captcha_verify_container'):
                    return True
            except Exception:
                pass
            return False

        pw = None
        browser = None
        try:
            pw = sync_playwright().start()

            # 第一轮：headless 尝试
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ],
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            cookie_list = _build_cookie_list()
            if cookie_list:
                context.add_cookies(cookie_list)

            page = context.new_page()
            page.on('response', _on_response)
            page.goto(page_url, wait_until='domcontentloaded', timeout=20000)

            try:
                page.wait_for_selector('video', timeout=10000)
            except Exception:
                pass

            if not _is_captcha_page(page):
                _extract_from_page(page)
                # 检查是否拿到的是占位视频
                if video_info['video_url'] and not self._is_placeholder_video(video_info['video_url']):
                    print(f"   浏览器提取完成(headless): 标题='{video_info['title'][:30]}' URL=有")
                    return video_info

                # 占位视频或无 URL → 尝试其余候选 URL
                for alt_url in candidate_urls[1:]:
                    if alt_url == page_url:
                        continue
                    print(f"   尝试备选页面: {alt_url}")
                    captured_detail.clear()
                    video_info['video_url'] = None
                    video_info['title'] = '未命名视频'
                    video_info['author'] = '未知作者'
                    page.goto(alt_url, wait_until='domcontentloaded', timeout=20000)
                    try:
                        page.wait_for_selector('video, .note-content, [data-e2e="note-slide"]', timeout=10000)
                    except Exception:
                        pass
                    if not _is_captcha_page(page):
                        _extract_from_page(page)
                        if video_info['video_url'] and not self._is_placeholder_video(video_info['video_url']):
                            print(f"   浏览器提取完成(headless): 标题='{video_info['title'][:30]}' URL=有")
                            return video_info

            # headless 失败或遇到验证码 → 关闭 headless，切换有界面模式
            browser.close()
            browser = None
            captured_detail.clear()
            video_info['video_url'] = None
            video_info['title'] = '未命名视频'
            video_info['author'] = '未知作者'

            print("   ⚠️ headless 被风控拦截，切换为有界面模式...")
            print("   📢 如果弹出验证码，请在浏览器里手动完成验证，完成后程序会自动继续")

            browser = pw.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ],
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            if cookie_list:
                context.add_cookies(cookie_list)

            page = context.new_page()
            page.on('response', _on_response)

            # headed 模式：按候选列表逐一尝试
            for try_url in candidate_urls:
                captured_detail.clear()
                video_info['video_url'] = None
                video_info['title'] = '未命名视频'
                video_info['author'] = '未知作者'

                print(f"   headed 访问: {try_url}")
                page.goto(try_url, wait_until='domcontentloaded', timeout=30000)

                # 等待用户通过验证码 → 页面出现 video 标签
                try:
                    page.wait_for_selector('video, .note-content, [data-e2e="note-slide"]', timeout=60000)
                except Exception:
                    pass

                _extract_from_page(page)
                if video_info['video_url'] and not self._is_placeholder_video(video_info['video_url']):
                    print(f"   浏览器提取完成(headed): 标题='{video_info['title'][:30]}' URL=有")
                    return video_info
                print(f"   该页面未获取到有效视频 URL，尝试下一个...")

            # 所有候选都试过了
            if video_info['video_url'] and self._is_placeholder_video(video_info['video_url']):
                video_info['video_url'] = None
                print("   ⚠️ 该内容可能是图文笔记，不包含可下载的视频")
            print(f"   浏览器提取完成(headed): 标题='{video_info['title'][:30]}' URL={'有' if video_info['video_url'] else '无'}")
            return video_info

        except Exception as e:
            print(f"   Playwright 回退失败: {e}")
            return None
        finally:
            try:
                if browser:
                    browser.close()
                if pw:
                    pw.stop()
            except Exception:
                pass

    def get_video_info_fallback(self, video_id):
        """
        备用方式：从视频页面解析标题/作者并尝试获取视频URL。

        Args:
            video_id: 视频ID

        Returns:
            dict: 尽力而为的视频信息
        """
        page_url = f"https://www.douyin.com/video/{video_id}"
        try:
            response = self._request_with_retry(page_url, headers={"Referer": "https://www.douyin.com/"})
            html = response.text

            # 尝试提取标题/作者（尽力而为）
            title_match = re.search(r'"desc":"([^"]+)"', html)
            author_match = re.search(r'"nickname":"([^"]+)"', html)

            video_info = {
                'video_id': video_id,
                'title': title_match.group(1) if title_match else '未命名视频',
                'author': author_match.group(1) if author_match else '未知作者',
                'author_id': '',
                'create_time': 0,
                'duration': 0,
                'statistics': {},
                'video_url': None,
                'cover_url': None,
            }

            video_url = self._extract_video_url_from_html(html) or self.get_video_url_direct(video_id)
            if video_url:
                video_info['video_url'] = video_url
            if video_info['video_url']:
                return video_info
        except Exception as e:
            print(f"备用解析失败: {e}")

        # 终极回退：Playwright 浏览器
        print("   requests 方式均失败，尝试 Playwright 浏览器...")
        pw_info = self._get_video_info_playwright(video_id, original_url=getattr(self, '_current_original_url', None))
        if pw_info:
            return pw_info

        return {
            'video_id': video_id,
            'title': '未命名视频',
            'author': '未知作者',
            'author_id': '',
            'create_time': 0,
            'duration': 0,
            'statistics': {},
            'video_url': None,
            'cover_url': None,
        }
    
    def get_video_url_direct(self, video_id):
        """
        直接获取视频下载URL（备用方法）
        
        Args:
            video_id: 视频ID
            
        Returns:
            str: 视频下载URL
        """
        candidate_pages = [
            f"https://www.douyin.com/video/{video_id}",
            f"https://www.iesdouyin.com/share/video/{video_id}/",
        ]
        
        for page_url in candidate_pages:
            try:
                response = self._request_with_retry(page_url, headers={"Referer": "https://www.douyin.com/"})
                html = response.text

                video_url = self._extract_video_url_from_html(html)
                if video_url:
                    return video_url
            except Exception as e:
                print(f"直接获取视频URL失败: {e}")
        
        return None
    
    def download_video(self, video_url, output_path, chunk_size=8192):
        """
        下载视频文件
        
        Args:
            video_url: 视频下载URL
            output_path: 输出文件路径
            chunk_size: 分块大小
            
        Returns:
            bool: 是否下载成功
        """
        video_url = self._normalize_video_url(video_url)
        temp_output_path = output_path + ".part"

        try:
            # 设置视频下载的特定请求头
            video_headers = {
                "User-Agent": self.headers["User-Agent"],
                "Referer": "https://www.douyin.com/",
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "Range": "bytes=0-",
            }

            response = self._request_with_retry(video_url, headers=video_headers, stream=True)
            response.raise_for_status()

            content_type = (response.headers.get('content-type') or '').lower()
            if 'text/html' in content_type:
                raise ValueError("返回HTML页面，疑似触发风控或链接失效")

            total_size = int(response.headers.get('content-length', 0) or 0)
            downloaded = 0

            with open(temp_output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    f.write(chunk)

                    # 显示下载进度
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        done = int(50 * downloaded / total_size)
                        sys.stdout.write(f"\r下载进度: [{'=' * done}{' ' * (50-done)}] {percent:.1f}% ({downloaded}/{total_size} bytes)")
                        sys.stdout.flush()

            if downloaded == 0:
                raise ValueError("未下载到有效内容")

            os.replace(temp_output_path, output_path)
            print(f"\n视频下载完成: {output_path}")
            return True

        except Exception as e:
            if os.path.exists(temp_output_path):
                try:
                    os.remove(temp_output_path)
                except Exception:
                    pass

            print(f"\n视频下载失败: {e}")
            return False
    
    def check_ffmpeg(self):
        """检查FFmpeg是否可用"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def cleanup_filename(self, filename):
        """清理文件名中的非法字符"""
        illegal_chars = r'[<>:"/\\|?*]'
        cleaned = re.sub(illegal_chars, '_', str(filename or ''))
        cleaned = cleaned.strip().rstrip('.')

        if not cleaned:
            cleaned = 'video'

        # Windows 保留名处理（忽略扩展名）
        stem = cleaned.split('.')[0].upper()
        reserved = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
        }
        if stem in reserved:
            cleaned = f"_{cleaned}"

        return cleaned[:120]
    
    def dry_run(self, url):
        """
        仅解析视频信息，不执行下载。
        用于排查 Cookie / 风控 / 链接有效性。
        """
        print("=" * 60)
        print("抖音视频下载器  [dry-run 模式]")
        print("=" * 60)

        try:
            print(f"\n1. 解析URL: {url}")
            clean_url = self._extract_first_url(url)
            self._current_original_url = clean_url
            video_id = self.extract_video_id(clean_url)
            print(f"   视频ID: {video_id}")
            if self.last_resolved_url and self.last_resolved_url != clean_url:
                print(f"   最终链接: {self.last_resolved_url}")

            print(f"\n2. 获取视频信息...")
            try:
                video_info = self.get_video_info(video_id)
            except Exception as e:
                print(f"   获取视频信息失败，改用备用解析: {e}")
                video_info = self.get_video_info_fallback(video_id)

            print(f"   标题:   {video_info['title']}")
            print(f"   作者:   {video_info['author']}")
            print(f"   时长:   {video_info['duration']}秒")
            stats = video_info.get('statistics', {})
            if stats:
                print(f"   点赞:   {stats.get('digg_count', '-')}")
                print(f"   评论:   {stats.get('comment_count', '-')}")
                print(f"   分享:   {stats.get('share_count', '-')}")
                print(f"   播放:   {stats.get('play_count', '-')}")

            print(f"\n3. 获取视频下载链接...")
            video_url = self._normalize_video_url(video_info.get('video_url'))
            # 占位视频视为无效
            if video_url and self._is_placeholder_video(video_url):
                print("   检测到占位视频，视为无效")
                video_url = None
            if not video_url:
                print("   使用备用方法获取视频URL...")
                video_url = self.get_video_url_direct(video_id)

            if not video_url:
                print("   requests 方式均失败，尝试 Playwright 浏览器...")
                pw_info = self._get_video_info_playwright(video_id, original_url=clean_url)
                if pw_info:
                    video_info = pw_info
                    video_url = pw_info.get('video_url')

            if video_url:
                print(f"   ✅ 视频URL有效")
                print(f"   URL: {video_url[:120]}{'...' if len(video_url) > 120 else ''}")
            else:
                print(f"   ❌ 无法获取视频下载链接（可能Cookie失效或触发风控）")

            print(f"\n{'=' * 60}")
            print("dry-run 完成，未执行下载")
            return video_info

        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            return None

    def download(self, url, output_dir='.', filename=None, use_ffmpeg=False):
        """
        主下载方法
        
        Args:
            url: 抖音视频URL
            output_dir: 输出目录
            filename: 自定义文件名（不含扩展名）
            use_ffmpeg: 是否使用FFmpeg优化视频
            
        Returns:
            str: 下载的视频文件路径
        """
        print("=" * 60)
        print("抖音视频下载器")
        print("=" * 60)
        
        try:
            # 1. 提取视频ID
            print(f"\n1. 解析URL: {url}")
            clean_url = self._extract_first_url(url)
            self._current_original_url = clean_url
            video_id = self.extract_video_id(clean_url)
            print(f"   视频ID: {video_id}")
            if self.last_resolved_url and self.last_resolved_url != clean_url:
                print(f"   最终链接: {self.last_resolved_url}")
            
            # 2. 获取视频信息
            print(f"\n2. 获取视频信息...")
            try:
                video_info = self.get_video_info(video_id)
            except Exception as e:
                print(f"   获取视频信息失败，改用备用解析: {e}")
                video_info = self.get_video_info_fallback(video_id)

            print(f"   标题: {video_info['title']}")
            print(f"   作者: {video_info['author']}")
            print(f"   时长: {video_info['duration']}秒")
            
            # 3. 获取视频URL
            print(f"\n3. 获取视频下载链接...")
            video_url = self._normalize_video_url(video_info.get('video_url'))
            
            # 占位视频视为无效
            if video_url and self._is_placeholder_video(video_url):
                print("   检测到占位视频，视为无效")
                video_url = None
            if not video_url:
                print("   使用备用方法获取视频URL...")
                video_url = self.get_video_url_direct(video_id)

            if not video_url:
                print("   requests 方式均失败，尝试 Playwright 浏览器...")
                pw_info = self._get_video_info_playwright(video_id, original_url=clean_url)
                if pw_info and pw_info.get('video_url'):
                    video_info = pw_info
                    video_url = pw_info['video_url']

            if not video_url:
                raise ValueError("无法获取视频下载链接（该内容可能是图文笔记，不包含可下载的视频）")
            
            print(f"   视频URL获取成功")
            
            # 4. 准备输出路径
            os.makedirs(output_dir, exist_ok=True)
            
            if filename:
                safe_filename = self.cleanup_filename(filename)
            else:
                safe_title = self.cleanup_filename(video_info['title'][:50])
                safe_author = self.cleanup_filename(video_info['author'][:20])
                safe_filename = f"{safe_author}_{safe_title}"
            
            # 添加时间戳避免重复
            timestamp = int(time.time())
            output_path = os.path.join(output_dir, f"{safe_filename}_{timestamp}.mp4")
            
            # 5. 下载视频
            print(f"\n4. 开始下载视频...")
            print(f"   保存到: {output_path}")
            
            success = self.download_video(video_url, output_path)
            
            if success:
                print(f"\n✅ 下载完成!")
                print(f"   文件: {output_path}")
                
                # 检查文件是否存在并获取大小
                if os.path.exists(output_path):
                    file_size = os.path.getsize(output_path)
                    print(f"   大小: {file_size / 1024 / 1024:.2f} MB")
                else:
                    print(f"   大小: 文件已下载但无法获取大小信息")
                
                # 6. 可选：使用FFmpeg优化
                if use_ffmpeg and self.check_ffmpeg():
                    print(f"\n5. 使用FFmpeg优化视频...")
                    optimized_path = output_path.replace('.mp4', '_optimized.mp4')
                    cmd = [
                        'ffmpeg', '-i', output_path,
                        '-c', 'copy',
                        '-movflags', '+faststart',
                        '-y', optimized_path
                    ]
                    
                    try:
                        subprocess.run(cmd, check=True, capture_output=True)
                        print(f"   优化完成: {optimized_path}")
                        # 删除原始文件，保留优化后的文件
                        os.remove(output_path)
                        output_path = optimized_path
                    except subprocess.CalledProcessError as e:
                        print(f"   优化失败: {e}")
                
                return output_path
            else:
                raise Exception("视频下载失败")
                
        except Exception as e:
            print(f"\n❌ 错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return None


def main():
    """命令行入口函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='抖音视频下载器')
    parser.add_argument('url', nargs='?', help='抖音视频URL（下载模式必填）')
    parser.add_argument('-o', '--output', default='.', help='输出目录 (默认: 当前目录)')
    parser.add_argument('-f', '--filename', help='自定义文件名 (不含扩展名)')
    parser.add_argument('--ffmpeg', action='store_true', help='使用FFmpeg优化视频')
    parser.add_argument('--timeout', type=int, default=30, help='请求超时时间 (默认: 30秒)')
    parser.add_argument('--retries', type=int, default=3, help='失败重试次数 (默认: 3)')
    parser.add_argument('--retry-delay', type=float, default=1.0, help='重试基准间隔秒数 (默认: 1.0)')
    parser.add_argument('--cookie-file', help='Cookie文件路径（支持 cookie header / Netscape / 浏览器表格复制）')
    parser.add_argument('--check-cookie', action='store_true', help='仅检查Cookie关键字段，不执行下载')
    parser.add_argument('--dry-run', action='store_true', help='仅解析视频信息，不下载（排查Cookie/风控）')
    
    args = parser.parse_args()
    
    downloader = DouyinDownloader(
        timeout=args.timeout,
        max_retries=args.retries,
        retry_delay=args.retry_delay,
    )

    # 自动加载 cookie 文件（显式参数优先，其次查找默认 cookie.txt）
    cookie_path = args.cookie_file
    if cookie_path is None:
        candidates = [
            'cookie.txt',
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookie.txt'),
        ]
        for c in candidates:
            if os.path.exists(c):
                cookie_path = c
                break

    if cookie_path:
        try:
            downloader.load_cookies_from_file(cookie_path)
            cookie_ok = downloader.check_cookie_health()
            if not cookie_ok:
                print("⚠️ Cookie 可能不完整，下载成功率可能受影响")
        except Exception as e:
            print(f"加载Cookie失败: {e}")
            if args.check_cookie:
                sys.exit(1)

    if args.check_cookie:
        # 仅做自检
        ok = downloader.check_cookie_health()
        sys.exit(0 if ok else 1)

    if not args.url:
        parser.error('下载模式下必须提供 url，或使用 --check-cookie / --dry-run')

    if args.dry_run:
        info = downloader.dry_run(url=args.url)
        sys.exit(0 if info else 1)

    result = downloader.download(
        url=args.url,
        output_dir=args.output,
        filename=args.filename,
        use_ffmpeg=args.ffmpeg
    )
    
    if result:
        print(f"\n🎉 视频下载成功: {result}")
        sys.exit(0)
    else:
        print(f"\n💥 视频下载失败")
        sys.exit(1)


if __name__ == "__main__":
    main()