import json
import logging
import os
import smtplib
from datetime import date, time
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from peewee import IntegrityError
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from classes import DailyPrompt, Entry, Prompt, User, db

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize /start conversation states
NAME, EMAIL, TZ, TIME = range(4)


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Here's how to use this bot:\n\n"
        "/start - Subscribe to daily songwriting prompts\n"
        "/list - List your last 5 responses\n"
        "/email - Email your responses to yourself\n"
        "/help - Show this help message\n"
    )


async def list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Get the last 5 user responses from the database
    user_id = update.effective_user.id
    entries = Entry.select().where(Entry.user == user_id).order_by(Entry.id.desc()).limit(5)
    responses = []
    for entry in entries:
        prompt = Prompt.get_by_id(entry.prompt_id)
        responses.append(f"Prompt: {prompt.text}\nResponse: {entry.response}\n")
    await update.message.reply_text(
        "Here are your last 5 responses:\n\n" + "\n".join(responses) if responses else "You have no responses yet."
    )


async def daily_prompt(context: ContextTypes.DEFAULT_TYPE):
    # Retrieve the chat_id passed via the 'data' parameter when the job was scheduled
    chat_id = context.job.data
    user_id = context.job.user_id

    # Check for DailyPrompt with matching DailyPrompt.date and get the corresponding prompt_id
    prompt_id = DailyPrompt.select().where(DailyPrompt.date == date.today()).first()
    prompt = Prompt.get_by_id(prompt_id.prompt_id) if prompt_id else None

    # If no DailyPrompt, get a random prompt from the database that the user has not responded to yet
    if not prompt:
        user_responses = Entry.select(Entry.prompt_id).where(Entry.user == user_id)
        prompt = Prompt.select().where(Prompt.id.not_in(user_responses)).order_by(db.random()).first()
        DailyPrompt.create(date=date.today(), prompt_id=prompt.id) if prompt else None

    # If all prompts have been responded to, just pick a random prompt
    if not prompt:
        prompt = Prompt.select().order_by(db.random()).first()
        DailyPrompt.create(date=date.today(), prompt_id=prompt.id) if prompt else None

    # If still no prompt, just give up
    if not prompt:
        logger.warning(f"No prompts available for user {user_id}.")
        await context.bot.send_message(
            chat_id=chat_id,
            text="No prompts are available at the moment. Please try again later."
        )
        return

    # Mark this user as "awaiting a response" — no ConversationHandler needed
    context.application.bot_data.setdefault('awaiting_response', {})[user_id] = prompt.id

    await context.bot.send_message(
        chat_id=chat_id, 
        text=f"Here's your daily songwriting prompt:\n\n{prompt.text}"
    )


async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    awaiting = context.application.bot_data.get('awaiting_response', {})

    if user_id not in awaiting:
        await update.message.reply_text("You don't have a prompt to respond to right now. Please wait for your daily prompt or use /help for more options.")
        return

    prompt_id = awaiting.pop(user_id)
    user_response = update.message.text

    # Save the user's response to the database
    Entry.create(
        user=User.get(User.chat_id == str(update.effective_chat.id)).id,
        prompt_id=prompt_id,
        response=user_response
    )

    await update.message.reply_text("Thank you for your response! Your entry has been saved.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! What is your name?")
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.text
    context.user_data['name'] = user_name
    await update.message.reply_text(f"Nice to meet you, {user_name}! What is your email address?")
    return EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text
    await update.message.reply_text("What is your preferred time zone?\n\n1. US Pacific\n2. US Mountain\n3. US Central\n4. US Eastern")
    return TZ


async def get_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_zone_choice = update.message.text
    time_zones = {
        "1": "America/Los_Angeles",
        "2": "America/Denver",
        "3": "America/Chicago",
        "4": "America/New_York"
    }
    
    if time_zone_choice in time_zones:
        selected_time_zone = time_zones[time_zone_choice]
        context.user_data['time_zone'] = selected_time_zone
        await update.message.reply_text(f"Great! You've selected {selected_time_zone}. Please enter the time you would like to receive your daily prompt in HH:MM format (24-hour clock).")
        return TIME
    else:
        await update.message.reply_text("Invalid choice. Please select a valid time zone (1-4).")
        return TZ


async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    preferred_time = update.message.text
    context.user_data['preferred_time'] = preferred_time
    try:
        hour, minute = map(int, preferred_time.split(':'))
    except ValueError:
        await update.message.reply_text("Invalid time format. Please enter the time in HH:MM format (24-hour clock).")
        return TIME
    if not (0 <= hour < 24 and 0 <= minute < 60):
        await update.message.reply_text("Invalid time format. Please enter the time in HH:MM format (24-hour clock).")
        return TIME
    
    # Save the user's time zone and preferred time to the database
    if User.select().where(User.chat_id == str(update.effective_chat.id)).exists():
        user = User.get(User.chat_id == str(update.effective_chat.id))
        user.name = context.user_data['name']
        user.time_zone = context.user_data['time_zone']
        user.message_time = preferred_time
        user.save()
    else:
        try:
            user = User.create(
                id=str(update.effective_user.id),
                chat_id=str(update.effective_chat.id),
                name=context.user_data['name'],
                email=context.user_data['email'],
                time_zone=context.user_data['time_zone'],
                message_time=preferred_time
            )
        except IntegrityError as e:
            logger.error(f"Database constraint violated: {e}")
            await update.message.reply_text("There was an error saving your information. Please try again.")
            return ConversationHandler.END

    hour, minute = map(int, preferred_time.split(':'))
    # If a job already exists for this user, remove it before scheduling a new one
    existing_job = context.application.job_queue.get_jobs_by_name(f"daily_job_{update.effective_chat.id}")
    if existing_job:
        existing_job[0].schedule_removal()
    context.application.job_queue.run_daily(
        callback=daily_prompt,
        time=time(hour=hour, minute=minute, second=0, tzinfo=ZoneInfo(context.user_data['time_zone'])),
        days=(0, 1, 2, 3, 4, 5, 6),  # 0=Monday, 6=Sunday. Runs every day.
        user_id=update.effective_user.id,  # Pass the user ID to the job context
        chat_id=update.effective_chat.id,  # Pass the chat ID to the job context
        data=update.effective_chat.id,  # Custom data passed into the job context
        name=f"daily_job_{update.effective_chat.id}"  # Giving the job a name makes it manageable later
    )
    
    await update.message.reply_text(f"Thank you! You will receive your daily songwriting prompt at {preferred_time} in your selected time zone.")
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Subscription process canceled. You can start again anytime by sending /start.")
    return ConversationHandler.END


async def email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Get user from the database
    try:
        user = User.get(User.chat_id == str(update.effective_chat.id))
    except User.DoesNotExist:
        await update.message.reply_text("You are not registered. Please use /start to register first.")
        return

    # Gather all responses for the user
    responses = []
    entries = Entry.select().where(Entry.user == user_id).order_by(Entry.id.desc())
    for entry in entries:
        prompt = Prompt.get_by_id(entry.prompt_id)
        responses.append(f"Prompt: {prompt.text}\nResponse: {entry.response}\n")

    # Create email content
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_USERNAME")
    msg["To"] = user.email
    msg["Subject"] = "Your Songwriting Responses"
    msg.set_content("\n".join(responses) if responses else "You have no responses yet.")

    try:
        with smtplib.SMTP(os.getenv("SMTP_SERVER"), int(os.getenv("SMTP_PORT"))) as smtp:
            smtp.starttls()  # Upgrade the connection to secure encrypted TLS
            smtp.login(os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD"))  # Use the app password from environment variable
            smtp.send_message(msg)
            logger.info(f"Email sent to {user.email}")
            await update.message.reply_text("Your responses have been emailed successfully!")
    except smtplib.SMTPSenderRefused as e:
        logger.error(f"SMTP server refused: {e}")
        await update.message.reply_text("Failed to send email. Please try again later.")
        return
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication error: {e}")
        await update.message.reply_text("Failed to send email. Please try again later.")
        return


def main():
    # Initialize Telegram app
    token = os.getenv("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()

    # Initialize the database and create tables if they don't exist
    db.connect()
    db.create_tables([User, Prompt, Entry, DailyPrompt], safe=True)

    # Load prompts from prompts.json (list) and save them to the database if they don't already exist
    with open('prompts.json', 'r') as f:
        prompts = json.load(f)
        for prompt in prompts:
            if not Prompt.select().where(Prompt.text == prompt).exists():
                Prompt.create(text=prompt, reviewed=True)

    # Conversation handler for the /start command
    start_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            TZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_timezone)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Schedule daily prompts for all users in the database
    users = User.select()
    for user in users:
        hour, minute = map(int, user.message_time.split(':'))
        app.job_queue.run_daily(
            callback=daily_prompt,
            time=time(hour=hour, minute=minute, second=0, tzinfo=ZoneInfo(user.time_zone)),
            days=(0, 1, 2, 3, 4, 5, 6),  # 0=Monday, 6=Sunday. Runs every day.
            user_id=int(user.id),  # Pass the user ID to the job context
            chat_id=int(user.chat_id),  # Pass the chat ID to the job context
            data=user.chat_id,          # Custom data passed into the job context
            name=f"daily_job_{user.chat_id}"  # Giving the job a name makes it manageable later
        )

    # Add conversation, message, and command handlers to the application
    app.add_handlers([
        start_handler,
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_response),
        CommandHandler("list", list),
        CommandHandler("email", email),
        CommandHandler("help", help),
        MessageHandler(filters.COMMAND, help),
    ])

    # Start the bot
    app.run_polling()


if __name__ == "__main__":
    main()
