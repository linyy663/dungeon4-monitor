# -*- coding: utf-8 -*-
"""
TapTap 深空之眼 舆情日报
- 抓取单日数据（默认昨天）
- 生成HTML日报（仅本地，不推送飞书）
"""
import sys, os, json, time, re, uuid, urllib.parse
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
import requests

# ── Config ──────────────────────────────────────
APP_ID    = "213181"
GROUP_ID  = "295957"
GAME_NAME = "深空之眼"

today = datetime.now()
DATE = (today - timedelta(days=1)).strftime("%Y-%m-%d")

DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "aether_gazer")
JSON_FILE    = os.path.join(DATA_DIR, f"taptap_daily_{DATE}.json")
HTML_DIR     = os.path.join(DATA_DIR, "html_report")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HTML_DIR, exist_ok=True)

CST = timezone(timedelta(hours=8))

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
              "没实装","面板错误","伤害异常","穿模"]
    suggest_kw = ["建议","希望","能不能","求","期待","优化","改善","改进","增加","添加","加入",
                  "更新","调整","平衡","修改","改一下","活动","福利","奖励","玩法","功能",
                  "要是","如果","出个","来个","开放","保底","概率","透明","公示","说明",
                  "加点","降低","提高","加强","削弱","引导","提示","新手","难度",
                  "复刻","返场","皮肤","联机","端游","模拟器","怀旧服"]
    complain_kw = ["垃圾","坑","骗","太贵","不值","差评","失望","后悔","恶心","离谱","无语",
                   "不好玩","无聊","没意思","浪费时间","弃坑","卸载","不玩了","退游","关服",
                   "停服","暴毙","腰斩","换皮","抄袭","逼氪","吃相","难看","割韭菜","氪金",
                   "付费","坑钱","骗氪","逼肝","服了","辣鸡","再见","晚安"]
    guide_kw = ["攻略","阵容","打法","过关","配置","阵容推荐","怎么打","怎么过","求阵容",
                "求助","请教","大佬","指点","帮忙看看","分享","思路","带什么","配什么",
                "用什么","选哪个","怎么配","怎么选","哪个好","谁厉害","通关",
                "刻印","神格","专武","钥从","赋能","配队"]
    official_kw = ["公告","官方","可公开","更新预告","维护预告","活动预告","版本"]

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
        "修正者/角色": ["修正者","角色","薇儿","奥西里斯","托特","诗寇蒂","天庚","赫拉",
                       "海拉","冥王","重明","武罗","凯丽","技能","强度","新角色"],
        "刻印/装备": ["刻印","钥从","专武","神格","赋能","装备","词条","套装"],
        "抽卡/保底": ["抽卡","保底","概率","抽到","十连","招募","歪了","出货"],
        "付费/氪金": ["氪","充值","付费","月卡","价格","划算","双倍","礼包"],
        "活动/福利": ["活动","福利","奖励","掉落","兑换","签到","版本"],
        "剧情/世界观": ["剧情","主线","支线","盖亚","视骸","文案","配音","CG"],
        "停服相关": ["停服","关服","暴毙","告别","最后","没了","腰斩","新游","勇仕"],
        "联机/模式": ["联机","组队","公会","模拟器","端游","手机","画质","体验"],
        "BUG/异常": ["bug","异常","错误","闪退","卡死","穿模"],
        "攻略/打法": ["攻略","打法","思路","怎么打","阵容推荐","配队"],
    }
    for topic, kws in patterns.items():
        if any(kw in full_text for kw in kws):
            topics.add(topic)
    return list(topics)

# ══════════════════════════════════════════════
# Fetch reviews (single day)
# ══════════════════════════════════════════════
def fetch_reviews(date_str):
    log(f"[1/3] 抓取评分评论 ({date_str})...")
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json", "Referer": f"https://www.taptap.cn/app/{APP_ID}",
    })
    try: sess.get(f"https://www.taptap.cn/app/{APP_ID}", timeout=15)
    except: pass
    xua = urllib.parse.quote(f"V=1&PN=WebApp&LANG=zh_CN&VN_CODE=102&LOC=CN&PLT=PC&DS=Android&UID={uuid.uuid4()}&OS=Windows&OSV=10&DT=PC")

    all_reviews, from_offset, found_older, fail_streak = [], 0, False, 0
    while from_offset < 500:
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
        for item in items:
            ri = extract_review_item(item)
            if ri["date"] == date_str: all_reviews.append(ri)
            elif ri["date"] < date_str: found_older = True
        if found_older and from_offset >= 50: break
        from_offset += 10; time.sleep(0.8)
    log(f"  [评论] 共 {len(all_reviews)} 条")
    return all_reviews

# ══════════════════════════════════════════════
# Fetch forum posts (single day)
# ══════════════════════════════════════════════
JS_FETCH = "async (url) => { try { const r = await fetch(url, {credentials:'include'}); const t = await r.text(); return {ok:r.ok, status:r.status, body:t}; } catch(e) { return {ok:false, status:0, body:e.toString()}; } }"

def _fetch_forum_requests(sess, xua, date_str):
    all_posts, from_offset, found_older, fail_streak = [], 0, False, 0
    while from_offset < 1000:
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
        for item in items:
            fi = extract_forum_item(item)
            if fi["date"] == date_str: all_posts.append(fi)
            elif fi["date"] < date_str: found_older = True
        pn = from_offset//10+1
        log(f"  [论坛] p{pn}: {len(items)}条, 范围匹配: {sum(1 for x in items if extract_forum_item(x)['date']==date_str)}")
        if found_older and from_offset >= 100: break
        from_offset += 10; time.sleep(0.8)
    log(f"  [论坛] 共 {len(all_posts)} 条")
    return all_posts

def _fetch_forum_playwright(xua, date_str):
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
        while from_offset < 1000:
            url = f"https://www.taptap.cn/webapiv2/feed/v7/by-group?from={from_offset}&group_id={GROUP_ID}&limit=10&sort=created&status=0&type=feed&with_hot_comment=true&X-UA={xua}"
            try:
                result = page.evaluate(JS_FETCH, url)
            except:
                fail_streak += 1; time.sleep(2)
                if fail_streak >= 5: break; continue
            if not result or not result.get("ok"):
                fail_streak += 1; from_offset += 10; time.sleep(1)
                if fail_streak >= 5: break; continue
            fail_streak = 0
            try: d = json.loads(result["body"])
            except: from_offset += 10; continue
            items = d.get("data",{}).get("list",[])
            if not items: break
            for item in items:
                fi = extract_forum_item(item)
                if fi["date"] == date_str: all_posts.append(fi)
                elif fi["date"] < date_str: found_older = True
            pn = from_offset//10+1
            log(f"  [论坛] p{pn}: {len(items)}条, 范围匹配: {sum(1 for x in items if extract_forum_item(x)['date']==date_str)}")
            if found_older and from_offset >= 100: break
            from_offset += 10; time.sleep(0.3)
        browser.close()
    log(f"  [论坛] 共 {len(all_posts)} 条")
    return all_posts

def fetch_forum(date_str):
    log(f"[2/3] 抓取论坛帖子 ({date_str})...")
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
            log("  [论坛] requests 不可用，切换到 Playwright")
    except:
        log("  [论坛] requests 异常，切换到 Playwright")

    if use_requests:
        return _fetch_forum_requests(sess, xua, date_str)
    return _fetch_forum_playwright(xua, date_str)

# ══════════════════════════════════════════════
# Fetch comments
# ══════════════════════════════════════════════
def fetch_comments_requests(all_posts):
    if not all_posts: return 0, 0
    log(f"[3/3] 抓取 {len(all_posts)} 个帖子的回复...")
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
# HTML Report
# ══════════════════════════════════════════════
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f7fa;color:#333;line-height:1.7}
.container{max-width:900px;margin:0 auto;padding:20px}
.header{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;padding:40px 30px;border-radius:12px;margin-bottom:24px}
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
.bar-label{width:80px;font-size:13px;text-align:right;padding-right:8px}
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

def summarize_items(items, label="问题"):
    if not items: return ""
    lines = []
    for i, item in enumerate(items[:5]):
        title = (item.get("title", "") or item.get("body", "")[:30] or "无标题")[:40]
        body = (item.get("body", "") or item.get("text", "") or "")
        snippet = body[:150].replace("\n", " ").strip()
        if not snippet: snippet = title
        lines.append(f"{i+1}. **{title}**：{snippet}")
    return "\n".join(lines)

def generate_html_report(all_items, date_str):
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

    H = []
    H.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{GAME_NAME} TapTap舆情日报 {date_str}</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
<div class="header" style="background:linear-gradient(135deg,#1a1a2e,#0f3460)">
<h1>{GAME_NAME} TapTap 舆情日报</h1>
<div class="meta">📅 {date_str} &nbsp;|&nbsp; 🕐 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; 📡 数据来源: TapTap</div>
</div>""")

    cat_order = ["建议","BUG","吐槽","攻略交流","官方","其他"]
    bug_items = cat_map.get("BUG", [])
    suggest_items = cat_map.get("建议", [])
    complain_items = cat_map.get("吐槽", [])

    # Summary
    H.append('<div class="summary-box"><h2>📋 本日舆情概括</h2>')
    cat_parts = []
    for i, cat in enumerate(cat_order):
        cnt = len(cat_map.get(cat, []))
        if cnt > 0: cat_parts.append(f'<span class="tag tag-{["suggest","bug","complain","guide","official","other"][i]}">{cat} {cnt}条</span>')
    H.append(f'<p>本日共产生 <strong>{total}</strong> 条内容（{len(reviews)}条评分 + {len(posts)}条论坛帖子），玩家回复 <strong>{total_c}</strong> 条，嵌套回复 <strong>{total_n}</strong> 条，互动总量 <strong>{total_interact}</strong> 条。分类分布：{" ".join(cat_parts)}</p>')

    if suggest_items:
        H.append(f'<p><strong>💡 建议聚焦：</strong>玩家主要关注修正者平衡、刻印机制优化、活动福利等方向。共 {len(suggest_items)} 条建议帖。</p>')
    if bug_items:
        H.append(f'<p><strong>🐛 BUG聚焦：</strong>报告了 <strong>{len(bug_items)}</strong> 个问题：</p>')
        bug_summary = summarize_items(bug_items, "BUG")
        for line in bug_summary.split("\n"):
            H.append(f'<p style="margin:2px 0 2px 16px;font-size:13px">{line}</p>')
    if complain_items:
        H.append(f'<p><strong>😤 吐槽聚焦：</strong>共 {len(complain_items)} 条负面内容：</p>')
        comp_summary = summarize_items(complain_items, "吐槽")
        for line in comp_summary.split("\n"):
            H.append(f'<p style="margin:2px 0 2px 16px;font-size:13px">{line}</p>')

    priority_parts = []
    if bug_items: priority_parts.append(f'<strong>P0</strong> 修复 {len(bug_items)} 个BUG')
    if suggest_items: priority_parts.append(f'<strong>P1</strong> 评估 {len(suggest_items)} 条建议')
    if complain_items: priority_parts.append(f'<strong>P2</strong> 关注 {len(complain_items)} 条吐槽')
    if priority_parts:
        H.append(f'<p><strong>📌 优先级：</strong>{"；".join(priority_parts)}</p>')
    if topic_counter:
        top_3 = topic_counter.most_common(3)
        H.append(f'<p>🔥 本日热点：{"、".join([f"{t}({c}次)" for t,c in top_3])}</p>')
    H.append('</div>')

    # Stats
    H.append(f"""<div class="stats-grid">
<div class="stat-box"><div class="num">{total}</div><div class="label">内容总数</div></div>
<div class="stat-box"><div class="num">{len(posts)}</div><div class="label">论坛帖子</div></div>
<div class="stat-box"><div class="num">{len(reviews)}</div><div class="label">评分评论</div></div>
<div class="stat-box"><div class="num">{total_c}</div><div class="label">帖子回复</div></div>
<div class="stat-box"><div class="num">{total_n}</div><div class="label">嵌套回复</div></div>
<div class="stat-box"><div class="num">{total_interact}</div><div class="label">互动总量</div></div>
</div>""")

    # Category
    H.append('<div class="card"><h2>📊 分类分布</h2>')
    max_cat_cnt = max(len(cat_map.get(c,[])) for c in cat_order) or 1
    bar_colors = {"建议":"bar-suggest","BUG":"bar-bug","吐槽":"bar-complain","攻略交流":"bar-guide","官方":"bar-official","其他":"bar-other"}
    for cat in cat_order:
        cnt = len(cat_map.get(cat,[]))
        pct = cnt/max_cat_cnt*100
        H.append(f'<div class="bar-chart"><div class="bar-label">{cat}</div><div class="bar-track"><div class="bar-fill {bar_colors.get(cat,"")}" style="width:{pct:.0f}%">{cnt}条</div></div></div>')
    H.append('</div>')

    # Hot topics
    if topic_counter:
        H.append('<div class="card"><h2>🔥 热点话题</h2>')
        for topic, count in topic_counter.most_common(8):
            H.append(f'<div class="bar-chart"><div class="bar-label" style="width:90px">{topic}</div><div class="bar-track"><div class="bar-fill bar-guide" style="width:{count/max(topic_counter.values())*100:.0f}%">{count}次</div></div></div>')
        H.append('</div>')

    # Action items
    H.append('<div class="card"><h2>⚡ 开发侧要点</h2>')
    if bug_items:
        H.append('<h3 class="p0">P0 - 立即处理（BUG）</h3>')
        for item in bug_items[:5]:
            body = (item.get("body","") or item.get("text",""))[:200]
            H.append(f'<div class="priority-item">🔴 {body}')
            if item.get("url"): H.append(f' <a href="{item["url"]}" target="_blank">[链接]</a>')
            H.append('</div>')
    display_s = [i for i in suggest_items if any(kw in (i.get("body","") or i.get("text","") or "") for kw in ["失效","不生效","异常","无法","消失"])] or suggest_items[:5]
    if display_s:
        H.append('<h3 class="p1">P1 - 本周跟进（建议）</h3>')
        for item in display_s[:5]:
            body = (item.get("body","") or item.get("text",""))[:200]
            H.append(f'<div class="priority-item">🟠 {body}')
            if item.get("url"): H.append(f' <a href="{item["url"]}" target="_blank">[链接]</a>')
            H.append('</div>')
    if complain_items:
        H.append('<h3 class="p2">P2 - 关注（吐槽趋势）</h3>')
        H.append(f'<div class="priority-item">⚪ 共 {len(complain_items)} 条负面内容，关注玩家情绪</div>')
    H.append('</div>')

    # Hot posts TOP10 + TOP3 comments
    hot_posts = sorted([p for p in posts if p.get("comments")], key=lambda x: len(x["comments"]), reverse=True)[:10]
    if hot_posts:
        H.append('<div class="card"><h2>⭐ 热议帖子 TOP10</h2><table><tr><th>#</th><th>标题</th><th>作者</th><th>回复</th></tr>')
        for idx, p in enumerate(hot_posts):
            title = (p.get("title","") or p.get("body","")[:40] or "（无标题）")[:50]
            H.append(f'<tr><td>{idx+1}</td><td><a href="{p["url"]}" target="_blank">{title}</a></td><td>{p["author"]}</td><td>{len(p["comments"])}</td></tr>')
        H.append('</table>')
        for idx, p in enumerate(hot_posts[:3]):
            title = (p.get("title","") or p.get("body","")[:30])[:40]
            H.append(f'<h3>TOP{idx+1}: <a href="{p["url"]}" target="_blank">{title}</a></h3>')
            H.append(f'<div class="item-meta">👤 {p["author"]}  |  💬 {len(p["comments"])}回复</div>')
            for c in p.get("comments", [])[:3]:
                H.append(f'<div class="comment-thread"><div class="comment-user">{c["author"]}</div><div class="comment-text">{c["text"][:200]}</div>')
                for nr in c.get("nested_replies", [])[:2]:
                    H.append(f'<div class="comment-thread"><div class="comment-user">↳ {nr["author"]}</div><div class="comment-text">{nr["text"][:150]}</div></div>')
                H.append('</div>')
        H.append('</div>')

    # All posts
    if posts:
        H.append(f'<div class="card"><h2>📋 本日全部论坛帖子 ({len(posts)}条)</h2>')
        for idx, p in enumerate(posts, 1):
            title = (p.get("title","") or p.get("body","")[:50] or "（无标题）")[:60]
            cat = p.get("category","其他")
            cat_class = {"建议":"tag-suggest","BUG":"tag-bug","吐槽":"tag-complain","攻略交流":"tag-guide","官方":"tag-official"}.get(cat,"tag-other")
            H.append(f'<div class="item-row"><span class="tag {cat_class}">{cat}</span> <span class="item-title"><a href="{p["url"]}" target="_blank">{idx}. {title}</a></span> <span class="item-meta">👤 {p["author"]}  💬 {len(p.get("comments",[]))}回复</span></div>')
        H.append('</div>')

    H.append(f'<div class="footer">日报由 TapTap 舆情监控系统自动生成 | {date_str} | {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>')
    H.append('</div></body></html>')
    return "\n".join(H)

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════
def main():
    log("=" * 60)
    log(f"{GAME_NAME} TapTap 舆情日报")
    log(f"日期: {DATE}")
    log("=" * 60)

    reviews = fetch_reviews(DATE)
    posts = fetch_forum(DATE)
    total_c, total_n = fetch_comments_requests(posts)

    all_items = reviews + posts
    for item in all_items:
        item["category"] = classify_content(item)
    cat_count = Counter(i["category"] for i in all_items)
    log(f"\n分类结果: {dict(cat_count)}")

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    log(f"[保存] JSON -> {os.path.basename(JSON_FILE)} ({len(all_items)} items)")

    log("[生成] HTML 日报...")
    html_report = generate_html_report(all_items, DATE)
    html_path = os.path.join(HTML_DIR, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)
    log(f"[保存] HTML -> {html_path} ({len(html_report)} chars)")

    log("=" * 60)
    log(f"汇总: {len(reviews)}评分 + {len(posts)}帖子 + {total_c}回复 + {total_n}嵌套 = {len(reviews)+len(posts)+total_c+total_n}总互动")
    log(f"HTML 报告路径: {html_path}")
    log("=" * 60)

if __name__ == "__main__":
    main()
