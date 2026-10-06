from datetime import date, datetime

from peewee import (
    BooleanField,
    DateField,
    DateTimeField,
    ForeignKeyField,
    Model,
    SqliteDatabase,
    TextField,
)

db = SqliteDatabase('db/sqlite.db')

class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    id = TextField(primary_key=True)
    chat_id = TextField(unique=True)
    name = TextField()
    email = TextField()
    message_time = TextField()
    time_zone = TextField()


class Prompt(BaseModel):
    text = TextField()
    reviewed = BooleanField(default=False)
    user = ForeignKeyField(User, backref='prompts', null=True)


class Entry(BaseModel):
    timestamp = DateTimeField(
        default=datetime.now,
        index=True)
    prompt_id = ForeignKeyField(Prompt, backref='entries')
    user = ForeignKeyField(User, backref='entries')
    response = TextField()


class DailyPrompt(BaseModel):
    date = DateField(default=date.today, index=True)
    prompt_id = ForeignKeyField(Prompt, backref='daily_prompts')
