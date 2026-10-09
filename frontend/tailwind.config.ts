import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: "#a3e635",
          hover: "#84cc16",
        },
        surface: {
          light: "#F5F3EE",
          dark: "#1a1a1a",
        },
        card: {
          light: "#ffffff",
          dark: "#242424",
        },
      },
    },
  },
  plugins: [],
};

export default config;
