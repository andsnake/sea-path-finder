# ---- Base image -------------------------------------------------------------
FROM python:3.12-slim

# ---- Runtime configuration --------------------------------------------------
ENV PYTHONUNBUFFERED=1        \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ---- Working dir ------------------------------------------------------------
WORKDIR /app

# ---- Dependencies -----------------------------------------------------------
# Copy only requirements first to leverage Docker’s layer cache
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- Application code -------------------------------------------------------
COPY sea_route_service.py .

EXPOSE 8000
CMD ["uvicorn", "sea_route_service:app", "--host", "0.0.0.0", "--port", "8000"]
