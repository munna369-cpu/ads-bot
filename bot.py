import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# == Credentials ==
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_USER_ID = int(os.environ.get("TELEGRAM_USER_ID", "0"))
DEVELOPER_TOKEN = os.environ.get("DEVELOPER_TOKEN")
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")
MCC_CUSTOMER_ID = os.environ.get("MCC_CUSTOMER_ID")
GTM_CONTAINER_ID = os.environ.get("GTM_CONTAINER_ID", "")
GTM_ACCOUNT_ID = os.environ.get("GTM_ACCOUNT_ID", "")

logging.basicConfig(level=logging.INFO)

# ==============================
# HELPERS
# ==============================

def get_ads_client():
    credentials = {
        "developer_token": DEVELOPER_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "login_customer_id": MCC_CUSTOMER_ID,
        "use_proto_plus": True
    }
    return GoogleAdsClient.load_from_dict(credentials)

def get_gtm_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token"
    )
    return build("tagmanager", "v2", credentials=creds)

def is_authorized(user_id):
    return user_id == TELEGRAM_USER_ID

async def send_loading(message, text="⏳ কাজ করছি..."):
    return await message.reply_text(text)

# ==============================
# MENUS
# ==============================

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Google Ads", callback_data="menu_ads")],
        [InlineKeyboardButton("🏷️ GTM", callback_data="menu_gtm")],
        [InlineKeyboardButton("📅 Auto Report", callback_data="menu_auto")],
    ])

def ads_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Campaign List", callback_data="campaigns")],
        [InlineKeyboardButton("📈 Performance Report (7d)", callback_data="report")],
        [InlineKeyboardButton("🎯 Lead Report (30d)", callback_data="leads")],
        [InlineKeyboardButton("💰 Account Status", callback_data="status")],
        [InlineKeyboardButton("⏸️ Campaign Pause/Resume", callback_data="campaign_toggle")],
        [InlineKeyboardButton("💵 Budget Change", callback_data="budget_menu")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ])

def gtm_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Container List", callback_data="gtm_containers")],
        [InlineKeyboardButton("🏷️ Tag List", callback_data="gtm_tags")],
        [InlineKeyboardButton("⚡ Trigger List", callback_data="gtm_triggers")],
        [InlineKeyboardButton("📝 Variable List", callback_data="gtm_variables")],
        [InlineKeyboardButton("🚀 Publish Version", callback_data="gtm_publish")],
        [InlineKeyboardButton("🕐 Version History", callback_data="gtm_versions")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized!")
        return
    await update.message.reply_text(
        "🤖 *Google Ads & GTM Bot Manager*\n\nকী করতে চাও বেছে নাও:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

# ==============================
# GOOGLE ADS FUNCTIONS
# ==============================

async def get_campaigns(message):
    loading = await send_loading(message, "📋 Campaign list আনছি...")
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT campaign.id, campaign.name, campaign.status,
                metrics.clicks, metrics.impressions, metrics.cost_micros
            FROM campaign
            WHERE segments.date DURING LAST_30_DAYS
            ORDER BY metrics.cost_micros DESC LIMIT 10
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        msg = "📋 *Campaigns (শেষ ৩০ দিন):*\n\n"
        count = 0
        for row in response:
            cost = row.metrics.cost_micros / 1_000_000
            status = "✅" if "ENABLED" in str(row.campaign.status) else "⏸️"
            msg += f"{status} *{row.campaign.name}*\n"
            msg += f"   Clicks: {row.metrics.clicks} | Cost: ${cost:.2f}\n\n"
            count += 1
        if count == 0:
            msg = "কোনো campaign নেই।"
        await loading.delete()
        await message.reply_text(msg, parse_mode="Markdown")
    except GoogleAdsException as ex:
        await loading.delete()
        await message.reply_text(f"❌ Google Ads Error: {ex.error.code().name}")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ Error: {str(ex)[:300]}")

async def get_report(message):
    loading = await send_loading(message, "📈 Report তৈরি হচ্ছে...")
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT metrics.clicks, metrics.impressions,
                metrics.cost_micros, metrics.conversions
            FROM customer
            WHERE segments.date DURING LAST_7_DAYS
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        total_clicks = total_impressions = total_cost = total_conv = 0
        for row in response:
            total_clicks += row.metrics.clicks
            total_impressions += row.metrics.impressions
            total_cost += row.metrics.cost_micros / 1_000_000
            total_conv += row.metrics.conversions
        ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        cpc = (total_cost / total_clicks) if total_clicks > 0 else 0
        msg = (
            f"📈 *শেষ ৭ দিনের Report:*\n\n"
            f"👆 Clicks: `{total_clicks}`\n"
            f"👁️ Impressions: `{total_impressions}`\n"
            f"💰 Cost: `${total_cost:.2f}`\n"
            f"🎯 Conversions: `{total_conv:.0f}`\n"
            f"📊 CTR: `{ctr:.2f}%`\n"
            f"💵 CPC: `${cpc:.2f}`"
        )
        await loading.delete()
        await message.reply_text(msg, parse_mode="Markdown")
    except GoogleAdsException as ex:
        await loading.delete()
        await message.reply_text(f"❌ Google Ads Error: {ex.error.code().name}")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ Error: {str(ex)[:300]}")

async def get_leads(message):
    loading = await send_loading(message, "🎯 Lead report আনছি...")
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT campaign.name, metrics.conversions, metrics.cost_per_conversion
            FROM campaign
            WHERE segments.date DURING LAST_30_DAYS AND metrics.conversions > 0
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        msg = "🎯 *Lead Report (শেষ ৩০ দিন):*\n\n"
        count = 0
        for row in response:
            cpl = row.metrics.cost_per_conversion / 1_000_000
            msg += f"📌 *{row.campaign.name}*\n"
            msg += f"   Leads: `{row.metrics.conversions:.0f}` | CPL: `${cpl:.2f}`\n\n"
            count += 1
        if count == 0:
            msg = "কোনো lead নেই।"
        await loading.delete()
        await message.reply_text(msg, parse_mode="Markdown")
    except GoogleAdsException as ex:
        await loading.delete()
        await message.reply_text(f"❌ Google Ads Error: {ex.error.code().name}")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ Error: {str(ex)[:300]}")

async def get_status(message):
    loading = await send_loading(message, "💰 Account status আনছি...")
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT customer.id, customer.descriptive_name, customer.currency_code
            FROM customer LIMIT 1
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        found = False
        for row in response:
            msg = (
                f"💰 *Account Status:*\n\n"
                f"🏢 Name: `{row.customer.descriptive_name}`\n"
                f"💱 Currency: `{row.customer.currency_code}`\n"
                f"🔢 ID: `{row.customer.id}`\n"
                f"✅ Status: Active"
            )
            await loading.delete()
            await message.reply_text(msg, parse_mode="Markdown")
            found = True
            break
        if not found:
            await loading.delete()
            await message.reply_text("❌ Account info পাওয়া যায়নি।")
    except GoogleAdsException as ex:
        await loading.delete()
        await message.reply_text(f"❌ Google Ads Error: {ex.error.code().name}")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ Error: {str(ex)[:300]}")

async def show_campaign_toggle(message):
    loading = await send_loading(message, "⏸️ Campaign list আনছি...")
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT campaign.id, campaign.name, campaign.status
            FROM campaign
            WHERE campaign.status != 'REMOVED'
            LIMIT 10
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        buttons = []
        for row in response:
            status = "✅" if "ENABLED" in str(row.campaign.status) else "⏸️"
            action = "pause" if "ENABLED" in str(row.campaign.status) else "enable"
            buttons.append([InlineKeyboardButton(
                f"{status} {row.campaign.name}",
                callback_data=f"toggle_{action}_{row.campaign.id}"
            )])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu_ads")])
        await loading.delete()
        await message.reply_text(
            "⏸️ *Campaign Pause/Resume:*\nক্লিক করলে status বদলাবে:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    except GoogleAdsException as ex:
        await loading.delete()
        await message.reply_text(f"❌ Google Ads Error: {ex.error.code().name}")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ Error: {str(ex)[:300]}")

async def toggle_campaign(message, action, campaign_id):
    loading = await send_loading(message, "🔄 Campaign status বদলাচ্ছি...")
    try:
        client = get_ads_client()
        campaign_service = client.get_service("CampaignService")
        campaign = client.get_type("Campaign")
        campaign.resource_name = campaign_service.campaign_path(CUSTOMER_ID, campaign_id)
        campaign.status = client.enums.CampaignStatusEnum.PAUSED if action == "pause" else client.enums.CampaignStatusEnum.ENABLED
        field_mask = client.get_type("FieldMask")
        field_mask.paths.append("status")
        op = client.get_type("CampaignOperation")
        op.update.CopyFrom(campaign)
        op.update_mask.CopyFrom(field_mask)
        campaign_service.mutate_campaigns(customer_id=CUSTOMER_ID, operations=[op])
        status_text = "⏸️ Paused" if action == "pause" else "✅ Enabled"
        await loading.delete()
        await message.reply_text(f"✅ Campaign {status_text} করা হয়েছে!")
    except GoogleAdsException as ex:
        await loading.delete()
        await message.reply_text(f"❌ Google Ads Error: {ex.error.code().name}")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ Error: {str(ex)[:300]}")

async def show_budget_menu(message):
    loading = await send_loading(message, "💵 Campaign list আনছি...")
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT campaign.id, campaign.name, campaign_budget.amount_micros
            FROM campaign
            WHERE campaign.status = 'ENABLED'
            LIMIT 10
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        buttons = []
        for row in response:
            budget = row.campaign_budget.amount_micros / 1_000_000
            buttons.append([InlineKeyboardButton(
                f"💵 {row.campaign.name} (${budget:.0f}/day)",
                callback_data=f"setbudget_{row.campaign.id}"
            )])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu_ads")])
        await loading.delete()
        await message.reply_text(
            "💵 *Budget Change:*\nকোন campaign-এর budget বদলাতে চাও?",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    except GoogleAdsException as ex:
        await loading.delete()
        await message.reply_text(f"❌ Google Ads Error: {ex.error.code().name}")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ Error: {str(ex)[:300]}")

# ==============================
# GTM FUNCTIONS
# ==============================

async def gtm_containers(message):
    loading = await send_loading(message, "📦 GTM containers আনছি...")
    try:
        service = get_gtm_service()
        result = service.accounts().containers().list(
            parent=f"accounts/{GTM_ACCOUNT_ID}"
        ).execute()
        containers = result.get("container", [])
        msg = "📦 *GTM Containers:*\n\n"
        for c in containers:
            msg += f"🔹 *{c.get('name')}*\n"
            msg += f"   ID: `{c.get('containerId')}`\n\n"
        await loading.delete()
        await message.reply_text(msg or "কোনো container নেই।", parse_mode="Markdown")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ GTM Error: {str(ex)[:300]}")

async def gtm_tags(message):
    loading = await send_loading(message, "🏷️ GTM tags আনছি...")
    try:
        service = get_gtm_service()
        parent = f"accounts/{GTM_ACCOUNT_ID}/containers/{GTM_CONTAINER_ID}/workspaces/1"
        result = service.accounts().containers().workspaces().tags().list(parent=parent).execute()
        tags = result.get("tag", [])
        msg = "🏷️ *GTM Tags:*\n\n"
        for t in tags:
            status = "✅" if not t.get("paused") else "⏸️"
            msg += f"{status} *{t.get('name')}* — `{t.get('type')}`\n\n"
        await loading.delete()
        await message.reply_text(msg or "কোনো tag নেই।", parse_mode="Markdown")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ GTM Error: {str(ex)[:300]}")

async def gtm_triggers(message):
    loading = await send_loading(message, "⚡ GTM triggers আনছি...")
    try:
        service = get_gtm_service()
        parent = f"accounts/{GTM_ACCOUNT_ID}/containers/{GTM_CONTAINER_ID}/workspaces/1"
        result = service.accounts().containers().workspaces().triggers().list(parent=parent).execute()
        triggers = result.get("trigger", [])
        msg = "⚡ *GTM Triggers:*\n\n"
        for t in triggers:
            msg += f"🔸 *{t.get('name')}* — `{t.get('type')}`\n\n"
        await loading.delete()
        await message.reply_text(msg or "কোনো trigger নেই।", parse_mode="Markdown")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ GTM Error: {str(ex)[:300]}")

async def gtm_variables(message):
    loading = await send_loading(message, "📝 GTM variables আনছি...")
    try:
        service = get_gtm_service()
        parent = f"accounts/{GTM_ACCOUNT_ID}/containers/{GTM_CONTAINER_ID}/workspaces/1"
        result = service.accounts().containers().workspaces().variables().list(parent=parent).execute()
        variables = result.get("variable", [])
        msg = "📝 *GTM Variables:*\n\n"
        for v in variables:
            msg += f"🔹 *{v.get('name')}* — `{v.get('type')}`\n\n"
        await loading.delete()
        await message.reply_text(msg or "কোনো variable নেই।", parse_mode="Markdown")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ GTM Error: {str(ex)[:300]}")

async def gtm_publish(message):
    loading = await send_loading(message, "🚀 GTM publish করছি...")
    try:
        service = get_gtm_service()
        parent = f"accounts/{GTM_ACCOUNT_ID}/containers/{GTM_CONTAINER_ID}/workspaces/1"
        version = service.accounts().containers().workspaces().create_version(
            path=parent,
            body={"name": "Auto-published", "notes": "Published via Telegram Bot"}
        ).execute()
        version_id = version.get("containerVersion", {}).get("containerVersionId")
        service.accounts().containers().versions().publish(
            path=f"accounts/{GTM_ACCOUNT_ID}/containers/{GTM_CONTAINER_ID}/versions/{version_id}"
        ).execute()
        await loading.delete()
        await message.reply_text(f"✅ GTM Version `{version_id}` publish হয়েছে!", parse_mode="Markdown")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ GTM Error: {str(ex)[:300]}")

async def gtm_versions(message):
    loading = await send_loading(message, "🕐 Version history আনছি...")
    try:
        service = get_gtm_service()
        result = service.accounts().containers().versions().list(
            parent=f"accounts/{GTM_ACCOUNT_ID}/containers/{GTM_CONTAINER_ID}"
        ).execute()
        versions = result.get("containerVersionHeader", [])[:5]
        msg = "🕐 *GTM Version History:*\n\n"
        for v in versions:
            msg += f"📌 Version `{v.get('containerVersionId')}` — {v.get('name', 'Unnamed')}\n\n"
        await loading.delete()
        await message.reply_text(msg or "কোনো version নেই।", parse_mode="Markdown")
    except Exception as ex:
        await loading.delete()
        await message.reply_text(f"❌ GTM Error: {str(ex)[:300]}")

# ==============================
# AUTO DAILY REPORT
# ==============================

async def send_daily_report(app):
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT metrics.clicks, metrics.impressions,
                metrics.cost_micros, metrics.conversions
            FROM customer
            WHERE segments.date DURING LAST_7_DAYS
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        total_clicks = total_impressions = total_cost = total_conv = 0
        for row in response:
            total_clicks += row.metrics.clicks
            total_impressions += row.metrics.impressions
            total_cost += row.metrics.cost_micros / 1_000_000
            total_conv += row.metrics.conversions
        ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        msg = (
            f"🌅 *সকালের Auto Report:*\n\n"
            f"👆 Clicks: `{total_clicks}`\n"
            f"👁️ Impressions: `{total_impressions}`\n"
            f"💰 Cost: `${total_cost:.2f}`\n"
            f"🎯 Conversions: `{total_conv:.0f}`\n"
            f"📊 CTR: `{ctr:.2f}%`"
        )
        await app.bot.send_message(chat_id=TELEGRAM_USER_ID, text=msg, parse_mode="Markdown")
    except Exception as ex:
        await app.bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"❌ Auto report error: {str(ex)[:200]}")

# ==============================
# BUTTON HANDLER
# ==============================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    msg = query.message

    if data == "main_menu":
        await msg.reply_text("কী করতে চাও বেছে নাও:", reply_markup=main_menu_keyboard())
    elif data == "menu_ads":
        await msg.reply_text("📊 *Google Ads Menu:*", reply_markup=ads_menu_keyboard(), parse_mode="Markdown")
    elif data == "menu_gtm":
        await msg.reply_text("🏷️ *GTM Menu:*", reply_markup=gtm_menu_keyboard(), parse_mode="Markdown")
    elif data == "menu_auto":
        await msg.reply_text("📅 প্রতিদিন সকাল ৯টায় auto report পাঠানো হবে। ✅")
    elif data == "campaigns":
        await get_campaigns(msg)
    elif data == "report":
        await get_report(msg)
    elif data == "leads":
        await get_leads(msg)
    elif data == "status":
        await get_status(msg)
    elif data == "campaign_toggle":
        await show_campaign_toggle(msg)
    elif data == "budget_menu":
        await show_budget_menu(msg)
    elif data.startswith("toggle_"):
        parts = data.split("_")
        action = parts[1]
        campaign_id = parts[2]
        await toggle_campaign(msg, action, campaign_id)
    elif data.startswith("setbudget_"):
        campaign_id = data.split("_")[1]
        context.user_data["budget_campaign_id"] = campaign_id
        await msg.reply_text("💵 নতুন daily budget লিখো (শুধু সংখ্যা, যেমন: 50):")
    elif data == "gtm_containers":
        await gtm_containers(msg)
    elif data == "gtm_tags":
        await gtm_tags(msg)
    elif data == "gtm_triggers":
        await gtm_triggers(msg)
    elif data == "gtm_variables":
        await gtm_variables(msg)
    elif data == "gtm_publish":
        await gtm_publish(msg)
    elif data == "gtm_versions":
        await gtm_versions(msg)

# ==============================
# TEXT HANDLER (budget input)
# ==============================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    campaign_id = context.user_data.get("budget_campaign_id")
    if not campaign_id:
        return
    text = update.message.text.strip()
    if not (text.isdigit() or text.replace(".", "").isdigit()):
        await update.message.reply_text("❌ শুধু সংখ্যা লিখো, যেমন: 50")
        return
    loading = await send_loading(update.message, "💵 Budget update করছি...")
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT campaign.campaign_budget
            FROM campaign
            WHERE campaign.id = {campaign_id}
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        budget_resource = None
        for row in response:
            budget_resource = row.campaign.campaign_budget
        if budget_resource:
            budget_service = client.get_service("CampaignBudgetService")
            budget = client.get_type("CampaignBudget")
            budget.resource_name = budget_resource
            budget.amount_micros = int(float(text) * 1_000_000)
            field_mask = client.get_type("FieldMask")
            field_mask.paths.append("amount_micros")
            op = client.get_type("CampaignBudgetOperation")
            op.update.CopyFrom(budget)
            op.update_mask.CopyFrom(field_mask)
            budget_service.mutate_campaign_budgets(customer_id=CUSTOMER_ID, operations=[op])
            context.user_data.pop("budget_campaign_id", None)
            await loading.delete()
            await update.message.reply_text(f"✅ Budget `${text}/day` সেট হয়েছে!", parse_mode="Markdown")
        else:
            await loading.delete()
            await update.message.reply_text("❌ Campaign খুঁজে পাওয়া যায়নি।")
    except GoogleAdsException as ex:
        await loading.delete()
        await update.message.reply_text(f"❌ Google Ads Error: {ex.error.code().name}")
    except Exception as ex:
        await loading.delete()
        await update.message.reply_text(f"❌ Error: {str(ex)[:300]}")

# ==============================
# MAIN
# ==============================

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_report, "cron", hour=9, minute=0, args=[app])
    scheduler.start()

    print("Bot চালু হয়েছে!")
    app.run_polling()

if __name__ == "__main__":
    main()
