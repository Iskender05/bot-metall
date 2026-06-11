from dotenv import load_dotenv
from os import getenv


load_dotenv()

MYSQL_HOST = getenv('MYSQL_HOST', 'mysql')
MYSQL_PORT = int(getenv('MYSQL_PORT', '3306'))
MYSQL_USER = getenv('MYSQL_USER', 'root')
MYSQL_PASSWORD = getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = getenv('MYSQL_DATABASE')
