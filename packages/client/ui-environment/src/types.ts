/** Remote boundary vocabulary of the environment rail's Host half, safe for both planes. */

/** The branch answer; `null` covers every case without a named branch. */
export interface EnvironmentBranch {
  /** Checked-out branch name, or null for no workspace, no repository, a detached HEAD, or any failure. */
  readonly branch: string | null
}
