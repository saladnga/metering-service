FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS builder

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

RUN useradd --create-home appuser
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY . .

USER appuser
ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000
CMD [ "uvicorn", "metering.api:app", "--host", "0.0.0.0", "--port", "8000" ]