/**
 * The TUI's signed-out state machine (N74: sign-in happens inside the harness). The composer stays
 * open while signed out or not entitled; prompts are refused with a notice until `/login` (or Enter
 * on the empty composer) succeeds. `loginFn`, `checkGateFn` and `restartHostFn` are injected so this
 * runs without a browser, a real rig, or a real ACP host child.
 */

/** Copy shown while blocked; `entitled-false` uses the gate's own reason text instead. */
export const NOTICE = {
  signedOut: "You're not signed in to Plexar. Press Enter to sign in in your browser, or type /login.",
  waiting: 'Waiting for you to sign in in your browser… (Esc to cancel)',
};

/** `checkGate()` messages that mean "no valid key", as opposed to a valid key that just isn't entitled. */
export const SIGNED_OUT_MESSAGES = new Set([
  'Not signed in. Run: plexar-harness login',
  'Please sign in again: plexar-harness login',
]);

export class SignInState {
  /**
   * @param {{
   *   loginFn: () => Promise<{ok: boolean}>,
   *   checkGateFn: () => Promise<{ok: boolean, key?: string, message?: string, warning?: string, models?: object[], allModels?: object[]}>,
   *   restartHostFn: (gate: {key: string, models?: object[], allModels?: object[]}) => Promise<void>,
   * }} deps
   */
  constructor({ loginFn, checkGateFn, restartHostFn }) {
    this.loginFn = loginFn;
    this.checkGateFn = checkGateFn;
    this.restartHostFn = restartHostFn;
    /** @type {'signed-in' | 'signed-out' | 'entitled-false'} */
    this.status = 'signed-out';
    this.reason = undefined;
    this.busy = false;
  }

  /** @returns {boolean} whether a submitted prompt must be refused right now. */
  get blocked() {
    return this.status !== 'signed-in';
  }

  /** @returns {string} the notice to show while blocked. */
  get notice() {
    return this.status === 'entitled-false' ? this.reason : NOTICE.signedOut;
  }

  /**
   * Apply a `checkGate()` result to the state, without running login or restarting the host.
   * @returns {object} the same gate result, so the caller can act on `key`/`models`/`warning`.
   */
  applyGate(gate) {
    if (gate.ok) {
      this.status = 'signed-in';
      this.reason = undefined;
    } else {
      this.status = SIGNED_OUT_MESSAGES.has(gate.message) ? 'signed-out' : 'entitled-false';
      this.reason = gate.message;
    }
    return gate;
  }

  /** Re-run `checkGateFn` and apply it. @returns {Promise<object>} the gate result. */
  async refresh() {
    return this.applyGate(await this.checkGateFn());
  }

  /**
   * Run `loginFn` (the loopback PKCE flow), re-check the gate, and on success restart the ACP host
   * so it inherits the new key before moving to `signed-in`. A cancelled or failed login, or a
   * second gate failure (e.g. `entitled: false`), leaves the state blocked.
   * @returns {Promise<{ok: boolean}>}
   */
  async login() {
    this.busy = true;
    try {
      const result = await this.loginFn();
      if (!result.ok) return { ok: false };
      const gate = await this.refresh();
      if (!gate.ok) return { ok: false };
      await this.restartHostFn(gate);
      return { ok: true };
    } finally {
      this.busy = false;
    }
  }
}
