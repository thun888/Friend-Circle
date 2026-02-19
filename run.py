import logging
import json
import sys
import os
import requests

from friend_circle_lite.get_info import (
    fetch_and_process_data,
    marge_data_from_json_url,
    marge_errors_from_json_url,
    deal_with_large_data
)
from friend_circle_lite.get_conf import load_config
from rss_subscribe.push_article_update import (
    get_latest_articles_from_link,
    extract_emails_from_issues
)
from push_rss_update.send_email import send_emails

# ========== 日志设置 ==========
logging.basicConfig(
    level=logging.INFO,
    format='😋 %(levelname)s: %(message)s'
)

# ========== 加载配置 ==========
config = load_config("./conf.yaml")

# ========== 爬虫模块 ==========
if config["spider_settings"]["enable"]:
    logging.info("✅ 爬虫已启用")

    json_url = config['spider_settings']['json_url']
    article_count = config['spider_settings']['article_count']
    specific_rss = config['specific_RSS']

    logging.info(f"📥 正在从 {json_url} 获取数据，每个博客获取 {article_count} 篇文章")
    result, lost_friends = fetch_and_process_data(
        json_url=json_url,
        specific_RSS=specific_rss,
        count=article_count
    ) # type: ignore

    if config["spider_settings"]["merge_result"]["enable"]:
        merge_url = config['spider_settings']["merge_result"]['merge_json_url']
        logging.info(f"🔀 合并功能开启，从 {merge_url} 获取外部数据")

        result = marge_data_from_json_url(result, f"{merge_url}/all.json")
        lost_friends = marge_errors_from_json_url(lost_friends, f"{merge_url}/errors.json")

    article_count = len(result.get("article_data", []))
    logging.info(f"📦 数据获取完毕，共有 {article_count} 位好友的动态，正在处理数据")

    result = deal_with_large_data(result)

    with open("all.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open("results_30.json", "w", encoding="utf-8") as f:
        result = deal_with_large_data(result, max_articles=30)
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open("errors.json", "w", encoding="utf-8") as f:
        json.dump(lost_friends, f, ensure_ascii=False, indent=2)

# ========== 邮箱推送准备 ==========
SMTP_isReady = False

sender_email = ""
server = ""
port = 0
use_tls = False
password = ""
tg_chat_id = ""
tg_bot_token = ""

if config["email_push"]["enable"] or config["rss_subscribe"]["enable"]:
    logging.info("📨 推送功能已启用，正在准备中...")

    smtp_conf = config["smtp"]
    sender_email = smtp_conf["email"]
    server = smtp_conf["server"]
    port = smtp_conf["port"]
    use_tls = smtp_conf["use_tls"]
    password = os.getenv("SMTP_PWD")
    tg_chat_id = config["tg"]["chat_id"]
    tg_bot_token = os.getenv("TG_BOT_TOKEN")

    logging.info(f"📡 SMTP 服务器：{server}:{port}")
    if not password or not sender_email or not server or not port:
        logging.error("❌ 环境变量 SMTP_PWD 未设置，无法发送邮件")
    else:
        # logging.info(f"🔐 密码(部分)：{password[:3]}*****")
        SMTP_isReady = True

# ========== 邮件推送（待实现）==========
if config["email_push"]["enable"] and SMTP_isReady:
    logging.info("📧 邮件推送已启用")
    logging.info("⚠️ 抱歉，目前尚未实现邮件推送功能")

# ========== RSS 订阅推送 ==========
if config["rss_subscribe"]["enable"] and SMTP_isReady:
    logging.info("📰 RSS 订阅推送已启用")

    # 获取 GitHub 仓库信息
    fcl_repo = os.getenv('FCL_REPO') # 仓库内置
    if fcl_repo:
        github_username, github_repo = fcl_repo.split('/')
    else:
        github_username = str(config["rss_subscribe"]["github_username"]).strip()
        github_repo = str(config["rss_subscribe"]["github_repo"]).strip()

    logging.info(f"👤 GitHub 用户名：{github_username}")
    logging.info(f"📁 GitHub 仓库：{github_repo}")

    your_blog_url = config["rss_subscribe"]["your_blog_url"]
    email_template = config["rss_subscribe"]["email_template"]
    website_title = config["rss_subscribe"]["website_info"]["title"]

    latest_articles = get_latest_articles_from_link(
        url=your_blog_url,
        count=5,
        last_articles_path="./rss_subscribe/last_articles.json" # 存储上一次的文章
    )

    if not latest_articles:
        logging.info("📭 无新文章，无需推送")
    else:
        logging.info(f"🆕 获取到的最新文章：{latest_articles}")

        github_api_url = (
            f"https://api.github.com/repos/{github_username}/{github_repo}/issues"
            f"?state=closed&label=subscribed&per_page=200"
        )
        logging.info(f"🔎 正在从 GitHub 获取订阅邮箱：{github_api_url}")
        email_list = extract_emails_from_issues(github_api_url)

        if not email_list:
            logging.info("⚠️ 无订阅邮箱，请检查格式或是否有订阅者")
            sys.exit(0)

        logging.info(f"📬 获取到邮箱列表：{email_list}")

        for article in latest_articles:
            template_data = {
                "title": article["title"],
                "summary": article["summary"],
                "published": article["published"],
                "link": article["link"],
                "website_title": website_title,
                "github_issue_url": (
                    f"https://github.com/{github_username}/{github_repo}"
                    "/issues?q=is%3Aissue+is%3Aclosed"
                ),
            }

            send_emails(
                emails=email_list["emails"],
                sender_email=sender_email,
                smtp_server=server,
                port=port,
                password=password,
                subject=f"{website_title} 的最新文章：{article['title']}",
                body=(
                    f"📄 文章标题：{article['title']}\n"
                    f"🔗 链接：{article['link']}\n"
                    f"📝 简介：{article['summary']}\n"
                    f"🕒 发布时间：{article['published']}"
                ),
                template_path=email_template,
                template_data=template_data,
                use_tls=use_tls
            )

            # Push to Talegram Channel
            title = "#NewArticle"
            message = f"🥳 有新文章：[{article['title']}]({article['link']})\n📝 简介：{article['summary']}\n"
            url = f"https://api.telegram.org/bot{tg_bot_token}/sendMessage"
            payload = {
                "chat_id": tg_chat_id,
                "text": f"{title} \n {message}",
                "parse_mode": "Markdown",
                "disable_web_page_preview": "true"
            }

            response = requests.post(url, data=payload)
            if response.json()["ok"]:
                print("推送到频道成功")
            else:
                print(response.json())