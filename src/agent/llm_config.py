import os

from dotenv import load_dotenv


load_dotenv()

open_api_key = os.getenv('OPENAI_API_KEY')
open_api_base = os.getenv('OPENAI_API_BASE') or None
openai_model = os.getenv('OPENAI_MODEL', 'gpt-5.1')
openai_temperature = float(os.getenv('OPENAI_TEMPERATURE', '1'))
