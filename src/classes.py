from datetime import datetime
from peewee import *

db = SqliteDatabase('songwriting_prompts.db')

class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    id = TextField(primary_key=True)
    chat_id = TextField(unique=True)
    name = TextField()
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


class UserState(BaseModel):
    user = ForeignKeyField(User, backref='state', unique=True)
    pending_prompt_id = ForeignKeyField(Prompt, backref='pending_state', null=True)
