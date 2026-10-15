/** Plain-language messages for errors the user can act on (rig loading, revoked access, rig unreachable). */
import { REVOKED_COPY, UNAUTHORIZED_COPY } from './auth.mjs';

/**
 * Turn rig errors the user can act on into one plain sentence; anything else is shown as-is.
 * @param {Error} error
 * @returns {string}
 */
export function explain(error) {
  const text = error.message;
  if (/engine_unavailable|is not ready/.test(text)) {
    const progress = /\((\d+%)\)/.exec(text)?.[1];
    return `The Plexar rig is still loading the model${progress ? ` (${progress})` : ''}. Try again in a moment.`;
  }
  if (text.includes(REVOKED_COPY) || /product_not_granted/.test(text)) return REVOKED_COPY;
  if (/\b401\b|unauthori[sz]ed|invalid api key/i.test(text)) return UNAUTHORIZED_COPY;
  if (/ECONNREFUSED|ETIMEDOUT|EHOSTUNREACH|fetch failed/.test(text)) {
    return `Could not reach the Plexar rig at ${process.env.PLEXAR_RIG_URL ?? 'https://llm.plexar.tech'}. Check the network, or set PLEXAR_RIG_URL to a rig you can reach.`;
  }
  return text;
}
