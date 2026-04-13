// Package backoff implements exponential-with-jitter wait scheduling
// for the atlas-burst controller. Mirrors the polite-submit Python
// BackoffController: each call to NextWait() returns an increasing
// duration up to MaxBackoff, with +/-25% jitter to avoid thundering
// herds when many controllers all wake at once.
package backoff

import (
	"math"
	"math/rand"
	"time"

	"github.com/ahb-sjsu/atlas-burst/internal/config"
)

// Controller tracks attempt count and total wait, applies thresholds,
// and produces wait durations.
type Controller struct {
	cfg config.Politeness

	attempts  int
	totalWait time.Duration
	rng       *rand.Rand
}

// New constructs a Controller from the given politeness config.
// The RNG is deterministically seeded by time.Now().UnixNano() so
// production users get jitter; tests can swap it via WithRNG.
func New(p config.Politeness) *Controller {
	return &Controller{
		cfg: p,
		rng: rand.New(rand.NewSource(time.Now().UnixNano())),
	}
}

// WithRNG returns a copy of c with a fixed-seed RNG, for tests.
func (c *Controller) WithRNG(seed int64) *Controller {
	clone := *c
	clone.rng = rand.New(rand.NewSource(seed))
	return &clone
}

// Attempts returns the number of waits already produced.
func (c *Controller) Attempts() int { return c.attempts }

// TotalWait returns the cumulative wait so far.
func (c *Controller) TotalWait() time.Duration { return c.totalWait }

// ShouldAbort returns true if we've exceeded MaxAttempts.
func (c *Controller) ShouldAbort() bool {
	return c.attempts >= c.cfg.MaxAttempts
}

// NextWait computes the next wait duration without sleeping.
// Increments the attempt counter as a side effect — call it once per
// backoff cycle.
func (c *Controller) NextWait() time.Duration {
	base := float64(c.cfg.InitialBackoff) * math.Pow(c.cfg.BackoffMultiplier, float64(c.attempts))
	if base > float64(c.cfg.MaxBackoff) {
		base = float64(c.cfg.MaxBackoff)
	}
	// +/-25% jitter
	jitter := 1.0 + (c.rng.Float64()-0.5)*0.5
	dur := time.Duration(base * jitter)
	c.attempts++
	c.totalWait += dur
	return dur
}
