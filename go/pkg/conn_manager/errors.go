package conn_manager

import (
	"errors"
)

var (
	// ErrConnectionRefused is returned when the target address actively rejects the connection.
	ErrConnectionRefused = errors.New("connection refused")

	// ErrMaxRetriesReached is returned when the network manager gives up after the configured number of attempts.
	ErrMaxRetriesReached = errors.New("max retries reached")

	// ErrNoConnection is returned when an operation is attempted on a nil or closed connection.
	ErrNoConnection = errors.New("no active connection")

	// ErrWriteFailed is returned when data could not be sent over the socket.
	ErrWriteFailed = errors.New("write failed")
)
