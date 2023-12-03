import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import make_wsgi_app, CollectorRegistry, multiprocess, ProcessCollector, PlatformCollector
from fastapi import HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
import threading
from wsgiref.simple_server import make_server
import logging
from pythonjsonlogger import jsonlogger
import sys
import traceback
import time
import os


os.environ['PROMETHEUS_MULTIPROC_DIR'] = '/tmp/prometheus_multiproc_dir'


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        now = time.time()
        log_record['timestamp'] = int(now)
        log_record.pop('color_message', None)


logger = logging.getLogger('uvicorn')
logHandler = logging.StreamHandler()
formatter = CustomJsonFormatter('%(timestamp)s %(levelname)s %(name)s %(message)s')
logHandler.setFormatter(formatter)
logger.handlers.clear()
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)


prometheus_logger = logging.getLogger("prometheus")
prometheus_handler = logging.StreamHandler()
prometheus_handler.setFormatter(CustomJsonFormatter())
prometheus_logger.addHandler(prometheus_handler)
prometheus_logger.setLevel(logging.INFO)


exception_logger = logging.getLogger("exceptions")
exception_handler = logging.StreamHandler(sys.stderr)
exception_handler.setFormatter(CustomJsonFormatter())
exception_logger.addHandler(exception_handler)
exception_logger.setLevel(logging.ERROR)


app = FastAPI()


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return await exc(request)


app.mount("/static", StaticFiles(directory="static"), name="static")


templates = Jinja2Templates(directory="templates")


registry = CollectorRegistry()
multiprocess.MultiProcessCollector(registry)
ProcessCollector(registry=registry)
PlatformCollector(registry=registry)


async def app_lifespan():
    threading.Thread(target=serve_metrics, daemon=True).start()
    yield


app.router.add_event_handler("startup", app_lifespan)


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/healthz")
async def root(request: Request):
    return templates.TemplateResponse("healthz.html", {"request": request})


@app.get("/login")
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/signup")
async def signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


def serve_metrics():
    try:
        app = make_wsgi_app(registry)
        httpd = make_server('', 9084, app)
        httpd.serve_forever()
    except Exception as e:
        logging.error(f"Failed to start Prometheus metrics server: {e}")


@app.on_event("startup")
async def startup_event():
    threading.Thread(target=serve_metrics, daemon=True).start()


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


    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8084,
        log_level="info",
        log_config=logging_config
    )
