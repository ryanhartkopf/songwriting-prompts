import json
import logging
from datetime import time
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import (
    filters,
    Application,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler
)
from classes import (
    db,
    Entry,
    Prompt,
    User
)


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Initialize conversation states
NAME, TZ, TIME = range(3)


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Here's how to use this bot:\n\n"
        "/hello - Greet the bot\n"
        "/start - Subscribe to daily songwriting prompts\n"
        "/help - Show this help message\n"
    )


async def daily_prompt(context: ContextTypes.DEFAULT_TYPE):
    # Retrieve the chat_id passed via the 'data' parameter when the job was scheduled
    chat_id = context.job.data
    user_id = context.job.user_id

    # Get a random prompt from the database
    prompt = Prompt.select().order_by(db.random()).get()

    user = User.get(User.id == user_id)


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
        await update.message.reply_text("You don't have a prompt to respond to right now. Please wait for your daily prompt.")
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
    await update.message.reply_text(f"Nice to meet you, {user_name}! What is your preferred time zone?\n\n1. US Pacific\n2. US Mountain\n3. US Central\n4. US Eastern")
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
    
    # Save the user's time zone and preferred time to the database
    if User.select().where(User.chat_id == str(update.effective_chat.id)).exists():
        user = User.get(User.chat_id == str(update.effective_chat.id))
        user.name = context.user_data['name']
        user.time_zone = context.user_data['time_zone']
        user.message_time = preferred_time
        user.save()
    else:
        user = User.create(
            id=str(update.effective_user.id),
            chat_id=str(update.effective_chat.id),
            name=context.user_data['name'],
            time_zone=context.user_data['time_zone'],
            message_time=preferred_time
        )

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


def main():
    # Initialize Telegram app
    app = Application.builder().token("8892169399:AAHPdYWv8hkiJjFdQe07wsYEtYSWOrookLc").build()

    # Initialize the database and create tables if they don't exist
    db.connect()
    #db.drop_tables([User, Prompt, Entry])
    db.create_tables([User, Prompt, Entry], safe=True)

    # Load prompts from prompts.json (list) and save them to the database if they don't already exist
    with open('prompts.json', 'r') as f:
        prompts = json.load(f)
        print(prompts)
        for prompt in prompts:
            print(prompt)
            if not Prompt.select().where(Prompt.text == prompt).exists():
                Prompt.create(text=prompt, reviewed=True)

    start_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            TZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_timezone)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

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

    app.add_handlers([
        start_handler,
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_response),
        CommandHandler("hello", hello),
        CommandHandler("help", help),
    ])

    app.run_polling()


if __name__ == "__main__":
    main()
