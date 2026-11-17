/**
 * The Pages Function route of `/v1/*`: the ingress (ADR-0016, statement 2). Pages requires the
 * file name `[[path]]`, which matches every path below this folder, so the name is an exception
 * to the kebab-case file names of TS-07. Pages bundles this file without the `@/` alias, so it
 * imports the ingress by a relative path.
 */
export { onRequest } from "../../ingress/ingress.ts";
