package decider

import (
	"testing"
	"time"

	"github.com/ahb-sjsu/atlas-burst/internal/config"
)

func defaultPoliteness() config.Politeness {
	return config.Politeness{
		MaxConcurrentJobs:    50,
		MaxPendingJobs:       20,
		QueueDepthThreshold:  200,
		UtilizationThreshold: 0.90,
		InitialBackoff:       30 * time.Second,
		MaxBackoff:           30 * time.Minute,
		BackoffMultiplier:    2.0,
		MaxAttempts:          20,
	}
}

func TestUtilizationZeroNodesReturnsOne(t *testing.T) {
	s := ClusterState{TotalNodes: 0}
	if got := s.Utilization(); got != 1.0 {
		t.Fatalf("want 1.0 (worst case), got %v", got)
	}
}

func TestUtilizationFractional(t *testing.T) {
	s := ClusterState{TotalNodes: 10, AllocatedNodes: 3}
	if got := s.Utilization(); got != 0.3 {
		t.Fatalf("want 0.3, got %v", got)
	}
}

func TestDecideSubmitOnIdleCluster(t *testing.T) {
	d, reason := Decide(ClusterState{TotalNodes: 10, AllocatedNodes: 2}, defaultPoliteness())
	if d != Submit {
		t.Fatalf("want Submit, got %v (reason: %s)", d, reason)
	}
}

func TestDecideBackoffOnSelfRunningCap(t *testing.T) {
	p := defaultPoliteness()
	s := ClusterState{TotalNodes: 10, AllocatedNodes: 1, MyRunning: p.MaxConcurrentJobs}
	d, _ := Decide(s, p)
	if d != Backoff {
		t.Fatalf("want Backoff at running cap, got %v", d)
	}
}

func TestDecideBackoffOnSelfPendingCap(t *testing.T) {
	p := defaultPoliteness()
	s := ClusterState{TotalNodes: 10, AllocatedNodes: 1, MyPending: p.MaxPendingJobs}
	d, _ := Decide(s, p)
	if d != Backoff {
		t.Fatalf("want Backoff at pending cap, got %v", d)
	}
}

func TestDecideBackoffOnQueuePressure(t *testing.T) {
	p := defaultPoliteness()
	s := ClusterState{TotalNodes: 10, AllocatedNodes: 1, OthersPending: p.QueueDepthThreshold + 1}
	d, _ := Decide(s, p)
	if d != Backoff {
		t.Fatalf("want Backoff under queue pressure, got %v", d)
	}
}

func TestDecideBackoffOnHighUtilization(t *testing.T) {
	p := defaultPoliteness()
	// 95% utilization > default 90% threshold
	s := ClusterState{TotalNodes: 100, AllocatedNodes: 95}
	d, _ := Decide(s, p)
	if d != Backoff {
		t.Fatalf("want Backoff on high util, got %v", d)
	}
}

func TestDecisionString(t *testing.T) {
	cases := map[Decision]string{
		Submit:  "submit",
		Backoff: "backoff",
		Abort:   "abort",
	}
	for d, want := range cases {
		if got := d.String(); got != want {
			t.Errorf("Decision(%d).String() = %q, want %q", d, got, want)
		}
	}
}
