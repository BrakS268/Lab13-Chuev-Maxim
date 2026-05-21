FROM golang:1.26-alpine AS builder
 
WORKDIR /app
 
COPY go.mod ./
COPY main.go ./
RUN go mod tidy && go build -o checkin-agent .
 
FROM alpine:3.19
 
WORKDIR /app
COPY --from=builder /app/checkin-agent .
 
CMD ["./checkin-agent"]
 