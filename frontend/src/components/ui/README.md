# UI Components - shadcn/ui Integration

shadcn/ui component library integration with custom theme system and shading-based design approach.

## Overview

This directory contains shadcn/ui components that have been installed and customised for the application. All components integrate seamlessly with the custom theme system and follow the shading-based design philosophy.

## shadcn/ui Configuration

### Installation Setup
```json
// components.json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": true,                    // React Server Components support
  "tsx": true,                    // TypeScript support
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/app/globals.css",
    "baseColor": "slate",         // Chosen for neutral, professional appearance
    "cssVariables": true,         // Enables dynamic theming
    "prefix": ""                  // No prefix for cleaner class names
  },
  "aliases": {
    "components": "@/components", // Import path for components
    "utils": "@/lib/utils"       // Import path for utilities
  }
}
```

### Base Colour Choice: Slate
**Rationale for Slate:**
- **Professional Appearance**: Neutral grey tones work well in business applications
- **High Contrast**: Excellent accessibility with proper contrast ratios
- **Theme Harmony**: Coordinates perfectly with the shading-based design approach
- **Versatility**: Works equally well in light and dark modes

## Installed Components

### Layout & Navigation
- **`resizable.tsx`** - Resizable panel system for split layouts
- **`separator.tsx`** - Visual dividers with theme-aware styling
- **`sheet.tsx`** - Slide-out panels for mobile navigation
- **`sidebar.tsx`** - Main navigation sidebar with custom styling

### Interactive Elements
- **`button.tsx`** - Primary interactive component with variant system
- **`input.tsx`** - Form input fields with validation styling
- **`textarea.tsx`** - Multi-line text input with auto-resize capability

### Feedback & Display
- **`card.tsx`** - Content containers with subtle elevation
- **`dialog.tsx`** - Modal dialogs for user interactions
- **`skeleton.tsx`** - Loading state placeholders
- **`tooltip.tsx`** - Contextual information overlays

### Custom Components
- **`thinking-dots.tsx`** - Custom loading animation for AI thinking states

## Theme Integration

### CSS Variables Integration
All components automatically use the custom theme system:

```tsx
// Example: Button component using theme variables
<Button className="bg-primary text-primary-foreground hover:bg-primary/90">
  Submit
</Button>
```

### Shading-Based Styling
Components follow the shading-based design philosophy:

```tsx
// Card component with subtle elevation
<Card className="bg-card border-border shadow-sm">
  <CardContent className="bg-secondary/50">
    Nested content with subtle shading
  </CardContent>
</Card>
```

## Component Categories

### Core Interactive Components

#### Button (`button.tsx`)
**Variants:**
- `default` - Primary action button with theme colours
- `destructive` - Warning/danger actions with red colouring
- `outline` - Secondary actions with border styling
- `secondary` - Subtle actions with muted styling
- `ghost` - Minimal styling for tertiary actions
- `link` - Text-style buttons for navigation

**Sizes:**
- `sm` - Compact buttons for tight spaces
- `default` - Standard button size
- `lg` - Prominent actions requiring emphasis

**Usage Example:**
```tsx
<Button variant="default" size="lg" className="custom-override">
  Primary Action
</Button>
```

#### Input (`input.tsx`)
**Features:**
- Theme-aware border and background colours
- Focus states with ring styling
- Disabled states with appropriate opacity
- Error states (via additional styling)

**Integration:**
```tsx
<Input 
  className="border-input bg-background text-foreground"
  placeholder="Enter text..."
/>
```

### Layout Components

#### Card (`card.tsx`)
**Structure:**
```tsx
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Subtitle</CardDescription>
  </CardHeader>
  <CardContent>
    Main content
  </CardContent>
  <CardFooter>
    Actions or additional info
  </CardFooter>
</Card>
```

**Shading Integration:**
- Uses `--card` variable for background
- Subtle border with `--border` variable
- Text uses `--card-foreground` for proper contrast

#### Sidebar (`sidebar.tsx`)
**Custom Theme Variables:**
```css
/* Dedicated sidebar colour system */
--sidebar: 210 40% 98%;
--sidebar-foreground: 222.2 84% 4.9%;
--sidebar-accent: 210 40% 90%;
--sidebar-accent-foreground: 222.2 84% 4.9%;
--sidebar-border: 214.3 31.8% 91.4%;
```

**Usage Pattern:**
```tsx
<SidebarProvider>
  <Sidebar className="bg-sidebar border-sidebar-border">
    <SidebarContent className="text-sidebar-foreground">
      Navigation items
    </SidebarContent>
  </Sidebar>
</SidebarProvider>
```

### Modal & Overlay Components

#### Dialog (`dialog.tsx`)
**Features:**
- Backdrop with theme-aware overlay
- Focus management for accessibility
- ESC key handling
- Automatic focus return

**Structure:**
```tsx
<Dialog>
  <DialogTrigger>Open Dialog</DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Dialog Title</DialogTitle>
      <DialogDescription>Description</DialogDescription>
    </DialogHeader>
    {/* Content */}
    <DialogFooter>
      <DialogClose>Cancel</DialogClose>
      <Button>Confirm</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

#### Sheet (`sheet.tsx`)
**Mobile-First Design:**
- Responsive slide-out behaviour
- Touch-friendly interaction
- Backdrop dismiss functionality
- Multiple slide directions (top, right, bottom, left)

### Feedback Components

#### Skeleton (`skeleton.tsx`)
**Loading States:**
```tsx
// Card skeleton
<div className="space-y-4">
  <Skeleton className="h-4 w-3/4" />
  <Skeleton className="h-4 w-1/2" />
  <Skeleton className="h-8 w-full" />
</div>
```

**Theme Integration:**
- Uses `--muted` for skeleton background
- Animated pulse effect with theme colours
- Maintains proper contrast in both light and dark modes

#### Tooltip (`tooltip.tsx`)
**Accessibility Features:**
- Proper ARIA attributes
- Keyboard navigation support
- Configurable delay and positioning
- Theme-aware styling

## Custom Extensions

### Thinking Dots (`thinking-dots.tsx`)
**Purpose:** Custom loading animation for AI response states

```tsx
export const ThinkingDots = () => {
  return (
    <div className="flex space-x-1">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="w-2 h-2 bg-muted-foreground rounded-full animate-pulse"
          style={{ animationDelay: `${i * 0.3}s` }}
        />
      ))}
    </div>
  );
};
```

**Features:**
- Theme-aware colouring
- Staggered animation timing
- Subtle, non-intrusive design
- Integrates with chat interface loading states

## Customisation Patterns

### Extending Component Variants
```tsx
// Adding custom button variant
const buttonVariants = cva(
  "base-styles",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        custom: "bg-accent text-accent-foreground hover:bg-accent/80",
      },
    },
  }
);
```

### Theme Variable Usage
```tsx
// Component using custom CSS variables
<div className="bg-sidebar text-sidebar-foreground border-sidebar-border">
  Sidebar content with custom theme variables
</div>
```

### Responsive Design Integration
```tsx
// Mobile-first responsive component
<Sheet>
  <SheetContent side="left" className="w-[300px] sm:w-[400px]">
    Responsive width based on screen size
  </SheetContent>
</Sheet>
```

## Development Guidelines

### Installing New Components
```bash
# Install new shadcn/ui component
npx shadcn@latest add [component-name]
```

**Post-Installation Checklist:**
1. Verify theme variable integration
2. Test in both light and dark modes
3. Ensure accessibility features work
4. Add custom styling if needed
5. Document any customisations

### Customising Components
```tsx
// Extending a component with additional functionality
export const CustomButton = ({ variant = "default", ...props }) => {
  return (
    <Button
      variant={variant}
      className={cn(
        "additional-custom-styles",
        variant === "custom" && "special-custom-variant"
      )}
      {...props}
    />
  );
};
```

### Theme Consistency
**Always use theme variables:**
```tsx
// Good: Uses theme variables
<div className="bg-card text-card-foreground border-border">

// Avoid: Hard-coded colours
<div className="bg-gray-100 text-gray-900 border-gray-200">
```

## Accessibility Features

### Built-in Accessibility
- **Keyboard Navigation**: All components support proper keyboard interaction
- **Screen Reader Support**: ARIA attributes and semantic HTML
- **Focus Management**: Proper focus indicators and management
- **High Contrast**: Theme system ensures proper contrast ratios

### Testing Accessibility
```tsx
// Example accessibility testing approach
import { render, screen } from '@testing-library/react';
import { Button } from './button';

test('button has proper accessibility attributes', () => {
  render(<Button aria-label="Submit form">Submit</Button>);
  expect(screen.getByRole('button')).toHaveAttribute('aria-label', 'Submit form');
});
```

## Performance Considerations

### Bundle Size
- **Tree Shaking**: Only imported components are included in build
- **Minimal Dependencies**: shadcn/ui has minimal external dependencies
- **CSS Optimisation**: Tailwind purges unused styles

### Runtime Performance
- **CSS Variables**: Efficient theme switching without JavaScript
- **Minimal Re-renders**: Components optimised for React performance
- **Lazy Loading**: Components can be code-split if needed

## Future Enhancements

### Planned Additions
- **Data Table**: Complex table component for data display
- **Command Palette**: Quick action and navigation component
- **Calendar**: Date picking and scheduling component
- **Charts**: Data visualisation components

### Theme Improvements
- **Animation System**: Coordinated animations using theme variables
- **Extended Colour Palette**: Additional semantic colours for specific use cases
- **Component Variants**: More variant options for existing components

### Accessibility Enhancements
- **High Contrast Mode**: Enhanced contrast option
- **Reduced Motion**: Respect for user motion preferences
- **Font Size Scaling**: Better support for user font size preferences

## Integration Examples

### Chat Interface Integration
```tsx
// Example: Dialog used for file duplicate resolution
<Dialog open={duplicateDialog.open}>
  <DialogContent className="sm:max-w-md">
    <DialogHeader>
      <DialogTitle className="flex items-center gap-2">
        <AlertTriangle className="h-5 w-5 text-amber-500" />
        Duplicate File Found
      </DialogTitle>
    </DialogHeader>
    
    <div className="bg-muted/50 rounded-lg p-3 border">
      File information display
    </div>
    
    <DialogFooter className="flex-col gap-2">
      <Button variant="default" onClick={handleResolve}>
        Use Existing File
      </Button>
      <Button variant="destructive" onClick={handleOverwrite}>
        Overwrite Existing
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

### Layout Integration
```tsx
// Example: Resizable panels with sidebar
<SidebarProvider>
  <div className="flex min-h-screen">
    <Sidebar />
    <ResizablePanelGroup direction="horizontal">
      <ResizablePanel defaultSize={70}>
        Main content area
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel defaultSize={30}>
        Secondary panel
      </ResizablePanel>
    </ResizablePanelGroup>
  </div>
</SidebarProvider>
```

The UI component system provides a solid foundation for consistent, accessible, and performant user interface development while maintaining the application's shading-based design philosophy.