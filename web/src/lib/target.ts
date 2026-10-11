// Which namespace a step is about. The words come from the values the step
// sends, and "not configured" is said out loud rather than guessed at.

export const NOT_CONFIGURED = "not configured";

/** "example-cluster / example-ns", or the words for what is missing. */
export function targetText(cluster: string, namespace: string): string {
  if (cluster && namespace) return `${cluster} / ${namespace}`;
  return cluster || namespace || NOT_CONFIGURED;
}

const JENKINS_DEFAULT = "Jenkins default";
export const JENKINS_DEFAULTS = "Jenkins defaults";

/** The review's words for a target: what the step does not send is left to Jenkins. */
export function reviewTargetText(cluster: string, namespace: string): string {
  if (!cluster && !namespace) return JENKINS_DEFAULTS;
  return `${cluster || JENKINS_DEFAULT} / ${namespace || JENKINS_DEFAULT}`;
}

/** One line per target, steps that share one on the same line: "Steps 1 and 3" · "example-cluster / example-ns". */
export function targetGroups(
  steps: { position: number; cluster: string; namespace: string }[],
): { steps: string; target: string }[] {
  const byTarget = new Map<string, number[]>();
  for (const step of steps) {
    const target = reviewTargetText(step.cluster.trim(), step.namespace.trim());
    byTarget.set(target, [...(byTarget.get(target) ?? []), step.position]);
  }
  return [...byTarget].map(([target, positions]) => ({ steps: stepList(positions), target }));
}

/** "Steps 1 and 3", "Step 2", "Steps 1, 2 and 4" -- positions are 1-based here. */
export function stepList(positions: number[]): string {
  const numbers = positions.map((position) => position + 1).sort((left, right) => left - right);
  if (numbers.length === 0) return "";
  if (numbers.length === 1) return `Step ${numbers[0]}`;
  const last = numbers[numbers.length - 1];
  return `Steps ${numbers.slice(0, -1).join(", ")} and ${last}`;
}
