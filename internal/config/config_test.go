package config

import "testing"

func TestDefaultsSetQueueGroup(t *testing.T) {
	// Without a queue group every running controller receives every submit
	// message and they race to create the same Job. The loser's AlreadyExists
	// is silent, so a caller sees a job accepted that never appears. Observed
	// 2026-08-03 with an Atlas controller and an in-cluster controller both
	// subscribed to burst.submit. Default it on; an operator can still clear
	// it deliberately to restore broadcast behaviour.
	d := Defaults()
	if d.NATS.QueueGroup == "" {
		t.Fatal("default NATS.QueueGroup is empty; concurrent controllers would race")
	}
}
