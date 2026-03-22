import json
import os

FILE = "data/guilds.json"

def load_config():
    if not os.path.exists(FILE):
        return {}
    with open(FILE, "r") as f:
        return json.load(f)

def save_config(data):
    with open(FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_guild(guild_id):
    data = load_config()
    return data.get(str(guild_id), {"anime": False})

def set_guild(guild_id, key, value):
    data = load_config()
    gid = str(guild_id)

    if gid not in data:
        data[gid] = {}

    data[gid][key] = value
    save_config(data)