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

func main() {
	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = nats.DefaultURL
	}

	logger := setupLogger()

	var nc *nats.Conn
	var err error
	for i := 0; i < 5; i++ {
		nc, err = nats.Connect(natsURL)
		if err == nil {
			break
		}
		logger.Printf("WARN: не удалось подключиться к NATS (%s), попытка %d/5...", natsURL, i+1)
		time.Sleep(2 * time.Second)
	}
	if err != nil {
		logger.Fatalf("ERROR: не удалось подключиться к NATS: %v", err)
	}
	defer nc.Close()

	logger.Printf("INFO: подключён к NATS %s", natsURL)

	nc.Subscribe("hotel.checkin", func(m *nats.Msg) {
		var task Task
		if err := json.Unmarshal(m.Data, &task); err != nil {
			logger.Printf("ERROR: не удалось разобрать задачу: %v", err)
			return
		}

		logger.Printf("INFO: получена задача %s, тип=%s, гость=%s, номер=%d",
			task.ID, task.Type, task.GuestName, task.RoomNumber)

		result := processTask(nc, logger, task)

		atomic.AddInt64(&processedCount, 1)
		logger.Printf("INFO: задача %s выполнена, статус=%s, всего обработано=%d",
			task.ID, result.RoomStatus, atomic.LoadInt64(&processedCount))

		data, _ := json.Marshal(result)
		nc.Publish("hotel.results", data)
	})

	logger.Println("INFO: агент запущен, ожидаю задачи на hotel.checkin...")
	select {}
}

func setupLogger() *log.Logger {
	logDir := os.Getenv("LOG_DIR")
	if logDir == "" {
		logDir = "logs"
	}
	os.MkdirAll(logDir, 0755)

	logFile, err := os.OpenFile(
		fmt.Sprintf("%s/checkin-agent.log", logDir),
		os.O_CREATE|os.O_WRONLY|os.O_APPEND,
		0644,
	)
	if err != nil {
		log.Printf("WARN: не удалось открыть файл лога: %v, пишу только в консоль", err)
		return log.New(os.Stdout, "[CheckInAgent] ", log.LstdFlags)
	}

	writer := io.MultiWriter(os.Stdout, logFile)
	return log.New(writer, "[CheckInAgent] ", log.LstdFlags)
}

func processTask(nc *nats.Conn, logger *log.Logger, task Task) Result {
	switch task.Type {
	case "check_in":
		return handleCheckIn(logger, task)
	case "check_out":
		return handleCheckOut(nc, logger, task)
	default:
		logger.Printf("ERROR: неизвестный тип задачи: %s", task.Type)
		return Result{
			TaskID:  task.ID,
			Success: false,
			Output:  "неизвестный тип задачи: " + task.Type,
		}
	}
}

func handleCheckIn(logger *log.Logger, task Task) Result {
	if task.RoomNumber < 101 || (task.RoomNumber > 110 && task.RoomNumber < 201) || task.RoomNumber > 205 {
		msg := "номер не существует"
		logger.Printf("ERROR: задача %s — %s: %d", task.ID, msg, task.RoomNumber)
		return Result{TaskID: task.ID, Success: false, Output: msg}
	}

	if guest, busy := occupiedRooms[task.RoomNumber]; busy {
		msg := "номер " + itoa(task.RoomNumber) + " уже занят гостем " + guest
		logger.Printf("ERROR: задача %s — %s", task.ID, msg)
		return Result{TaskID: task.ID, Success: false, Output: msg}
	}

	if task.Nights < 1 {
		msg := "минимальный срок проживания — 1 ночь"
		logger.Printf("ERROR: задача %s — %s", task.ID, msg)
		return Result{TaskID: task.ID, Success: false, Output: msg}
	}

	occupiedRooms[task.RoomNumber] = task.GuestName
	msg := "гость " + task.GuestName + " заселён в номер " + itoa(task.RoomNumber) +
		" на " + itoa(task.Nights) + " ночей (с " + task.CheckInDate + ")"

	return Result{
		TaskID:     task.ID,
		Success:    true,
		Output:     msg,
		RoomStatus: "occupied",
		RoomNumber: task.RoomNumber,
	}
}

func handleCheckOut(nc *nats.Conn, logger *log.Logger, task Task) Result {
	if _, busy := occupiedRooms[task.RoomNumber]; !busy {
		msg := "номер " + itoa(task.RoomNumber) + " не занят"
		logger.Printf("ERROR: задача %s — %s", task.ID, msg)
		return Result{TaskID: task.ID, Success: false, Output: msg}
	}

	delete(occupiedRooms, task.RoomNumber)

	cleaningTask := CleaningTask{
		TaskID:     task.ID + "-clean",
		Type:       "clean_room",
		RoomNumber: task.RoomNumber,
		Priority:   "normal",
	}
	data, _ := json.Marshal(cleaningTask)
	nc.Publish("hotel.cleaning", data)
	logger.Printf("INFO: задача %s — отправлена задача уборки для номера %d", task.ID, task.RoomNumber)

	msg := "гость " + task.GuestName + " выселен из номера " + itoa(task.RoomNumber) + ", уборка запланирована"
	return Result{
		TaskID:     task.ID,
		Success:    true,
		Output:     msg,
		RoomStatus: "needs_cleaning",
		RoomNumber: task.RoomNumber,
	}
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
