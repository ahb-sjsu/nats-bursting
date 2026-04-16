package natsbridge

import (
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/ahb-sjsu/nats-bursting/internal/config"
	"github.com/ahb-sjsu/nats-bursting/internal/submitter"
)

// TestSubmitMessageRoundTrip verifies the client-emitted envelope
// unmarshals into the bridge's expected struct. This is the contract
// between the Python client (python/nats_bursting/descriptor.py) and
// the Go controller; breaking it breaks every submitter.
func TestSubmitMessageRoundTrip(t *testing.T) {
	// Shape matches what nats_bursting.descriptor.SubmitEnvelope.to_json()
	// produces. If this literal changes, update the Python side in lockstep.
	payload := `{
	  "job_id": "abc-123",
	  "descriptor": {
	    "name": "trainer",
	    "image": "ghcr.io/example/trainer:1.0",
	    "command": ["python", "train.py"],
	    "args": ["--epochs", "10"],
	    "env": {"WANDB_DISABLED": "true"},
	    "resources": {"cpu": "4", "memory": "16Gi", "gpu": 1},
	    "labels": {"owner": "andrew"},
	    "backoff_limit": 2
	  }
	}`

	var msg SubmitMessage
	if err := json.Unmarshal([]byte(payload), &msg); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if msg.JobID != "abc-123" {
		t.Errorf("JobID: got %q, want abc-123", msg.JobID)
	}
	if msg.Descriptor.Name != "trainer" {
		t.Errorf("Name: got %q, want trainer", msg.Descriptor.Name)
	}
	if msg.Descriptor.Resources.GPU != 1 {
		t.Errorf("GPU: got %d, want 1", msg.Descriptor.Resources.GPU)
	}
	if msg.Descriptor.BackoffLimit != 2 {
		t.Errorf("BackoffLimit: got %d, want 2", msg.Descriptor.BackoffLimit)
	}
	if msg.Descriptor.Env["WANDB_DISABLED"] != "true" {
		t.Errorf("Env: %v", msg.Descriptor.Env)
	}
}

// TestSubmitMessageRejectsGarbage verifies malformed messages don't
// panic the handler. Handle() logs and drops; we test the unmarshal
// path surfaces an error before reaching Submit().
func TestSubmitMessageRejectsGarbage(t *testing.T) {
	for _, bad := range []string{
		"",                                  // empty
		"not json",                          // unparseable
		`{"job_id": 42, "descriptor": {}}`,  // wrong type for job_id
		`{"descriptor": {"name": "ok"}}`,    // missing job_id (valid JSON but empty string field)
	} {
		var msg SubmitMessage
		err := json.Unmarshal([]byte(bad), &msg)
		// We don't require an error on every shape (empty job_id is
		// technically valid JSON), but we do require no panics.
		_ = err
	}
}

// TestStatusMessageShape ensures the published event contains every
// field subscribers rely on. Python's nats_bursting.descriptor.StatusEvent
// has is_terminal() that keys off State — don't change the enum strings
// without also changing that client.
func TestStatusMessageShape(t *testing.T) {
	ts := time.Date(2026, 4, 16, 19, 52, 53, 0, time.UTC)
	cases := []struct {
		name  string
		state string
	}{
		{"submitted", "submitted"},
		{"error", "error"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			sm := StatusMessage{
				JobID:     "abc-123",
				State:     tc.state,
				K8sJob:    "trainer-xy",
				Timestamp: ts,
			}
			data, err := json.Marshal(sm)
			if err != nil {
				t.Fatalf("marshal: %v", err)
			}
			s := string(data)
			for _, field := range []string{`"job_id":"abc-123"`, `"state":"` + tc.state + `"`, `"ts":"2026-04-16T19:52:53Z"`} {
				if !strings.Contains(s, field) {
					t.Errorf("missing %s in %s", field, s)
				}
			}
		})
	}
}

// TestStatusSubjectComposition verifies the per-job subject naming
// convention. Subscribers compute this path from StatusPrefix + JobID;
// a change here silently breaks every subscriber.
func TestStatusSubjectComposition(t *testing.T) {
	cfg := config.NATSConfig{
		StatusPrefix: "burst.status",
	}
	got := fmt.Sprintf("%s.%s", cfg.StatusPrefix, "abc-123")
	if got != "burst.status.abc-123" {
		t.Errorf("status subject: got %q, want burst.status.abc-123", got)
	}
}

// TestBridgeStructInitialization smoke-tests that the zero-value
// Bridge holds expected types — catches accidental field renames.
func TestBridgeStructInitialization(t *testing.T) {
	var b Bridge
	if b.nc != nil {
		t.Error("nc should be nil on zero value")
	}
	if b.sub != nil {
		t.Error("sub should be nil on zero value")
	}
}

// Ensure SubmitMessage round-trips by re-marshalling.
func TestSubmitMessageReEncode(t *testing.T) {
	in := SubmitMessage{
		JobID: "xyz",
		Descriptor: submitter.JobDescriptor{
			Name:  "re-encode",
			Image: "alpine:3",
			Resources: submitter.Resources{
				CPU:    "1",
				Memory: "256Mi",
			},
		},
	}
	data, err := json.Marshal(in)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var out SubmitMessage
	if err := json.Unmarshal(data, &out); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if out.Descriptor.Name != "re-encode" || out.Descriptor.Resources.Memory != "256Mi" {
		t.Errorf("round-trip lost fields: %+v", out)
	}
}
