FROM python:3.13-alpine AS base

WORKDIR /app

FROM base AS packages

COPY requirements.txt .

RUN pip install \
--platform manylinux2014_x86_64 \
--target ./package \
--implementation cp \
--python-version 3.13 \
--only-binary=:all: \
-r requirements.txt

FROM scratch
COPY src .
COPY --from=packages /app/package/ .