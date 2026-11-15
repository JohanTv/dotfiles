# Prompts y Especificaciones de Identidad Visual: ALLOSTASIS (`alo`)

> **Herramienta:** Allostasis  
> **Tagline:** *"The Sovereign Developer Cockpit for Flow, Invisible Work, and Cognitive Load Regulation"*  
> **Autor:** Strategic Visual Architect  
> **Fecha:** Noviembre 2026  
> **Destino de Generación:** Banana Pro / FLUX.1 / SDXL / Stable Diffusion  

---

## 1. Fundamentos de Identidad y Paleta Cromática

- **Fondo Primario:** `#080B10` (*Abyssal Void Slate*, negro profundo anti-reflejo para dark mode puro).
- **Flujo Alostático (Deep Work):** Gradiente de **Cian Eléctrico (`#00F5D4`)** a **Azul Cerúleo Profundo (`#0077B6`)**.
- **Nodo de Regulación Cognitiva:** **Ámbar Dorado Cálido (`#FFB703`)**.
- **Contraste:** 21:1 estricto para accesibilidad y visualización en pantallas Retina/HiDPI.

---

## 2. Activo Visual 1: Isotipo e Icono Principal de la Marca

### Concepto: *"The Dynamic Möbius Wave" (El Bucle Alostático)*
Una cinta de Möbius continua combinada con una onda senoidal amortiguada. En su trayectoria cerrada y matemáticamente precisa, el trazo dibuja de forma sutil la letra **`a`** minúscula en su espacio negativo, simbolizando el circuito de autorregulación biológica sin fin.

### Parámetros JSON:
```json
{
  "asset_name": "allostasis_primary_isotype_icon",
  "version": "1.0",
  "prompt": "Minimalist modern tech logo, app icon symbol for 'Allostasis', a stylized continuous Möbius loop combined with a smooth dampening sine wave, subtly forming an abstract lowercase 'a' in negative space, cyber-biological dynamic feedback loop motif. Flat 2D vector graphic, pristine geometric contours, ultra-clean solid lines, sharp mathematical precision. Dark mode aesthetic, isolated on a solid pitch-black background #080B10. Bioluminescent gradient along the continuous ribbon flowing seamlessly from electric cyan-teal (#00F5D4) to deep cerulean blue (#0077B6) with a single warm glowing amber-gold node accent (#FFB703) marking the focal equilibrium point. Minimal, iconic, high contrast, SVG vector emblem style, Dribbble portfolio award winning branding, suitable for 32x32 favicon and high-resolution master mark.",
  "negative_prompt": "3d render, photorealistic, shiny bevel, skeuomorphic, noisy textures, detailed gradients, drop shadow, complex clutter, text, typography, letters, words, watermark, signature, blurry, artifacts, low resolution, hand drawn, sketch, raster noise, glossy plastic, extra lines",
  "parameters": {
    "aspect_ratio": "1:1",
    "resolution": "2048x2048",
    "camera_and_lens": "Orthographic, flat lay, centered front view, zero perspective distortion",
    "lighting": "Self-illuminating bioluminescent vectors, edge-lit luminescence against pure dark void, zero ambient shadows",
    "materiality": "Flat vector matte finish, pristine digital surface, sharp mathematical bezier curves, clean negative space",
    "color_palette": {
      "background": "#080B10 (Abyssal Void Slate)",
      "primary_flow": "#00F5D4 (Electric Cyan) transitioning to #00BBF9 (Flow Blue)",
      "accent_equilibrium": "#FFB703 (Cognitive Warm Amber)",
      "contrast_ratio": "21:1 pure dark mode compliance"
    },
    "composition": "Centered, perfectly balanced symmetrical geometry with dynamic rotational flow, rule of space, golden ratio curve distribution",
    "cfg_scale": 8.5,
    "sampler": "Euler a / DPM++ 2M Karras",
    "steps": 35
  }
}
```

### Variaciones Técnicas:
- **Variación A (Monochrome Terminal Glyph):** Trazo plano monocromático en blanco hueso `#F8FAFC` con nodo en cian puro, sin degradados, para displays ASCII o prompts de shell (`starship` / `zsh`).
- **Variación B (Web Hero Glow):** Difusión sutil de halo volumétrico al 5% de opacidad para encabezados web o portadas interactivas.

---

## 3. Activo Visual 2: Banner de GitHub / Hero Header de README

### Concepto: *"The Sovereign Horizon & Damped Flow" (El Horizonte Soberano)*
Encabezado panorámico horizontal en proporción 16:9. A la derecha, múltiples ondas oscilantes turbulentas (representando el estrés de interrupciones y soporte no planificado) se amortiguan gradualmente hasta transformarse en un flujo continuo, sereno y perfectamente laminar. A la izquierda y centro, generoso espacio negativo sobre fondo negro abisal `#080B10` para el logotipo y el tagline del proyecto.

### Parámetros JSON:
```json
{
  "asset_name": "allostasis_github_hero_banner",
  "version": "1.0",
  "prompt": "Ultra-wide panoramic GitHub README hero header banner for 'ALLOSTASIS'. Minimalist high-tech developer cockpit interface aesthetic, dark abyss color palette #080B10. On the right side, an elegant harmonic visualization of allostatic flow: multiple ultra-thin continuous luminescent curves and stabilizing sine waves transitioning from high-frequency turbulence into calm, serene, perfectly balanced laminar flow lines. Bioluminescent glowing gradients along the trajectories in cyber cyan-teal (#00F5D4), deep electric blue (#0077B6), and discrete warm amber nodes (#FFB703) signifying cognitive balance and energy regulation. Deep generous negative space on the left and center for typography and minimalist brand mark. Faint microscopic telemetry coordinate grid with 4% opacity in the background. Cinematic volumetric ambient rim lighting, crisp 8k digital art, clean vector fidelity, sophisticated UI/UX developer dashboard backdrop, pristine composition, zero clutter, ultra-wide aspect ratio.",
  "negative_prompt": "clutter, complex text, chaotic neon, lens flare, bright oversaturated background, 3d spaceship interior, pilot chairs, cartoon, anime, noisy textures, blurry, pixilated, watermark, stock photo, low quality, artifacts, heavy bokeh, illegible symbols",
  "parameters": {
    "aspect_ratio": "16:9",
    "resolution": "2560x1440",
    "camera_and_lens": "Cinematic ultra-wide angle (24mm focal equivalent), straight-on orthographic horizon, deep lateral depth of field with sharp edge-to-edge foreground clarity",
    "lighting": "Low-key volumetric bioluminescence, darkroom studio ambient, subtle cyan edge glow highlighting wave trajectories against the void",
    "materiality": "Matte carbon-slate finish, luminescent fiber-optic lines, pristine anti-reflective digital dark glass surface, zero dust or scratches",
    "color_palette": {
      "background_void": "#080B10 to #0D1117 (Deep Void Gradient)",
      "stabilizing_flow": "#00F5D4 (Electric Cyan / Flow State)",
      "energy_nodes": "#FFB703 (Regulated Cognitive Amber)",
      "telemetry_grid": "rgba(255, 255, 255, 0.04)"
    },
    "composition": "Golden ratio horizontal landscape, rule of thirds: heavy negative space on the left 60% for title text and branding, dynamic stabilizing energy wave cluster on the right 40%",
    "cfg_scale": 8.5,
    "sampler": "DPM++ 2M Karras / FLUX.1 dev",
    "steps": 40
  }
}
```

### Variaciones Técnicas:
- **Variación A (Telemetry Cockpit Grid):** Enfatiza ejes sutiles de coordenadas y telemetría de sistemas (`[alo: active]`, `load: nominal`).
- **Variación B (Pure Zen Flow):** Elimina cuadrículas, enfatizando puramente las líneas de luz fluidas suspendidas en el vacío oscuro para máxima calma mental.

---

*(Este documento se actualizará automáticamente conforme se generen los siguientes activos: Icono de Terminal / Splash Screen TUI, Social Card Open Graph y Wallpapers).*
