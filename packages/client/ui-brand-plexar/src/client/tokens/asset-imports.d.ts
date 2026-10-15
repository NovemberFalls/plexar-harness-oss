/** The copied shared token sheet, compiled to text by the client bundler's `?inline` loader. */
declare module '*.css?inline' {
  const source: string
  export default source
}
