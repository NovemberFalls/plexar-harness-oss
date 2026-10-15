/**
 * Raw-mode keyboard router. Exactly one handler receives keys at a time (the top of a stack), so a
 * select prompt opened during a turn takes the keyboard and hands it back when it resolves.
 */
import { emitKeypressEvents } from 'node:readline';

const stack = [];
let started = false;

/**
 * Deliver one key to the current handler. The raw-mode listener calls this; tests call it directly.
 * @param {string | undefined} text
 * @param {{name?: string, ctrl?: boolean, shift?: boolean, meta?: boolean} | undefined} key
 */
export function dispatchKey(text, key) {
  const handler = stack[stack.length - 1];
  if (handler) handler(text ?? '', key ?? { name: text });
}

const onKeypress = dispatchKey;

/** Put stdin in raw mode and start routing keypresses. Idempotent. */
export function startKeys() {
  if (started) return;
  started = true;
  emitKeypressEvents(process.stdin);
  process.stdin.setRawMode(true);
  process.stdin.resume();
  process.stdin.on('keypress', onKeypress);
}

/** Restore the terminal's normal mode. */
export function stopKeys() {
  if (!started) return;
  started = false;
  process.stdin.off('keypress', onKeypress);
  process.stdin.setRawMode(false);
  process.stdin.pause();
}

/**
 * Route keys to `handler` until the returned function is called.
 * @param {(text: string, key: {name?: string, ctrl?: boolean, shift?: boolean, meta?: boolean, sequence?: string}) => void} handler
 * @returns {() => void} releases the keyboard to the previous handler
 */
export function pushKeys(handler) {
  stack.push(handler);
  return () => {
    const i = stack.lastIndexOf(handler);
    if (i >= 0) stack.splice(i, 1);
  };
}
