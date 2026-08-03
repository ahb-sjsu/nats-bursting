// Package natsbridge subscribes to job-submission requests on NATS
// and publishes status/result events back. Designed so the same
// binary can run as either:
//
//   - controller mode: subscribes to burst.submit.*, writes status
//     back as messages flow through the K8s submitter
//   - runner mode: invoked inside a Nautilus pod, publishes
//     burst.status.<job_id> heartbeats and a final
//     burst.result.<job_id> event
//
// This file ships the controller side; runner mode is a follow-up.
package natsbridge

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/ahb-sjsu/nats-bursting/internal/config"
	"github.com/ahb-sjsu/nats-bursting/internal/submitter"
	"github.com/nats-io/nats.go"
)

// Bridge wires a NATS subscription to a Submitter.
type Bridge struct {
	cfg config.NATSConfig
	sub *submitter.Submitter
	nc  *nats.Conn
	log *slog.Logger
}

// New connects to NATS using cfg and wraps the given Submitter.
func New(cfg config.NATSConfig, sub *submitter.Submitter, log *slog.Logger) (*Bridge, error) {
	opts := []nats.Option{
		nats.Name("nats-bursting"),
		nats.Timeout(cfg.ConnectWait),
		nats.MaxReconnects(-1),
	}
	if cfg.CredsFile != "" {
		opts = append(opts, nats.UserCredentials(cfg.CredsFile))
	}
	nc, err := nats.Connect(cfg.URL, opts...)
	if err != nil {
		return nil, fmt.Errorf("connect nats %q: %w", cfg.URL, err)
	}
	return &Bridge{cfg: cfg, sub: sub, nc: nc, log: log}, nil
}

// Close releases the NATS connection.
func (b *Bridge) Close() {
	if b.nc != nil {
		b.nc.Drain() //nolint:errcheck
	}
}

// SubmitMessage is the JSON payload received on burst.submit.
type SubmitMessage struct {
	JobID      string                  `json:"job_id"`
	Descriptor submitter.JobDescriptor `json:"descriptor"`
}

// StatusMessage is the JSON payload published on burst.status.<job_id>.
type StatusMessage struct {
	JobID     string    `json:"job_id"`
	State     string    `json:"state"` // submitted | accepted | rejected | error
	Reason    string    `json:"reason,omitempty"`
	K8sJob    string    `json:"k8s_job,omitempty"`
	Timestamp time.Time `json:"ts"`
}

// Run blocks, dispatching submit messages to the Submitter until ctx
// is cancelled.
func (b *Bridge) Run(ctx context.Context) error {
	subj := b.cfg.SubmitSubj
	queue := b.cfg.QueueGroup

	// A queue subscription delivers each message to exactly one member of the
	// group. A plain subscription delivers it to every controller running,
	// which then race to create the same Job; the loser's AlreadyExists is
	// silent, so the submitter sees a job that was accepted and never appears.
	var (
		sub *nats.Subscription
		err error
	)
	handler := func(msg *nats.Msg) { b.handle(ctx, msg) }
	if queue != "" {
		b.log.Info("subscribing", "subject", subj, "queue_group", queue)
		sub, err = b.nc.QueueSubscribe(subj, queue, handler)
	} else {
		b.log.Warn("subscribing without a queue group, so concurrent "+
			"controllers will race to create the same job", "subject", subj)
		sub, err = b.nc.Subscribe(subj, handler)
	}
	if err != nil {
		return fmt.Errorf("subscribe %s: %w", subj, err)
	}
	defer sub.Unsubscribe() //nolint:errcheck

	<-ctx.Done()
	return nil
}

func (b *Bridge) handle(ctx context.Context, msg *nats.Msg) {
	var req SubmitMessage
	if err := json.Unmarshal(msg.Data, &req); err != nil {
		b.log.Warn("bad submit message", "err", err)
		return
	}
	b.log.Info("submit request", "job_id", req.JobID, "name", req.Descriptor.Name)

	statusSubj := fmt.Sprintf("%s.%s", b.cfg.StatusPrefix, req.JobID)

	jobName, err := b.sub.Submit(ctx, req.Descriptor)
	status := StatusMessage{JobID: req.JobID, Timestamp: time.Now().UTC()}
	if err != nil {
		status.State = "error"
		status.Reason = err.Error()
		// Log it as well as publishing it. The status subject is the only
		// place this used to go, and the Python client misses it (it requests
		// a reply the handler never sends, then subscribes after the publish
		// has already happened). So a descriptor rejected by admission looked
		// exactly like a submission that silently did nothing: "submit
		// request" in the journal and no other trace anywhere.
		b.log.Error("submit failed", "job_id", req.JobID,
			"name", req.Descriptor.Name, "err", err)
	} else {
		status.State = "submitted"
		status.K8sJob = jobName
		b.log.Info("job created", "job_id", req.JobID, "k8s_job", jobName)
	}

	payload, _ := json.Marshal(status)
	if err := b.nc.Publish(statusSubj, payload); err != nil {
		b.log.Warn("publish status", "err", err)
	}
}
