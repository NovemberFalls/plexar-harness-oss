# Source of the copied tokens

`plexar-tokens.css` and `fonts/montserrat-medium.woff2` are byte-for-byte copies of:

- `<workspace>\plexar-coord\brand\tokens\plexar-tokens.css`
- `<workspace>\plexar-coord\brand\tokens\fonts\montserrat-medium.woff2`

at commit `33fa228` (`brand: shared --px-* tokens from Len's Claude Design export (one look for every Plexar product)`).

Do not edit either file. To pick up an update, re-copy both files from that path at the new
commit and re-run `scripts/generate-font.ts` to refresh `font.ts` (see that script's header).
