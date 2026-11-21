// dependency-cruiser rules of frontend: the import rules of TS-06, the feature boundaries of
// ARCH-17 and ARCH-18, the file names of TS-07, and no import cycles (CODE-23). Type-only imports
// count as dependencies.
/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      comment: "CODE-23 and ARCH-18: import cycles are forbidden at every level.",
      severity: "error",
      from: {},
      to: { circular: true },
    },
    {
      name: "feature-public-api",
      comment: "TS-06 and ARCH-17: another feature is reached only through its index.ts.",
      severity: "error",
      from: { path: "^src/features/([^/]+)/" },
      to: {
        path: "^src/features/[^/]+/.+",
        pathNot: ["^src/features/$1/", "^src/features/[^/]+/index\\.ts$"],
      },
    },
    {
      name: "app-uses-feature-public-api",
      comment: "TS-06: app/ composes features through their index.ts.",
      severity: "error",
      from: { path: "^src/app/" },
      to: { path: "^src/features/[^/]+/.+", pathNot: "^src/features/[^/]+/index\\.ts$" },
    },
    {
      name: "design-system-is-independent",
      comment: "TS-06: design-system/ imports nothing from features/, app/, or api/.",
      severity: "error",
      from: { path: "^src/design-system/" },
      to: { path: "^src/(features|app|api)/" },
    },
    {
      name: "only-feature-api-reaches-the-client",
      comment:
        "TS-06 and TS-28: only features/*/api/ imports from api/. The composition root creates " +
        "the client (ARCH-21), and test utilities give it a fake fetch.",
      severity: "error",
      from: {
        pathNot: [
          "^src/features/[^/]+/api/",
          "^src/api/",
          "^src/app/composition-root\\.tsx$",
          "^src/test/",
        ],
      },
      to: { path: "^src/api/" },
    },
    {
      name: "only-api-layers-use-openapi-fetch",
      comment: "TS-28: components never call the client or fetch.",
      severity: "error",
      from: { pathNot: ["^src/api/", "^src/features/[^/]+/api/", "^src/test/"] },
      to: { path: "node_modules/openapi-fetch" },
    },
    {
      name: "model-is-pure",
      comment:
        "TS-09: model/ maps contract types to view models. It imports only the contract types " +
        "of its own feature (api/contract-types.ts), never hooks, components, or React.",
      severity: "error",
      from: { path: "^src/features/([^/]+)/model/" },
      to: {
        path: [
          "^src/features/[^/]+/(components|api)/",
          "node_modules/(react|react-dom|@tanstack)/",
        ],
        pathNot: "^src/features/$1/api/contract-types\\.ts$",
      },
    },
    {
      name: "features-do-not-import-app",
      comment: "TS-06: app/ composes features, never the other way round.",
      severity: "error",
      from: { path: "^src/(features|design-system|api)/" },
      to: { path: "^src/app/" },
    },
    {
      name: "styles-come-from-tokens",
      comment: "UI-05: every style sheet lives in design-system/tokens/.",
      severity: "error",
      from: {},
      to: { path: "\\.css$", pathNot: ["^src/design-system/tokens/", "node_modules/"] },
    },
    {
      name: "production-code-does-not-import-tests",
      comment: "Test utilities and fixtures stay out of the bundle.",
      severity: "error",
      from: { path: "^src/", pathNot: ["\\.(test|stories)\\.tsx?$", "^src/test/"] },
      to: { path: ["^src/test/", "\\.(test|stories)\\.tsx?$", "^\\.\\./contracts/"] },
    },
    {
      name: "kebab-case-file-names",
      comment: "TS-07: file and folder names are kebab-case.",
      severity: "error",
      from: { path: "^src/", pathNot: "^src/[a-z0-9./-]+$" },
      to: {},
    },
    {
      name: "ingress-imports-nothing",
      comment:
        "ADR-0016: the Pages Function runs on the Workers runtime, so its code imports only the " +
        "ingress module: no package, no Node module, and nothing of src/.",
      severity: "error",
      from: { path: "^(ingress|functions)/", pathNot: "\\.test\\.ts$" },
      to: { pathNot: "^ingress/ingress\\.ts$" },
    },
    {
      name: "app-does-not-import-ingress",
      comment: "The page and the Pages Function are bundled apart, so src/ never imports them.",
      severity: "error",
      from: { path: "^src/" },
      to: { path: "^(ingress|functions)/" },
    },
  ],
  options: {
    doNotFollow: { path: ["node_modules", "^src/api/generated/"] },
    tsPreCompilationDeps: true,
    tsConfig: { fileName: "tsconfig.app.json" },
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "require", "node", "default", "types"],
      mainFields: ["module", "main", "types", "typings"],
    },
    reporterOptions: { text: { highlightFocused: true } },
  },
};
