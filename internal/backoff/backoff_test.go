package backoff

import (
	"testing"
	"time"

	"github.com/ahb-sjsu/nats-bursting/internal/config"
)

func tinyPoliteness() config.Politeness {
	return config.Politeness{
		InitialBackoff:    1 * time.Second,
		MaxBackoff:        16 * time.Second,
		BackoffMultiplier: 2.0,
		MaxAttempts:       4,
	}
}

func TestNextWaitGrowsExponentially(t *testing.T) {
	c := New(tinyPoliteness()).WithRNG(1)
	prev := time.Duration(0)
	for i := 0; i < 4; i++ {
		w := c.NextWait()
		if i > 0 && w < prev {
			t.Fatalf("attempt %d: wait shrank from %v to %v", i, prev, w)
		}
		prev = w
	}
	if c.Attempts() != 4 {
		t.Fatalf("want Attempts=4, got %d", c.Attempts())
	}
}

func TestNextWaitClampsToMax(t *testing.T) {
	c := New(tinyPoliteness()).WithRNG(2)
	// After enough attempts the base value will exceed MaxBackoff.
	var maxObserved time.Duration
	for i := 0; i < 10; i++ {
		w := c.NextWait()
		if w > maxObserved {
			maxObserved = w
		}
	}
	// 16s base * 1.25 jitter ceiling = 20s
	if maxObserved > 25*time.Second {
		t.Fatalf("max wait %v exceeded jitter ceiling for 16s cap", maxObserved)
	}
}

func TestShouldAbortAfterMaxAttempts(t *testing.T) {
	c := New(tinyPoliteness()).WithRNG(3)
	for i := 0; i < 4; i++ {
		if c.ShouldAbort() {
			t.Fatalf("aborted too early at attempt %d", i)
		}
		c.NextWait()
	}
	if !c.ShouldAbort() {
		t.Fatal("should abort after MaxAttempts waits")
	}
}

func TestTotalWaitAccumulates(t *testing.T) {
	c := New(tinyPoliteness()).WithRNG(4)
	c.NextWait()
	c.NextWait()
	if c.TotalWait() <= 0 {
		t.Fatalf("TotalWait should be positive, got %v", c.TotalWait())
	}
}
