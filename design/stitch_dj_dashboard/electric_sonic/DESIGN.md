# Design System Document

## 1. Overview & Creative North Star
### The Creative North Star: "The Sonic Architect"
This design system moves away from generic management dashboards toward a high-end, editorial experience tailored for the professional DJ and event curator. It balances the high-energy, "club-adjacent" atmosphere of nightlife with the clinical precision required for live operational management. 

We break the "template" look by prioritizing **Intentional Depth and Tonal Hierarchy**. Instead of relying on traditional grids and borders, the layout uses overlapping surfaces and varying levels of "luminance" to guide the eye. The interface feels less like a static website and more like a physical piece of premium DJ hardware—layered, tactile, and highly responsive.

---

## 2. Colors
Our palette is rooted in deep, sophisticated blues and energetic purples, designed to maintain legibility in low-light environments while looking sharp on high-resolution desktop displays.

*   **Primary (`#0040e0`) & Secondary (`#2e5bff`):** The operational core. Used for primary actions and the "Command Sidebar."
*   **Tertiary (`#5e24e1`):** Reserved for "Party Moments"—high-interaction elements like song requests or special announcements.
*   **Accent Cyan (`#00e3fd`):** Our high-visibility marker for active states and critical metadata (BPM, Key).

### The "No-Line" Rule
**Explicit Instruction:** Designers are prohibited from using 1px solid borders for sectioning or containment. Boundaries must be defined solely through background color shifts. Use `surface-container-low` (`#f1f4f7`) against a `surface` (`#f7fafd`) background to create separation.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers:
1.  **Base Layer:** `surface` (#f7fafd) - The global canvas.
2.  **Section Layer:** `surface-container-low` (#f1f4f7) - Used for grouping major functional areas.
3.  **Action Layer:** `surface-container-lowest` (#ffffff) - Used for individual cards and interactive data rows. This creates a "lifted" effect without artificial shadows.

### Signature Textures
Main CTAs and the Sidebar must utilize a **Directional Gradient** (from `primary_container` to `primary`). This provides a visual "soul" and depth that prevents the UI from feeling flat or "SaaS-generic."

---

## 3. Typography
We utilize a high-contrast typographic pairing to establish authority and professional polish.

*   **Headings (Epilogue):** An architectural, sans-serif font with a distinct personality. Use `display-lg` for dashboard titles to create a "poster-like" editorial feel. The wide stance of Epilogue conveys stability and confidence.
*   **Body (Plus Jakarta Sans):** A modern, geometric sans-serif optimized for high-density legibility. This is used for all operational data, tables, and system labels.

**Hierarchy as Identity:** 
By scaling from a bold `display-sm` (2.25rem) for section headers down to a sharp `label-sm` (0.6875rem) for metadata, we create a clear path for the user’s eye, allowing them to scan a dense table of songs in milliseconds.

---

## 4. Elevation & Depth
Elevation is conveyed through **Tonal Layering** rather than structural lines.

*   **The Layering Principle:** Stack `surface-container` tiers. A white card (`surface-container-lowest`) should sit on a soft grey track (`surface-container-low`). This creates a soft, natural lift.
*   **Ambient Shadows:** For floating modals or "active" cards, use "The Sonic Shadow":
    *   *Blur:* 24px - 40px
    *   *Opacity:* 4%-6%
    *   *Color:* Tinted with `primary` (#0040e0) to mimic ambient light reflecting off a screen.
*   **Glassmorphism:** For the Topbar and Tooltips, use `surface-container-lowest` at 80% opacity with a `20px` backdrop-blur. This allows the vibrant club-adjacent colors to bleed through, softening the interface.
*   **The Ghost Border Fallback:** If a border is required for accessibility, use `outline-variant` (#c4c5d8) at **15% opacity**. Never use a 100% opaque border.

---

## 5. Components

### Premium Sidebar (L'Esquerra)
The sidebar is the "Command Center." Use a subtle vertical gradient from `primary` to `primary_container`. 
*   **Active State:** Use a high-contrast `surface-container-lowest` pill with `on_primary_fixed_variant` text.
*   **Language:** Ensure all labels are in Catalan (e.g., *Inici*, *Gestió*, *Configuració*).

### Data Tables (Taules de Dades)
Tables must be dense and scannable.
*   **Row Styling:** Forbid divider lines. Use `8px` of vertical spacing between rows.
*   **Interactive State:** On hover, a row should transition to `surface-container-high` (#e5e8eb) with a `lg` (0.5rem) corner radius.
*   **Status Pills:** Use high-saturation backgrounds with `on_primary` text for BPM and Key indicators (e.g., `primary_container` for '128 BPM').

### Buttons (Botons)
*   **Primary:** Gradient fill (`primary` to `primary_container`), `md` radius, Epilogue Semibold.
*   **Secondary:** `surface-container-highest` background, no border, `on_surface` text.
*   **Glass Action:** Used for "over-image" actions. 20% white fill with a heavy backdrop blur.

### Integrated Topbar
The topbar should not be a separate "block" but a blurred extension of the background. It houses the global search and user profile, utilizing `label-md` for the "Marc Planagumà Valls" identifier.

---

## 6. Do's and Don'ts

### Do
*   **Do** prioritize "Information Density." DJs need to see 20+ songs at once. Use `spacing-2` and `spacing-2.5` between data points.
*   **Do** use `accent_cyan` sparingly to highlight "now playing" or "critical action" states.
*   **Do** use asymmetrical layouts. For example, a wide 2/3 column for the "Maleta del DJ" (Tracklist) and a 1/3 column for "Temes demanats" (Requests).

### Don't
*   **Don't** use black (`#000000`) for text. Always use `on_surface` (#181c1e) to maintain a premium, editorial feel.
*   **Don't** use standard "drop shadows" on cards. Rely on background color shifts to define shape.
*   **Don't** use icons without labels in the sidebar. The professional nature of the app requires zero ambiguity.
*   **Don't** add borders to input fields. Use `surface-container-highest` as a solid fill for inputs to create a "recessed" look.

---

## 7. Interaction States (The 'Club' Feel)
To evoke the energy of a club environment, interactions should feel kinetic.
*   **Transitions:** All hover states must use a `200ms ease-out` curve. 
*   **Active Pulse:** When a song is "Pushed" (*Posada*), the status badge should briefly pulse with a `tertiary_container` glow to provide tactile feedback to the DJ.