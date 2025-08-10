# App - Next.js App Router and Theme System

Next.js 15 App Router configuration with comprehensive theme system built on shadcn/ui and CSS custom properties.

## Directory Structure

```
app/
├── favicon.ico          # Application favicon
├── globals.css          # Global styles and theme system
├── layout.tsx           # Root layout with providers
└── page.tsx             # Landing page component
```

## Theme System Architecture

### Design Philosophy: Shading-Based Visual Hierarchy

The application uses a **shading-based theme approach** rather than border-based styling for visual hierarchy and component differentiation.

#### Key Design Decisions:
- **Subtle gradients** via lightness variations rather than hard borders
- **Consistent depth perception** through strategic shading
- **Seamless dark/light mode** with automatic browser preference detection
- **High contrast accessibility** while maintaining visual softness

### Theme Configuration

#### shadcn/ui Integration
```json
// components.json
{
  "style": "default",
  "tailwind": {
    "baseColor": "slate",
    "cssVariables": true
  }
}
```

**Base Colour Choice: Slate**
- **Rationale**: Neutral, professional colour that works in both light and dark modes
- **Flexibility**: Provides excellent contrast ratios for accessibility
- **Consistency**: Harmonises with the shading-based approach

#### CSS Variables System
Located in `globals.css:5-60`, the theme uses CSS custom properties for dynamic theming:

```css
:root {
  /* Core theme variables */
  --background: 0 0% 100%;      /* Pure white background */
  --foreground: 222.2 84% 4.9%; /* Near-black text */
  --muted: 210 40% 85%;         /* Light grey for subtle backgrounds */
  --card: 0 0% 95%;             /* Off-white for elevated surfaces */
  
  /* Primary colour: Professional blue */
  --primary: 221.2 83.2% 53.3%;
  --primary-foreground: 210 40% 98%;
  
  /* Shading system for hierarchy */
  --secondary: 210 40% 90%;     /* Lighter shade for secondary elements */
  --accent: 210 40% 80%;        /* Medium shade for accents */
  --muted: 210 40% 85%;         /* Subtle shade for backgrounds */
}
```

### Dark Mode Implementation

#### Automatic Detection
```css
@media (prefers-color-scheme: dark) {
  :root {
    --background: 220 13% 15%;    /* Dark blue-grey background */
    --card: 220 13% 25%;          /* Elevated dark surfaces */
    --muted: 215 27.9% 35%;       /* Dark mode subtle shading */
  }
}
```

**Dark Mode Strategy:**
- **Automatic**: Respects user's system preference via `prefers-color-scheme`
- **Consistent Variables**: Same variable names, different values
- **Maintained Contrast**: Ensures accessibility in dark mode
- **Shading Preservation**: Visual hierarchy maintained through darkness variations

### Colour Palette Breakdown

#### Light Mode Shading System
```css
/* Visual hierarchy through lightness variations */
--background: 0 0% 100%;     /* Base: Pure white */
--card: 0 0% 95%;           /* Level 1: Slight grey for cards */
--secondary: 210 40% 90%;    /* Level 2: Subtle backgrounds */
--accent: 210 40% 80%;       /* Level 3: Interactive elements */
--muted: 210 40% 85%;        /* Level 4: Disabled/secondary text areas */
```

#### Dark Mode Shading System
```css
/* Inverted hierarchy with dark base */
--background: 220 13% 15%;   /* Base: Dark blue-grey */
--card: 220 13% 25%;        /* Level 1: Lighter for elevation */
--secondary: 215 27.9% 30%;  /* Level 2: Interactive backgrounds */
--accent: 215 27.9% 40%;     /* Level 3: Highlighted elements */
--muted: 215 27.9% 35%;      /* Level 4: Subtle content areas */
```

## Sidebar Theme Extension

### Custom Sidebar Variables
The application extends the base theme with sidebar-specific variables for consistent visual treatment:

```css
/* Light mode sidebar */
--sidebar: 210 40% 98%;              /* Slightly off-white */
--sidebar-foreground: 222.2 84% 4.9%; /* Standard text colour */
--sidebar-accent: 210 40% 90%;        /* Hover/active states */

/* Dark mode sidebar */
--sidebar: 220 13% 12%;              /* Darker than main background */
--sidebar-accent: 215 27.9% 22%;     /* Subtle interaction feedback */
```

**Sidebar Design Rationale:**
- **Distinct but Harmonious**: Slightly different shade to separate from main content
- **Consistent Interaction**: Uses same shading principles for hover/active states
- **Accessibility**: Maintains proper contrast ratios in both modes

## Global Styles

### Typography System
```css
body {
  background: hsl(var(--background));
  color: hsl(var(--foreground));
  font-family: system-ui, -apple-system, sans-serif;
}
```

**Font Choice Rationale:**
- **System Fonts**: Uses user's preferred system font for familiarity
- **Performance**: No web font loading required
- **Consistency**: Matches OS design language

### Layout Constraints
```css
html, body {
  height: 100%;
  overflow: hidden;  /* Prevents page scrolling - components handle their own scroll */
}
```

**Layout Strategy:**
- **Full Height**: Application takes full viewport height
- **Controlled Scrolling**: Individual components manage their scroll behavior
- **Chat Interface Optimised**: Prevents unwanted page-level scrolling

### Custom Scrollbar Styling

#### Light Mode Scrollbars
```css
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: hsl(var(--muted));
}

::-webkit-scrollbar-thumb {
  background: hsl(var(--muted-foreground) / 0.3);
  border-radius: 4px;
}
```

#### Dark Mode Scrollbars
```css
@media (prefers-color-scheme: dark) {
  ::-webkit-scrollbar-thumb {
    background: hsl(var(--muted-foreground) / 0.4);
  }
}
```

**Scrollbar Design:**
- **Subtle**: Low opacity for non-intrusive appearance
- **Theme-Consistent**: Uses theme variables for automatic colour adaptation
- **Hover Feedback**: Increased opacity on hover for better usability

## External Dependencies

### CSS Imports
```css
@import "tailwindcss";                      /* Tailwind CSS framework */
@import "highlight.js/styles/github-dark.css"; /* Code syntax highlighting */
@import "katex/dist/katex.min.css";        /* Mathematical notation rendering */
```

**Import Strategy:**
- **Tailwind First**: Base framework styles loaded first
- **Feature-Specific**: Additional imports for specific functionality (code, maths)
- **Theme Coordination**: External styles work with the theme system

## Tailwind Configuration

### Extended Theme Integration
The `tailwind.config.ts` extends Tailwind's default theme with the custom CSS variables:

```typescript
theme: {
  extend: {
    colors: {
      // Map CSS variables to Tailwind colour classes
      background: "hsl(var(--background))",
      foreground: "hsl(var(--foreground))",
      primary: "hsl(var(--primary))",
      // ... all theme variables
    },
    borderRadius: {
      // Dynamic radius system
      lg: "var(--radius)",           // 0.5rem base
      md: "calc(var(--radius) - 2px)", // Slightly smaller
      sm: "calc(var(--radius) - 4px)", // Smallest variant
    },
  },
}
```

**Configuration Benefits:**
- **CSS Variable Integration**: Seamless use of theme variables in Tailwind classes
- **Dynamic Theming**: Automatic adaptation to light/dark modes
- **Consistent Radius**: Coordinated border radius throughout the application

## Usage Patterns

### Component Styling
```tsx
// Using theme colours in components
<div className="bg-background text-foreground">
  <div className="bg-card text-card-foreground border border-border">
    <button className="bg-primary text-primary-foreground hover:bg-primary/90">
      Action
    </button>
  </div>
</div>
```

### Shading-Based Hierarchy
```tsx
// Visual hierarchy through subtle shading
<main className="bg-background">          {/* Base level */}
  <section className="bg-card">           {/* Elevated surface */}
    <div className="bg-secondary">        {/* Secondary content */}
      <span className="bg-accent">        {/* Accent elements */}
        <small className="text-muted-foreground">  {/* Subtle text */}
```

### Responsive Design Integration
```tsx
// Dark mode aware components
<div className="bg-sidebar text-sidebar-foreground">
  {/* Automatically adapts to light/dark mode */}
</div>
```

## Accessibility Considerations

### Contrast Ratios
- **WCAG AA Compliant**: All colour combinations meet minimum contrast requirements
- **High Contrast Available**: Enhanced contrast in dark mode for better readability
- **Text Readability**: Careful colour selection ensures text remains legible

### User Preferences
- **Respects System Settings**: Automatic dark mode based on user preference
- **No Flash**: Smooth transitions between light/dark themes
- **Reduced Motion Support**: Theme changes respect motion preferences

## Development Guidelines

### Adding New Theme Variables
```css
:root {
  /* Add new variable following naming convention */
  --new-element: 210 40% 75%;
}

@media (prefers-color-scheme: dark) {
  :root {
    /* Provide dark mode equivalent */
    --new-element: 215 27.9% 45%;
  }
}
```

### Tailwind Integration
```typescript
// Add to tailwind.config.ts
colors: {
  "new-element": "hsl(var(--new-element))",
}
```

### Component Usage
```tsx
// Use in components
<div className="bg-new-element text-foreground">
  Content with new theme colour
</div>
```

## Testing Theme System

### Visual Testing
- **Light/Dark Toggle**: Verify all components adapt correctly
- **Contrast Validation**: Use accessibility tools to validate contrast ratios
- **Cross-Browser**: Ensure CSS variable support across target browsers

### Performance Testing
- **CSS Loading**: Monitor theme application performance
- **Variable Updates**: Test dynamic theme changes if implemented
- **Memory Usage**: Ensure efficient CSS variable usage

The theme system provides a robust foundation for consistent, accessible design across the entire application while maintaining flexibility for future enhancements and customisations.