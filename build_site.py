#!/usr/bin/env python3
"""合并所有游戏日报/周报HTML到 public/ 目录，用于 GitHub Pages 部署"""
import os, shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
os.makedirs(PUBLIC_DIR, exist_ok=True)

def copy_html(src_rel, dst_rel):
    """复制单个 HTML 文件到 public/ 目录"""
    src = os.path.join(BASE_DIR, src_rel)
    dst = os.path.join(PUBLIC_DIR, dst_rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"  ✅ {dst_rel}")
        return True
    else:
        print(f"  ⚠️ 缺失: {src_rel}")
        return False

print("=" * 50)
print("构建 GitHub Pages 站点")

# === 地下城堡4 ===
print("\n[地下城堡4]")
copy_html("data/html_report_daily/index.html", "dungeon4/daily/index.html")
copy_html("data/html_report_daily/index.html", "daily/index.html")       # 兼容旧链接
copy_html("data/html_report/index.html", "dungeon4/weekly/index.html")
copy_html("data/html_report/index.html", "weekly/index.html")            # 兼容旧链接

# === 深空之眼 ===
print("\n[深空之眼]")
copy_html("data/aether_gazer/html_report/index.html", "aether_gazer/daily/index.html")

# === 统一首页 ===
index_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>游戏舆情监控</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); min-height: 100vh; color: #e0e0e0; }}
.container {{ max-width: 800px; margin: 0 auto; padding: 60px 20px; text-align: center; }}
h1 {{ font-size: 1.8rem; margin-bottom: 8px; background: linear-gradient(90deg, #f5af19, #f12711); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.subtitle {{ color: #8892b0; margin-bottom: 40px; font-size: 0.95rem; }}
.game-section {{ margin-bottom: 40px; }}
.game-title {{ color: #ccd6f6; font-size: 1.1rem; margin-bottom: 16px; text-align: left; padding-left: 8px; border-left: 3px solid #f5af19; }}
.links {{ display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }}
.card {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 24px 20px; min-width: 200px; transition: all 0.3s; cursor: pointer; text-decoration: none; display: block; }}
.card:hover {{ background: rgba(255,255,255,0.1); transform: translateY(-2px); border-color: rgba(245,175,25,0.4); }}
.card h2 {{ color: #f5af19; margin-bottom: 6px; font-size: 1.1rem; }}
.card p {{ color: #8892b0; font-size: 0.8rem; }}
.icon {{ font-size: 1.6rem; margin-bottom: 8px; }}
.footer {{ margin-top: 40px; color: #495670; font-size: 0.75rem; }}
</style>
</head>
<body>
<div class="container">
    <h1>📊 游戏舆情监控</h1>
    <p class="subtitle">TapTap 社区舆情自动化报告</p>

    <div class="game-section">
        <div class="game-title">🏰 地下城堡4</div>
        <div class="links">
            <a href="./dungeon4/daily/" class="card">
                <div class="icon">📰</div>
                <h2>每日舆情日报</h2>
                <p>帖子 · 评分 · 评论趋势</p>
            </a>
            <a href="./dungeon4/weekly/" class="card">
                <div class="icon">📊</div>
                <h2>每周舆情周报</h2>
                <p>分类分布 · TOP10热议</p>
            </a>
        </div>
    </div>

    <div class="game-section">
        <div class="game-title">🔮 深空之眼</div>
        <div class="links">
            <a href="./aether_gazer/daily/" class="card">
                <div class="icon">📰</div>
                <h2>每日舆情日报</h2>
                <p>帖子 · 评分 · 评论趋势</p>
            </a>
        </div>
    </div>

    <p class="footer">更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M")} | Powered by GitHub Actions</p>
</div>
</body>
</html>'''

with open(os.path.join(PUBLIC_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(index_html)
print("\n✅ 首页生成完成")
print("=" * 50)
