package ring

import "testing"

func TestRetainsLastN(t *testing.T) {
	r := New(3)
	for i := 0; i < 5; i++ {
		r.Publish([]byte{byte(i)})
	}
	got := r.Recent()
	if len(got) != 3 {
		t.Fatalf("want 3 retained, got %d", len(got))
	}
	// should be messages 2,3,4
	if got[0][0] != 2 || got[2][0] != 4 {
		t.Fatalf("unexpected retained contents: %v", got)
	}
}

func TestSubscriberReceives(t *testing.T) {
	r := New(10)
	_, ch := r.Subscribe(4)
	r.Publish([]byte("hello"))
	select {
	case m := <-ch:
		if string(m) != "hello" {
			t.Fatalf("got %q", m)
		}
	default:
		t.Fatal("subscriber did not receive message")
	}
}

func TestBackpressureDropsNotBlocks(t *testing.T) {
	r := New(10)
	// buffer of 1; publish 5 without draining -> 4 dropped, no deadlock
	r.Subscribe(1)
	for i := 0; i < 5; i++ {
		r.Publish([]byte{byte(i)})
	}
	if d := r.Dropped(); d != 4 {
		t.Fatalf("want 4 dropped, got %d", d)
	}
}

func TestUnsubscribeCloses(t *testing.T) {
	r := New(4)
	id, ch := r.Subscribe(1)
	r.Unsubscribe(id)
	if _, ok := <-ch; ok {
		t.Fatal("channel should be closed after unsubscribe")
	}
}
