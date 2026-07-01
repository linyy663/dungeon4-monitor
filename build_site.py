#!/usr/bin/env python3
"""合并日报/周报HTML到 public/ 目录，用于 GitHub Pages 部署"""
import os, shutil, glob
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
os.makedirs(PUBLIC_DIR, exist_ok=True)

# 日报
daily_src = os.path.join(BASE_DIR, "data", "html_report_daily", "index.html")
daily_dst = os.path.join(PUBLIC_DIR, "daily", "index.html")
os.makedirs(os.path.dirname(daily_dst), exist_ok=True)
if os.path.exists(daily_src):
    shutil.copy2(daily_src, daily_dst)
    print(f"✅ 日报复制完成: {daily_dst}")
else:
    print(f"⚠️ 日报文件不存在: {daily_src}")

# 周报
weekly_src = os.path.join(BASE_DIR, "data", "html_report", "index.html")
weekly_dst = os.path.join(PUBLIC_DIR, "weekly", "index.html")
os.makedirs(os.path.dirname(weekly_dst), exist_ok=True)
if os.path.exists(weekly_src):
    shutil.copy2(weekly_src, weekly_dst)
    print(f"✅ 周报复制完成: {weekly_dst}")
else:
    print(f"⚠️ 周报文件不存在: {weekly_src}")

# 首页
index_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>地下城堡4 舆情监控</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); min-height: 100vh; color: #e0e0e0; }}
.container {{ max-width: 600px; margin: 0 auto; padding: 60px 20px; text-align: center; }}
h1 {{ font-size: 2rem; margin-bottom: 8px; background: linear-gradient(90deg, #f5af19, #f12711); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.subtitle {{ color: #8892b0; margin-bottom: 40px; font-size: 0.95rem; }}
.card {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 30px 24px; margin-bottom: 20px; transition: all 0.3s; cursor: pointer; text-decoration: none; display: block; }}
.card:hover {{ background: rgba(255,255,255,0.1); transform: translateY(-2px); border-color: rgba(245,175,25,0.4); }}
.card h2 {{ color: #f5af19; margin-bottom: 8px; font-size: 1.2rem; }}
.card p {{ color: #8892b0; font-size: 0.85rem; }}
.icon {{ font-size: 2rem; margin-bottom: 12px; }}
.footer {{ margin-top: 40px; color: #495670; font-size: 0.75rem; }}
</style>
</head>
<body>
<div class="container">
    <h1>🏰 地下城堡4 · 舆情监控</h1>
    <p class="subtitle">TapTap 社区舆情自动化报告</p>
    <a href="./daily/" class="card">
        <div class="icon">📰</div>
        <h2>每日舆情日报</h2>
        <p>点击查看最新日报 — 帖子、评分、评论趋势</p>
    </a>
    <a href="./weekly/" class="card">
        <div class="icon">📊</div>
        <h2>每周舆情周报</h2>
        <p>点击查看最新周报 — 分类分布、TOP10热议帖子</p>
    </a>
    <p class="footer">更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M")} | Powered by GitHub Actions</p>
</div>
</body>
</html>'''

with open(os.path.join(PUBLIC_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(index_html)
print(f"✅ 首页生成完成")
'''
<CQ_code>
</CQ_code>
