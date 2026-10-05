// ---------------------------------------------------------------------------
// HTML marker overlay for Google Maps.
// One OverlayView positions all marker elements. Visual treatment is driven
// entirely by CSS classes built from the central classification/severity
// config — no colours or sizes are decided here beyond reading that config.
// ---------------------------------------------------------------------------
import { classificationOf } from '../../config/classification.js';
import { severityOf } from '../../config/severity.js';

function hexToRgba(hex, alpha) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** Visual spec for an event marker — the only place marker styling is derived. */
export function markerSpec(event, { selected = false, historical = false } = {}) {
  const cls = classificationOf(event.classification?.key);
  const sev = severityOf(event.severity) || severityOf('low');
  return {
    color: cls.color,
    soft: hexToRgba(cls.color, 0.22),
    size: historical ? Math.round(sev.markerSize * 0.75) : sev.markerSize,
    treatment: historical ? 'static' : sev.treatment,
    selected,
    historical,
  };
}

function buildEventEl() {
  const el = document.createElement('div');
  el.className = 'tw-marker';
  el.innerHTML =
    '<span class="tw-marker__pulse"></span><span class="tw-marker__pulse tw-marker__pulse--late"></span>' +
    '<span class="tw-marker__halo"></span><span class="tw-marker__locate"></span>' +
    '<button type="button" class="tw-marker__dot"></button>';
  return el;
}

function buildFacilityEl() {
  const el = document.createElement('div');
  el.className = 'tw-marker tw-marker--facility';
  el.innerHTML = '<button type="button" class="tw-marker__facility"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 14.5V7l4 2.5V7l4 2.5V3.5h5v11z"/></svg></button>';
  return el;
}

export function createMarkerOverlay(maps) {
  class MarkerOverlay extends maps.OverlayView {
    constructor(onClick) {
      super();
      this.onClick = onClick;
      this.items = new Map();
      this.container = document.createElement('div');
      this.container.className = 'tw-marker-layer';
      this.container.addEventListener('click', (e) => {
        const target = e.target.closest('[data-id]');
        if (!target) return;
        e.stopPropagation();
        this.onClick?.(target.dataset.kind, target.dataset.id);
      });
      if (maps.OverlayView.preventMapHitsAndGesturesFrom) {
        maps.OverlayView.preventMapHitsAndGesturesFrom(this.container);
      }
    }

    onAdd() {
      this.getPanes().overlayMouseTarget.appendChild(this.container);
    }

    onRemove() {
      this.container.remove();
    }

    draw() {
      const proj = this.getProjection();
      if (!proj) return;
      for (const item of this.items.values()) {
        const p = proj.fromLatLngToDivPixel(new maps.LatLng(item.lat, item.lng));
        if (!p) continue;
        item.el.style.transform = `translate(${Math.round(p.x)}px, ${Math.round(p.y)}px)`;
      }
    }

    /**
     * items: [{ key, kind: 'event'|'facility', id, lat, lng, title, spec?, z }]
     * Elements are reused by key so CSS animations do not restart on updates.
     */
    setItems(list) {
      const next = new Set();
      for (const it of list) {
        next.add(it.key);
        let rec = this.items.get(it.key);
        if (!rec) {
          const el = it.kind === 'facility' ? buildFacilityEl() : buildEventEl();
          this.container.appendChild(el);
          rec = { el };
          this.items.set(it.key, rec);
        }
        rec.lat = it.lat;
        rec.lng = it.lng;
        const { el } = rec;
        const btn = el.querySelector('button');
        btn.dataset.id = it.id;
        btn.dataset.kind = it.kind;
        btn.title = it.title;
        btn.setAttribute('aria-label', it.title);
        el.style.zIndex = String(it.z || 1);
        if (it.kind === 'event') {
          const s = it.spec;
          el.className = [
            'tw-marker',
            `tw-marker--${s.treatment}`,
            s.selected ? 'tw-marker--selected' : '',
            s.historical ? 'tw-marker--historical' : '',
          ].join(' ').trim();
          el.style.setProperty('--c', s.color);
          el.style.setProperty('--c-soft', s.soft);
          el.style.setProperty('--s', `${s.size}px`);
        }
      }
      for (const [key, rec] of this.items) {
        if (!next.has(key)) {
          rec.el.remove();
          this.items.delete(key);
        }
      }
      this.draw();
    }

    /** One-shot "located" ring; removed on animationend, no timers. */
    highlight(key) {
      const rec = this.items.get(key);
      if (!rec) return;
      const ring = rec.el.querySelector('.tw-marker__locate');
      if (!ring) return;
      ring.classList.remove('is-on');
      void ring.offsetWidth; // restart animation
      ring.classList.add('is-on');
      ring.addEventListener('animationend', () => ring.classList.remove('is-on'), { once: true });
    }
  }
  return MarkerOverlay;
}
