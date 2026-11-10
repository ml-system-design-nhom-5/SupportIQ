// ESLint settings for frontend: the rule sets of TS-02, the limits of TS-04 and CODE-11, and the
// design-system rules of UI-02, UI-05, and TS-25, so a tool checks them (RULE-03). Generated code
// is never linted (CON-26).
import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import betterTailwindcss from "eslint-plugin-better-tailwindcss";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import simpleImportSort from "eslint-plugin-simple-import-sort";
import globals from "globals";
import tseslint from "typescript-eslint";

const COLOR_LITERAL = String.raw`/#[0-9a-fA-F]{3,8}\b|\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/`;
const PIXEL_VALUE = String.raw`/\b[0-9]+(\.[0-9]+)?px\b/`;

/** TS-14 and CODE-35: no TypeScript enum, and no nested ternary. */
const languageRestrictions = [
  { selector: "TSEnumDeclaration", message: "TS-14: use a string literal union, not an enum." },
  {
    selector: "ConditionalExpression ConditionalExpression",
    message: "CODE-35: extract the inner condition, because nested ternaries are hard to read.",
  },
];
/** TS-16: no class component outside app/. */
const classComponentRestrictions = [
  {
    selector:
      "ClassDeclaration[superClass.name=/^(Component|PureComponent)$/], ClassDeclaration[superClass.property.name=/^(Component|PureComponent)$/]",
    message: "TS-16: use a function component. Only the error boundaries in app/ are classes.",
  },
];
/** UI-05: no color literal and no pixel value outside the token files. */
const visualLiteralRestrictions = [
  { selector: `Literal[value=${COLOR_LITERAL}]`, message: "UI-05: use a color token." },
  { selector: `TemplateElement[value.raw=${COLOR_LITERAL}]`, message: "UI-05: use a color token." },
  { selector: `Literal[value=${PIXEL_VALUE}]`, message: "UI-05: use a spacing or size token." },
  { selector: `TemplateElement[value.raw=${PIXEL_VALUE}]`, message: "UI-05: use a size token." },
];

/** UI-05 and TS-25: Tailwind classes that bypass the tokens. */
const restrictedTailwindClasses = [
  { pattern: String.raw`^.*\[.*$`, message: "TS-25: arbitrary values are forbidden: $0." },
  { pattern: String.raw`^.*\(.*$`, message: "TS-25: arbitrary variables are forbidden: $0." },
  { pattern: String.raw`^(.*:)?duration-(?!100$|200$).*$`, message: "UI-09: use 100 or 200 ms." },
  { pattern: String.raw`^!.*|.*!$`, message: "UI-05: the important modifier is forbidden." },
];

/** TS-04 and CODE-11: the MUST limits. */
const sizeLimits = {
  complexity: ["error", 8],
  "max-depth": ["error", 3],
  "max-params": ["error", 3],
  "max-lines": ["error", { max: 300, skipBlankLines: true, skipComments: true }],
  "max-lines-per-function": ["error", { max: 40, skipBlankLines: true, skipComments: true }],
};

export default defineConfig(
  {
    ignores: [
      "node_modules/",
      "dist/",
      "storybook-static/",
      "coverage/",
      "playwright-report/",
      "test-results/",
      "src/api/generated/",
    ],
  },
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: { allowDefaultProject: ["eslint.config.js", ".dependency-cruiser.cjs"] },
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: { "simple-import-sort": simpleImportSort },
    rules: {
      ...sizeLimits,
      "no-console": "error",
      "no-restricted-syntax": ["error", ...languageRestrictions],
      "no-restricted-imports": [
        "error",
        { patterns: [{ group: ["../../*"], message: "TS-07: use the @/ path alias." }] },
      ],
      "simple-import-sort/imports": "error",
      "simple-import-sort/exports": "error",
      "@typescript-eslint/consistent-type-assertions": ["error", { assertionStyle: "never" }],
      "@typescript-eslint/consistent-type-definitions": ["error", "type"],
      "@typescript-eslint/switch-exhaustiveness-check": [
        "error",
        { considerDefaultExhaustiveForUnions: false, requireDefaultForNonUnion: true },
      ],
      "@typescript-eslint/naming-convention": [
        "error",
        { selector: "typeLike", format: ["PascalCase"] },
        // TS-08: UPPER_SNAKE_CASE only for module-level primitive constants.
        { selector: "variable", format: ["camelCase", "PascalCase"] },
        {
          selector: "variable",
          modifiers: ["const", "global"],
          types: ["string", "number"],
          format: ["camelCase", "UPPER_CASE"],
        },
        {
          selector: ["variable", "parameter", "typeProperty"],
          types: ["boolean"],
          format: ["PascalCase"],
          prefix: ["is", "has", "can", "should"],
          filter: { regex: "^asChild$", match: false },
        },
      ],
    },
  },
  {
    files: ["**/*.js", "**/*.cjs"],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["vite.config.ts", "playwright.config.ts", ".storybook/main.ts", "scripts/**", "e2e/**"],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["src/**/*.{ts,tsx}", ".storybook/**/*.{ts,tsx}"],
    extends: [
      react.configs.flat.recommended,
      react.configs.flat["jsx-runtime"],
      reactHooks.configs.flat["recommended-latest"],
      jsxA11y.flatConfigs.strict,
      betterTailwindcss.configs["correctness-error"],
    ],
    languageOptions: { globals: globals.browser },
    settings: {
      react: { version: "detect" },
      "better-tailwindcss": { entryPoint: "src/design-system/tokens/tokens.css" },
    },
    rules: {
      "no-restricted-syntax": [
        "error",
        ...languageRestrictions,
        ...classComponentRestrictions,
        ...visualLiteralRestrictions,
      ],
      "react/prop-types": "off",
      "react/no-danger": "error",
      "react/no-array-index-key": "error",
      "react/forbid-dom-props": ["error", { forbid: ["style"] }],
      "react/forbid-component-props": ["error", { forbid: ["style"] }],
      "better-tailwindcss/no-restricted-classes": [
        "error",
        { restrict: restrictedTailwindClasses },
      ],
      "better-tailwindcss/no-duplicate-classes": "error",
      "better-tailwindcss/no-unnecessary-whitespace": "error",
      "better-tailwindcss/enforce-consistent-class-order": "error",
    },
  },
  {
    // TS-17: a component MUST stay under 150 lines. Other functions keep the 40-line limit.
    files: ["src/**/*.tsx", ".storybook/**/*.tsx"],
    rules: {
      "max-lines-per-function": ["error", { max: 150, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    // UI-02: features and app compose design-system components and never style elements.
    files: ["src/features/**/*.{ts,tsx}", "src/app/**/*.{ts,tsx}"],
    rules: {
      "react/forbid-dom-props": ["error", { forbid: ["style", "className"] }],
      "react/forbid-component-props": ["error", { forbid: ["style", "className"] }],
    },
  },
  {
    // TS-16: the error boundaries in app/ are the only class components.
    files: ["src/app/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": ["error", ...languageRestrictions, ...visualLiteralRestrictions],
    },
  },
  {
    // The token files are the only place for visual literals (UI-05).
    files: ["src/design-system/tokens/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": ["error", ...languageRestrictions, ...classComponentRestrictions],
    },
  },
);
