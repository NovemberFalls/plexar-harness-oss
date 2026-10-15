/**
 * Relay helpers replacing the upstream `debug` logger and `ManualPromise`.
 * @module @plexar/dsh-plexar/browser-bridge/log
 */

/**
 * Consume a relay-internal rejection nobody awaits (a closed connection or an abandoned handshake).
 * Such rejections are expected during teardown and carry no token or page data worth reporting.
 * @param _error - the ignored rejection reason.
 */
export function logUnhandledError(_error: unknown): void {}

/** A promise settled from outside, with a settled flag. */
export class Deferred extends Promise<void> {
  /** `then` and `catch` derive plain promises, not further deferreds. */
  static override get [Symbol.species](): PromiseConstructor { return Promise }

  private done = false
  private readonly settle: { resolve: () => void; reject: (error: Error) => void }

  constructor() {
    let settle!: { resolve: () => void; reject: (error: Error) => void }
    super((resolve, reject) => { settle = { resolve: () => { resolve() }, reject } })
    this.settle = settle
  }

  /** @returns whether the promise has been resolved or rejected. */
  isDone(): boolean { return this.done }

  /** Resolve once; later calls do nothing. */
  resolve(): void {
    if (this.done) return
    this.done = true
    this.settle.resolve()
  }

  /**
   * Reject once; later calls do nothing.
   * @param error - the rejection reason.
   */
  reject(error: Error): void {
    if (this.done) return
    this.done = true
    this.settle.reject(error)
  }
}
