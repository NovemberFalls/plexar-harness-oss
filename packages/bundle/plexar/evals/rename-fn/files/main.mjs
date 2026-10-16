import { fetchTotal } from './lib.mjs';
import { double } from './util.mjs';

export const result = fetchTotal([1, 2]) + double([1]) + fetchTotal([0]);
