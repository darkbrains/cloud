FROM python:3.9-slim

WORKDIR /app

COPY /app/ .

RUN pip install -r requirements.txt

RUN mkdir /tmp/prometheus_multiproc_dir

CMD ["python3", "main.py"]

EXPOSE 8084
