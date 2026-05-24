# Saving South Street

A public-facing companion site for an urban planning thesis on South Street, Philadelphia. The site compares South Street to East Passyunk Avenue and presents the case for a Pennsylvania Creative District designation paired with a local Creative Corridor Overlay. It is built for a mixed audience of neighbors, planners, and local governance partners (City Council, BIDs, RCOs, civic associations), and is intended to serve as a foundational source for future South Street Vision Master Plans.

## Tech stack

- **[Astro](https://astro.build/)** — static site framework, content-first
- **[Tailwind CSS](https://tailwindcss.com/)** — utility-first styling
- **[Leaflet](https://leafletjs.com/)** — interactive map (added later)
- **Netlify** — hosting (added later)

## Running locally

You'll need [Node.js](https://nodejs.org/) (v18 or newer).

```bash
npm install      # one-time, installs dependencies
npm run dev      # starts the local dev server at http://localhost:4321
```

Other commands:

```bash
npm run build    # builds the production site into ./dist
npm run preview  # serves the built site locally to preview before deploy
```

## Project structure

```
src/
  layouts/      # shared page wrapper (nav, footer, <head>)
  pages/        # one file per route — index.astro is the homepage (Map)
  styles/       # global CSS, including Tailwind import
public/         # static assets served as-is (favicon, images, downloads)
source-files/   # raw research materials — gitignored, not deployed
```
