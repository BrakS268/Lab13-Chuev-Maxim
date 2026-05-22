package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"sync/atomic"
	"time"

	"github.com/nats-io/nats.go"
)

type Task struct {
	ID          string `json:"task_id"`
	Type        string `json:"type"`
	GuestName   string `json:"guest_name"`
	RoomNumber  int    `json:"room_number"`
	Nights      int    `json:"nights"`
	CheckInDate string `json:"check_in_date"`
}

type Result struct {
	TaskID     string `json:"task_id"`
	Success    bool   `json:"success"`
	Output     string `json:"output"`
	RoomStatus string `json:"room_status"`
	RoomNumber int    `json:"room_number"`
}

type CleaningTask struct {
	TaskID     string `json:"task_id"`
	Type       string `json:"type"`
	RoomNumber int    `json:"room_number"`
	Priority   string `json:"priority"`
}

var occupiedRooms = map[int]string{}
var processedCount int64

func logf(logger *log.Logger, format string, args ...interface{}) {
	if logger != nil {
		logger.Printf(format, args...)
	}
}

func main() {
	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = nats.DefaultURL
	}

	agentID := os.Getenv("AGENT_ID")
	if agentID == "" {
		agentID = "default"
	}

	logger := setupLogger(agentID)

	var nc *nats.Conn
	var err error
	for i := 0; i < 5; i++ {
		nc, err = nats.Connect(natsURL)
		if err == nil {
			break
		}
		logf(logger, "WARN: не удалось подключиться к NATS (%s), попытка %d/5...", natsURL, i+1)
		time.Sleep(2 * time.Second)
	}
	if err != nil {
		logger.Fatalf("ERROR: не удалось подключиться к NATS: %v", err)
	}
	defer nc.Close()

	logf(logger, "INFO: агент [%s] подключён к NATS %s", agentID, natsURL)

	nc.QueueSubscribe("hotel.checkin", "checkin-workers", func(m *nats.Msg) {
		var task Task
		if err := json.Unmarshal(m.Data, &task); err != nil {
			logf(logger, "ERROR: не удалось разобрать задачу: %v", err)
			return
		}

		logf(logger, "INFO: [%s] получена задача %s, тип=%s, гость=%s, номер=%d",
			agentID, task.ID, task.Type, task.GuestName, task.RoomNumber)

		result := processTask(nc, logger, agentID, task)

		count := atomic.AddInt64(&processedCount, 1)
		logf(logger, "INFO: [%s] задача %s выполнена, статус=%s, всего обработано=%d",
			agentID, task.ID, result.RoomStatus, count)

		data, _ := json.Marshal(result)
		nc.Publish("hotel.results", data)
	})

	logf(logger, "INFO: агент [%s] запущен, ожидаю задачи на hotel.checkin (queue=checkin-workers)...", agentID)
	select {}
}

func setupLogger(agentID string) *log.Logger {
	logDir := os.Getenv("LOG_DIR")
	if logDir == "" {
		logDir = "logs"
	}
	os.MkdirAll(logDir, 0755)

	logFile, err := os.OpenFile(
		fmt.Sprintf("%s/checkin-agent-%s.log", logDir, agentID),
		os.O_CREATE|os.O_WRONLY|os.O_APPEND,
		0644,
	)
	if err != nil {
		return log.New(os.Stdout, fmt.Sprintf("[CheckInAgent-%s] ", agentID), log.LstdFlags)
	}

	writer := io.MultiWriter(os.Stdout, logFile)
	return log.New(writer, fmt.Sprintf("[CheckInAgent-%s] ", agentID), log.LstdFlags)
}

func processTask(nc *nats.Conn, logger *log.Logger, agentID string, task Task) Result {
	switch task.Type {
	case "check_in":
		return handleCheckIn(logger, agentID, task)
	case "check_out":
		return handleCheckOut(nc, logger, agentID, task)
	default:
		logf(logger, "ERROR: [%s] неизвестный тип задачи: %s", agentID, task.Type)
		return Result{TaskID: task.ID, Success: false, Output: "неизвестный тип задачи: " + task.Type}
	}
}

func handleCheckIn(logger *log.Logger, agentID string, task Task) Result {
	if task.RoomNumber < 101 || (task.RoomNumber > 110 && task.RoomNumber < 201) || task.RoomNumber > 205 {
		msg := "номер не существует"
		logf(logger, "ERROR: [%s] задача %s — %s: %d", agentID, task.ID, msg, task.RoomNumber)
		return Result{TaskID: task.ID, Success: false, Output: msg}
	}

	if guest, busy := occupiedRooms[task.RoomNumber]; busy {
		msg := "номер " + itoa(task.RoomNumber) + " уже занят гостем " + guest
		logf(logger, "ERROR: [%s] задача %s — %s", agentID, task.ID, msg)
		return Result{TaskID: task.ID, Success: false, Output: msg}
	}

	if task.Nights < 1 {
		msg := "минимальный срок проживания — 1 ночь"
		logf(logger, "ERROR: [%s] задача %s — %s", agentID, task.ID, msg)
		return Result{TaskID: task.ID, Success: false, Output: msg}
	}

	occupiedRooms[task.RoomNumber] = task.GuestName
	msg := "гость " + task.GuestName + " заселён в номер " + itoa(task.RoomNumber) +
		" на " + itoa(task.Nights) + " ночей (с " + task.CheckInDate + ")"

	return Result{TaskID: task.ID, Success: true, Output: msg, RoomStatus: "occupied", RoomNumber: task.RoomNumber}
}

func handleCheckOut(nc *nats.Conn, logger *log.Logger, agentID string, task Task) Result {
	if _, busy := occupiedRooms[task.RoomNumber]; !busy {
		msg := "номер " + itoa(task.RoomNumber) + " не занят"
		logf(logger, "ERROR: [%s] задача %s — %s", agentID, task.ID, msg)
		return Result{TaskID: task.ID, Success: false, Output: msg}
	}

	delete(occupiedRooms, task.RoomNumber)

	if nc != nil {
		cleaningTask := CleaningTask{TaskID: task.ID + "-clean", Type: "clean_room", RoomNumber: task.RoomNumber, Priority: "normal"}
		data, _ := json.Marshal(cleaningTask)
		nc.Publish("hotel.cleaning", data)
		logf(logger, "INFO: [%s] задача %s — отправлена задача уборки для номера %d", agentID, task.ID, task.RoomNumber)
	}

	msg := "гость " + task.GuestName + " выселен из номера " + itoa(task.RoomNumber) + ", уборка запланирована"
	return Result{TaskID: task.ID, Success: true, Output: msg, RoomStatus: "needs_cleaning", RoomNumber: task.RoomNumber}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := false
	if n < 0 {
		neg = true
		n = -n
	}
	buf := [20]byte{}
	pos := len(buf)
	for n > 0 {
		pos--
		buf[pos] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		pos--
		buf[pos] = '-'
	}
	return string(buf[pos:])
}
