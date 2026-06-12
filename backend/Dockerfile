FROM golang:1.22-alpine AS builder

RUN apk add --no-cache git ca-certificates

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /citevision-api ./cmd/api

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

COPY --from=builder /citevision-api .
COPY migrations ./migrations

ENV APP_ENV=production
EXPOSE 8080

USER nobody

ENTRYPOINT ["./citevision-api"]
