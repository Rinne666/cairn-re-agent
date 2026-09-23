# Cognitive Graph Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Execute inline in the current feature branch. Steps use checkbox syntax for tracking.

**Goal:** Make the graph a layered, context-first view of meaningful reverse-engineering concepts instead of a mirror of all stored graph records.

**Architecture:** Keep canonical graph nodes and evidence in the existing database model. Add a frontend projection that defaults to semantic summary nodes, compresses overflow functions into expandable clusters, and reveals related raw/evidence nodes only through relation-specific analysis controls. Keep source data and IDs unchanged.

**Tech Stack:** React, TypeScript, Zustand, React Flow, existing FastAPI/SQLAlchemy graph API.

---

### Task 1: Define graph view and projection contracts

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/components/graphProjection.ts`
- Modify: `backend/app/services/graph.py`

- [x] Define Summary/Analysis modes, relation expansion categories, projected node metrics, and cluster metadata.
- [x] Project high-value semantic nodes across graph types; rank program functions by connected semantic relationships and compress overflow into one expandable cluster.
- [x] Compute support/conflict counts from the canonical nodes and edges without mutating persisted data.
- [x] Canonicalize address-bearing program entities by kind, binary/project, and address before upsert.

### Task 2: Implement summary and analysis graph behavior

**Files:**
- Modify: `frontend/src/components/GraphCanvas.tsx`
- Modify: `frontend/src/components/GraphCard.tsx`

- [x] Default to Summary mode and render only high-value semantic nodes plus summary edges.
- [x] Add an Analysis mode that starts from the selected semantic node and exposes neighbors only through callers, callees, dataflow, evidence, and xref relation filters.
- [x] Make relationship actions filter actual edge kinds and show bounded one-to-two-hop context.
- [x] Make function clusters expand/collapse locally without selecting synthetic IDs as persisted graph nodes.
- [x] Show evidence/conflict counts on relevant semantic nodes and let the evidence badge request the Evidence expansion.

### Task 3: Preserve navigation and raw-detail behavior

**Files:**
- Modify: `frontend/src/store.ts`
- Modify: `frontend/src/components/Inspector.tsx` (only if projection-specific selection handling is needed)
- Modify: `frontend/src/styles.css`

- [x] Keep sidebar graph scopes working with the new view modes.
- [x] Keep canonical node selection connected to the Inspector; synthetic clusters never appear as database entities.
- [x] Style mode controls, evidence badges, and clusters within the existing light visual system and responsive layout.

### Task 4: Verify and commit

**Files:**
- Review all changed frontend files.

- [x] Run frontend lint and production build.
- [x] Inspect the running browser view at desktop and narrow viewport widths.
- [x] Confirm the Git diff contains only the graph-view changes and plan.
- [ ] Commit the finished implementation on `feature/cognitive-graph-views`.
