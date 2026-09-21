FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite DB is stored here — attach a Railway Volume to /app/data
# so your settings/users/orders/wallets survive redeploys.
RUN mkdir -p /app/data

CMD ["python", "main.py"]
