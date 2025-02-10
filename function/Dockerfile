FROM python:3.13-alpine AS base

WORKDIR /app

FROM base AS packages

COPY requirements.txt .
RUN pip install -r requirements.txt --target ./package

FROM scratch
COPY src .
COPY --from=packages /app/package/ .