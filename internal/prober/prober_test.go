package prober

import (
	"context"
	"testing"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func ptrInt32(v int32) *int32 { return &v }

func TestSummarizeNodesSkipsUnschedulableAndCountsNotReadyAsAllocated(t *testing.T) {
	nodes := []corev1.Node{
		{
			ObjectMeta: metav1.ObjectMeta{Name: "ready-1"},
			Status: corev1.NodeStatus{Conditions: []corev1.NodeCondition{
				{Type: corev1.NodeReady, Status: corev1.ConditionTrue},
			}},
		},
		{
			ObjectMeta: metav1.ObjectMeta{Name: "ready-2"},
			Status: corev1.NodeStatus{Conditions: []corev1.NodeCondition{
				{Type: corev1.NodeReady, Status: corev1.ConditionTrue},
			}},
		},
		{
			ObjectMeta: metav1.ObjectMeta{Name: "notready"},
			Status: corev1.NodeStatus{Conditions: []corev1.NodeCondition{
				{Type: corev1.NodeReady, Status: corev1.ConditionFalse},
			}},
		},
		{
			ObjectMeta: metav1.ObjectMeta{Name: "cordoned"},
			Spec:       corev1.NodeSpec{Unschedulable: true},
			Status: corev1.NodeStatus{Conditions: []corev1.NodeCondition{
				{Type: corev1.NodeReady, Status: corev1.ConditionTrue},
			}},
		},
	}
	total, allocated := SummarizeNodes(nodes)
	if total != 3 {
		t.Errorf("total: want 3, got %d", total)
	}
	if allocated != 1 {
		t.Errorf("allocated (NotReady): want 1, got %d", allocated)
	}
}

func TestSummarizeJobsCountsActiveAndPending(t *testing.T) {
	jobs := []batchv1.Job{
		{Status: batchv1.JobStatus{Active: 1}, Spec: batchv1.JobSpec{Completions: ptrInt32(1)}},
		{Status: batchv1.JobStatus{Active: 2}, Spec: batchv1.JobSpec{Completions: ptrInt32(3)}},
		{Status: batchv1.JobStatus{Succeeded: 0}, Spec: batchv1.JobSpec{Completions: ptrInt32(1)}}, // pending
		{Status: batchv1.JobStatus{Succeeded: 1}, Spec: batchv1.JobSpec{Completions: ptrInt32(1)}}, // done
	}
	running, pending := SummarizeJobs(jobs)
	if running != 2 {
		t.Errorf("running: want 2, got %d", running)
	}
	if pending != 1 {
		t.Errorf("pending: want 1, got %d", pending)
	}
}

func TestProbeEndToEndAgainstFakeClient(t *testing.T) {
	client := fake.NewSimpleClientset(
		// 2 schedulable Ready nodes, 1 NotReady → total=3, allocated=1
		&corev1.Node{
			ObjectMeta: metav1.ObjectMeta{Name: "n1"},
			Status: corev1.NodeStatus{Conditions: []corev1.NodeCondition{
				{Type: corev1.NodeReady, Status: corev1.ConditionTrue}}},
		},
		&corev1.Node{
			ObjectMeta: metav1.ObjectMeta{Name: "n2"},
			Status: corev1.NodeStatus{Conditions: []corev1.NodeCondition{
				{Type: corev1.NodeReady, Status: corev1.ConditionTrue}}},
		},
		&corev1.Node{
			ObjectMeta: metav1.ObjectMeta{Name: "n3"},
			Status: corev1.NodeStatus{Conditions: []corev1.NodeCondition{
				{Type: corev1.NodeReady, Status: corev1.ConditionFalse}}},
		},
		// One job in our namespace, active
		&batchv1.Job{
			ObjectMeta: metav1.ObjectMeta{Name: "myjob", Namespace: "mine"},
			Spec:       batchv1.JobSpec{Completions: ptrInt32(1)},
			Status:     batchv1.JobStatus{Active: 1},
		},
		// Pending pods: 1 in my namespace, 2 elsewhere
		&corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{Name: "p-mine", Namespace: "mine"},
			Status:     corev1.PodStatus{Phase: corev1.PodPending},
		},
		&corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{Name: "p-alice", Namespace: "alice"},
			Status:     corev1.PodStatus{Phase: corev1.PodPending},
		},
		&corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{Name: "p-bob", Namespace: "bob"},
			Status:     corev1.PodStatus{Phase: corev1.PodPending},
		},
	)

	p := New(client, "mine")
	state, err := p.Probe(context.Background())
	if err != nil {
		t.Fatalf("Probe: %v", err)
	}
	if state.TotalNodes != 3 {
		t.Errorf("TotalNodes: want 3, got %d", state.TotalNodes)
	}
	if state.AllocatedNodes != 1 {
		t.Errorf("AllocatedNodes: want 1, got %d", state.AllocatedNodes)
	}
	if state.MyRunning != 1 {
		t.Errorf("MyRunning: want 1, got %d", state.MyRunning)
	}
	// fake client doesn't honor field selectors, so we'd see all 3 pending
	// pods minus the 1 in our namespace = 2.
	if state.OthersPending != 2 {
		t.Errorf("OthersPending: want 2, got %d", state.OthersPending)
	}
}
