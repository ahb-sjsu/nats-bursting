# syntax=docker/dockerfile:1.7
# Build stage
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/nats-bursting ./cmd/nats-bursting

# Runtime stage — distroless static, no shell, ~3 MB
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/nats-bursting /nats-bursting
USER nonroot:nonroot
ENTRYPOINT ["/nats-bursting"]
