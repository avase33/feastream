// Package ring is an in-memory publish/subscribe ring — the offline stand-in
// for the Redis Pub/Sub buffer in the architecture diagram.
//
// Publish is non-blocking: if a subscriber's channel is full the message is
// dropped for that subscriber and counted. That dropped counter IS the
// backpressure signal the gateway exposes to operators — a slow consumer never
// stalls ingestion.
package ring

import "sync"

// Ring is a bounded pub/sub buffer. It keeps the last `size` messages for late
// subscribers and fans out live messages to every subscriber.
type Ring struct {
	mu      sync.Mutex
	buf     [][]byte
	size    int
	subs    map[int]chan []byte
	nextID  int
	dropped int64
}

// New creates a ring that retains the last `size` messages.
func New(size int) *Ring {
	if size < 1 {
		size = 1
	}
	return &Ring{
		buf:  make([][]byte, 0, size),
		size: size,
		subs: make(map[int]chan []byte),
	}
}

// Publish stores the message and fans it out. Never blocks.
func (r *Ring) Publish(msg []byte) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if len(r.buf) >= r.size {
		// drop the oldest retained message
		r.buf = r.buf[1:]
	}
	r.buf = append(r.buf, msg)

	for _, ch := range r.subs {
		select {
		case ch <- msg:
		default:
			r.dropped++
		}
	}
}

// Subscribe returns a subscriber id and a channel of future messages.
func (r *Ring) Subscribe(buffer int) (int, <-chan []byte) {
	r.mu.Lock()
	defer r.mu.Unlock()
	id := r.nextID
	r.nextID++
	ch := make(chan []byte, buffer)
	r.subs[id] = ch
	return id, ch
}

// Unsubscribe removes a subscriber and closes its channel.
func (r *Ring) Unsubscribe(id int) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if ch, ok := r.subs[id]; ok {
		delete(r.subs, id)
		close(ch)
	}
}

// Recent returns a copy of the retained messages, oldest first.
func (r *Ring) Recent() [][]byte {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([][]byte, len(r.buf))
	copy(out, r.buf)
	return out
}

// Dropped reports how many fan-out sends were dropped due to full subscribers.
func (r *Ring) Dropped() int64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.dropped
}
