# Light Living Graph Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Cairn frontend to the approved light “Living graph” visual system with softer graph nodes and restrained runtime motion while preserving the existing three-column layout and behavior.

**Architecture:** Keep the current React/Vite and `@xyflow/react` architecture. Use CSS custom properties, scoped keyframes, and state-derived classes; update React Flow colors and only add the minimal class/data hooks needed for selection, loading, worker activity, and staggered node reveal. No new dependency is needed.

**Tech Stack:** React 19, TypeScript, Vite, `@xyflow/react`, `lucide-react`, CSS, Node.js built-in test runner.

---

### Task 1: Add a failing light-theme contract check

**Files:**
- Create: `frontend/scripts/check-light-theme.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: Write the failing check**

Create a Node script that reads `src/styles.css`, `src/components/GraphCanvas.tsx`, and `src/components/GraphCard.tsx`, then asserts the future contract: light root background, sage accent token, reduced-motion media query, light React Flow mode, and graph-card motion/state hooks. Use Node’s built-in `assert` module so no dependency is added.

- [ ] **Step 2: Register the check**

Add a `test:theme` script that runs `node scripts/check-light-theme.mjs` from `frontend`.

- [ ] **Step 3: Run it and verify RED**

Run `npm run test:theme` in `frontend`.

Expected: FAIL because the current stylesheet is dark, React Flow uses `colorMode="dark"`, and the requested motion contract is absent.

### Task 2: Replace the dark visual foundation with the light system

**Files:**
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Update root tokens and global surfaces**

Replace dark tokens with the approved warm off-white, white panel, pale green-gray border, charcoal-green text, muted sage accent, muted semantic accents, and 12–16px radius family. Preserve the current sizing and grid structure.

- [ ] **Step 2: Restyle shared controls and panels**

Update topbar, sidebar, graph toolbar, inspector, activity panel, welcome state, empty state, loading state, and error toast to use the new tokens. Keep all existing selectors and interaction states functional.

- [ ] **Step 3: Add motion primitives and accessibility fallback**

Add node reveal, runtime breathe, relation signal, selected halo, hover lift, and shimmer keyframes. Restrict motion to transform/opacity/box-shadow where needed and add a reduced-motion override that removes infinite animation and shortens transitions.

### Task 3: Rework graph surfaces and semantic node styles

**Files:**
- Modify: `frontend/src/components/GraphCanvas.tsx`
- Modify: `frontend/src/components/GraphCard.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Switch React Flow rendering to light mode**

Change `colorMode` to `light`, update the dot background, controls, minimap, edge labels, label backgrounds, and semantic edge colors to the light palette.

- [ ] **Step 2: Add stable graph motion hooks**

Add deterministic motion-order data/classes to generated graph nodes and a graph refresh/context class without changing layout coordinates or selection behavior.

- [ ] **Step 3: Refine node variants**

Keep the current node content and handles, but add semantic classes for sage functions, dashed amber hypotheses, mist-blue evidence, and neutral facts/conclusions/strings. Apply selected/hover motion through CSS.

- [ ] **Step 4: Run the contract check and verify GREEN**

Run `npm run test:theme` in `frontend`.

Expected: PASS with all light-theme and motion contract assertions satisfied.

### Task 4: Align runtime status, loading, and feedback styling

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Topbar.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/components/ActivityPanel.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add state classes without changing data flow**

Expose running/paused/offline, worker active, error, and loading states through existing class names or small additions. Keep WebSocket refresh, worker execution, buttons, and activity behavior unchanged.

- [ ] **Step 2: Apply runtime feedback styling**

Use breathing status dots, inline loading shimmer, subdued error treatment, and activity markers. Ensure the reduced-motion override keeps every state understandable without motion.

- [ ] **Step 3: Run lint and type/build checks**

Run `npm run lint` and `npm run build` in `frontend`.

Expected: both commands exit 0 with no TypeScript or ESLint errors.

### Task 5: Browser verification and responsive audit

**Files:**
- Modify only if visual QA finds an issue: `frontend/src/styles.css` or affected component files.

- [ ] **Step 1: Start the frontend**

Run `npm run dev -- --host 0.0.0.0` in `frontend` and open the reported local URL.

- [ ] **Step 2: Verify core workspace states**

Inspect the welcome screen, loaded three-column workspace, graph selection, sidebar section switching, inspector tabs, worker action, activity panel, empty graph state, and error toast.

- [ ] **Step 3: Verify motion and accessibility**

Confirm node reveal, status breathing, relation signals, selected halo, hover lift, and reduced-motion behavior. Confirm no horizontal overflow at the existing narrow breakpoint.

- [ ] **Step 4: Re-run all checks**

Run `npm run test:theme`, `npm run lint`, and `npm run build` after any QA adjustment.

## Review notes

- The workspace has no Git metadata, so commit steps and SHA-based subagent review are not available.
- The implementation should not install dependencies or alter backend code.
