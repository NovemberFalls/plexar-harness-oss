/**
 * Client-namespace projection of token-meter's browser-safe contracts and folds.
 *
 * @module @deepseek-ai/dsh-token-meter/client
 */

export type * from './projection.ts'
export { deriveTurnTokenUsage } from './turn-usage.ts'
export type { TurnTokenUsage, TurnTokenUsageRoute } from './turn-usage.ts'
export { contextOccupancy } from './context-occupancy.ts'
export type { ContextOccupancy } from './context-occupancy.ts'
