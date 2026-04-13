// Package prober probes Kubernetes cluster state for the politeness
// decider. Talks to the API server via client-go.
package prober

import (
	"context"

	"github.com/ahb-sjsu/atlas-burst/internal/decider"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/fields"
	"k8s.io/client-go/kubernetes"
)

// Prober reads cluster state. Implementations may target different
// backends; for now we only ship a Kubernetes one.
type Prober interface {
	Probe(ctx context.Context) (decider.ClusterState, error)
}

// K8sProber probes a Kubernetes cluster via client-go.
type K8sProber struct {
	Client    kubernetes.Interface
	Namespace string
}

// New returns a K8sProber using the given clientset.
func New(client kubernetes.Interface, namespace string) *K8sProber {
	return &K8sProber{Client: client, Namespace: namespace}
}

// Probe collects node, job, and pending-pod counts. Each sub-call
// degrades gracefully: if any individual API call fails (RBAC,
// unavailable resource, etc.) the corresponding fields stay at zero
// and the decider falls back to the remaining signals.
func (p *K8sProber) Probe(ctx context.Context) (decider.ClusterState, error) {
	state := decider.ClusterState{Namespace: p.Namespace}

	if nodes, err := p.Client.CoreV1().Nodes().List(ctx, metav1.ListOptions{}); err == nil {
		total, allocated := SummarizeNodes(nodes.Items)
		state.TotalNodes = total
		state.AllocatedNodes = allocated
		state.IdleNodes = total - allocated
	}

	if jobs, err := p.Client.BatchV1().Jobs(p.Namespace).List(ctx, metav1.ListOptions{}); err == nil {
		state.MyRunning, state.MyPending = SummarizeJobs(jobs.Items)
	}

	pendingSel := fields.OneTermEqualSelector("status.phase", string(corev1.PodPending))
	if pods, err := p.Client.CoreV1().Pods(metav1.NamespaceAll).List(ctx, metav1.ListOptions{
		FieldSelector: pendingSel.String(),
	}); err == nil {
		others := 0
		for _, pod := range pods.Items {
			if pod.Namespace != p.Namespace {
				others++
			}
		}
		state.OthersPending = others
	}

	return state, nil
}

// SummarizeNodes returns (total, allocated) where "allocated" is a
// coarse proxy: nodes that are unschedulable get excluded entirely;
// nodes that are not Ready count as allocated (they can't accept
// new work). For a precise utilization number, layer in metrics-server.
func SummarizeNodes(nodes []corev1.Node) (total, allocated int) {
	for _, n := range nodes {
		if n.Spec.Unschedulable {
			continue
		}
		total++
		if !nodeReady(n) {
			allocated++
		}
	}
	return
}

func nodeReady(n corev1.Node) bool {
	for _, c := range n.Status.Conditions {
		if c.Type == corev1.NodeReady && c.Status == corev1.ConditionTrue {
			return true
		}
	}
	return false
}

// SummarizeJobs counts a job as "running" if it has active pods, and
// "pending" if it's been declared but hasn't reached its desired
// completions yet (and isn't currently active).
func SummarizeJobs(jobs []batchv1.Job) (running, pending int) {
	for _, j := range jobs {
		if j.Status.Active > 0 {
			running++
			continue
		}
		var completions int32 = 1
		if j.Spec.Completions != nil {
			completions = *j.Spec.Completions
		}
		if j.Status.Succeeded+j.Status.Failed < completions {
			pending++
		}
	}
	return
}
