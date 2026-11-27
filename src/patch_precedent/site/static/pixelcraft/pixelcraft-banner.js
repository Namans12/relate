import { preparePanel } from './scatter.js';

const stylesheet = new URL('./banner.css', import.meta.url).href;

class PixelcraftBanner extends HTMLElement {
  static observedAttributes = ['variant', 'block-size', 'src', 'alt'];

  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <link rel="stylesheet">
      <p id="instructions" class="sr-only">Move your pointer or drag to scatter the pixels. Use the arrow keys or Space when focused.</p>
      <section class="poster" tabindex="0" aria-label="Interactive artwork" aria-describedby="instructions"></section>
    `;
    this.shadowRoot.querySelector('link').href = stylesheet;
    this.poster = this.shadowRoot.querySelector('section');
  }

  connectedCallback() { this.render(); }
  disconnectedCallback() { this.controller?.abort(); }
  attributeChangedCallback() { if (this.isConnected) this.render(); }

  render() {
    this.controller?.abort();
    this.controller = new AbortController();
    const variant = this.getAttribute('variant');
    const src = this.getAttribute('src');
    this.poster.className = 'poster custom';
    this.poster.replaceChildren();
    if (!src) return;
    const hoverDrift = variant === 'hover-drift';
    const closeup = variant === 'closeup' || hoverDrift;
    const layout = src ? 'custom' : closeup ? 'closeup' : 'banner';
    const requested = Number(this.getAttribute('block-size'));
    const grain = requested > 0 && Number.isFinite(requested)
      ? Math.min(64, Math.max(1, Math.round(requested)))
      : closeup ? 6 : 4;
    this.poster.className = 'poster ' + layout;
    this.poster.replaceChildren();
    const names = layout === 'banner' ? ['headline', 'illustration'] : ['artwork'];
    for (const name of names) {
      const panel = document.createElement('div');
      panel.className = 'panel ' + name;
      const image = new Image();
      image.draggable = false;
      image.alt = this.getAttribute('alt') ?? '';
      if (name === 'illustration') panel.setAttribute('aria-hidden', 'true');
      image.src = src;
      const canvas = document.createElement('canvas');
      canvas.setAttribute('aria-hidden', 'true');
      panel.append(image, canvas);
      this.poster.append(panel);
      preparePanel(panel, this.poster, { grain, hold: closeup, hoverDrift, signal: this.controller.signal })
        .catch(error => console.error('Pixelcraft image could not load.', error));
    }
  }
}

if (!customElements.get('pixelcraft-banner')) customElements.define('pixelcraft-banner', PixelcraftBanner);
