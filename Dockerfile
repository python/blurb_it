FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY blurb_it blurb_it
COPY templates templates
COPY static static

CMD ["python", "-m", "blurb_it"]
