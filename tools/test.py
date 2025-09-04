from dotenv import load_dotenv
import os

load_dotenv()
print("ID:", repr(os.environ.get("ZAEDA_ID")))
print("PW:", repr(os.environ.get("ZAEDA_PW")))
