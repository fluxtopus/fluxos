# Tentackl Frontend Architecture

This document describes the architecture and organization of the Tentackl workflow visualization frontend application.

**Production URL:** https://fluxtopus.com
**Backend API:** https://flow.fluxtopus.com

## Overview

The Tentackl frontend is a React-based single-page application built with TypeScript that provides real-time visualization and monitoring of multi-agent workflows. It uses modern web technologies and follows React best practices for state management and component composition.

## Technology Stack

- **React 18**: UI framework with hooks and functional components
- **TypeScript**: Type-safe development
- **Tailwind CSS**: Utility-first CSS framework with dark mode support
- **Cytoscape.js**: Graph visualization library for workflow rendering
- **Zustand**: Lightweight state management
- **Socket.io Client**: Real-time WebSocket communication
- **Axios**: HTTP client for REST API calls
- **Framer Motion**: Animation library
- **Recharts**: Data visualization for metrics
- **React Hot Toast**: Notification system

## Project Structure

```
frontend/
├── public/              # Static assets
├── src/
│   ├── components/      # React components
│   ├── services/        # API and WebSocket services
│   ├── store/          # Zustand state management
│   ├── types/          # TypeScript type definitions
│   ├── utils/          # Utility functions and configs
│   ├── App.tsx         # Main application component
│   ├── index.tsx       # Application entry point
│   └── index.css       # Global styles and Tailwind imports
├── package.json        # Dependencies and scripts
├── tailwind.config.js  # Tailwind CSS configuration
└── tsconfig.json       # TypeScript configuration
```

## Core Components

### App.tsx
The main application component that provides:
- Layout structure with collapsible sidebar
- Dark mode toggle
- Error handling and display
- Global state integration

### Components

#### WorkflowList.tsx
- Displays a list of available workflows
- Handles workflow selection and loading
- Shows workflow status indicators
- Provides create/delete workflow actions

#### WorkflowVisualization.tsx
- Core visualization component using Cytoscape.js
- Renders workflow nodes and edges as an interactive graph
- Real-time updates via WebSocket subscriptions
- Node animations for running states
- Interactive pan, zoom, and node selection

#### MetricsPanel.tsx
- Displays real-time workflow execution metrics
- Shows node execution times and status counts
- Provides performance insights
- Updates automatically as workflow progresses

### Services

#### api.ts
- REST API client using Axios
- Endpoints for workflow CRUD operations
- Type-safe API responses
- Error handling and retry logic

#### websocket.ts
- Socket.io client for real-time updates
- Handles workflow state changes
- Reconnection logic
- Event-based communication

### State Management

#### workflowStore.ts
- Zustand store for global application state
- Manages:
  - Current workflow selection
  - Workflow list
  - Real-time workflow updates
  - Error states
  - Loading states
- Provides actions for state mutations
- Integrates with WebSocket for live updates

### Type System

#### workflow.ts
- Core TypeScript interfaces and enums
- Defines:
  - `Workflow`: Main workflow structure
  - `Node`: Workflow node with position and status
  - `Edge`: Connections between nodes
  - `NodeStatus`: Enum for node states
  - `WorkflowStatus`: Enum for workflow states
  - `ExecutionMetrics`: Performance data

### Utilities

#### cytoscapeConfig.ts
- Cytoscape.js configuration and styling
- Node status color mapping
- Graph layout options
- Animation configurations
- Helper functions for element creation

## Key Features

### Real-time Updates
- WebSocket connection for live workflow state changes
- Automatic UI updates without page refresh
- Node status animations during execution

### Interactive Visualization
- Pan and zoom graph navigation
- Node selection and highlighting
- Automatic layout with breadth-first algorithm
- Responsive to workflow structure changes

### Dark Mode
- System-wide dark mode toggle
- Persistent user preference
- Tailwind CSS class-based theming

### Error Handling
- Global error boundary
- Toast notifications for user feedback
- Automatic error dismissal
- Detailed error logging

## Development Workflow

### Available Scripts

```bash
# Start development server
npm start

# Build for production
npm build

# Run tests
npm test

# Type checking
npm run lint

# Code formatting
npm run format
```

### Environment Setup

The application expects a backend API at `http://localhost:8000` (configured via proxy in package.json).

### Code Style

- Functional components with TypeScript
- Custom hooks for reusable logic
- Tailwind CSS for styling
- ESLint and Prettier for code consistency

## Performance Considerations

- Cytoscape.js optimizations for large graphs
- Debounced WebSocket updates
- Memoized component renders
- Lazy loading for heavy components
- Efficient state updates with Zustand

## Future Enhancements

- Workflow execution controls (pause/resume/cancel)
- Advanced filtering and search
- Export visualization as image/PDF
- Collaborative features
- Performance profiling tools
- Custom node type renderers
