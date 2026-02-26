/** @type {import('tailwindcss').Config} */
const config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        mc: {
          bg0: "hsl(var(--mc-bg-0))",
          bg1: "hsl(var(--mc-bg-1))",
          surface: "hsl(var(--mc-surface))",
          surface2: "hsl(var(--mc-surface-2))",
          border: "hsl(var(--mc-border))",
          fg: "hsl(var(--mc-fg))",
          muted: "hsl(var(--mc-muted))",
          muted2: "hsl(var(--mc-muted-2))",
          accent: "hsl(var(--mc-accent))",
          danger: "hsl(var(--mc-danger))",
          success: "hsl(var(--mc-success))",
        },
      },
    },
  },
};

export default config;
