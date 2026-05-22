package main

import (
	"testing"
)

func resetRooms() {
	occupiedRooms = map[int]string{}
}

func TestHandleCheckIn_Success(t *testing.T) {
	resetRooms()
	task := Task{ID: "t1", Type: "check_in", GuestName: "Иван Иванов", RoomNumber: 101, Nights: 3, CheckInDate: "2025-05-21"}
	result := handleCheckIn(nil, "", task)

	if !result.Success {
		t.Fatalf("ожидали успех, получили: %s", result.Output)
	}
	if result.RoomStatus != "occupied" {
		t.Errorf("ожидали статус occupied, получили: %s", result.RoomStatus)
	}
}

func TestHandleCheckIn_RoomAlreadyOccupied(t *testing.T) {
	resetRooms()
	occupiedRooms[101] = "Мария Петрова"
	task := Task{ID: "t2", Type: "check_in", GuestName: "Иван Иванов", RoomNumber: 101, Nights: 2}
	result := handleCheckIn(nil, "", task)

	if result.Success {
		t.Fatal("ожидали ошибку: номер занят")
	}
}

func TestHandleCheckIn_InvalidRoom(t *testing.T) {
	resetRooms()
	task := Task{ID: "t3", Type: "check_in", GuestName: "Иван Иванов", RoomNumber: 999, Nights: 1}
	result := handleCheckIn(nil, "", task)

	if result.Success {
		t.Fatal("ожидали ошибку: номер не существует")
	}
}

func TestHandleCheckIn_ZeroNights(t *testing.T) {
	resetRooms()
	task := Task{ID: "t4", Type: "check_in", GuestName: "Иван Иванов", RoomNumber: 102, Nights: 0}
	result := handleCheckIn(nil, "", task)

	if result.Success {
		t.Fatal("ожидали ошибку: nights < 1")
	}
}

func TestHandleCheckOut_Success(t *testing.T) {
	resetRooms()
	occupiedRooms[101] = "Иван Иванов"
	task := Task{ID: "t5", Type: "check_out", GuestName: "Иван Иванов", RoomNumber: 101}
	result := handleCheckOut(nil, nil, "", task)

	if !result.Success {
		t.Fatalf("ожидали успех, получили: %s", result.Output)
	}
	if result.RoomStatus != "needs_cleaning" {
		t.Errorf("ожидали статус needs_cleaning, получили: %s", result.RoomStatus)
	}
	if _, still := occupiedRooms[101]; still {
		t.Error("номер должен быть освобождён после выселения")
	}
}

func TestHandleCheckOut_RoomNotOccupied(t *testing.T) {
	resetRooms()
	task := Task{ID: "t6", Type: "check_out", GuestName: "Иван Иванов", RoomNumber: 101}
	result := handleCheckOut(nil, nil, "", task)

	if result.Success {
		t.Fatal("ожидали ошибку: номер не занят")
	}
}

func TestItoa(t *testing.T) {
	cases := []struct {
		input    int
		expected string
	}{
		{0, "0"},
		{1, "1"},
		{101, "101"},
		{-5, "-5"},
	}
	for _, c := range cases {
		got := itoa(c.input)
		if got != c.expected {
			t.Errorf("itoa(%d) = %s, ожидали %s", c.input, got, c.expected)
		}
	}
}
