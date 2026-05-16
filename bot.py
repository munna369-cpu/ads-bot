import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# == Railway Variables থেকে credentials নেবে ==
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_USER_ID = int(os.environ.get("TELEGRAM_USER_ID", "0"))
DEVELOPER_TOKEN = os.environ.get("DEVELOPER_TOKEN")
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")
MCC_CUSTOMER_ID = os.environ.get("MCC_CUSTOMER_ID")

logging.basicConfig(level=logging.INFO)

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

def is_authorized(user_id):
    return user_id == TELEGRAM_USER_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized!")
        return
    keyboard = [
        [InlineKeyboardButton("Campaign List", callback_data="campaigns")],
        [InlineKeyboardButton("Performance Report", callback_data="report")],
        [InlineKeyboardButton("Leads", callback_data="leads")],
        [InlineKeyboardButton("Account Status", callback_data="status")],
    ]
    await update.message.reply_text(
        "Google Ads Bot Manager\n\nনিচের বাটন থেকে কাজ বেছে নাও:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    await update.message.reply_text("Campaign list আনছি...")
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
        message = "Campaigns (শেষ ৩০ দিন):\n\n"
        for row in response:
            cost = row.metrics.cost_micros / 1_000_000
            message += f"- {row.campaign.name}\n"
            message += f"  Clicks: {row.metrics.clicks} | Cost: ${cost:.2f}\n\n"
        await update.message.reply_text(message or "কোনো campaign নেই।")
    except GoogleAdsException as ex:
        await update.message.reply_text(f"Error: {ex.error.code().name}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    await update.message.reply_text("Report তৈরি হচ্ছে...")
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
        message = (
            f"শেষ ৭ দিনের Report:\n\n"
            f"Clicks: {total_clicks}\n"
            f"Impressions: {total_impressions}\n"
            f"Cost: ${total_cost:.2f}\n"
            f"Conversions: {total_conv:.0f}\n"
            f"CTR: {ctr:.2f}%"
        )
        await update.message.reply_text(message)
    except GoogleAdsException as ex:
        await update.message.reply_text(f"Error: {ex.error.code().name}")

async def leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT campaign.name, metrics.conversions, metrics.cost_per_conversion
            FROM campaign
            WHERE segments.date DURING LAST_30_DAYS AND metrics.conversions > 0
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        message = "Lead Report (শেষ ৩০ দিন):\n\n"
        for row in response:
            cpl = row.metrics.cost_per_conversion / 1_000_000
            message += f"- {row.campaign.name}\n"
            message += f"  Leads: {row.metrics.conversions:.0f} | CPL: ${cpl:.2f}\n\n"
        await update.message.reply_text(message or "কোনো lead নেই।")
    except GoogleAdsException as ex:
        await update.message.reply_text(f"Error: {ex.error.code().name}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    try:
        client = get_ads_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT customer.id, customer.descriptive_name, customer.currency_code
            FROM customer LIMIT 1
        """
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        for row in response:
            message = (
                f"Account Status:\n\n"
                f"Name: {row.customer.descriptive_name}\n"
                f"Currency: {row.customer.currency_code}\n"
                f"ID: {row.customer.id}\n"
                f"Status: Active"
            )
            await update.message.reply_text(message)
            return
    except GoogleAdsException as ex:
        await update.message.reply_text(f"Error: {ex.error.code().name}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "campaigns":
        await query.message.reply_text("Campaign list আনছি...")
        try:
            client = get_ads_client()
            ga_service = client.get_service("GoogleAdsService")
            q = """
                SELECT campaign.id, campaign.name, campaign.status,
                    metrics.clicks, metrics.impressions, metrics.cost_micros
                FROM campaign
                WHERE segments.date DURING LAST_30_DAYS
                ORDER BY metrics.cost_micros DESC LIMIT 10
            """
            response = ga_service.search(customer_id=CUSTOMER_ID, query=q)
            message = "Campaigns (শেষ ৩০ দিন):\n\n"
            for row in response:
                cost = row.metrics.cost_micros / 1_000_000
                message += f"- {row.campaign.name}\n"
                message += f"  Clicks: {row.metrics.clicks} | Cost: ${cost:.2f}\n\n"
            await query.message.reply_text(message or "কোনো campaign নেই।")
        except GoogleAdsException as ex:
            await query.message.reply_text(f"Error: {ex.error.code().name}")

    elif query.data == "report":
        await query.message.reply_text("Report তৈরি হচ্ছে...")
        try:
            client = get_ads_client()
            ga_service = client.get_service("GoogleAdsService")
            q = """
                SELECT metrics.clicks, metrics.impressions,
                    metrics.cost_micros, metrics.conversions
                FROM customer
                WHERE segments.date DURING LAST_7_DAYS
            """
            response = ga_service.search(customer_id=CUSTOMER_ID, query=q)
            total_clicks = total_impressions = total_cost = total_conv = 0
            for row in response:
                total_clicks += row.metrics.clicks
                total_impressions += row.metrics.impressions
                total_cost += row.metrics.cost_micros / 1_000_000
                total_conv += row.metrics.conversions
            ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            message = (
                f"শেষ ৭ দিনের Report:\n\n"
                f"Clicks: {total_clicks}\n"
                f"Impressions: {total_impressions}\n"
                f"Cost: ${total_cost:.2f}\n"
                f"Conversions: {total_conv:.0f}\n"
                f"CTR: {ctr:.2f}%"
            )
            await query.message.reply_text(message)
        except GoogleAdsException as ex:
            await query.message.reply_text(f"Error: {ex.error.code().name}")

    elif query.data == "leads":
        try:
            client = get_ads_client()
            ga_service = client.get_service("GoogleAdsService")
            q = """
                SELECT campaign.name, metrics.conversions, metrics.cost_per_conversion
                FROM campaign
                WHERE segments.date DURING LAST_30_DAYS AND metrics.conversions > 0
            """
            response = ga_service.search(customer_id=CUSTOMER_ID, query=q)
            message = "Lead Report (শেষ ৩০ দিন):\n\n"
            for row in response:
                cpl = row.metrics.cost_per_conversion / 1_000_000
                message += f"- {row.campaign.name}\n"
                message += f"  Leads: {row.metrics.conversions:.0f} | CPL: ${cpl:.2f}\n\n"
            await query.message.reply_text(message or "কোনো lead নেই।")
        except GoogleAdsException as ex:
            await query.message.reply_text(f"Error: {ex.error.code().name}")

    elif query.data == "status":
        try:
            client = get_ads_client()
            ga_service = client.get_service("GoogleAdsService")
            q = """
                SELECT customer.id, customer.descriptive_name, customer.currency_code
                FROM customer LIMIT 1
            """
            response = ga_service.search(customer_id=CUSTOMER_ID, query=q)
            for row in response:
                message = (
                    f"Account Status:\n\n"
                    f"Name: {row.customer.descriptive_name}\n"
                    f"Currency: {row.customer.currency_code}\n"
                    f"ID: {row.customer.id}\n"
                    f"Status: Active"
                )
                await query.message.reply_text(message)
                return
        except GoogleAdsException as ex:
            await query.message.reply_text(f"Error: {ex.error.code().name}")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("campaigns", campaigns))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("leads", leads))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot চালু হয়েছে!")
    app.run_polling()

if __name__ == "__main__":
    main()
