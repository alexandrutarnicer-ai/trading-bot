/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0f1117",
          card:    "#1a1d27",
          border:  "#2a2d3d",
        },
        profit: "#22c55e",
        loss:   "#ef4444",
        warn:   "#f59e0b",
      },
    },
  },
  plugins: [],
};
