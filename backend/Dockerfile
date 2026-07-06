FROM golang:1.25-alpine AS builder

RUN apk add --no-cache git ca-certificates

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /citevision-v2-api ./cmd/api

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

COPY --from=builder /citevision-v2-api .
COPY migrations ./migrations

ENV APP_ENV=production
ENV API_PORT=8081
EXPOSE 8081

USER nobody

ENTRYPOINT ["./citevision-v2-api"]
