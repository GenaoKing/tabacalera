/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    // Todas las apps Django
    './*/templates/**/*.html',
    // base.html global
    './app/templates/**/*.html',
  ],
  theme: {
    extend: {
      fontFamily: {
        'display': ['"DM Sans"', 'system-ui', 'sans-serif'],
        'body': ['"DM Sans"', 'system-ui', 'sans-serif'],
        'mono': ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        // Acentos cálidos para tabaco
        tobacco: {
          50:  '#fdf8f0',
          100: '#f9edda',
          200: '#f2d8b4',
          300: '#e9bd84',
          400: '#df9c53',
          500: '#d68332',
          600: '#c86b28',
          700: '#a65223',
          800: '#854223',
          900: '#6c371f',
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
