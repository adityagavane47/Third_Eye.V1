# Nexus Guardian - Web3 Security Dashboard

## Overview
A modern, responsive React dashboard UI for the Nexus Guardian Web3 security platform. Built with Vite, React, TypeScript, Tailwind CSS, and Recharts.

## Features

✨ **Modern UI/UX**
- Dark cyber-security themed interface with neon accents
- Responsive three-panel layout (Sidebar, Main Content, Right Panel)
- Glassmorphism design elements
- Smooth animations and transitions

📊 **Dashboard**
- Real-time threat visualization with charts
- Key security metrics (threats detected, security score, wallets protected)
- Recent threats list with severity levels
- Risk distribution pie chart
- Threat timeline line chart

🔍 **Monitor Page**
- Real-time activity overview with bar charts
- Monitored addresses table with detailed status
- Chain protection metrics
- Alert configuration
- Address search and filtering

📈 **Insights Page**
- Risk trend analysis with area charts
- Emerging threat patterns
- Security recommendations
- Protocol breakdown
- Attack vector statistics
- Protected chains overview

🎨 **Design System**
- Tailwind CSS with custom cyber color palette
- Neon colors (blue, green, pink, purple, amber)
- Responsive layout for all screen sizes
- Custom animations and glow effects
- Dark mode optimized

## Installation

### Prerequisites
- Node.js 18+ 
- npm or yarn

### Setup
```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

The app will be available at `http://localhost:5173`

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── Sidebar.tsx         # Left navigation panel
│   │   ├── MainContent.tsx     # Main content router
│   │   ├── RightPanel.tsx      # Right details panel
│   │   └── pages/
│   │       ├── DashboardPage.tsx    # Dashboard with charts and metrics
│   │       ├── MonitorPage.tsx      # Monitoring and tracking
│   │       └── InsightsPage.tsx     # Analytics and insights
│   ├── App.tsx                 # Main app component
│   ├── main.tsx                # Entry point
│   └── index.css               # Global styles
├── index.html                  # HTML template
├── package.json                # Dependencies
├── tailwind.config.js          # Tailwind configuration
├── vite.config.ts              # Vite configuration
└── tsconfig.json              # TypeScript configuration
```

## Theme Colors

**Cyber Palette:**
- Background: `#0f172a` (cyber-950)
- Surfaces: `#1e293b` (cyber-900)
- Borders: `#334155` (cyber-700)

**Neon Accents:**
- Blue: `#00d9ff`
- Green: `#39ff14`
- Pink: `#ff006e`
- Purple: `#d946ef`
- Amber: `#fbbf24`

## Placeholder Data

All data displayed is placeholder data. Key features:
- Threat cards with risk scores and severity levels
- Chart data with realistic patterns
- Sample monitored addresses
- Mock vulnerability patterns
- Dummy recommendations and insights

## Future Integration

When ready to integrate with the backend:

1. **API Configuration**: Update `VITE_API_URL` in `.env`
2. **Threat Data**: Replace placeholder data in components with API calls
3. **Real-time Updates**: Implement WebSocket or polling for live data
4. **Web3 Integration**: Connect Privy wallet integration (configured in `useShield` hook)
5. **Authentication**: Add user authentication and session management

## Dependencies

- **react**: UI library
- **react-dom**: React DOM rendering
- **recharts**: Chart library
- **tailwindcss**: CSS framework
- **lucide-react**: Icon library
- **vite**: Build tool

## Development

### Styling
- Tailwind CSS classes with custom extensions
- Dark mode by default
- Responsive breakpoints: sm, md, lg
- Custom animations via CSS

### Icons
Using `lucide-react` for consistent icon system. Import and use:
```tsx
import { Shield, AlertCircle, TrendingUp } from 'lucide-react';
```

### Charts
Using `recharts` for data visualization. Examples:
```tsx
<LineChart>, <AreaChart>, <BarChart>, <PieChart>
```

## Browser Support

- Chrome/Edge: Latest
- Firefox: Latest
- Safari: Latest
- Mobile browsers: iOS Safari, Chrome Mobile

## Notes

- No backend integration yet - all data is placeholder
- No authentication implemented
- No persistent storage
- Responsive design works on mobile but optimized for desktop/tablet

## License

Part of the Nexus Guardian project.
