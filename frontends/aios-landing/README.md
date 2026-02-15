# aios landing page

Marketing site for `fluxtopus.com`.

## Features

- Next.js 16 with App Router
- Tailwind CSS with tactical dark theme
- Custom fonts: Rajdhani (headings) + Space Mono (monospace)
- Responsive design
- Animated hero section
- Feature highlights

## Development

```bash
# Install dependencies
npm install

# Run dev server (port 3002)
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

## Structure

```
src/
├── app/
│   ├── layout.tsx              # Root layout with fonts
│   ├── page.tsx                # Home page
│   ├── globals.css             # Tailwind + custom styles
│   └── checkout/
│       ├── success/page.tsx    # Post-checkout success
│       └── cancel/page.tsx     # Checkout canceled
└── components/
    └── marketing/
        ├── Hero.tsx            # Hero section
        ├── Features.tsx        # Feature grid
        ├── Pricing.tsx         # Pricing cards
        └── Footer.tsx          # Footer links
```

## Design System

### Colors
- Primary: `oklch(0.75 0.15 45)` - Tactical orange/amber
- Background: `oklch(0.12 0.01 260)` - Deep blue-black
- Foreground: `oklch(0.95 0.01 90)` - Warm white

### Typography
- **Headings**: Rajdhani (300, 400, 500, 600, 700)
- **Monospace**: Space Mono (400, 700)

### Animations
- `pulse-glow` - Subtle pulsing glow effect
- `slide-up` - Entry animation for hero elements
- `fade-in` - Fade in with stagger support

## Deployment

```bash
# Docker build
docker build -t aios-landing .

# Docker run
docker run -p 3002:3002 aios-landing
```

## License

MIT. See `/LICENSE`.
