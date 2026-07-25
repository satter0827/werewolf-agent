import boundaries from "eslint-plugin-boundaries";
import tseslint from "typescript-eslint";

export default [
  {
    files: ["e2e/**/*.ts", "*.config.ts"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: { sourceType: "module" },
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        sourceType: "module",
      },
    },
    plugins: { boundaries },
    settings: {
      "boundaries/elements": [
        { type: "generated", pattern: "src/generated/**" },
        { type: "data", pattern: "src/data/**" },
        { type: "feature", pattern: "src/features/**" },
        { type: "shared", pattern: "src/gameClient/**" },
        { type: "skin", pattern: "src/skins/**" },
        { type: "store", pattern: "src/store/**" },
        { type: "test", pattern: "src/test/**" },
      ],
    },
    rules: {
      "boundaries/dependencies": [
        "error",
        {
          default: "allow",
          policies: [
            {
              from: { element: { types: { anyOf: ["feature", "shared"] } } },
              disallow: { to: { element: { type: "generated" } } },
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/data/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: { sourceType: "module" },
    },
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.property.name='from']",
          message: "Supabase Data API is forbidden; use the generated HTTP API client.",
        },
      ],
    },
  },
];
