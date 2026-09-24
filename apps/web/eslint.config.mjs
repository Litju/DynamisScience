import { FlatCompat } from "@eslint/eslintrc";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const directory = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: directory });

const config = [{ ignores: [".next/**", "node_modules/**", "out/**", "coverage/**", "next-env.d.ts"] }, ...compat.extends("next/core-web-vitals", "next/typescript")];

export default config;
