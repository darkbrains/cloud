import uvicorn
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import make_wsgi_app, CollectorRegistry, multiprocess, ProcessCollector, PlatformCollector
from starlette.exceptions import HTTPException as StarletteHTTPException
import threading
import logging
from pythonjsonlogger import jsonlogger
import sys
import time
import os
import random
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import mysql.connector
from mysql.connector import Error
import bcrypt
from wsgiref.simple_server import make_server
from fastapi import HTTPException


DATABASE_HOST = os.environ['MYSQL_HOST']
DATABASE_USER = os.environ['MYSQL_USER']
DATABASE_PASSWORD = os.environ['MYSQL_PASSWORD']
DATABASE_NAME = os.environ['MYSQL_DB']
DATABASE_PORT = os.environ['MYSQL_PORT']
EMAIL_ADDRESS = os.environ['EMAIL_ADDRESS']
EMAIL_PASSWORD = os.environ['EMAIL_PASSWORD']


os.environ['PROMETHEUS_MULTIPROC_DIR'] = '/tmp/prometheus_multiproc_dir'


app = FastAPI()


templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return await exc(request)



def create_db_connection():
    try:
        return mysql.connector.connect(
            host=DATABASE_HOST,
            user=DATABASE_USER,
            passwd=DATABASE_PASSWORD,
            database=DATABASE_NAME,
            port=DATABASE_PORT
        )
    except Error as e:
        print(f"Error: '{e}'")
        return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def store_verification_code(email: str, code: str):
    current_time = int(time.time())
    connection = create_db_connection()
    if connection is not None:
        try:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO VERIFICATION_CODES (email, code, timestamp) VALUES (%s, %s, %s)",
                (email, code, current_time)
            )
            connection.commit()
        except Error as e:
            print(f"Error: '{e}'")
        finally:
            cursor.close()
            connection.close()


def get_verification_code(email: str):
    connection = create_db_connection()
    if connection is not None:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT code, timestamp FROM VERIFICATION_CODES WHERE email = %s ORDER BY timestamp DESC LIMIT 1",
                    (email,)
                )
                result = cursor.fetchone()
                if result:
                    return result
                else:
                    return None, None
        except Error as e:
            print(f"Error retrieving verification code: {e}")
        finally:
            connection.close()
    else:
        print("Failed to create database connection")
    return None, None


def scheduled_cleanup():
    while True:
        cleanup_database()
        time.sleep(300)


def cleanup_database():
    connection = create_db_connection()
    if connection is not None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM VERIFICATION_CODES WHERE timestamp < (UNIX_TIMESTAMP() - 300)")
                cursor.execute("DELETE FROM USERS WHERE is_verified = FALSE AND timestamp < (UNIX_TIMESTAMP() - 172800)")
            connection.commit()
        except Error as e:
            print(f"Database cleanup error: {e}")
        finally:
            connection.close()


def mark_user_as_verified(email: str):
    connection = create_db_connection()
    if connection is not None:
        try:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE USERS SET is_verified = TRUE WHERE email = %s",
                (email,)
            )
            connection.commit()
        except Error as e:
            print(f"Error: '{e}'")
        finally:
            cursor.close()
            connection.close()


def register_user(email: str, hashed_password: str, verification_code: str):
    connection = create_db_connection()
    if connection is not None:
        try:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO USERS (email, hashed_password, verification_code) VALUES (%s, %s, %s)",
                (email, hashed_password, verification_code)
            )
            connection.commit()
        except Error as e:
            print(f"Error: '{e}'")
        finally:
            cursor.close()
            connection.close()


def send_email(receiver_email, code):
    message = MIMEMultipart("alternative")
    message["Subject"] = "Verification Code"
    message["From"] = EMAIL_ADDRESS
    message["To"] = receiver_email
    text = f"Your verification code is: {code}. This code will expire in 5 minutes."
    part1 = MIMEText(text, "plain")
    message.attach(part1)
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, receiver_email, message.as_string())


def user_exists(email: str):
    connection = create_db_connection()
    if connection is not None:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM USERS WHERE email = %s",
                    (email,)
                )
                result = cursor.fetchone()
                return result[0] > 0
        except Error as e:
            print(f"Error: {e}'")
        finally:
            connection.close()
    return False


def is_user_verified(email: str) -> bool:
    connection = create_db_connection()
    if connection is not None:
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT is_verified FROM USERS WHERE email = %s",
                (email,)
            )
            result = cursor.fetchone()
            return result[0] if result else False
        except Error as e:
            print(f"Error: {e}'")
        finally:
            cursor.close()
            connection.close()
    return False


def generate_verification_code():
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])


@app.get("/")
async def root():
    return RedirectResponse(url="/login", status_code=301)


@app.get("/api/healthz")
async def health_check():
    connection = create_db_connection()
    if connection is not None and connection.is_connected():
        connection.close()
        return {"status": "healthy"}
    else:
        return {"status": "unhealthy"}, 503


@app.get("/login")
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/signup")
async def signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup")
async def signup(request: Request, email: str = Form(...), password: str = Form(...)):
    if user_exists(email):
        if not is_user_verified(email):
            verification_code = generate_verification_code()
            store_verification_code(email, verification_code)
            send_email(email, verification_code)
            return templates.TemplateResponse("verify.html", {"request": request, "email": email})
        else:
            return templates.TemplateResponse("already-registered.html", {"request": request, "email": email})


    hashed_password = hash_password(password)
    verification_code = generate_verification_code()
    store_verification_code(email, verification_code)
    send_email(email, verification_code)
    register_user(email, hashed_password, verification_code)
    return templates.TemplateResponse("verify.html", {"request": request, "email": email})


@app.post("/verify")
async def verify(request: Request, email: str = Form(...),
                 code1: str = Form(...), code2: str = Form(...),
                 code3: str = Form(...), code4: str = Form(...),
                 code5: str = Form(...), code6: str = Form(...)):
    full_code = code1 + code2 + code3 + code4 + code5 + code6
    stored_code, timestamp = get_verification_code(email)
    if stored_code is None:
        raise HTTPException(status_code=404, detail="Verification code not found")
    current_time = int(time.time())
    if stored_code == full_code and current_time - timestamp <= 300:
        mark_user_as_verified(email)
        return templates.TemplateResponse("verify-success.html", {"request": request})
    else:
        return templates.TemplateResponse("verify-error.html", {"request": request, "email": email, "error": "Invalid verification code or code expired"})


registry = CollectorRegistry()
ProcessCollector(registry=registry)
PlatformCollector(registry=registry)


multiprocess.MultiProcessCollector(registry)


@app.on_event("startup")
async def startup_event():
    threading.Thread(target=serve_metrics, daemon=True).start()
    threading.Thread(target=scheduled_cleanup, daemon=True).start()


def serve_metrics():
    try:
        app = make_wsgi_app(registry)
        httpd = make_server('', 9084, app)
        httpd.serve_forever()
    except Exception as e:
        logging.error(f"Failed to start Prometheus metrics server: {e}")


if __name__ == "__main__":
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
        },
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "fmt": "%(levelname)s %(name)s %(message)s",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.access": {"handlers": ["default"], "level": "INFO"},
        },
    }
    uvicorn.run("main:app", host="0.0.0.0", port=8084, log_level="info", log_config=logging_config)
