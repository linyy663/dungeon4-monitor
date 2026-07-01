# -*- coding: utf-8 -*-
"""
TapTap 地下城堡4 舆情周报 v7
- 聊天推送：统计信息 + 问题汇总 + CloudStudio HTML链接
- CloudStudio：完整HTML周报（漂亮排版）
"""
import sys, os, json, time, re, uuid, urllib.parse
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter

import requests

# ── Config ──────────────────────────────────────
APP_ID    = "728798"
GROUP_ID  = "853936"
GAME_NAME = "地下城堡4"

FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/39d53112-44e8-4bba-bb18-4a6de567fe45"

today = datetime.now()
last_monday = today - timedelta(days=today.weekday() + 7)
last_sunday  = last_monday + timedelta(days=6)
START_DATE = last_monday.strftime("%Y-%m-%d")
END_DATE   = last_sunday.strftime("%Y-%m-%d")

DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
JSON_FILE    = os.path.join(DATA_DIR, f"taptap_week_{START_DATE}_{END_DATE}.json")
REPORT_FILE  = os.path.join(DATA_DIR, f"report_week_{START_DATE}_{END_DATE}.md")
HTML_DIR     = os.path.join(DATA_DIR, "html_report")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HTML_DIR, exist_ok=True)

CST = timezone(timedelta(hours=8))
WEEK_LABEL = f"{START_DATE} ~ {END_DATE}"

def log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)

# ══════════════════════════════════════════════
# Rich text extraction
# ══════════════════════════════════════════════
def extract_rich_text(contents):
    if not contents: return ""
    if contents.get("text"): return contents.get("text", "")
    if contents.get("raw_text"): return contents.get("raw_text", "")
    json_arr = contents.get("json", [])
    if not json_arr: return ""
    parts = []
    for para in json_arr:
        for child in para.get("children", []):
            t = child.get("text", "")
            if t: parts.append(t)
    return "".join(parts)

def ts_to_date(ts):
    if isinstance(ts, (int, float)) and ts > 1_000_000_000:
        return time.strftime("%Y-%m-%d", time.gmtime(int(ts) + 8 * 3600))
    return str(ts)[:10] if ts else ""

def ts_to_datetime(ts):
    if isinstance(ts, (int, float)) and ts > 1_000_000_000:
        return datetime.fromtimestamp(ts, tz=CST)
    return datetime.now(CST)

# ══════════════════════════════════════════════
# Extract items from API
# ══════════════════════════════════════════════
def extract_forum_item(item):
    m = item.get("moment", {})
    topic = m.get("topic", {})
    author = (m.get("author") or {}).get("user") or {}
    stat = m.get("stat") or {}
    title = topic.get("title", "")
    summary = topic.get("summary", "")
    content = summary if summary else extract_rich_text(m.get("contents", {}))
    if not title: title = content[:50].replace("\n", " ") if content else ""
    return {
        "source": "forum", "id": m.get("id_str", ""),
        "author": author.get("name", "匿名"),
        "date": ts_to_date(m.get("created_time", 0)),
        "datetime": ts_to_datetime(m.get("created_time", 0)).strftime("%Y-%m-%d %H:%M"),
        "title": title, "body": content, "text": content,
        "likes": stat.get("supports", 0), "shares": stat.get("share_count", 0),
        "views": stat.get("pv_total", 0),
        "comments_count": stat.get("comments", 0),
        "url": f"https://www.taptap.cn/moment/{m.get('id_str','')}",
        "comments": [], "category": "",
    }

def extract_review_item(item):
    m = item.get("moment", {})
    review = m.get("review", {})
    author = (m.get("author") or {}).get("user") or {}
    stat = m.get("stat") or {}
    content = extract_rich_text(review.get("contents", {}))
    return {
        "source": "review", "id": m.get("id_str", ""),
        "author": author.get("name", "匿名"),
        "date": ts_to_date(m.get("created_time", 0)),
        "datetime": ts_to_datetime(m.get("created_time", 0)).strftime("%Y-%m-%d %H:%M"),
        "title": "", "body": content, "text": content,
        "score": review.get("score", 0),
        "likes": stat.get("supports", 0), "views": stat.get("pv_total", 0),
        "url": "", "comments": [], "category": "",
    }

def extract_comment(comment):
    author = comment.get("author") or {}
    author_name = author.get("name") or (author.get("user") or {}).get("name") or "匿名"
    text = extract_rich_text(comment.get("contents", {}))
    nested = []
    for cp in comment.get("child_posts", []):
        cp_author = (cp.get("author") or {}).get("name") or "?"
        cp_text = extract_rich_text(cp.get("contents", {}))
        if cp_text: nested.append({"author": cp_author, "text": cp_text})
    return {
        "id": str(comment.get("id_str") or comment.get("id", "")),
        "author": author_name, "text": text,
        "time": ts_to_datetime(comment.get("created_time", 0)).strftime("%Y-%m-%d %H:%M"),
        "likes": comment.get("like_count") or comment.get("ups", 0),
        "nested_replies": nested,
    }

# ══════════════════════════════════════════════
# Classification
# ══════════════════════════════════════════════
def classify_content(item):
    title = item.get("title", "") or ""
    body = item.get("body", "") or item.get("text", "") or ""
    full_text = f"{title} {body}".lower()
    for c in item.get("comments", []):
        full_text += " " + (c.get("text", "") or "")
        for nr in c.get("nested_replies", []):
            full_text += " " + (nr.get("text", "") or "")

    bug_kw = ["bug","闪退","卡死","黑屏","崩溃","报错","错误","卡住","加载不了","掉线","延迟",
              "卡顿","没反应","出不来","打不开","异常","乱码","消失","不显示","吞了","失效",
              "无法","进不去","服务器","维护","连接失败","登录不了","回档","数据丢失",
              "装备异常","装备丢失","属性异常","不生效","无效","没触发","不能","没了","无法使用"]
    suggest_kw = ["建议","希望","能不能","求","期待","优化","改善","改进","增加","添加","加入",
                  "更新","调整","平衡","修改","改一下","活动","福利","奖励","玩法","功能",
                  "要是","如果","出个","来个","开放","保底","概率","透明","公示","说明",
                  "加点","降低","提高","加强","削弱","可玩性","引导","提示","新手","难度"]
    complain_kw = ["垃圾","坑","骗","太贵","不值","差评","失望","后悔","恶心","离谱","无语",
                   "不好玩","无聊","没意思","浪费时间","弃坑","卸载","不玩了","退游","关服",
                   "换皮","抄袭","逼氪","吃相","难看","割韭菜","氪金","付费","坑钱","骗氪",
                   "逼肝","服了","辣鸡"]
    guide_kw = ["攻略","阵容","打法","过关","配置","阵容推荐","怎么打","怎么过","求阵容",
                "求助","请教","大佬","指点","帮忙看看","分享","思路","带什么","配什么",
                "用什么","选哪个","怎么配","怎么选","哪个好","谁厉害","通关","出装",
                "装备搭配","技能","加点","流派","过图"]
    official_kw = ["公告","官方","可公开","更新预告","维护预告","活动预告"]

    s_s = sum(1 for kw in suggest_kw if kw in full_text)
    s_b = sum(1 for kw in bug_kw if kw in full_text)
    s_c = sum(1 for kw in complain_kw if kw in full_text)
    s_g = sum(1 for kw in guide_kw if kw in full_text)
    s_o = sum(1 for kw in official_kw if kw in full_text)

    scores = {"建议": s_s, "BUG": s_b, "吐槽": s_c, "攻略交流": s_g, "官方": s_o}
    max_cat = max(scores, key=scores.get)
    if scores[max_cat] == 0: return "其他"
    if s_o >= 1: return "官方"
    if s_g >= 2: return "攻略交流"
    return max_cat

# ══════════════════════════════════════════════
# Topic extraction
# ══════════════════════════════════════════════
def extract_topics(text, title="", body=""):
    full_text = f"{title} {body} {text}".lower()
    topics = set()
    patterns = {
        "关卡/难度": ["关卡","卡关","难度","章节","过不去","怎么过"],
        "英雄/角色": ["英雄","角色","阵容","sp","光盾","剑圣","烈","输出","前排",
                     "命格","断荆者","塞雷娜","狼人","沙女","夜莺","莫里斯"],
        "装备/词条": ["装备","戒指","武器","防具","暴击","词条","首饰","套装"],
        "抽卡/保底": ["抽卡","保底","概率","抽到","十连","招募"],
        "付费/氪金": ["氪","充值","付费","月卡","价格","划算"],
        "活动/福利": ["活动","福利","奖励","掉落","兑换"],
        "体验/数值": ["数值","平衡","伤害","免伤","公式","机制"],
        "BUG/异常": ["bug","异常","错误","闪退","卡死"],
        "攻略/打法": ["攻略","打法","思路","怎么打","阵容推荐"],
    }
    for topic, kws in patterns.items():
        if any(kw in full_text for kw in kws):
            topics.add(topic)
    return list(topics)

def sentiment_score(text):
    pos = ["好","喜欢","不错","推荐","赞","值","棒","良心","惊喜","期待","支持","加油","好评"]
    neg = ["差","垃圾","坑","失望","后悔","无语","逼氪","弃坑","卸载","恶心","骗"]
    s = sum(1 for kw in pos if kw in text) - sum(1 for kw in neg if kw in text)
    if s > 0: return "正面"
    if s < 0: return "负面"
    return "中性"

# ══════════════════════════════════════════════
# STEP 1: Fetch reviews
# ══════════════════════════════════════════════
def fetch_reviews():
    log(f"[1/4] 抓取评分评论 ({START_DATE} ~ {END_DATE})...")
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json", "Referer": f"https://www.taptap.cn/app/{APP_ID}",
    })
    try: sess.get(f"https://www.taptap.cn/app/{APP_ID}", timeout=15)
    except: pass
    xua = urllib.parse.quote(f"V=1&PN=WebApp&LANG=zh_CN&VN_CODE=102&LOC=CN&PLT=PC&DS=Android&UID={uuid.uuid4()}&OS=Windows&OSV=10&DT=PC")

    all_reviews, from_offset, found_older, fail_streak = [], 0, False, 0
    while from_offset < 1000:
        url = f"https://www.taptap.cn/webapiv2/review/v2/list-by-app?app_id={APP_ID}&sort=new&limit=10&from={from_offset}&X-UA={xua}"
        try:
            r = sess.get(url, timeout=20)
            if "text/html" in r.headers.get("Content-Type","") or r.text[:100].lower().startswith("<!doctype"):
                sess.cookies.clear()
                try: sess.get(f"https://www.taptap.cn/app/{APP_ID}", timeout=15)
                except: pass
                fail_streak += 1; time.sleep(3)
                if fail_streak >= 5: break
                continue
            d = r.json(); fail_streak = 0
        except Exception:
            fail_streak += 1
            if fail_streak >= 5: break
            time.sleep(2); continue

        items = d.get("data",{}).get("list",[])
        if not items: break
        in_range = 0
        for item in items:
            ri = extract_review_item(item)
            if not ri["date"]: continue
            if ri["date"] < START_DATE: found_older = True
            elif ri["date"] <= END_DATE: in_range += 1; all_reviews.append(ri)
        pn = from_offset//10+1
        log(f"  [评论] p{pn}: {len(items)}条, {in_range}条在范围内")
        if found_older and in_range == 0 and from_offset >= 100: break
        from_offset += 10; time.sleep(0.8)
    log(f"  [评论] 共 {len(all_reviews)} 条")
    return all_reviews

# ══════════════════════════════════════════════
# STEP 2: Fetch forum posts
# ══════════════════════════════════════════════
JS_FETCH = "async (url) => { try { const r = await fetch(url, {credentials:'include'}); const t = await r.text(); return {ok:r.ok, status:r.status, body:t}; } catch(e) { return {ok:false, status:0, body:e.toString()}; } }"

def fetch_forum():
    log(f"[2/4] 抓取论坛帖子 ({START_DATE} ~ {END_DATE})...")
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json", "Referer": f"https://www.taptap.cn/app/{APP_ID}",
    })
    try: sess.get(f"https://www.taptap.cn/app/{APP_ID}", timeout=15)
    except: pass
    xua = urllib.parse.quote(f"V=1&PN=WebApp&LANG=zh_CN&VN_CODE=102&LOC=CN&PLT=PC&DS=Android&UID={uuid.uuid4()}&OS=Windows&OSV=10&DT=PC")

    test_url = f"https://www.taptap.cn/webapiv2/feed/v7/by-group?from=0&group_id={GROUP_ID}&limit=1&sort=created&status=0&type=feed&with_hot_comment=true&X-UA={xua}"
    use_requests = False
    try:
        tr = sess.get(test_url, timeout=15)
        if tr.status_code == 200 and '"type":"moment"' in tr.text:
            use_requests = True; log("  [论坛] requests 可用")
        else:
            log("  [论坛] requests 不可用 (WAF)，切换到 Playwright")
    except:
        log("  [论坛] requests 异常，切换到 Playwright")

    if use_requests: return _fetch_forum_requests(sess, xua)
    return _fetch_forum_playwright(xua)

def _fetch_forum_requests(sess, xua):
    all_posts, from_offset, found_older, fail_streak = [], 0, False, 0
    while from_offset < 2000:
        url = f"https://www.taptap.cn/webapiv2/feed/v7/by-group?from={from_offset}&group_id={GROUP_ID}&limit=10&sort=created&status=0&type=feed&with_hot_comment=true&X-UA={xua}"
        try:
            r = sess.get(url, timeout=20)
            if "text/html" in r.headers.get("Content-Type","") or r.text[:100].lower().startswith("<!doctype"):
                fail_streak += 1; time.sleep(2)
                if fail_streak >= 5: break
                continue
            d = r.json(); fail_streak = 0
        except:
            fail_streak += 1; time.sleep(2)
            if fail_streak >= 5: break
            continue

        items = d.get("data",{}).get("list",[])
        if not items: break
        in_range = 0
        for item in items:
            fi = extract_forum_item(item)
            if not fi["date"]: continue
            if fi["date"] < START_DATE: found_older = True
            elif fi["date"] <= END_DATE: in_range += 1; all_posts.append(fi)
        pn = from_offset//10+1
        log(f"  [论坛] p{pn}: {len(items)}条, {in_range}条在范围内" + (" [超范围]" if found_older else ""))
        if found_older and in_range == 0 and from_offset >= 100: break
        from_offset += 10; time.sleep(0.8)
    log(f"  [论坛] requests 模式完成: {len(all_posts)} 条")
    return all_posts

def _fetch_forum_playwright(xua):
    try: from playwright.sync_api import sync_playwright
    except ImportError: log("  [论坛] playwright 未安装"); return []
    all_posts, from_offset, found_older, fail_streak = [], 0, False, 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36", locale="zh-CN")
        page = ctx.new_page(); page.set_default_timeout(15000)
        try: page.goto(f"https://www.taptap.cn/app/{APP_ID}", wait_until="commit", timeout=20000)
        except: pass
        time.sleep(2)
        while from_offset < 2000:
            url = f"https://www.taptap.cn/webapiv2/feed/v7/by-group?from={from_offset}&group_id={GROUP_ID}&limit=10&sort=created&status=0&type=feed&with_hot_comment=true&X-UA={xua}"
            try:
                result = page.evaluate(JS_FETCH, url)
            except:
                fail_streak += 1; time.sleep(2)
                if fail_streak >= 5: break
                continue
            if not result or not result.get("ok"):
                fail_streak += 1; from_offset += 10; time.sleep(1)
                if fail_streak >= 5: break
                continue
            fail_streak = 0
            try: d = json.loads(result["body"])
            except: from_offset += 10; continue
            items = d.get("data",{}).get("list",[])
            if not items: break
            in_range = 0
            for item in items:
                fi = extract_forum_item(item)
                if not fi["date"]: continue
                if fi["date"] < START_DATE: found_older = True
                elif fi["date"] <= END_DATE: in_range += 1; all_posts.append(fi)
            pn = from_offset//10+1
            log(f"  [论坛] p{pn}: {len(items)}条, {in_range}条在范围内" + (" [超范围]" if found_older else ""))
            if found_older and in_range == 0 and from_offset >= 100: break
            from_offset += 10; time.sleep(0.3)
        browser.close()
    log(f"  [论坛] Playwright 模式完成: {len(all_posts)} 条")
    return all_posts

# ══════════════════════════════════════════════
# STEP 3: Fetch comments
# ══════════════════════════════════════════════
def fetch_comments_requests(all_posts):
    if not all_posts: return 0, 0
    log(f"[3/4] 抓取 {len(all_posts)} 个帖子的回复...")
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json", "Referer": f"https://www.taptap.cn/app/{APP_ID}",
    })
    try: sess.get(f"https://www.taptap.cn/app/{APP_ID}", timeout=15)
    except: pass
    xua = urllib.parse.quote(f"V=1&PN=WebApp&LANG=zh_CN&VN_CODE=102&LOC=CN&PLT=PC&DS=Android&UID={uuid.uuid4()}&OS=Windows&OSV=10&DT=PC")
    total_c = total_n = 0
    for i, post in enumerate(all_posts):
        url = f"https://www.taptap.cn/webapiv2/moment-comment/v1/by-moment?moment_id={post['id']}&from=0&limit=20&X-UA={xua}"
        try:
            r = sess.get(url, timeout=20)
            comments_raw = r.json().get("data",{}).get("list",[])
        except: comments_raw = []
        comments = [extract_comment(c) for c in comments_raw]
        post["comments"] = comments
        nc = len(comments); nn = sum(len(c.get("nested_replies",[])) for c in comments)
        total_c += nc; total_n += nn
        if (i+1) % 20 == 0: log(f"  [回复] {i+1}/{len(all_posts)}  (累计: {total_c}回复, {total_n}嵌套)")
        time.sleep(0.2)
    log(f"  [回复] 完成: {total_c} 条回复, {total_n} 条嵌套")
    return total_c, total_n

# ══════════════════════════════════════════════
# HTML Report Generation
# ══════════════════════════════════════════════
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f7fa;color:#333;line-height:1.7}
.container{max-width:900px;margin:0 auto;padding:20px}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:40px 30px;border-radius:12px;margin-bottom:24px}
.header h1{font-size:26px;margin-bottom:8px}
.header .meta{opacity:.8;font-size:14px}
.card{background:#fff;border-radius:10px;padding:24px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card h2{font-size:18px;color:#1a1a2e;border-bottom:2px solid #e8ecf0;padding-bottom:10px;margin-bottom:16px}
.card h3{font-size:15px;color:#444;margin:12px 0 8px}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:16px}
.stat-box{background:#f0f4f8;border-radius:8px;padding:14px;text-align:center}
.stat-box .num{font-size:28px;font-weight:700;color:#1a1a2e}
.stat-box .label{font-size:12px;color:#888;margin-top:4px}
table{width:100%;border-collapse:collapse;margin:12px 0}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #e8ecf0;font-size:14px}
th{background:#f0f4f8;font-weight:600;color:#555}
tr:hover{background:#fafbfc}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;margin:0 2px}
.tag-bug{background:#fee;color:#c0392b}
.tag-suggest{background:#e8f4fd;color:#2980b9}
.tag-complain{background:#fff3e0;color:#e67e22}
.tag-guide{background:#e8f8e8;color:#27ae60}
.tag-official{background:#f0e6ff;color:#8e44ad}
.tag-other{background:#f5f5f5;color:#888}
.item-row{padding:10px 0;border-bottom:1px dotted #e8ecf0}
.item-row:last-child{border-bottom:none}
.item-title{font-weight:600;color:#1a1a2e}
.item-title a{color:#1a73e8;text-decoration:none}
.item-title a:hover{text-decoration:underline}
.item-meta{font-size:12px;color:#999;margin:4px 0}
.item-body{font-size:14px;color:#555;margin:4px 0;line-height:1.6}
.comment-thread{margin:6px 0 6px 16px;padding:6px 0 6px 12px;border-left:2px solid #e0e6ed}
.comment-user{font-weight:600;font-size:13px;color:#333}
.comment-text{font-size:13px;color:#666;margin:2px 0}
.bar-chart{display:flex;align-items:center;margin:4px 0}
.bar-label{width:70px;font-size:13px;text-align:right;padding-right:8px}
.bar-track{flex:1;height:22px;background:#f0f4f8;border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px;font-size:12px;font-weight:600;color:#fff;min-width:30px}
.bar-suggest{background:linear-gradient(90deg,#3498db,#2980b9)}
.bar-bug{background:linear-gradient(90deg,#e74c3c,#c0392b)}
.bar-complain{background:linear-gradient(90deg,#f39c12,#e67e22)}
.bar-guide{background:linear-gradient(90deg,#2ecc71,#27ae60)}
.bar-official{background:linear-gradient(90deg,#9b59b6,#8e44ad)}
.bar-other{background:linear-gradient(90deg,#95a5a6,#7f8c8d)}
.summary-box{background:#fffdf0;border:1px solid #f0e6a0;border-radius:8px;padding:16px;margin-bottom:16px;font-size:14px}
.summary-box h2{color:#b8860b;border-color:#f0e6a0}
.badge{display:inline-block;padding:2px 6px;border-radius:3px;font-size:11px;margin:0 4px;background:#eee}
.priority-item{padding:8px 0;border-bottom:1px dashed #e8ecf0}
.priority-item:last-child{border-bottom:none}
.p0{color:#c0392b;font-weight:700}
.p1{color:#e67e22;font-weight:700}
.p2{color:#7f8c8d;font-weight:700}
.footer{text-align:center;color:#aaa;font-size:12px;margin-top:24px;padding:16px}
a{color:#1a73e8;text-decoration:none}
a:hover{text-decoration:underline}
"""

def generate_html_report(all_items):
    """Generate a beautiful HTML weekly report."""
    reviews = [i for i in all_items if i["source"] == "review"]
    posts   = [i for i in all_items if i["source"] == "forum"]
    total = len(all_items)

    cat_map = defaultdict(list)
    for item in all_items: cat_map[item["category"]].append(item)

    by_date = defaultdict(list)
    for item in all_items: by_date[item.get("date", "")].append(item)

    topic_counter = Counter()
    all_text = ""
    for item in all_items:
        text = (item.get("title","")+" "+item.get("body","")+" "+item.get("text","")).lower()
        all_text += text + " "
        for t in extract_topics(item.get("text",""), item.get("title",""), item.get("body","")):
            topic_counter[t] += 1
        for c in item.get("comments", []):
            c_text = c.get("text",""); all_text += c_text + " "
            for t in extract_topics(c_text): topic_counter[t] += 1

    total_c = sum(len(i.get("comments",[])) for i in all_items)
    total_n = sum(sum(len(c.get("nested_replies",[])) for c in i.get("comments",[])) for i in all_items)
    total_interact = total + total_c + total_n

    H = []
    H.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{GAME_NAME} TapTap舆情周报 {WEEK_LABEL}</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">

<div class="header">
<h1>{GAME_NAME} TapTap 舆情周报</h1>
<div class="meta">📅 {WEEK_LABEL} &nbsp;|&nbsp; 🕐 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; 📡 数据来源: TapTap</div>
</div>

<!-- Summary -->
<div class="summary-box">
<h2>📋 本周舆情概括</h2>
""")

    cat_order = ["建议","BUG","吐槽","攻略交流","官方","其他"]
    suggest_items = cat_map.get("建议", [])
    bug_items = cat_map.get("BUG", [])
    complain_items = cat_map.get("吐槽", [])

    # --- Build intelligent summary ---
    summary = []
    summary.append(f'<p>本周共产生 <strong>{total}</strong> 条内容（{len(reviews)}条评分 + {len(posts)}条论坛帖子），玩家回复 <strong>{total_c}</strong> 条，嵌套回复 <strong>{total_n}</strong> 条，互动总量 <strong>{total_interact}</strong> 条。')

    # Classification tags
    cat_parts = []
    for cat in cat_order:
        cnt = len(cat_map.get(cat, []))
        if cnt > 0: cat_parts.append(f'<span class="tag tag-{["suggest","bug","complain","guide","official","other"][cat_order.index(cat)]}">{cat} {cnt}条</span>')
    summary.append(f'分类分布：{" ".join(cat_parts)}</p>')

    # --- SUGGESTION ANALYSIS ---
    if suggest_items:
        suggestions_all_text = " ".join([(i.get("body","") or i.get("text","") or "") + " " + (i.get("title","") or "") for i in suggest_items])
        suggestions_all_text += " " + " ".join([c.get("text","") for i in suggest_items for c in i.get("comments",[])])
        suggestions_all_text += " " + " ".join([nr.get("text","") for i in suggest_items for c in i.get("comments",[]) for nr in c.get("nested_replies",[])])

        suggest_themes = []
        if any(kw in suggestions_all_text for kw in ["英雄","角色","命格","SP","阵容","sp","断荆者","塞雷娜","狼人","剑圣","英雄平衡","职业"]):
            suggest_themes.append("英雄/角色平衡与命格机制优化")
        if any(kw in suggestions_all_text for kw in ["装备","套装","词条","武器","戒指","暴击","属性","装备词缀"]):
            suggest_themes.append("装备系统与套装效果完善")
        if any(kw in suggestions_all_text for kw in ["难度","关卡","推图","章节","过不去"]):
            suggest_themes.append("关卡难度曲线调整与新手引导")
        if any(kw in suggestions_all_text for kw in ["活动","福利","奖励","掉落","兑换","收益"]):
            suggest_themes.append("活动频率与资源获取优化")
        if any(kw in suggestions_all_text for kw in ["抽卡","保底","概率","十连","招募"]):
            suggest_themes.append("抽卡概率与保底机制透明化")
        if any(kw in suggestions_all_text for kw in ["优化","改善","改进","ui","界面","操作","手感","体验","快捷"]):
            suggest_themes.append("UI交互与操作体验提升")
        if any(kw in suggestions_all_text for kw in ["功能","添加","增加","新玩法","新内容","pvp","公会","社交"]):
            suggest_themes.append("新玩法与新功能需求")
        if any(kw in suggestions_all_text for kw in ["氪","付费","价格","月卡","划算"]):
            suggest_themes.append("付费/经济体系调整建议")
        if not suggest_themes:
            suggest_themes.append("综合优化建议")

        summary.append(f'<p><strong>💡 建议聚焦：</strong>玩家主要关注{"、".join(suggest_themes[:4])}等方向。共 {len(suggest_items)} 条建议帖，其中高频诉求集中在英雄平衡性调整与装备机制完善。</p>')

    # --- BUG ANALYSIS ---
    if bug_items:
        bugs_all_text = " ".join([(i.get("body","") or i.get("text","") or "") + " " + (i.get("title","") or "") for i in bug_items])
        bugs_all_text += " " + " ".join([c.get("text","") for i in bug_items for c in i.get("comments",[])])

        bug_themes = []
        if any(kw in bugs_all_text for kw in ["套装","塞雷娜","装备效果","不生效","无效","不触发","套装效果"]):
            bug_themes.append("装备/套装效果不生效（塞雷娜套装等）")
        if any(kw in bugs_all_text for kw in ["琉璃","碎梦","武器","剑圣","大招","技能机制","技能描述","描述错误"]):
            bug_themes.append("技能机制异常或描述不符（琉璃碎梦武器等）")
        if any(kw in bugs_all_text for kw in ["闪退","卡死","黑屏","崩溃","掉线","卡顿","加载","进不去"]):
            bug_themes.append("闪退/卡死/加载异常")
        if any(kw in bugs_all_text for kw in ["显示","ui","界面","乱码","不显示","看不见","消失"]):
            bug_themes.append("UI显示异常")
        if any(kw in bugs_all_text for kw in ["数据","丢失","回档","消失","没了","吞了","异常"]):
            bug_themes.append("数据丢失/回档问题")
        if any(kw in bugs_all_text for kw in ["狼人","头目","技能描述","描述错误","文案","描述"]):
            if "技能机制异常或描述不符" not in bug_themes:
                bug_themes.append("技能/文案描述错误")
        if not bug_themes:
            bug_themes.append("综合BUG反馈")

        summary.append(f'<p><strong>🐛 BUG聚焦：</strong>报告了 <strong>{len(bug_items)}</strong> 个问题，主要集中在{"、".join(bug_themes[:4])}。这些问题直接影响玩家游戏体验，需优先处理。</p>')

    # --- COMPLAINT ANALYSIS ---
    if complain_items:
        comp_all_text = " ".join([(i.get("body","") or i.get("text","") or "") + " " + (i.get("title","") or "") for i in complain_items])
        comp_all_text += " " + " ".join([c.get("text","") for i in complain_items for c in i.get("comments",[])])

        comp_themes = []
        if any(kw in comp_all_text for kw in ["退游","弃坑","不玩了","卸载","流失","没意思","无聊"]):
            comp_themes.append("玩家流失风险预警")
        if any(kw in comp_all_text for kw in ["氪","氪金","付费","太贵","坑钱","吃相","割韭菜","逼氪"]):
            comp_themes.append("付费体验/氪金感知差")
        if any(kw in comp_all_text for kw in ["难","太难","打不过","过不去","恶心"]):
            comp_themes.append("难度体验负面反馈")
        if any(kw in comp_all_text for kw in ["垃圾","坑","差评","失望","离谱"]):
            comp_themes.append("整体游戏体验不满")
        if any(kw in comp_all_text for kw in ["肝","太累","费时间","无聊"]):
            comp_themes.append("内容消耗过快/缺乏新鲜感")
        if not comp_themes:
            comp_themes.append("综合负面反馈")

        summary.append(f'<p><strong>😤 吐槽聚焦：</strong>共 {len(complain_items)} 条吐槽内容，核心诉求集中在{"、".join(comp_themes[:3])}。需关注玩家情绪走势，及时通过版本更新改善口碑。</p>')

    # --- PRIORITY SUMMARY ---
    priority_parts = []
    if bug_items:
        priority_parts.append(f'<strong>P0 立即处理：</strong>修复 {len(bug_items)} 个已确认BUG，优先解决装备/技能机制异常类问题')
    if suggest_items:
        priority_parts.append(f'<strong>P1 本周跟进：</strong>评估 {len(suggest_items)} 条玩家建议中的高优先级项（英雄平衡、装备机制等）')
    if complain_items:
        priority_parts.append(f'<strong>P2 持续关注：</strong>跟踪 {len(complain_items)} 条吐槽反映的付费/难度/流失风险，规划中长期优化')
    if priority_parts:
        summary.append(f'<p><strong>📌 优先级：</strong>{"；".join(priority_parts)}</p>')

    # Hot topics
    if topic_counter:
        top_3 = topic_counter.most_common(3)
        summary.append(f'<p>🔥 本周热点讨论：{"、".join([f"{t}({c}次)" for t,c in top_3])}</p>')

    H.append("".join(summary))
    H.append("</div>")

    # Stats cards
    H.append(f"""<div class="stats-grid">
<div class="stat-box"><div class="num">{total}</div><div class="label">内容总数</div></div>
<div class="stat-box"><div class="num">{len(posts)}</div><div class="label">论坛帖子</div></div>
<div class="stat-box"><div class="num">{len(reviews)}</div><div class="label">评分评论</div></div>
<div class="stat-box"><div class="num">{total_c}</div><div class="label">帖子回复</div></div>
<div class="stat-box"><div class="num">{total_n}</div><div class="label">嵌套回复</div></div>
<div class="stat-box"><div class="num">{total_interact}</div><div class="label">互动总量</div></div>
</div>""")

    # Category distribution
    H.append('<div class="card"><h2>📊 分类分布</h2>')
    max_cat_cnt = max(len(cat_map.get(c,[])) for c in cat_order) or 1
    bar_colors = {"建议":"bar-suggest","BUG":"bar-bug","吐槽":"bar-complain","攻略交流":"bar-guide","官方":"bar-official","其他":"bar-other"}
    for cat in cat_order:
        cnt = len(cat_map.get(cat,[]))
        pct = cnt/max_cat_cnt*100
        H.append(f'<div class="bar-chart"><div class="bar-label">{cat}</div><div class="bar-track"><div class="bar-fill {bar_colors.get(cat,"")}" style="width:{pct:.0f}%">{cnt}条</div></div></div>')
    H.append('</div>')

    # Daily trend
    H.append('<div class="card"><h2>📅 每日数据趋势</h2><table><tr><th>日期</th><th>总内容</th><th>论坛帖子</th><th>评分</th><th>回复</th></tr>')
    sd = datetime.strptime(START_DATE, "%Y-%m-%d")
    for i in range(7):
        d = (sd + timedelta(days=i)).strftime("%Y-%m-%d")
        day_items = by_date.get(d, [])
        day_forums = len([i2 for i2 in day_items if i2["source"]=="forum"])
        day_reviews = len([i2 for i2 in day_items if i2["source"]=="review"])
        day_c = sum(len(i2.get("comments",[])) for i2 in day_items if i2["source"]=="forum")
        H.append(f'<tr><td>{d}</td><td>{len(day_items)}</td><td>{day_forums}</td><td>{day_reviews}</td><td>{day_c}</td></tr>')
    H.append('</table></div>')

    # Hot topics
    if topic_counter:
        H.append('<div class="card"><h2>🔥 热点话题</h2>')
        for topic, count in topic_counter.most_common(10):
            H.append(f'<div class="bar-chart"><div class="bar-label" style="width:90px">{topic}</div><div class="bar-track"><div class="bar-fill bar-guide" style="width:{count/max(topic_counter.values())*100:.0f}%">{count}次</div></div></div>')
        H.append('</div>')

    # Action items (moved here - right after hot topics)
    H.append('<div class="card"><h2>⚡ 开发侧可执行要点</h2>')
    bug_items = cat_map.get("BUG", [])
    p0 = bug_items[:5]
    if p0:
        H.append('<h3 class="p0">P0 - 立即处理（BUG / 异常）</h3>')
        for item in p0:
            H.append(f'<div class="priority-item">🔴 {(item.get("body","") or item.get("text",""))[:200]}')
            if item.get("url"): H.append(f' <a href="{item["url"]}" target="_blank">[链接]</a>')
            H.append('</div>')
    suggest_items = cat_map.get("建议", [])
    high_suggest = [i for i in suggest_items if any(kw in (i.get("body","") or i.get("text","") or "") for kw in ["失效","不生效","异常","无法","消失"])]
    display = high_suggest[:5] if high_suggest else suggest_items[:5]
    if display:
        H.append('<h3 class="p1">P1 - 本周跟进（高频建议）</h3>')
        for item in display:
            H.append(f'<div class="priority-item">🟠 {(item.get("body","") or item.get("text",""))[:200]}')
            if item.get("url"): H.append(f' <a href="{item["url"]}" target="_blank">[链接]</a>')
            H.append('</div>')
    complain_items = cat_map.get("吐槽", [])
    if complain_items:
        H.append('<h3 class="p2">P2 - 后续规划（玩家吐槽趋势）</h3>')
        ct = " ".join([(i.get("body","") or i.get("text","") or "") for i in complain_items])
        themes = []
        if "氪" in ct or "付费" in ct: themes.append("付费体验 / 氪金感知问题")
        if "难" in ct: themes.append("难度曲线调整")
        if "无聊" in ct or "没意思" in ct: themes.append("内容可玩性优化")
        if "平衡" in ct or "数值" in ct: themes.append("数值 / 平衡性调整")
        for t in themes: H.append(f'<div class="priority-item">⚪ {t}</div>')
        if not themes: H.append(f'<div class="priority-item">⚪ 关注玩家流失风险，共 {len(complain_items)} 条负面情绪内容</div>')
    H.append('</div>')

    # Hot discussions TOP10
    hot_posts = sorted([p for p in posts if p.get("comments")], key=lambda x: len(x["comments"]), reverse=True)[:10]
    if hot_posts:
        H.append('<div class="card"><h2>⭐ 热议帖子 TOP10</h2><table><tr><th>#</th><th>标题</th><th>作者</th><th>日期</th><th>回复</th></tr>')
        for idx, p in enumerate(hot_posts):
            title = (p.get("title","") or p.get("body","")[:40] or "（无标题）")[:50]
            H.append(f'<tr><td>{idx+1}</td><td><a href="{p["url"]}" target="_blank">{title}</a></td><td>{p["author"]}</td><td>{p["date"]}</td><td>{len(p["comments"])}</td></tr>')
        H.append('</table>')

        # Detail for top 5
        for idx, p in enumerate(hot_posts[:5]):
            title = (p.get("title","") or p.get("body","")[:30])[:40]
            H.append(f'<h3>TOP{idx+1}: <a href="{p["url"]}" target="_blank">{title}</a></h3>')
            H.append(f'<div class="item-meta">👤 {p["author"]} &nbsp;|&nbsp; 📅 {p["date"]} &nbsp;|&nbsp; 💬 {len(p["comments"])}回复 &nbsp;|&nbsp; ❤️ {p.get("likes",0)}赞</div>')
            for c in p.get("comments", [])[:5]:
                H.append(f'<div class="comment-thread"><div class="comment-user">{c["author"]}</div><div class="comment-text">{c["text"][:200]}</div>')
                for nr in c.get("nested_replies", [])[:2]:
                    H.append(f'<div class="comment-thread"><div class="comment-user">↳ {nr["author"]}</div><div class="comment-text">{nr["text"][:150]}</div></div>')
                H.append('</div>')
        H.append('</div>')

    # Suggestions
    suggest_items = cat_map.get("建议", [])
    if suggest_items:
        H.append(f'<div class="card"><h2>💡 玩家建议汇总 ({len(suggest_items)}条)</h2>')
        topic_groups = defaultdict(list)
        for item in suggest_items:
            ts = extract_topics(item.get("text",""), item.get("title",""), item.get("body",""))
            if ts:
                for t in ts: topic_groups[t].append(item)
            else:
                topic_groups["其他建议"].append(item)
        for topic, group in sorted(topic_groups.items(), key=lambda x: -len(x[1])):
            H.append(f'<h3>{topic}（{len(group)}条）</h3>')
            for item in group[:5]:
                H.append(f'<div class="item-row"><div class="item-meta">👤 {item["author"]} &nbsp;|&nbsp; 📅 {item["date"]}</div><div class="item-body">{(item.get("body","") or item.get("text",""))[:300]}</div>')
                if item.get("url"): H.append(f'<a href="{item["url"]}" target="_blank">[查看详情]</a>')
                H.append('</div>')
            if len(group) > 5: H.append(f'<div class="item-meta">...还有 {len(group)-5} 条</div>')
        H.append('</div>')

    # BUG
    if bug_items:
        H.append(f'<div class="card"><h2>🐛 BUG / 异常汇总 ({len(bug_items)}条)</h2>')
        for item in bug_items[:15]:
            body = (item.get("body","") or item.get("text",""))[:300]
            H.append(f'<div class="item-row"><span class="tag tag-bug">BUG</span> <span class="item-meta">👤 {item["author"]} &nbsp;|&nbsp; 📅 {item["date"]}</span><div class="item-body">{body}</div>')
            for c in item.get("comments", [])[:2]:
                H.append(f'<div class="comment-thread"><div class="comment-user">{c["author"]}</div><div class="comment-text">{c["text"][:150]}</div></div>')
            if item.get("url"): H.append(f'<a href="{item["url"]}" target="_blank">[查看详情]</a>')
            H.append('</div>')
        H.append('</div>')

    # Complaints
    complain_items = cat_map.get("吐槽", [])
    if complain_items:
        H.append(f'<div class="card"><h2>😤 玩家吐槽汇总 ({len(complain_items)}条)</h2>')
        for item in complain_items[:10]:
            body = (item.get("body","") or item.get("text",""))[:300]
            H.append(f'<div class="item-row"><span class="tag tag-complain">吐槽</span> <span class="item-meta">👤 {item["author"]} &nbsp;|&nbsp; 📅 {item["date"]}</span><div class="item-body">{body}</div>')
            if item.get("url"): H.append(f'<a href="{item["url"]}" target="_blank">[查看详情]</a>')
            H.append('</div>')
        H.append('</div>')

    # All posts list
    if posts:
        H.append(f'<div class="card"><h2>📋 本周全部论坛帖子 ({len(posts)}条)</h2>')
        for idx, p in enumerate(posts, 1):
            title = (p.get("title","") or p.get("body","")[:50] or "（无标题）")[:60]
            cat = p.get("category","其他")
            cat_class = {"建议":"tag-suggest","BUG":"tag-bug","吐槽":"tag-complain","攻略交流":"tag-guide","官方":"tag-official"}.get(cat,"tag-other")
            H.append(f'<div class="item-row"><span class="tag {cat_class}">{cat}</span> <span class="item-title"><a href="{p["url"]}" target="_blank">{idx}. {title}</a></span> <span class="item-meta">👤 {p["author"]} &nbsp; 📅 {p["date"]} &nbsp; 💬 {len(p.get("comments",[]))}回复</span></div>')
        H.append('</div>')

    H.append(f'<div class="footer">本报告由 TapTap 舆情监控系统自动生成 | 数据范围：{START_DATE} 00:00 ~ {END_DATE} 23:59 | {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>')
    H.append('</div></body></html>')

    return "\n".join(H)

# ══════════════════════════════════════════════
# Chat summary
# ══════════════════════════════════════════════
def generate_chat_summary(all_items, report_url=""):
    reviews = [i for i in all_items if i["source"] == "review"]
    posts   = [i for i in all_items if i["source"] == "forum"]
    total = len(all_items)

    cat_map = defaultdict(list)
    for item in all_items: cat_map[item["category"]].append(item)

    topic_counter = Counter()
    for item in all_items:
        for t in extract_topics(item.get("text",""), item.get("title",""), item.get("body","")):
            topic_counter[t] += 1
        for c in item.get("comments", []):
            for t in extract_topics(c.get("text","")): topic_counter[t] += 1

    total_c = sum(len(i.get("comments",[])) for i in all_items)
    total_n = sum(sum(len(c.get("nested_replies",[])) for c in i.get("comments",[])) for i in all_items)
    total_interact = total + total_c + total_n

    L = []
    L.append(f"📊 **{GAME_NAME} TapTap 舆情周报**")
    L.append(f"📅 {WEEK_LABEL}（共7天）")
    L.append("")

    # ── 本周舆情概括（与 HTML 报告一致的分析总结）──
    L.append(f"📋 **本周舆情概括**")
    L.append(f"本周共产生 {total} 条内容（{len(reviews)}条评分 + {len(posts)}条论坛帖子），玩家回复 {total_c} 条，嵌套回复 {total_n} 条，互动总量 {total_interact} 条。")
    L.append("")

    cat_order = ["建议","BUG","吐槽","攻略交流","官方","其他"]
    cat_parts = [f"{cat} {len(cat_map.get(cat,[]))}条" for cat in cat_order if len(cat_map.get(cat,[])) > 0]
    L.append(f"📊 **分类分布**：{'  '.join(cat_parts)}")
    L.append("")

    bug_items = cat_map.get("BUG", [])
    suggest_items = cat_map.get("建议", [])
    complain_items = cat_map.get("吐槽", [])

    # ── 建议聚焦 ──
    if suggest_items:
        sugg_text = " ".join([(i.get("body","") or i.get("text","") or "") + " " + (i.get("title","") or "") for i in suggest_items])
        sugg_text += " " + " ".join([c.get("text","") for i in suggest_items for c in i.get("comments",[])])
        suggest_themes = []
        if any(kw in sugg_text for kw in ["英雄","角色","命格","SP","阵容","sp","断荆者","塞雷娜","狼人","剑圣","英雄平衡","职业"]):
            suggest_themes.append("英雄/角色平衡与命格机制优化")
        if any(kw in sugg_text for kw in ["装备","套装","词条","武器","戒指","暴击","属性","装备词缀"]):
            suggest_themes.append("装备系统与套装效果完善")
        if any(kw in sugg_text for kw in ["难度","关卡","推图","章节","过不去"]):
            suggest_themes.append("关卡难度曲线调整")
        if any(kw in sugg_text for kw in ["活动","福利","奖励","掉落","兑换","收益"]):
            suggest_themes.append("活动频率与资源获取优化")
        if any(kw in sugg_text for kw in ["抽卡","保底","概率","十连","招募"]):
            suggest_themes.append("抽卡保底机制透明化")
        if any(kw in sugg_text for kw in ["优化","改善","改进","ui","界面","操作","手感","体验","快捷"]):
            suggest_themes.append("UI交互与操作体验提升")
        if any(kw in sugg_text for kw in ["功能","添加","增加","新玩法","新内容","pvp","公会","社交"]):
            suggest_themes.append("新玩法与新功能需求")
        if any(kw in sugg_text for kw in ["氪","付费","价格","月卡","划算"]):
            suggest_themes.append("付费体系调整建议")
        if not suggest_themes:
            suggest_themes.append("综合优化建议")
        L.append(f"💡 **建议聚焦**：玩家主要关注{"、".join(suggest_themes[:4])}等方向。共 {len(suggest_items)} 条建议帖，高频诉求集中在英雄平衡性调整与装备机制完善。")
        L.append("")

    # ── BUG聚焦 ──
    if bug_items:
        bugs_all_text = " ".join([(i.get("body","") or i.get("text","") or "") + " " + (i.get("title","") or "") for i in bug_items])
        bugs_all_text += " " + " ".join([c.get("text","") for i in bug_items for c in i.get("comments",[])])
        bug_themes = []
        if any(kw in bugs_all_text for kw in ["套装","塞雷娜","装备效果","不生效","无效","不触发","套装效果"]):
            bug_themes.append("装备/套装效果不生效")
        if any(kw in bugs_all_text for kw in ["琉璃","碎梦","武器","剑圣","大招","技能机制","技能描述","描述错误"]):
            bug_themes.append("技能机制异常或描述不符")
        if any(kw in bugs_all_text for kw in ["闪退","卡死","黑屏","崩溃","掉线","卡顿","加载","进不去"]):
            bug_themes.append("闪退/卡死/加载异常")
        if any(kw in bugs_all_text for kw in ["显示","ui","界面","乱码","不显示","看不见","消失"]):
            bug_themes.append("UI显示异常")
        if any(kw in bugs_all_text for kw in ["数据","丢失","回档","没了","吞了"]):
            bug_themes.append("数据丢失/回档")
        if any(kw in bugs_all_text for kw in ["狼人","头目","文案","描述错误"]):
            if "技能机制异常或描述不符" not in bug_themes:
                bug_themes.append("技能/文案描述错误")
        if not bug_themes:
            bug_themes.append("综合BUG反馈")
        L.append(f"🐛 **BUG聚焦**：报告了 {len(bug_items)} 个问题，主要集中在{"、".join(bug_themes[:4])}。直接影响玩家游戏体验，需优先处理。")
        L.append("")

    # ── 吐槽聚焦 ──
    if complain_items:
        comp_all_text = " ".join([(i.get("body","") or i.get("text","") or "") + " " + (i.get("title","") or "") for i in complain_items])
        comp_all_text += " " + " ".join([c.get("text","") for i in complain_items for c in i.get("comments",[])])
        comp_themes = []
        if any(kw in comp_all_text for kw in ["退游","弃坑","不玩了","卸载","流失","没意思","无聊"]):
            comp_themes.append("玩家流失风险预警")
        if any(kw in comp_all_text for kw in ["氪","氪金","付费","太贵","坑钱","吃相","割韭菜","逼氪"]):
            comp_themes.append("付费体验/氪金感知差")
        if any(kw in comp_all_text for kw in ["难","太难","打不过","过不去","恶心"]):
            comp_themes.append("难度体验负面反馈")
        if any(kw in comp_all_text for kw in ["垃圾","坑","差评","失望","离谱"]):
            comp_themes.append("整体游戏体验不满")
        if any(kw in comp_all_text for kw in ["肝","太累","费时间"]):
            comp_themes.append("内容消耗过快/缺乏新鲜感")
        if not comp_themes:
            comp_themes.append("综合负面反馈")
        L.append(f"😤 **吐槽聚焦**：共 {len(complain_items)} 条吐槽内容，核心诉求集中在{"、".join(comp_themes[:3])}。需关注玩家情绪，及时通过版本更新改善口碑。")
        L.append("")

    # ── 优先级 ──
    priority_parts = []
    if bug_items:
        priority_parts.append(f"P0 立即处理：修复 {len(bug_items)} 个已确认BUG，优先装备/技能机制异常类")
    if suggest_items:
        priority_parts.append(f"P1 本周跟进：评估 {len(suggest_items)} 条玩家建议中的高优先级项（英雄平衡、装备机制等）")
    if complain_items:
        priority_parts.append(f"P2 持续关注：跟踪 {len(complain_items)} 条吐槽反映的付费/难度/流失风险")
    if priority_parts:
        L.append(f"📌 **优先级**：{"；".join(priority_parts)}")
        L.append("")

    # ── 热议帖子 TOP10 ──
    forum_posts = [p for p in all_items if p.get("source") == "forum" and p.get("comments")]
    top10 = sorted(forum_posts, key=lambda x: len(x.get("comments", [])), reverse=True)[:10]
    if top10:
        L.append("---")
        L.append("")
        L.append("⭐ **热议帖子 TOP10**")
        L.append("")
        for idx, p in enumerate(top10):
            title = (p.get("title","") or p.get("body","")[:40] or "（无标题）")[:40]
            url = p.get("url","") or f"https://www.taptap.cn/moment/{p.get('id','')}"
            L.append(f"{idx+1}. [{title}]({url}) — {p['author']} | {len(p['comments'])}回复")
        L.append("")

    # ── 完整报告链接（仅一次）──
    L.append(f"📄 **完整周报**：{report_url or '即将部署'}")

    return "\n".join(L)

# ══════════════════════════════════════════════
# Feishu push
# ══════════════════════════════════════════════
def push_chat_summary(summary_text):
    log("[飞书聊天] 推送摘要 (interactive 卡片)...")
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"{GAME_NAME} TapTap 舆情周报"},
                "template": "blue"
            },
            "elements": [{"tag": "markdown", "content": summary_text}]
        }
    }
    try:
        r = requests.post(FEISHU_WEBHOOK, json=payload, timeout=20)
        res = r.json()
        if res.get("code") == 0:
            log("  [飞书聊天] 推送成功")
            return True
        else:
            log(f"  [飞书聊天] 推送失败: {res}")
            return False
    except Exception as e:
        log(f"  [飞书聊天] 推送异常: {e}")
        return False

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    log("=" * 60)
    log(f"{GAME_NAME} TapTap 舆情周报 v7")
    log(f"周期: {WEEK_LABEL}")
    log("=" * 60)

    # 1-3. Fetch data
    reviews = fetch_reviews()
    posts = fetch_forum()
    total_c, total_n = fetch_comments_requests(posts)

    # 4. Classify
    log(f"\n[分析] 分类中...")
    all_items = reviews + posts
    for item in all_items:
        item["category"] = classify_content(item)
    cat_count = Counter(i["category"] for i in all_items)
    log(f"  分类结果: {dict(cat_count)}")

    # 5. Save JSON
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    log(f"[保存] JSON -> {os.path.basename(JSON_FILE)} ({len(all_items)} items)")

    # 6. Generate & save HTML report
    log("[生成] HTML 周报...")
    html_report = generate_html_report(all_items)
    html_path = os.path.join(HTML_DIR, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)
    log(f"[保存] HTML -> {html_path} ({len(html_report)} chars)")

    # 7. Generate & save markdown report
    md_report = f"# {GAME_NAME} TapTap 舆情周报 ({WEEK_LABEL})\n\n详细报告请查看 HTML 版本: <CloudStudio URL>\n\n生成了 {len(all_items)} 条内容: {len(reviews)}评分 + {len(posts)}帖子 + {total_c}回复 + {total_n}嵌套"
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(md_report)

    # 8. Save chat summary and final stats (for post-deploy push)
    summary_file = os.path.join(DATA_DIR, "chat_summary_latest.txt")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(generate_chat_summary(all_items, report_url="__CLOUDSTUDIO_URL__"))

    stats_file = os.path.join(DATA_DIR, "deploy_config.json")
    deploy_cfg = {
        "html_path": html_path,
        "total_items": len(all_items),
        "review_count": len(reviews),
        "post_count": len(posts),
        "comment_count": total_c,
        "nested_count": total_n,
        "total_interact": len(reviews) + len(posts) + total_c + total_n,
        "week_label": WEEK_LABEL
    }
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(deploy_cfg, f, ensure_ascii=False)
    log(f"[保存] 摘要 + 部署配置 -> data/")

    log("=" * 60)
    log(f"汇总: {len(reviews)}评分 + {len(posts)}帖子 + {total_c}回复 + {total_n}嵌套 = {deploy_cfg['total_interact']}总互动")
    log(f"HTML 报告: {html_path}")

    # 直接推送飞书（无需等待 CloudStudio）
    chat_summary = generate_chat_summary(all_items, report_url="https://linyy663.github.io/dungeon4-monitor/weekly/")
    push_chat_summary(chat_summary)
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(chat_summary)
    log(f"[保存] 推送摘要 -> chat_summary_latest.txt")
    log("=" * 60)

if __name__ == "__main__":
    main()
