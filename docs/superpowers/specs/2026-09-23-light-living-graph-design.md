# Light Living Graph Frontend Design

## Goal

Refresh the Cairn frontend from a dark, dense console into a light, calm investigation workspace while preserving the current three-column layout and all existing graph, inspector, worker, activity, and error interactions.

The visual direction is “Living graph”: a warm off-white workspace, low-saturation sage as the single primary accent, softer node surfaces, and restrained runtime motion that communicates activity without becoming distracting.

## Scope and constraints

- Keep the existing React + Vite + `@xyflow/react` architecture.
- Keep the current three-column workspace structure and component boundaries.
- Do not add a new UI or animation dependency; `lucide-react` and existing CSS remain the icon/styling foundation.
- Preserve existing data flow, WebSocket refresh behavior, worker actions, graph selection, inspector tabs, and activity panel behavior.
- Allow small spacing and hierarchy adjustments where required by the light theme.
- Avoid emoji, neon glow, pure black, oversaturated accents, and continuous layout-affecting animation.

## Visual system

### Foundation tokens

- `--bg`: warm off-white graph canvas, approximately `#f7faf8`.
- `--panel`: white or white-translucent panels, approximately `#ffffff`.
- `--card`: white node surfaces with a subtle green-gray diffusion shadow.
- `--border`: pale green-gray boundary, approximately `#dfe8e3`.
- `--text`: deep charcoal-green, approximately `#24362f`.
- `--secondary` / `--tertiary`: muted green-gray text for metadata and supporting copy.
- `--accent`: desaturated sage green, approximately `#5f9d7f`.
- semantic accents: muted amber for hypotheses, mist blue for evidence, muted red for conflict/error.
- `--mono`: existing monospace stack for addresses, counts, timestamps, and provenance.
- shared radius: increase from the current square treatment to a 12–16px family.

The palette should remain neutral-warm with one primary accent. Semantic colors only communicate node meaning and should not compete with the accent.

### Layout treatment

The topbar, sidebar, graph canvas, inspector, and activity panel retain their current positions. Panel boundaries become lighter and surfaces gain more breathing room. The graph canvas receives a faint dot-grid and an extremely subtle radial color wash; the effect must remain pointer-event-free and not be applied to scrolling containers.

### Node treatment

- Function nodes are the visual anchors: white surface, sage icon, rounded corners, clear address row, and a compact metrics footer.
- Hypothesis nodes remain visually distinct with a soft dashed border and muted amber semantic color.
- Intent nodes use sage/green status treatment rather than purple.
- Evidence and observation nodes use mist-blue metadata/icon treatment and a compact provenance row.
- Fact, conclusion, and string nodes use neutral surfaces with green verification or gray string semantics.
- React Flow handles become small round semantic markers with pale borders.
- Selected nodes receive a low-opacity sage ring rather than a glow.

## Motion and runtime behavior

All automatic motion uses `transform` and `opacity`; no animation changes `top`, `left`, `width`, or `height`.

- On graph mount or context change, nodes reveal with a short staggered fade-and-rise. Relation lines fade in after the node group.
- The runtime status dot breathes slowly while the project is running.
- Worker activity uses a small breathing marker and the existing spin treatment only while an action is genuinely in progress.
- Newly refreshed or selected graph content gets a short-lived halo/highlight class. It must not flash continuously.
- Relation paths may show a very slow, low-contrast traveling signal dot to communicate live flow.
- Hover lifts a node by a few pixels and strengthens the border. Active controls use the existing tactile press behavior.
- `@media (prefers-reduced-motion: reduce)` disables infinite motion and reduces reveal transitions to a minimal opacity change.

The implementation should prefer CSS keyframes and state-derived class names. React state is only needed for existing graph/worker/selection state or a short-lived refresh marker; continuous animation must remain outside the render loop.

## Component changes

### `frontend/src/styles.css`

- Replace dark theme tokens and hard-coded dark surfaces with the light token system.
- Restyle shared controls, topbar, sidebar, inspector, activity panel, welcome state, and error toast.
- Restyle all graph-card variants, handles, React Flow controls, minimap, and canvas background.
- Add scoped motion keyframes, stagger variables, and reduced-motion overrides.

### `frontend/src/components/GraphCard.tsx`

- Preserve node markup and data behavior.
- Add stable semantic/state classes only where required for node-specific animation and styling.
- Keep the existing icon system and node metrics.

### `frontend/src/components/GraphCanvas.tsx`

- Switch React Flow from dark to light mode.
- Update background, minimap, edge label, and edge semantic colors to the light palette.
- Add class/style hooks for stagger order and refreshed/selected visual state without changing graph layout algorithms.

### `frontend/src/components/Topbar.tsx`, `Sidebar.tsx`, `Inspector.tsx`, `ActivityPanel.tsx`, `App.tsx`

- Keep behavior and data contracts unchanged.
- Add only the class hooks needed for runtime status, loading, empty, and error states to match the new visual system.

## States and failure handling

- Loading: retain disabled controls and spinner semantics; use a soft inline shimmer/skeleton surface where a panel is waiting for data.
- Empty graph/context: retain the current centered empty state but use a light illustration treatment built from existing icons and text.
- Error: retain inline toast/error copy and API-running hint; use a muted red surface with sufficient contrast.
- Offline/reduced motion: all content remains usable without animation; no state depends on an animation completing.

## Validation plan

1. Run the existing frontend TypeScript/Vite build.
2. Run the existing frontend lint command.
3. Start the Vite app and inspect the welcome state, loaded workspace, graph selection, sidebar switching, worker action, inspector tabs, and activity panel.
4. Verify light theme contrast and that no purple/dark-only styling remains in the frontend stylesheet or React Flow configuration.
5. Verify runtime motion visually at normal speed and with reduced motion enabled.
6. Verify no horizontal overflow at the supported narrow breakpoint and that the three-column layout remains intact.

## Out of scope

- New graph layout algorithms or data model changes.
- New dependencies such as Framer Motion.
- Reworking the navigation information architecture.
- Changing backend APIs, worker protocols, or WebSocket event semantics.
- Adding a dark/light theme toggle; this change establishes the light visual baseline.
