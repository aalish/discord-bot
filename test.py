from dotenv import load_dotenv
import os
import json
load_dotenv()
TOKEN = json.loads(os.getenv("SERVERS"))

print(type(TOKEN))
print(TOKEN[0])
print(type(TOKEN[0]))