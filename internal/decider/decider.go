// Package decider contains the scheduler-agnostic
// submit/backoff/abort decision logic, ported from polite-submit's
// Python decider.
package decider

import (
	"fmt"

	"github.com/ahb-sjsu/atlas-burst/internal/config"
)

// Decision is the outcome of evaluating cluster state against
// politeness thresholds.
type Decision int

const (
	// Submit means it is polite to submit now.
	Submit Decision = iota
	// Backoff means we should wait and retry.
	Backoff
	// Abort means the situation is hopeless (e.g. exhausted attempts;
	// the controller layer applies that constraint, not the decider).
	Abort
)

func (d Decision) String() string {
	switch d {
	case Submit:
		return "submit"
	case Backoff:
		return "backoff"
	case Abort:
		return "abort"
	default:
		return "unknown"
	}
}

// ClusterState is the snapshot the prober produces and the decider
// reads. Fields map onto the same concepts the polite-submit Python
// version uses, so both tools can share threshold semantics.
type ClusterState struct {
	Namespace      string
	TotalNodes     int
	AllocatedNodes int
	IdleNodes      int
	MyRunning      int
	MyPending      int
	OthersPending  int
}

// Utilization returns allocated / total nodes, in [0, 1]. Defaults to
// 1.0 (worst case) when total is unknown so the decider errs on the
// side of politeness.
func (s ClusterState) Utilization() float64 {
	if s.TotalNodes == 0 {
		return 1.0
	}
	return float64(s.AllocatedNodes) / float64(s.TotalNodes)
}

// Decide evaluates the state against the configured thresholds.
// Priority order, matching polite-submit:
//
//  1. Self-limiting (don't exceed your own running/pending caps)
//  2. Courtesy (yield when many other users are pending)
//  3. Utilization (back off when cluster is heavily loaded)
//
// Returns the decision and a human-readable reason.
func Decide(s ClusterState, p config.Politeness) (Decision, string) {
	if s.MyRunning >= p.MaxConcurrentJobs {
		return Backoff, fmt.Sprintf(
			"already running %d/%d jobs",
			s.MyRunning, p.MaxConcurrentJobs)
	}
	if s.MyPending >= p.MaxPendingJobs {
		return Backoff, fmt.Sprintf(
			"already %d/%d jobs pending",
			s.MyPending, p.MaxPendingJobs)
	}
	if s.OthersPending > p.QueueDepthThreshold {
		return Backoff, fmt.Sprintf(
			"%d others waiting (threshold %d)",
			s.OthersPending, p.QueueDepthThreshold)
	}
	if util := s.Utilization(); util > p.UtilizationThreshold {
		return Backoff, fmt.Sprintf(
			"cluster %.0f%% utilized (threshold %.0f%%)",
			util*100, p.UtilizationThreshold*100)
	}
	return Submit, "clear to submit"
}
